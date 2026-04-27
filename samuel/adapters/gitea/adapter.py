from __future__ import annotations

import logging

from samuel.adapters.gitea.api import GiteaAPI
from samuel.core.ports import IAuthProvider, IVersionControl
from samuel.core.types import PR, Comment, Issue, Label

log = logging.getLogger(__name__)


class GiteaAdapter(IVersionControl):
    def __init__(self, base_url: str, repo: str, auth: IAuthProvider):
        self._base_url = base_url.rstrip("/")
        self._repo = repo
        self._api = GiteaAPI(base_url, auth)
        self._label_cache: dict[str, int] | None = None

    @property
    def capabilities(self) -> set[str]:
        return {"labels", "webhooks_basic"}

    def get_issue(self, number: int) -> Issue:
        data = self._api.request("GET", f"/repos/{self._repo}/issues/{number}")
        return self._to_issue(data)

    def get_comments(self, number: int) -> list[Comment]:
        data = self._api.request(
            "GET", f"/repos/{self._repo}/issues/{number}/comments"
        )
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
        labels = self._get_all_labels()
        # Remove first, then add — prevents double labels on partial failure
        if remove in labels:
            try:
                self._api.request(
                    "DELETE",
                    f"/repos/{self._repo}/issues/{number}/labels/{labels[remove]}",
                )
            except Exception:
                log.warning("Failed to remove label %s from #%d", remove, number)
        if add in labels:
            self._api.request(
                "POST",
                f"/repos/{self._repo}/issues/{number}/labels",
                {"labels": [labels[add]]},
            )

    def list_labels(self) -> list[dict]:
        data = self._api.request("GET", f"/repos/{self._repo}/labels") or []
        return [
            {"id": l["id"], "name": l["name"], "color": l.get("color", ""),
             "description": l.get("description", "")}
            for l in data
        ]

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        data = self._api.request(
            "POST",
            f"/repos/{self._repo}/labels",
            {"name": name, "color": color, "description": description},
        )
        self._label_cache = None
        return {"id": data["id"], "name": data["name"], "color": data.get("color", ""),
                "description": data.get("description", "")}

    def list_issues(self, labels: list[str]) -> list[Issue]:
        all_issues: list[Issue] = []
        page = 1
        limit = 50
        while True:
            params = f"?type=issues&state=open&limit={limit}&page={page}"
            if labels:
                params += f"&labels={','.join(labels)}"
            data = self._api.request("GET", f"/repos/{self._repo}/issues{params}")
            batch = data or []
            all_issues.extend(self._to_issue(i) for i in batch)
            if len(batch) < limit:
                break
            page += 1
        return all_issues

    def close_issue(self, number: int) -> None:
        self._api.request(
            "PATCH",
            f"/repos/{self._repo}/issues/{number}",
            {"state": "closed"},
        )

    def merge_pr(self, pr_id: int) -> bool:
        self._api.request(
            "POST",
            f"/repos/{self._repo}/pulls/{pr_id}/merge",
            {"Do": "merge", "delete_branch_after_merge": True},
        )
        return True

    def issue_url(self, number: int) -> str:
        return f"{self._base_url}/{self._repo}/issues/{number}"

    def pr_url(self, pr_id: int) -> str:
        return f"{self._base_url}/{self._repo}/pulls/{pr_id}"

    def branch_url(self, branch: str) -> str:
        return f"{self._base_url}/{self._repo}/src/branch/{branch}"

    def _get_all_labels(self) -> dict[str, int]:
        if self._label_cache is None:
            data = self._api.request("GET", f"/repos/{self._repo}/labels") or []
            self._label_cache = {label["name"]: label["id"] for label in data}
        return self._label_cache

    @staticmethod
    def _to_issue(data: dict) -> Issue:
        return Issue(
            number=data["number"],
            title=data["title"],
            body=data.get("body", ""),
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
            body=data.get("body", ""),
            user=data.get("user", {}).get("login", ""),
            created_at=data.get("created_at", ""),
        )

    @staticmethod
    def _to_pr(data: dict) -> PR:
        return PR(
            id=data["id"],
            number=data["number"],
            title=data["title"],
            html_url=data.get("html_url", ""),
            state=data.get("state", "open"),
            merged=data.get("merged", False),
        )
