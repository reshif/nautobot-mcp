"""Best-effort progress/log reporting for multi-call tools.

Wraps the MCP `Context` so fan-out tools can surface steps without every handler
taking a `ctx`. The registrar injects a live `Progress(ctx)` into any handler that
declares a `progress` parameter; direct calls (tests) use the no-op default, so
reporting never changes a tool's result and never raises if the client can't render it.
"""
from __future__ import annotations

from typing import Any

from .observability import get_logger

_logger = get_logger(__name__)


class Progress:
    def __init__(self, ctx: Any | None = None, total: float | None = None) -> None:
        self._ctx = ctx
        self._total = total
        self._done = 0.0

    def start(self, total: float) -> None:
        self._total = total
        self._done = 0.0

    async def step(self, message: str, *, advance: float = 1.0) -> None:
        self._done += advance
        if self._ctx is None:
            return
        try:
            await self._ctx.report_progress(progress=self._done, total=self._total, message=message)
        except Exception:  # noqa: BLE001 — progress is decorative; never break the tool
            _logger.debug("progress.report_failed")

    async def info(self, message: str) -> None:
        if self._ctx is None:
            return
        try:
            await self._ctx.info(message)
        except Exception:  # noqa: BLE001
            _logger.debug("progress.info_failed")


# Shared no-op used as the handler default (and by direct/unit calls).
NULL_PROGRESS = Progress()
