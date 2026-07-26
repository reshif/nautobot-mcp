"""MCP resources — browseable reference data (small, slow-changing lists).

Hosts that support MCP resources (Copilot Studio, Claude, VS Code) can browse
these; tools-only hosts ignore them and use `nautobot_find`. Parameterless (this
FastMCP version treats any param as a URI template), so they read the
process-scoped AppContext and reuse the cached resolver reference lists.
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from ..config import Settings
from ..context import process_app
from ..core.formatting import pick


def _dump(rows: list, keys: tuple[str, ...], label: str) -> str:
    trimmed = [pick(r, keys) for r in rows]
    return json.dumps({"count": len(trimmed), label: trimmed}, indent=2)


def register_resources(mcp: FastMCP, _settings: Settings) -> None:
    @mcp.resource("nautobot://locations", name="Nautobot locations",
                  description="Locations/sites: id, name, type, device_count.", mime_type="application/json")
    async def locations() -> str:
        rows = await process_app().resolver.reference("dcim/locations/", cap=1000)
        return _dump(rows, ("id", "name", "location_type", "device_count", "status"), "locations")

    @mcp.resource("nautobot://device-roles", name="Nautobot device roles",
                  description="Device roles: id, name.", mime_type="application/json")
    async def device_roles() -> str:
        rows = await process_app().resolver.reference("extras/roles/?content_types=dcim.device", cap=500)
        return _dump(rows, ("id", "name"), "roles")

    @mcp.resource("nautobot://statuses", name="Nautobot statuses",
                  description="Statuses (all content types): id, name.", mime_type="application/json")
    async def statuses() -> str:
        rows = await process_app().resolver.reference("extras/statuses/", cap=500)
        return _dump(rows, ("id", "name"), "statuses")

    @mcp.resource("nautobot://manufacturers", name="Nautobot manufacturers",
                  description="Manufacturers: id, name, device_type_count.", mime_type="application/json")
    async def manufacturers() -> str:
        rows = await process_app().resolver.reference("dcim/manufacturers/", cap=500)
        return _dump(rows, ("id", "name", "device_type_count"), "manufacturers")
