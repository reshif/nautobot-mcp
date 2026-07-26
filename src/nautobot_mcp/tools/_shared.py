"""The tool-authoring toolkit — one import for everything a tool module needs."""
from __future__ import annotations

from mcp.types import ToolAnnotations

from ..context import AppContext, get_app
from ..core.formatting import Trimmer, count_by, disp, filters, pick, project, ref
from ..core.response import Collector, Response, ToolResult
from ._registry import register_tool

__all__ = [
    "AppContext", "get_app", "register_tool",
    "Collector", "Response", "ToolResult",
    "pick", "project", "ref", "count_by", "Trimmer", "disp", "filters",
    "ro",
]


def ro(title: str) -> ToolAnnotations:
    """Annotations for a read-only, external-facing tool."""
    return ToolAnnotations(title=title, readOnlyHint=True, openWorldHint=True)
