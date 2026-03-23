import os
import pty
import select
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from app.config import CodexSettings
from app.repository import Repository, utc_now


@dataclass
class RunResult:
    run_id: int
    exit_code: int
    output_path: str
    result: str


class CodexRunner:
    def __init__(self, repository: Repository, codex_settings: CodexSettings, run_logs_dir: str):
        self.repository = repository
        self.codex_settings = codex_settings
        self.run_logs_dir = Path(run_logs_dir)
        self.run_logs_dir.mkdir(parents=True, exist_ok=True)

    def run_codex(self, task: Dict, mode: str) -> RunResult:
        prompt = self._build_prompt(task, mode)
        command = [self.codex_settings.command] + list(self.codex_settings.args) + [prompt]
        command_preview = " ".join(shlex.quote(token) for token in command)
        started_at = utc_now()
        run_id = self.repository.create_run(int(task["id"]), mode, prompt, command_preview, started_at=started_at)

        log_path = self.run_logs_dir / "{0}.log".format(run_id)
        exit_code = 127
        result = "failed"
        timeout_seconds = int(self.codex_settings.timeout_seconds)

        with log_path.open("wb") as log_file:
            try:
                exit_code = self._run_with_pty(command, log_file, timeout_seconds)
                result = self._derive_result(exit_code, log_path, mode)
            except FileNotFoundError as err:
                message = "codex command not found: {0}\n".format(err)
                log_file.write(message.encode("utf-8"))
                exit_code = 127
                result = "failed"

        self.repository.finish_run(run_id, exit_code, str(log_path), result, finished_at=utc_now())
        return RunResult(run_id=run_id, exit_code=exit_code, output_path=str(log_path), result=result)

    @staticmethod
    def _run_with_pty(command: List[str], log_file, timeout_seconds: int) -> int:
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)

        started = time.time()
        timed_out = False
        try:
            while True:
                if timeout_seconds > 0 and (time.time() - started) > timeout_seconds:
                    timed_out = True
                    process.kill()
                    break

                ready, _, _ = select.select([master_fd], [], [], 0.2)
                if ready:
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError:
                        chunk = b""
                    if chunk:
                        log_file.write(chunk)
                    elif process.poll() is not None:
                        break

                if process.poll() is not None and not ready:
                    break

            try:
                while True:
                    chunk = os.read(master_fd, 4096)
                    if not chunk:
                        break
                    log_file.write(chunk)
            except OSError:
                pass
        finally:
            os.close(master_fd)

        exit_code = process.wait()
        if timed_out:
            log_file.write(b"\n[agentflow] codex timeout reached\n")
            return -1
        return int(exit_code)

    @staticmethod
    def _derive_result(exit_code: int, log_path: Path, mode: str) -> str:
        if exit_code == -1:
            return "timeout"
        if exit_code != 0:
            return "failed"
        if mode != "review":
            return "success"
        tail = CodexRunner._read_tail(log_path)
        if "REVIEW_RESULT:FAIL" in tail or "AGENT_REVIEW:FAIL" in tail:
            return "fail"
        if "REVIEW_RESULT:PASS" in tail:
            return "pass"
        return "pass"

    @staticmethod
    def _read_tail(path: Path, max_bytes: int = 4000) -> str:
        data = path.read_bytes()
        return data[-max_bytes:].decode("utf-8", errors="ignore")

    @staticmethod
    def _build_prompt(task: Dict, mode: str) -> str:
        repo_full_name = task.get("repo_full_name")
        repo_forked = task.get("repo_forked")
        default_branch = task.get("repo_default_branch") or "main"
        repo_context = []
        if repo_full_name:
            repo_context.append("Upstream repository: {0}".format(repo_full_name))
        if repo_forked:
            repo_context.append("Fork repository: {0}".format(repo_forked))
        if repo_context:
            repo_context.append("Base branch: {0}".format(default_branch))
        repo_context_text = "\n".join(repo_context)
        if repo_context_text:
            repo_context_text = repo_context_text + "\n"

        if mode == "implement":
            prompt = (
                "Implement the GitHub issue.\n"
                "Title: {0}\n"
                "URL: {1}\n"
                "{2}"
                "Please make the required code changes and push updates."
            ).format(task.get("title"), task.get("url"), repo_context_text)
            if repo_forked and repo_full_name:
                prompt += (
                    "\nPush the branch to fork repository '{0}' (not upstream)."
                    "\nCreate a PR from fork '{0}' to upstream '{1}' targeting '{2}'."
                ).format(repo_forked, repo_full_name, default_branch)
            return prompt
        if mode == "fix":
            prompt = (
                "Address requested changes for this task.\n"
                "Title: {0}\n"
                "URL: {1}\n"
                "{2}"
                "Apply fixes and update the branch."
            ).format(task.get("title"), task.get("url"), repo_context_text)
            if repo_forked and repo_full_name:
                prompt += (
                    "\nPush updates to fork repository '{0}' (not upstream)."
                    "\nEnsure PR targets upstream '{1}' branch '{2}'."
                ).format(repo_forked, repo_full_name, default_branch)
            return prompt
        return (
            "Review this pull request and decide pass/fail.\n"
            "Title: {0}\n"
            "URL: {1}\n"
            "{2}"
            "Respond with REVIEW_RESULT:PASS or REVIEW_RESULT:FAIL."
        ).format(task.get("title"), task.get("url"), repo_context_text)
