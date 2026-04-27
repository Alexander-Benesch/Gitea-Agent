from __future__ import annotations

from samuel.adapters.secrets.env_secrets import EnvSecretsProvider
from samuel.core.ports import ISecretsProvider


class TestEnvSecretsProvider:
    def test_implements_interface(self):
        assert isinstance(EnvSecretsProvider(), ISecretsProvider)

    def test_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("TEST_SECRET_KEY", "my-secret-value")
        provider = EnvSecretsProvider()
        assert provider.get("TEST_SECRET_KEY") == "my-secret-value"

    def test_missing_var_returns_empty(self):
        provider = EnvSecretsProvider()
        assert provider.get("DEFINITELY_NOT_SET_XYZ_123") == ""
