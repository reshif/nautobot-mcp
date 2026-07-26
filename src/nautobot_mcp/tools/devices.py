"""Device tools: `nautobot_device`, `nautobot_device_interfaces`, `nautobot_list_devices`."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ._shared import AppContext, Collector, Response, ToolResult, Trimmer, disp, filters, ref, register_tool, ro

_DEVICE_DESC = (
    "Full source-of-truth record for ONE device: role, type/model, platform, status, location, "
    "rack/position, serial/asset tag, primary IPs, tenant, software version, and interface count. "
    "Pass the device NAME. For its interfaces use nautobot_device_interfaces; for cabling use "
    "nautobot_cabling."
)
_INTERFACES_DESC = (
    "List the interfaces of ONE device: name, type, enabled, mode, MTU, MAC, IP count, untagged "
    "VLAN, LAG, and cable/connected peer. Pass the device NAME. Set connected_only=true for just "
    "cabled/connected interfaces."
)
_LIST_DESC = (
    "List devices in the source of truth, filtered by location, role, status, manufacturer, or "
    "model (all by name). Use for inventory questions like 'what devices are in <site>?' or "
    "'all active routers'. For one device's detail use nautobot_device."
)


async def _device(app: AppContext, device: str) -> ToolResult:
    gw = app.gateway
    d = await app.resolver.one("device", device, depth=1)
    c = Collector()
    ifaces = await c.get("interface count", gw.get("dcim/interfaces/", {"device_id": d["id"], "limit": 1}))
    data = {
        "id": d["id"], "name": d.get("name"), "display": d.get("display"), "serial": d.get("serial"),
        "asset_tag": d.get("asset_tag"), "status": ref(d.get("status")), "role": ref(d.get("role")),
        "device_type": ref(d.get("device_type")), "platform": ref(d.get("platform")),
        "location": ref(d.get("location")), "rack": ref(d.get("rack")), "position": d.get("position"),
        "tenant": ref(d.get("tenant")), "primary_ip4": ref(d.get("primary_ip4")),
        "primary_ip6": ref(d.get("primary_ip6")), "software_version": ref(d.get("software_version")),
        "interface_count": (ifaces or {}).get("count"),
    }
    summary = (f"{d.get('name')}: {disp(d.get('role'))} {disp(d.get('device_type'))} at "
               f"{disp(d.get('location'))}, status {disp(d.get('status'))}, "
               f"{data['interface_count']} interfaces, primary IP {disp(d.get('primary_ip4'))}.")
    return Response.build(summary, data, scope=f"device:{d.get('name')}", collector=c)


async def _device_interfaces(app: AppContext, device: str, connected_only: bool = False) -> ToolResult:
    gw = app.gateway
    d = await app.resolver.one("device", device)
    t = Trimmer(app.settings.max_items)
    rows = await gw.list("dcim/interfaces/", {"device_id": d["id"], "depth": 1}, cap=app.settings.max_items + 1)
    if connected_only:
        rows = [r for r in rows if r.get("cable") or r.get("connected_endpoint")]
    items = [{
        "name": r.get("name"), "type": r.get("type"), "enabled": r.get("enabled"), "mode": r.get("mode"),
        "mtu": r.get("mtu"), "mac_address": r.get("mac_address"), "ip_address_count": r.get("ip_address_count"),
        "status": disp(r.get("status")), "untagged_vlan": disp(r.get("untagged_vlan")), "lag": disp(r.get("lag")),
        "cabled": bool(r.get("cable")), "connected_to": disp(r.get("connected_endpoint")),
        "reachable": r.get("connected_endpoint_reachable"), "description": r.get("description"),
    } for r in t.rows(rows)]
    summary = f"{d.get('name')}: {len(items)} interface(s)" + (" (connected only)" if connected_only else "") + "."
    return Response.build(summary, {"device": d.get("name"), "interfaces": items},
                          scope=f"device:{d.get('name')}", count=len(items), truncated=t.truncated)


async def _list_devices(app: AppContext, location: str | None = None, role: str | None = None,
                        status: str | None = None, manufacturer: str | None = None,
                        model: str | None = None) -> ToolResult:
    gw = app.gateway
    t = Trimmer(app.settings.max_items)
    params = {"depth": 1, **filters(
        ("location", location), ("role", role), ("status", status),
        ("manufacturer", manufacturer), ("device_type", model))}
    rows = await gw.list("dcim/devices/", params, cap=app.settings.max_items + 1)
    items = [{
        "id": r.get("id"), "name": r.get("name"), "role": disp(r.get("role")),
        "device_type": disp(r.get("device_type")), "status": disp(r.get("status")),
        "location": disp(r.get("location")), "primary_ip4": disp(r.get("primary_ip4")),
    } for r in t.rows(rows)]
    scope = ", ".join(f"{k}={v}" for k, v in (("location", location), ("role", role), ("status", status),
                      ("manufacturer", manufacturer), ("model", model)) if v) or "all"
    return Response.build(f"{len(items)} device(s) [{scope}].", {"filters": scope, "devices": items},
                          scope="devices", count=len(items), truncated=t.truncated)


_CONFIG_CONTEXT_DESC = (
    "Return the rendered config context for ONE device — the merged data (from config-context "
    "definitions + the device's local context) that automation/templates consume. Pass the device "
    "NAME. Use for 'what config context applies to <device>?' or to see intended config data."
)


async def _device_config_context(app: AppContext, device: str) -> ToolResult:
    gw = app.gateway
    d = await app.resolver.one("device", device)
    full = await gw.get(f"dcim/devices/{d['id']}/", {"include": "config_context"})
    ctx = full.get("config_context")
    keys = list(ctx.keys()) if isinstance(ctx, dict) else []
    return Response.build(f"{d.get('name')}: config context with {len(keys)} top-level key(s): {', '.join(keys[:12])}.",
                          {"device": d.get("name"), "config_context": ctx}, scope=f"device:{d.get('name')}")


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _device, name="nautobot_device", description=_DEVICE_DESC, annotations=ro("Device detail"))
    register_tool(mcp, _device_interfaces, name="nautobot_device_interfaces",
                  description=_INTERFACES_DESC, annotations=ro("Device interfaces"))
    register_tool(mcp, _device_config_context, name="nautobot_device_config_context",
                  description=_CONFIG_CONTEXT_DESC, annotations=ro("Device config context"))
    register_tool(mcp, _list_devices, name="nautobot_list_devices", description=_LIST_DESC, annotations=ro("List devices"))
