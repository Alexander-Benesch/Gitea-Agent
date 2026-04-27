from __future__ import annotations

import json
import tempfile
from pathlib import Path

from samuel.core.bootstrap import bootstrap
from samuel.core.bus import Bus


def test_bootstrap_returns_bus():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "agent.json"
        cfg.write_text(json.dumps({"log_level": "WARNING"}))
        bus = bootstrap(config_path=d)
        assert isinstance(bus, Bus)


def test_bootstrap_has_middlewares():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "agent.json"
        cfg.write_text(json.dumps({}))
        bus = bootstrap(config_path=d)
        assert len(bus._middlewares) == 6
