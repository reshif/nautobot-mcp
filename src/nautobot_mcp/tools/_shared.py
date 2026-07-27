"""The tool-authoring toolkit — one import for everything a tool module needs."""
from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from ..context import AppContext, get_app
from ..core.formatting import Trimmer, count_by, disp, filters, pick, project, ref
from ..core.response import Collector, Response, ToolResult
from ._registry import register_tool

__all__ = [
    "AppContext", "get_app", "register_tool",
    "Collector", "Response", "ToolResult",
    "pick", "project", "ref", "count_by", "Trimmer", "disp", "filters",
    "ro", "list_result",
]


def ro(title: str) -> ToolAnnotations:
    """Annotations for a read-only, external-facing tool.

    idempotentHint: every tool is a GET-style read, so repeating a call yields the
    same result (no side effects) — this lets clients safely retry/parallelize.
    """
    return ToolAnnotations(title=title, readOnlyHint=True, idempotentHint=True, openWorldHint=True)


def list_result(summary: str, items: list[Any], *, kind: str, scope: str, offset: int = 0,
                truncated: bool = False, extra: dict[str, Any] | None = None,
                collector: Collector | None = None) -> ToolResult:
    """Uniform envelope for every list-shaped tool result.

    Standardizes on `{kind, count, items}` (+ `offset`/`next_offset` for cursor paging)
    so an agent extracts results the same way from every list tool. `next_offset` is the
    value to pass back as `offset` to fetch the next page when a result is truncated.
    """
    data: dict[str, Any] = {"kind": kind, "count": len(items), "items": items}
    if offset:
        data["offset"] = offset
    if truncated:
        data["next_offset"] = offset + len(items)
    if extra:
        data.update(extra)
    return Response.build(summary, data, scope=scope, count=len(items), truncated=truncated, collector=collector)
