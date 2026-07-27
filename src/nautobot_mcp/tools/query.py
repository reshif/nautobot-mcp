"""`nautobot_query` — one generic reader over Nautobot's uniform REST API.

Nautobot has ~100 object types with an identical list/filter interface, so a
single well-guarded tool (closed `object_type` set + `q` search + optional
filter passthrough) gives broad coverage without minting 100 tools. Sharp
purpose tools (device, ip_lookup, prefix, location, …) handle the common
intents; this handles everything else.
"""
from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..core.catalog import PATHS as OBJECT_TYPES
from ..core.catalog import filters_for
from ..core.errors import NautobotValidationError
from ..core.response import ErrorKind
from ._params import OptLimit, OptOffset
from ._shared import AppContext, Response, ToolResult, Trimmer, disp, list_result, register_tool, ro

_PROJECT = ("id", "display", "name", "status", "role", "location", "device_type", "manufacturer",
            "prefix", "address", "vid", "cid", "tenant", "cluster", "provider", "url")

_DESC = (
    "Generic reader for ANY Nautobot object type via its uniform REST interface — the catch-all for "
    "object types WITHOUT a dedicated tool (e.g. 'racks', 'vrfs', 'services', 'virtual-machines', "
    "'tags', 'dynamic-groups', 'software-versions', 'cves'). PREFER the dedicated tools when they "
    "exist: nautobot_list_devices, nautobot_list_prefixes, nautobot_list_vlans, nautobot_ip_lookup, "
    "nautobot_circuits, nautobot_location — they have typed, described filters. For rich cross-object "
    "questions prefer nautobot_graphql. Pass optional q (full-text search) and filters (Nautobot query "
    "params, e.g. {'location':'AMS01'}); an unknown filter returns the valid filter names for that type. "
    "Large results are paged — pass the returned next_offset as offset for the next page."
)


async def _query(
    app: AppContext,
    object_type: Annotated[str, Field(description="Object type to read, e.g. 'racks', 'vrfs', 'services', 'virtual-machines', 'cves'. Unknown values return the supported list.")],
    q: Annotated[str | None, Field(description="Full-text search string across the object type.")] = None,
    filters: Annotated[dict | None, Field(description="Extra Nautobot query params as a dict, e.g. {'location': 'AMS01', 'status': 'Active'}. Unknown keys are rejected with the valid ones.")] = None,
    limit: OptLimit = None,
    offset: OptOffset = 0,
) -> ToolResult:
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
    params: dict = {"depth": 1, "offset": offset} if offset else {"depth": 1}
    if q:
        params["q"] = q
    if filters:
        params.update({k: v for k, v in filters.items() if v is not None})
    try:
        rows = await app.gateway.list(path, params, cap=cap + 1)
    except NautobotValidationError as exc:  # bad filter -> tell the LLM the valid ones for this type
        return Response.error(
            ErrorKind.INVALID_INPUT, exc.message,
            choices=[{"valid_filter": f} for f in filters_for(object_type)],
            summary=f"Invalid filter for '{object_type}': {exc.message}. See choices for valid filters.",
        )
    items = [{k: disp(r.get(k)) for k in _PROJECT if k in r} for r in t.rows(rows)]
    return list_result(f"{len(items)} {object_type}.", items, kind=object_type,
                       scope=f"nautobot:{object_type}", offset=offset, truncated=t.truncated,
                       extra={"object_type": object_type})


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _query, name="nautobot_query", description=_DESC, annotations=ro("Query any Nautobot object"))
