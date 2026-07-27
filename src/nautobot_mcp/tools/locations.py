"""`nautobot_location` — a site/location and what it contains."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ._params import Location
from ._shared import AppContext, Collector, Response, ToolResult, disp, ref, register_tool, ro

_DESC = (
    "Source-of-truth record for ONE location/site: type, parent, status, tenant, address, and "
    "contained-object counts (devices, prefixes, VLANs, racks, circuits) plus its child "
    "locations. Pass the location NAME. To list the devices in it, use "
    "nautobot_list_devices(location=...)."
)


async def _location(app: AppContext, location: Location) -> ToolResult:
    gw = app.gateway
    loc = await app.resolver.one("location", location, depth=1)
    c = Collector()
    children = await c.get("child locations", gw.list("dcim/locations/", {"parent": loc["id"]}, cap=app.settings.max_items))
    data = {
        "id": loc["id"], "name": loc.get("name"), "location_type": ref(loc.get("location_type")),
        "parent": ref(loc.get("parent")), "status": ref(loc.get("status")), "tenant": ref(loc.get("tenant")),
        "facility": loc.get("facility"), "physical_address": loc.get("physical_address"),
        "time_zone": loc.get("time_zone"),
        "counts": {k: loc.get(k) for k in ("device_count", "prefix_count", "vlan_count", "rack_count", "circuit_count", "virtual_machine_count")},
        "children": [{"id": ch.get("id"), "name": ch.get("name")} for ch in (children or [])],
    }
    ct = data["counts"]
    summary = (f"{loc.get('name')} ({disp(loc.get('location_type'))}): {ct.get('device_count')} devices, "
               f"{ct.get('prefix_count')} prefixes, {ct.get('vlan_count')} VLANs, "
               f"{ct.get('rack_count')} racks; {len(data['children'])} child location(s).")
    return Response.build(summary, data, scope=f"location:{loc.get('name')}", collector=c)


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _location, name="nautobot_location", description=_DESC, annotations=ro("Location detail"))
