"""Structured-friendly logging on stdlib logging (no extra dependency)."""
from __future__ import annotations

import logging

_configured = False


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(level=level.upper(), format="%(asctime)s %(levelname)-8s %(name)s :: %(message)s")
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
