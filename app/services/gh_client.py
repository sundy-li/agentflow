import json
import re
import subprocess
from typing import Dict, List, Optional

from app.constants import STATE_LABELS


class GHCommandError(RuntimeError):
    pass


class GHClient:
    def __init__(self, timeout_seconds: int = 120):
        self.timeout_seconds = timeout_seconds

    def list_agent_issues(self, repo_full_name: str) -> List[Dict]:
        return self._list_agent_items(repo_full_name, "issue")

    def list_agent_prs(self, repo_full_name: str) -> List[Dict]:
        return self._list_agent_items(repo_full_name, "pr")

    def list_open_pr_links(self, repo_full_name: str) -> List[Dict]:
        command = [
            "gh",
            "pr",
            "list",
            "--repo",
            repo_full_name,
            "--state",
            "open",
            "--limit",
            "500",
            "--json",
            "number,body",
        ]
        output = self._run(command)
        payload = json.loads(output or "[]")
        linked_prs = []
        for item in payload:
            linked_issue_numbers = self._parse_linked_issue_numbers(repo_full_name, item.get("body", ""))
            if not linked_issue_numbers:
                continue
            linked_prs.append(
                {
                    "number": int(item["number"]),
                    "linked_issue_numbers": linked_issue_numbers,
                }
            )
        return linked_prs

    def _list_agent_items(self, repo_full_name: str, item_type: str) -> List[Dict]:
        merged = {}
        json_fields = "number,title,url,labels,assignees,updatedAt"
        if item_type == "pr":
            json_fields = json_fields + ",headRefOid"
        for label in STATE_LABELS:
            command = [
                "gh",
                item_type,
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
                json_fields,
            ]
            output = self._run(command)
            payload = json.loads(output or "[]")
            for item in payload:
                normalized = self._normalize_item(item, item_type)
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
            "head_sha": item.get("headRefOid") if github_type == "pr" else None,
        }

    @staticmethod
    def _parse_linked_issue_numbers(repo_full_name: str, body: str) -> List[int]:
        if not body:
            return []
        repo_pattern = re.escape(repo_full_name)
        pattern = re.compile(
            r"(?i)\b(?:fix(?:es|ed)?|close(?:s|d)?|resolve(?:s|d)?)\s+((?:{0})?#\d+)".format(repo_pattern)
        )
        issue_numbers = []
        for match in pattern.finditer(body):
            reference = match.group(1)
            if "/" in reference and not reference.startswith(repo_full_name + "#"):
                continue
            issue_numbers.append(int(reference.split("#", 1)[1]))
        return sorted(set(issue_numbers))
