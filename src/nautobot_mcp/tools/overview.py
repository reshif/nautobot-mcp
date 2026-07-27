"""`nautobot_status_overview` — counts of devices grouped by status, role, or location."""
from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ._shared import AppContext, Collector, Response, ToolResult, register_tool, ro

_DESC = (
    "Fleet counts from the source of truth: number of devices grouped by status, role, or "
    "location. Use for 'how many devices per site/role?' or 'how many are active vs offline?'. "
    "Accurate counts (queried per group), not a sample."
)


async def _status_overview(
    app: AppContext,
    group_by: Annotated[Literal["status", "role", "location"], Field(description="Dimension to group the device counts by.")] = "status",
) -> ToolResult:
    gw = app.gateway
    c = Collector()

    if group_by == "location":
        # Locations carry a device_count field — top-N by device count, no per-group queries.
        locs = await c.get("locations", app.resolver.reference("dcim/locations/", cap=1000))
        ranked = sorted((locs or []), key=lambda x: x.get("device_count") or 0, reverse=True)
        counts = {loc.get("name"): loc.get("device_count") for loc in ranked[:app.settings.max_items] if loc.get("device_count")}
        total = sum(v or 0 for v in counts.values())
        return Response.build(f"Devices by location (top {len(counts)}); total counted {total}.",
                              {"group_by": "location", "counts": counts}, scope="devices", collector=c)

    ref_path = "extras/statuses/" if group_by == "status" else "extras/roles/"
    groups = await c.get(f"{group_by}s", app.resolver.reference(f"{ref_path}?content_types=dcim.device", cap=200)) or []
    names = [g.get("name") for g in groups if g.get("name")]

    async def _grp_count(name: str) -> tuple[str, int | None]:
        return name, await c.get(f"count {group_by}={name}", gw.count("dcim/devices/", {group_by: name}))

    pairs = await asyncio.gather(*(_grp_count(n) for n in names))
    counts = {name: cnt for name, cnt in pairs if cnt}
    total = sum(counts.values())
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
    summary = f"Devices by {group_by} (total {total}): " + ", ".join(f"{k}={v}" for k, v in top) + ("…" if len(counts) > 5 else "")
    return Response.build(summary, {"group_by": group_by, "counts": counts, "total": total},
                          scope="devices", collector=c)


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _status_overview, name="nautobot_status_overview",
                  description=_DESC, annotations=ro("Device status overview"))
