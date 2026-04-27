from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler


def setup_logging(level: str = "INFO", log_file: str | None = None, max_log_size_mb: int = 10) -> None:
    root = logging.getLogger("samuel")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not root.handlers:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        root.addHandler(console)

        if log_file:
            max_bytes = max_log_size_mb * 1024 * 1024
            fh = RotatingFileHandler(
                log_file, maxBytes=max_bytes, backupCount=5, encoding="utf-8",
            )
            fh.setFormatter(fmt)
            root.addHandler(fh)
