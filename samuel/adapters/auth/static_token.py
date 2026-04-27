from __future__ import annotations

from samuel.core.ports import IAuthProvider


class StaticTokenAuth(IAuthProvider):
    def __init__(self, token: str):
        self._token = token

    def get_token(self) -> str:
        return self._token

    def is_valid(self) -> bool:
        return bool(self._token)

    def refresh(self) -> None:
        pass
