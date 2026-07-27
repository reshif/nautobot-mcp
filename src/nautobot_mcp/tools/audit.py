"""`nautobot_object_changes` — the source-of-truth audit log (who changed what)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..core.catalog import CONTENT_TYPES as _TYPE_ALIASES
from ._params import OptLimit, OptOffset
from ._shared import AppContext, ToolResult, Trimmer, list_result, register_tool, ro

_DESC = (
    "Audit log of changes in the source of truth (create/update/delete): what object changed, "
    "the action, who did it, when, and the change context. Optionally scope to an object type "
    "(e.g. 'dcim.device', 'ipam.ipaddress'), a user, or a lookback window in days. Use for 'who "
    "changed X?' or 'recent changes to devices'."
)
_FIELDS = ("time", "action", "user_name", "changed_object_type", "object_repr",
           "change_context", "change_context_detail", "request_id")


async def _object_changes(
    app: AppContext,
    object_type: Annotated[str | None, Field(description="Filter by object type, e.g. 'device', 'ip', 'prefix', 'vlan' (or a raw 'dcim.device').")] = None,
    user: Annotated[str | None, Field(description="Filter by the username who made the change.")] = None,
    days: Annotated[int, Field(description="Look back this many days from now.", ge=1)] = 7,
    limit: OptLimit = None,
    offset: OptOffset = 0,
) -> ToolResult:
    gw = app.gateway
    cap = min(limit or app.settings.max_items, app.settings.max_items)
    t = Trimmer(cap)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params: dict = {"depth": 0, "time__gte": since, "offset": offset}
    if object_type:
        params["changed_object_type"] = _TYPE_ALIASES.get(object_type.lower(), object_type)
    if user:
        params["user_name"] = user
    rows = await gw.list("extras/object-changes/", params, cap=cap + 1)
    items = t.rows(rows, _FIELDS)
    scope = ", ".join(f"{k}={v}" for k, v in (("type", object_type), ("user", user), ("days", days)) if v)
    return list_result(f"{len(items)} change(s) [{scope}].", items, kind="object_change",
                       scope="audit", offset=offset, truncated=t.truncated, extra={"filters": scope})


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _object_changes, name="nautobot_object_changes", description=_DESC, annotations=ro("Change audit log"))
