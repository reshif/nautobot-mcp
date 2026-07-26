"""`nautobot_cabling` — physical connections for a device."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ._shared import AppContext, Response, ToolResult, Trimmer, disp, register_tool, ro

_DESC = (
    "Show the physical connections of a device: for each cabled interface, the local port, the "
    "cable, and the connected peer (remote device/port) with reachability. Pass the device NAME. "
    "Use for 'what is <device> connected to?'."
)


async def _cabling(app: AppContext, device: str) -> ToolResult:
    gw = app.gateway
    d = await app.resolver.one("device", device)
    t = Trimmer(app.settings.max_items)
    rows = await gw.list("dcim/interfaces/", {"device_id": d["id"], "depth": 1}, cap=app.settings.max_items * 2)
    connected = [r for r in rows if r.get("cable") or r.get("connected_endpoint")]
    links = [{
        "local_interface": r.get("name"),
        "cable": disp(r.get("cable")),
        "cable_peer": disp(r.get("cable_peer")),
        "connected_endpoint": disp(r.get("connected_endpoint")),
        "reachable": r.get("connected_endpoint_reachable"),
    } for r in t.rows(connected)]
    return Response.build(f"{d.get('name')}: {len(links)} cabled/connected interface(s).",
                          {"device": d.get("name"), "links": links},
                          scope=f"device:{d.get('name')}", count=len(links), truncated=t.truncated)


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _cabling, name="nautobot_cabling", description=_DESC, annotations=ro("Device cabling"))
