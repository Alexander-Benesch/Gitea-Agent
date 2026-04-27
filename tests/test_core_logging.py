from __future__ import annotations

import logging

from samuel.core.logging import setup_logging


def test_setup_logging_creates_handler():
    logger = logging.getLogger("samuel")
    logger.handlers.clear()
    setup_logging(level="DEBUG")
    assert len(logger.handlers) >= 1
    assert logger.level == logging.DEBUG


def test_setup_logging_no_duplicate_handlers():
    logger = logging.getLogger("samuel")
    logger.handlers.clear()
    setup_logging(level="INFO")
    count = len(logger.handlers)
    setup_logging(level="INFO")
    assert len(logger.handlers) == count
