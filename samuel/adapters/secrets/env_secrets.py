from __future__ import annotations

import os

from samuel.core.ports import ISecretsProvider


class EnvSecretsProvider(ISecretsProvider):
    def get(self, key: str) -> str:
        return os.environ.get(key, "")
