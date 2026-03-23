import json
import subprocess
from typing import Dict, List, Optional

from app.constants import AGENT_CHANGED, AGENT_ISSUE, AGENT_REVIEWABLE


class GHCommandError(RuntimeError):
    pass


class GHClient:
    def __init__(self, timeout_seconds: int = 120):
        self.timeout_seconds = timeout_seconds

    def list_agent_issues(self, repo_full_name: str) -> List[Dict]:
        command = [
            "gh",
            "issue",
            "list",
            "--repo",
            repo_full_name,
            "--state",
            "open",
            "--label",
            AGENT_ISSUE,
            "--limit",
            "200",
            "--json",
            "number,title,url,labels,assignees,updatedAt",
        ]
        output = self._run(command)
        payload = json.loads(output or "[]")
        return [self._normalize_item(item, "issue") for item in payload]

    def list_agent_prs(self, repo_full_name: str) -> List[Dict]:
        merged = {}
        for label in [AGENT_REVIEWABLE, AGENT_CHANGED]:
            command = [
                "gh",
                "pr",
                "list",
                "--repo",
                repo_full_name,
                "--state",
                "open",
                "--label",
                label,
                "--limit",
                "200",
                "--json",
                "number,title,url,labels,assignees,updatedAt",
            ]
            output = self._run(command)
            payload = json.loads(output or "[]")
            for item in payload:
                normalized = self._normalize_item(item, "pr")
                merged[int(normalized["number"])] = normalized
        return [merged[key] for key in sorted(merged.keys())]

    def set_labels(
        self,
        repo_full_name: str,
        item_type: str,
        number: int,
        add_labels: Optional[List[str]] = None,
        remove_labels: Optional[List[str]] = None,
    ) -> None:
        add = sorted(set(add_labels or []))
        remove = sorted(set(remove_labels or []))
        if not add and not remove:
            return
        if item_type not in ("issue", "pr"):
            raise ValueError("item_type must be issue or pr")

        command = [
            "gh",
            item_type,
            "edit",
            str(number),
            "--repo",
            repo_full_name,
        ]
        for label in add:
            command.extend(["--add-label", label])
        for label in remove:
            command.extend(["--remove-label", label])
        self._run(command)

    def _run(self, command: List[str]) -> str:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=self.timeout_seconds,
        )
        if result.returncode != 0:
            raise GHCommandError(
                "gh command failed ({0}): {1}".format(
                    result.returncode,
                    result.stderr.strip(),
                )
            )
        return result.stdout.strip()

    @staticmethod
    def _normalize_item(item: Dict, github_type: str) -> Dict:
        labels = [label.get("name", "") for label in item.get("labels", []) if label.get("name")]
        assignees = item.get("assignees", []) or []
        assignee = None
        if assignees:
            assignee = assignees[0].get("login")
        return {
            "type": github_type,
            "number": int(item["number"]),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "labels": labels,
            "assignee": assignee,
            "updated_at": item.get("updatedAt"),
        }

