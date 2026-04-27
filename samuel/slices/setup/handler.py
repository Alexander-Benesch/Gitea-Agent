from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.ports import IConfig, ISecretsProvider, IVersionControl

log = logging.getLogger(__name__)

REQUIRED_DIRS = ["config", "data", "data/logs"]
REQUIRED_ENV = ["SCM_URL", "SCM_TOKEN", "SCM_REPO"]

PRE_RECEIVE_HOOK = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "pre-receive"


class SetupHandler:
    def __init__(
        self,
        bus: Bus,
        config: IConfig | None = None,
        project_root: Path | None = None,
        secrets: ISecretsProvider | None = None,
        scm: IVersionControl | None = None,
    ) -> None:
        self._bus = bus
        self._config = config
        self._root = project_root or Path(".")
        self._secrets = secrets
        self._scm = scm

    def check_prerequisites(self) -> dict[str, Any]:
        issues: list[str] = []

        for d in REQUIRED_DIRS:
            p = self._root / d
            if not p.exists():
                issues.append(f"directory missing: {d}")

        for env in REQUIRED_ENV:
            legacy = {"SCM_URL": "GITEA_URL", "SCM_TOKEN": "GITEA_TOKEN", "SCM_REPO": "GITEA_REPO"}
            found = False
            if self._secrets:
                try:
                    if self._secrets.get(env):
                        found = True
                except Exception:
                    pass
                if not found:
                    try:
                        legacy_key = legacy.get(env, "")
                        if legacy_key and self._secrets.get(legacy_key):
                            found = True
                    except Exception:
                        pass
            else:
                if os.environ.get(env) or os.environ.get(legacy.get(env, "")):
                    found = True
            if not found:
                issues.append(f"env var missing: {env}")

        return {
            "ready": len(issues) == 0,
            "issues": issues,
        }

    def ensure_directories(self) -> list[str]:
        created: list[str] = []
        for d in REQUIRED_DIRS:
            p = self._root / d
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
                created.append(d)
        return created

    def install_server_hook(self, target_dir: Path) -> dict[str, Any]:
        if not PRE_RECEIVE_HOOK.exists():
            return {"installed": False, "error": f"Hook source not found: {PRE_RECEIVE_HOOK}"}

        target = target_dir / "pre-receive"
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PRE_RECEIVE_HOOK, target)
        target.chmod(0o755)
        log.info("Installed pre-receive hook to %s", target)
        return {"installed": True, "path": str(target)}

    def sync_labels(self, labels_file: Path | None = None) -> dict[str, Any]:
        if self._scm is None:
            return {"synced": False, "error": "SCM not configured"}

        labels_path = labels_file or (self._root / "config" / "labels.json")
        if not labels_path.exists():
            return {"synced": False, "error": f"Labels file not found: {labels_path}"}

        try:
            with open(labels_path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            return {"synced": False, "error": f"Failed to read {labels_path}: {exc}"}

        desired = data.get("labels", [])
        try:
            existing_raw = self._scm.list_labels()
        except Exception as exc:
            log.exception("Failed to list remote labels")
            return {"synced": False, "error": f"list_labels failed: {exc}"}

        existing = {l["name"]: l for l in existing_raw}
        created: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for label in desired:
            name = label["name"]
            if name in existing:
                skipped.append(name)
                continue
            try:
                self._scm.create_label(
                    name=name,
                    color=label.get("color", "cccccc"),
                    description=label.get("description", ""),
                )
                created.append(name)
                log.info("Created label: %s", name)
            except Exception as exc:
                msg = f"{name}: {exc}"
                errors.append(msg)
                log.warning("Failed to create label %s: %s", name, exc)

        return {
            "synced": len(errors) == 0,
            "created": created,
            "skipped": skipped,
            "errors": errors,
            "total": len(desired),
        }

    def get_hook_install_instructions(self, repo_path: str = "<owner>/<repo>") -> str:
        return (
            "## Gitea Server-Hook Installation\n\n"
            "Der pre-receive Hook schützt protected Branches serverseitig.\n"
            "`--no-verify` kann ihn NICHT umgehen.\n\n"
            "### Automatisch (als Gitea-Admin):\n"
            f"```bash\n"
            f"samuel setup --install-hook /data/gitea/repositories/{repo_path}.git/hooks/pre-receive\n"
            f"```\n\n"
            "### Manuell:\n"
            f"```bash\n"
            f"cp scripts/pre-receive /data/gitea/repositories/{repo_path}.git/hooks/pre-receive\n"
            f"chmod +x /data/gitea/repositories/{repo_path}.git/hooks/pre-receive\n"
            f"```\n\n"
            "### Konfiguration:\n"
            "- `SAMUEL_ALLOW_FORCE_PUSH=true` — Force-Push erlauben (nicht empfohlen)\n"
            "- Protected Branches: `main`, `master` (im Script konfigurierbar)\n"
        )
