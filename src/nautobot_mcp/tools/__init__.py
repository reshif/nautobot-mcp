"""Tool registration. Core always; optional behind a feature flag."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..config import Settings
from . import audit, cabling, devices, find, graphql, ipam, locations, overview, query, workflows

_CORE = (find, query, graphql, devices, locations, ipam, cabling, overview, audit, workflows)


def register_all(mcp: FastMCP, settings: Settings) -> None:
    for module in _CORE:
        module.register(mcp)
    if settings.enable_optional_tools:
        from .optional import golden_config, reports
        reports.register(mcp)
        golden_config.register(mcp)
