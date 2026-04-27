from __future__ import annotations

import logging

from samuel.adapters.github.api import GitHubAPI
from samuel.core.ports import IAuthProvider, IVersionControl
from samuel.core.types import PR, Comment, Issue, Label

log = logging.getLogger(__name__)


class GitHubAdapter(IVersionControl):
    def __init__(self, repo: str, auth: IAuthProvider, *, base_url: str = "https://api.github.com"):
        self._repo = repo
        self._api = GitHubAPI(auth, base_url=base_url)
        self._html_base = (
            "https://github.com" if "api.github.com" in base_url
            else base_url.replace("/api/v3", "").replace("/api", "")
        )

    @property
    def capabilities(self) -> set[str]:
        return {"labels", "webhooks_full", "checks", "pull_request_reviews"}

    def get_issue(self, number: int) -> Issue:
        data = self._api.request("GET", f"/repos/{self._repo}/issues/{number}")
        return self._to_issue(data)

    def get_comments(self, number: int) -> list[Comment]:
        data = self._api.request("GET", f"/repos/{self._repo}/issues/{number}/comments")
        return [self._to_comment(c) for c in (data or [])]

    def post_comment(self, number: int, body: str) -> Comment:
        data = self._api.request(
            "POST",
            f"/repos/{self._repo}/issues/{number}/comments",
            {"body": body},
        )
        return self._to_comment(data)

    def create_pr(self, head: str, base: str, title: str, body: str) -> PR:
        data = self._api.request(
            "POST",
            f"/repos/{self._repo}/pulls",
            {"title": title, "body": body, "head": head, "base": base},
        )
        return self._to_pr(data)

    def swap_label(self, number: int, remove: str, add: str) -> None:
        # Remove first, then add — prevents double labels on partial failure
        if remove:
            try:
                self._api.request(
                    "DELETE",
                    f"/repos/{self._repo}/issues/{number}/labels/{remove}",
                )
            except Exception:
                log.warning("Failed to remove label %s from #%d", remove, number)
        if add:
            self._api.request(
                "POST",
                f"/repos/{self._repo}/issues/{number}/labels",
                {"labels": [add]},
            )

    def list_labels(self) -> list[dict]:
        data = self._api.request("GET", f"/repos/{self._repo}/labels?per_page=100") or []
        return [
            {"id": l["id"], "name": l["name"], "color": l.get("color", ""),
             "description": l.get("description", "") or ""}
            for l in data
        ]

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        data = self._api.request(
            "POST",
            f"/repos/{self._repo}/labels",
            {"name": name, "color": color, "description": description},
        )
        return {"id": data["id"], "name": data["name"], "color": data.get("color", ""),
                "description": data.get("description", "") or ""}

    def list_issues(self, labels: list[str]) -> list[Issue]:
        params = "?state=open&per_page=50"
        if labels:
            params += f"&labels={','.join(labels)}"
        data = self._api.request("GET", f"/repos/{self._repo}/issues{params}")
        return [self._to_issue(i) for i in (data or []) if "pull_request" not in i]

    def close_issue(self, number: int) -> None:
        self._api.request(
            "PATCH",
            f"/repos/{self._repo}/issues/{number}",
            {"state": "closed"},
        )

    def merge_pr(self, pr_id: int) -> bool:
        self._api.request(
            "PUT",
            f"/repos/{self._repo}/pulls/{pr_id}/merge",
            {"merge_method": "merge"},
        )
        return True

    def issue_url(self, number: int) -> str:
        return f"{self._html_base}/{self._repo}/issues/{number}"

    def pr_url(self, pr_id: int) -> str:
        return f"{self._html_base}/{self._repo}/pull/{pr_id}"

    def branch_url(self, branch: str) -> str:
        return f"{self._html_base}/{self._repo}/tree/{branch}"

    @staticmethod
    def _to_issue(data: dict) -> Issue:
        return Issue(
            number=data["number"],
            title=data["title"],
            body=data.get("body") or "",
            state=data["state"],
            labels=[
                Label(id=l["id"], name=l["name"])
                for l in data.get("labels", [])
            ],
        )

    @staticmethod
    def _to_comment(data: dict) -> Comment:
        return Comment(
            id=data["id"],
            body=data.get("body") or "",
            user=data.get("user", {}).get("login", ""),
            created_at=data.get("created_at", ""),
        )

    @staticmethod
    def _to_pr(data: dict) -> PR:
        return PR(
            id=data.get("id", 0),
            number=data["number"],
            title=data["title"],
            html_url=data.get("html_url", ""),
            state=data.get("state", "open"),
            merged=data.get("merged", False),
        )
