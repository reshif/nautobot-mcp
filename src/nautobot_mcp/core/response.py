"""The response lifecycle — one contract every tool returns through.

Every tool returns a `ToolResult` = `summary` (one human line) + `data`
(structured, trimmed) + `meta` (scope/count/truncated/partial/warnings/note).
Multi-call tools fetch through a `Collector` so partial data is *declared*.
`enforce_budget` (run by the registrar) guarantees the result fits the agent.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .observability import get_logger

_logger = get_logger(__name__)


class ErrorKind(str, Enum):
    AMBIGUOUS_TARGET = "ambiguous_target"
    TARGET_NOT_FOUND = "target_not_found"
    TIMEOUT = "timeout"
    API_ERROR = "api_error"
    UNEXPECTED = "unexpected_error"


class ErrorInfo(BaseModel):
    error: bool = True
    kind: ErrorKind
    message: str
    operation: str | None = None
    choices: list[dict[str, Any]] | None = None


class Meta(BaseModel):
    scope: str | None = None
    count: int | None = None
    truncated: bool = False
    partial: bool = False
    warnings: list[str] = Field(default_factory=list)
    note: str | None = None
    elapsed_ms: int | None = None


class ToolResult(BaseModel):
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    meta: Meta = Field(default_factory=Meta)
    error: ErrorInfo | None = None


class Collector:
    """Runs a tool's fetches; on failure records a warning + marks partial (never a silent None)."""

    def __init__(self) -> None:
        self.warnings: list[str] = []

    async def get(self, label: str, awaitable: Awaitable[Any]) -> Any | None:
        try:
            return await awaitable
        except Exception as exc:  # gateway pre-normalizes to GatewayError
            self.warnings.append(f"{label}: {getattr(exc, 'message', None) or type(exc).__name__}")
            _logger.debug("collector.subfetch_failed", extra={"label": label})
            return None

    @property
    def partial(self) -> bool:
        return bool(self.warnings)


class Response:
    @staticmethod
    def build(summary: str, data: dict[str, Any] | None = None, *, scope: str | None = None,
              count: int | None = None, truncated: bool = False, collector: Collector | None = None) -> ToolResult:
        meta = Meta(scope=scope, count=count, truncated=truncated,
                    partial=bool(collector and collector.warnings),
                    warnings=list(collector.warnings) if collector else [])
        return ToolResult(summary=summary, data=data or {}, meta=meta)

    @staticmethod
    def error(kind: ErrorKind, message: str, *, operation: str | None = None,
              choices: list[dict[str, Any]] | None = None, summary: str | None = None) -> ToolResult:
        return ToolResult(summary=summary or message,
                          error=ErrorInfo(kind=kind, message=message, operation=operation, choices=choices))


def _size(data: Any) -> int:
    return len(json.dumps(data, default=str))


def _lists_in(obj: Any) -> list[list]:
    found: list[list] = []

    def walk(o: Any) -> None:
        if isinstance(o, list):
            found.append(o)
            for item in o:
                walk(item)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)

    walk(obj)
    return found


def enforce_budget(result: ToolResult, max_chars: int) -> None:
    """Shrink the largest arrays until `data` fits `max_chars`; flag it. Run for every tool."""
    if _size(result.data) <= max_chars:
        return
    for _ in range(64):
        lists = [lst for lst in _lists_in(result.data) if len(lst) > 1]
        if not lists:
            break
        biggest = max(lists, key=_size)
        del biggest[len(biggest) // 2:]
        if _size(result.data) <= max_chars:
            break
    result.meta.truncated = True
    result.meta.note = (
        f"Response exceeded the {max_chars}-char budget and was trimmed to fit the agent's context. "
        "Narrow the query (by location, role, status, or a specific object) for complete data."
    )
