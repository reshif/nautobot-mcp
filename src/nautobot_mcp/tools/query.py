"""`nautobot_query` — one generic reader over Nautobot's uniform REST API.

Nautobot has ~100 object types with an identical list/filter interface, so a
single well-guarded tool (closed `object_type` set + `q` search + optional
filter passthrough) gives broad coverage without minting 100 tools. Sharp
purpose tools (device, ip_lookup, prefix, location, …) handle the common
intents; this handles everything else.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..core.catalog import PATHS as OBJECT_TYPES
from ..core.response import ErrorKind
from ._shared import AppContext, Response, ToolResult, Trimmer, disp, register_tool, ro

_PROJECT = ("id", "display", "name", "status", "role", "location", "device_type", "manufacturer",
            "prefix", "address", "vid", "cid", "tenant", "cluster", "provider", "url")

_DESC = (
    "Generic reader for ANY Nautobot object type via its uniform REST interface — the catch-all "
    "for object types without a dedicated tool. Pass object_type (e.g. 'racks', 'vrfs', 'services', "
    "'virtual-machines', 'circuits', 'tags', 'dynamic-groups', 'software-versions'), an optional q "
    "(full-text search), and optional filters (Nautobot query params, e.g. {'location':'AMS01'}). "
    "For rich cross-object questions prefer nautobot_graphql; for devices/IPs/prefixes/locations use "
    "their dedicated tools."
)


async def _query(app: AppContext, object_type: str, q: str | None = None,
                 filters: dict | None = None, limit: int | None = None) -> ToolResult:
    path = OBJECT_TYPES.get(object_type)
    if not path:
        return Response.error(  # self-correcting: list valid types
            ErrorKind.TARGET_NOT_FOUND,
            f"Unknown object_type '{object_type}'.",
            choices=[{"object_type": k} for k in sorted(OBJECT_TYPES)],
            summary=f"Unknown object_type '{object_type}'. See choices for the {len(OBJECT_TYPES)} supported types.",
        )
    cap = min(limit or app.settings.max_items, app.settings.max_items)
    t = Trimmer(cap)
    params: dict = {"depth": 1}
    if q:
        params["q"] = q
    if filters:
        params.update({k: v for k, v in filters.items() if v is not None})
    rows = await app.gateway.list(path, params, cap=cap + 1)
    items = [{k: disp(r.get(k)) for k in _PROJECT if k in r} for r in t.rows(rows)]
    return Response.build(f"{len(items)} {object_type}.", {"object_type": object_type, "results": items},
                          scope=f"nautobot:{object_type}", count=len(items), truncated=t.truncated)


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _query, name="nautobot_query", description=_DESC, annotations=ro("Query any Nautobot object"))
