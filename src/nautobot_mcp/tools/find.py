"""`nautobot_find` — discover/look up objects by name or value."""
from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..core.resolver import Kind
from ._shared import AppContext, Response, ToolResult, pick, register_tool, ro

_DESC = (
    "Look up Nautobot objects by a human name or value: devices, locations/sites, prefixes, IP "
    "addresses, or VLANs. Returns matches with their IDs and display names. Use when you have a "
    "name but not an ID, or to check what exists. Status/detail tools accept names directly, so "
    "you usually don't need this first."
)
_KEYS = ("id", "display", "name", "prefix", "address", "vid")


async def _find(
    app: AppContext,
    query: Annotated[str, Field(description="Name or value to search for, e.g. a device name 'ams01-edge-01', a site 'AMS01', a CIDR '10.0.0.0/24', or an IP '10.0.0.1'.")],
    kind: Annotated[Literal["any", "device", "location", "prefix", "ip", "vlan"], Field(description="Restrict the search to one object type; 'any' (default) searches all.")] = "any",
) -> ToolResult:
    all_kinds: list[Kind] = ["device", "location", "prefix", "ip", "vlan"]
    kinds: list[Kind] = [kind] if kind != "any" else all_kinds
    found = await app.resolver.search(query, kinds, per_kind=app.settings.max_items // 10 or 10)
    data = {k: [pick(r, _KEYS) for r in rows] for k, rows in found.items() if rows}
    total = sum(len(v) for v in data.values())
    summary = f"{total} match(es) for '{query}': " + (", ".join(f"{len(v)} {k}" for k, v in data.items()) or "none")
    return Response.build(summary, data, scope="nautobot", count=total)


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _find, name="nautobot_find", description=_DESC, annotations=ro("Find Nautobot objects"))
