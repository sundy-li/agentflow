import os
import pty
import re
import select
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
from uuid import uuid4

from app.config import AppSettings, CodingAgentSettings
from app.repository import Repository, utc_now


@dataclass
class RunResult:
    run_id: int
    exit_code: int
    output_path: str
    result: str


class CodingAgentRunner:
    PROMPT_TEMPLATE_FILES = {
        "implement": "implement.md",
        "fix": "fix.md",
        "review": "review.md",
    }

    def __init__(self, repository: Repository, app_settings: AppSettings):
        self.repository = repository
        self.app_settings = app_settings
        self.run_logs_dir = Path(app_settings.run_logs_dir)
        self.run_logs_dir.mkdir(parents=True, exist_ok=True)
        self._shutdown_event = threading.Event()
        self._active_processes = set()
        self._active_processes_lock = threading.Lock()

    def run_task(self, task: Dict, mode: str) -> RunResult:
        prompt = self._build_prompt(task, mode)
        agent_settings = self._resolve_agent_settings(mode)
        command = self._build_command(prompt, mode)
        command_preview = " ".join(shlex.quote(token) for token in command)
        started_at = utc_now()
        log_path = self.run_logs_dir / self._build_log_name(task, mode, started_at)
        run_id = self.repository.create_run(
            int(task["id"]),
            mode,
            prompt,
            command_preview,
            started_at=started_at,
            output_path=str(log_path),
        )
        exit_code = 127
        result = "failed"
        timeout_seconds = int(agent_settings.timeout_seconds)
        workspace = task.get("repo_workspace")

        with log_path.open("wb") as log_file:
            try:
                if self._shutdown_event.is_set():
                    log_file.write(b"[agentflow] shutdown requested before coding agent launch\n")
                    exit_code = -15
                    result = "failed"
                else:
                    exit_code = self._run_with_pty(command, log_file, timeout_seconds, cwd=workspace)
                    result = self._derive_result(exit_code, log_path, mode)
            except FileNotFoundError as err:
                message = "coding agent command not found: {0}\n".format(err)
                log_file.write(message.encode("utf-8"))
                exit_code = 127
                result = "failed"

        self.repository.finish_run(run_id, exit_code, str(log_path), result, finished_at=utc_now())
        return RunResult(run_id=run_id, exit_code=exit_code, output_path=str(log_path), result=result)

    def run_codex(self, task: Dict, mode: str) -> RunResult:
        return self.run_task(task, mode)

    def shutdown(self) -> None:
        self._shutdown_event.set()
        with self._active_processes_lock:
            processes = list(self._active_processes)
        for process in processes:
            self._terminate_process(process)

    def _resolve_agent_settings(self, mode: str) -> CodingAgentSettings:
        return self.app_settings.resolve_agent_for_mode(mode)

    def _build_command(self, prompt: str, mode: str) -> List[str]:
        return self.__class__._compose_command(prompt, self._resolve_agent_settings(mode))

    def _run_with_pty(self, command: List[str], log_file, timeout_seconds: int, cwd: str = None) -> int:
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            close_fds=True,
            start_new_session=True,
        )
        os.close(slave_fd)
        self._register_process(process)

        started = time.time()
        timed_out = False
        shutdown_requested = False
        try:
            while True:
                if self._shutdown_event.is_set():
                    shutdown_requested = True
                    self._terminate_process(process)
                    break
                if timeout_seconds > 0 and (time.time() - started) > timeout_seconds:
                    timed_out = True
                    self._terminate_process(process)
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
            self._unregister_process(process)
            os.close(master_fd)

        exit_code = process.wait()
        if shutdown_requested:
            log_file.write(b"\n[agentflow] shutdown requested; terminating coding agent run\n")
            return -15
        if self._shutdown_event.is_set() and exit_code != 0:
            log_file.write(b"\n[agentflow] shutdown requested; terminating coding agent run\n")
            return -15
        if timed_out:
            log_file.write(b"\n[agentflow] coding agent timeout reached\n")
            return -1
        return int(exit_code)

    def _register_process(self, process: subprocess.Popen) -> None:
        with self._active_processes_lock:
            self._active_processes.add(process)

    def _unregister_process(self, process: subprocess.Popen) -> None:
        with self._active_processes_lock:
            self._active_processes.discard(process)

    @staticmethod
    def _terminate_process(process: subprocess.Popen, grace_seconds: float = 2.0) -> None:
        if process.poll() is not None:
            return
        try:
            if hasattr(os, "killpg"):
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            return
        deadline = time.time() + max(0.0, grace_seconds)
        while time.time() < deadline:
            if process.poll() is not None:
                return
            time.sleep(0.05)
        if process.poll() is not None:
            return
        try:
            if hasattr(os, "killpg"):
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return

    @staticmethod
    def _derive_result(exit_code: int, log_path: Path, mode: str) -> str:
        if exit_code == -1:
            return "timeout"
        if exit_code != 0:
            return "failed"
        if mode != "review":
            return "success"
        tail = CodingAgentRunner._read_tail(log_path)
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
    def _compose_command(prompt: str, agent_settings: CodingAgentSettings) -> List[str]:
        if not agent_settings.command:
            raise ValueError("Coding agent command must be configured.")
        tokens = [agent_settings.command]
        if agent_settings.kind == "codex":
            if Path(agent_settings.command).name in {"codex", "codex-cli"}:
                tokens.append("exec")
        elif agent_settings.kind == "claude_code":
            tokens.append("--print")
        elif agent_settings.kind == "opencode":
            tokens.append("run")
        else:
            raise ValueError("Unsupported coding agent kind: {0}".format(agent_settings.kind))
        tokens.extend(agent_settings.args)
        tokens.append(prompt)
        return tokens

    @staticmethod
    def _build_log_name(task: Dict, mode: str, started_at: str) -> str:
        timestamp = started_at.replace("-", "").replace(":", "").replace("T", "-").replace("Z", "")
        task_id = str(task.get("id") or "task")
        return "{0}-{1}-{2}-{3}.log".format(timestamp, task_id, mode, uuid4().hex[:8])

    @staticmethod
    def _build_prompt(task: Dict, mode: str) -> str:
        template = CodingAgentRunner._load_prompt_template(mode, task)
        context = CodingAgentRunner._build_prompt_context(task)
        return CodingAgentRunner._render_prompt_template(template, context)

    @staticmethod
    def _build_prompt_context(task: Dict) -> Dict[str, str]:
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
        return {
            "title": CodingAgentRunner._stringify_prompt_value(task.get("title")),
            "url": CodingAgentRunner._stringify_prompt_value(task.get("url")),
            "issue_number": CodingAgentRunner._stringify_prompt_value(task.get("github_number")),
            "repo_full_name": CodingAgentRunner._stringify_prompt_value(repo_full_name),
            "repo_forked": CodingAgentRunner._stringify_prompt_value(repo_forked),
            "default_branch": CodingAgentRunner._stringify_prompt_value(default_branch),
            "repo_context": "\n".join(repo_context),
            "delivery_context": CodingAgentRunner._stringify_prompt_value(task.get("delivery_context")),
        }

    @staticmethod
    def _load_prompt_template(mode: str, task: Dict = None) -> str:
        template_name = None
        if mode == "implement" and task and task.get("pr_followup_only"):
            template_name = "implement_pr_followup.md"
        else:
            try:
                template_name = CodingAgentRunner.PROMPT_TEMPLATE_FILES[mode]
            except KeyError as err:
                raise ValueError("Unsupported coding agent mode: {0}".format(mode)) from err
        template_path = CodingAgentRunner._prompt_templates_dir() / template_name
        return template_path.read_text(encoding="utf-8").strip()

    @staticmethod
    def _prompt_templates_dir() -> Path:
        return Path(__file__).resolve().parents[2] / "prompts"

    @staticmethod
    def _render_prompt_template(template: str, context: Dict[str, str]) -> str:
        pattern = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            value = context.get(key)
            if value is None:
                return match.group(0)
            return value

        return pattern.sub(replace, template).strip()

    @staticmethod
    def _stringify_prompt_value(value) -> str:
        if value is None:
            return ""
        return str(value)
