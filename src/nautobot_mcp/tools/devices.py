"""Device tools: `nautobot_device`, `nautobot_device_interfaces`, `nautobot_list_devices`."""
from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..core.response import ErrorKind
from ._params import Device, OptLocation, OptOffset, OptRole, OptStatus
from ._shared import (
    AppContext,
    Collector,
    Response,
    ToolResult,
    Trimmer,
    disp,
    filters,
    list_result,
    ref,
    register_tool,
    ro,
)

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


async def _device(app: AppContext, device: Device) -> ToolResult:
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


async def _device_interfaces(
    app: AppContext, device: Device,
    connected_only: Annotated[bool, Field(description="If true, return only cabled/connected interfaces.")] = False,
) -> ToolResult:
    gw = app.gateway
    d = await app.resolver.one("device", device)
    t = Trimmer(app.settings.max_items)
    rows = await gw.list("dcim/interfaces/", {"device_id": d["id"], "depth": 1}, cap=app.settings.max_items + 1)
    if connected_only:
        rows = [r for r in rows if r.get("cable") or r.get("connected_endpoint")]
    items = [{
        "id": r.get("id"), "name": r.get("name"), "type": disp(r.get("type")), "enabled": r.get("enabled"),
        "mode": disp(r.get("mode")), "mtu": r.get("mtu"), "mac_address": r.get("mac_address"),
        "ip_address_count": r.get("ip_address_count"), "status": disp(r.get("status")),
        "untagged_vlan": disp(r.get("untagged_vlan")), "lag": disp(r.get("lag")),
        "cabled": bool(r.get("cable")), "connected_to": disp(r.get("connected_endpoint")),
        "reachable": r.get("connected_endpoint_reachable"), "description": r.get("description"),
    } for r in t.rows(rows)]
    summary = f"{d.get('name')}: {len(items)} interface(s)" + (" (connected only)" if connected_only else "") + "."
    return list_result(summary, items, kind="interface", scope=f"device:{d.get('name')}",
                       truncated=t.truncated, extra={"device": d.get("name")})


async def _list_devices(
    app: AppContext, location: OptLocation = None, role: OptRole = None, status: OptStatus = None,
    manufacturer: Annotated[str | None, Field(description="Filter by manufacturer NAME, e.g. 'Cisco', 'Arista'.")] = None,
    model: Annotated[str | None, Field(description="Filter by device-type/model NAME, e.g. 'DCS-7280'.")] = None,
    platform: Annotated[str | None, Field(description="Filter by platform NAME (OS family), e.g. 'Arista EOS', 'Cisco IOS'.")] = None,
    software_version: Annotated[str | None, Field(description="Filter by running software version, e.g. '17.12.3' — answers 'which devices run version X?'.")] = None,
    offset: OptOffset = 0,
) -> ToolResult:
    gw = app.gateway
    t = Trimmer(app.settings.max_items)
    params = {"depth": 1, "offset": offset, **filters(
        ("location", location), ("role", role), ("status", status),
        ("manufacturer", manufacturer), ("device_type", model),
        ("platform", platform), ("software_version", software_version))}
    rows = await gw.list("dcim/devices/", params, cap=app.settings.max_items + 1)
    items = [{
        "id": r.get("id"), "name": r.get("name"), "role": disp(r.get("role")),
        "device_type": disp(r.get("device_type")), "status": disp(r.get("status")),
        "location": disp(r.get("location")), "primary_ip4": disp(r.get("primary_ip4")),
    } for r in t.rows(rows)]
    scope = ", ".join(f"{k}={v}" for k, v in (("location", location), ("role", role), ("status", status),
                      ("manufacturer", manufacturer), ("model", model), ("platform", platform),
                      ("software_version", software_version)) if v) or "all"
    return list_result(f"{len(items)} device(s) [{scope}].", items, kind="device", scope="devices",
                       offset=offset, truncated=t.truncated, extra={"filters": scope})


_CONFIG_CONTEXT_DESC = (
    "Return the rendered config context for ONE device — the merged data (from config-context "
    "definitions + the device's local context) that automation/templates consume. Pass the device "
    "NAME. Use for 'what config context applies to <device>?' or to see intended config data."
)


async def _device_config_context(app: AppContext, device: Device) -> ToolResult:
    gw = app.gateway
    d = await app.resolver.one("device", device)
    full = await gw.get(f"dcim/devices/{d['id']}/", {"include": "config_context"})
    ctx = full.get("config_context")
    keys = list(ctx.keys()) if isinstance(ctx, dict) else []
    return Response.build(f"{d.get('name')}: config context with {len(keys)} top-level key(s): {', '.join(keys[:12])}.",
                          {"device": d.get("name"), "config_context": ctx}, scope=f"device:{d.get('name')}")


_INTERFACE_DESC = (
    "Full detail for ONE interface on a device: type, enabled, mode, MTU, MAC, speed, description, "
    "LAG, untagged/tagged VLANs, assigned IP addresses, and the connected peer. Pass the device NAME "
    "and the interface name (e.g. 'GigabitEthernet0/1'). Use for 'show me interface X on <device>'; "
    "for the whole list use nautobot_device_interfaces."
)


async def _interface(
    app: AppContext, device: Device,
    name: Annotated[str, Field(description="Interface name exactly as in Nautobot, e.g. 'GigabitEthernet0/1', 'Ethernet1/1'.")],
) -> ToolResult:
    gw = app.gateway
    d = await app.resolver.one("device", device)
    rows = await gw.list("dcim/interfaces/", {"device_id": d["id"], "name": name, "depth": 1}, cap=2)
    if not rows:
        return Response.error(  # self-correcting: suggest listing them
            ErrorKind.TARGET_NOT_FOUND, f"No interface '{name}' on {d.get('name')}.",
            summary=f"No interface '{name}' on {d.get('name')}. Use nautobot_device_interfaces to list them.",
        )
    r = rows[0]
    ips = await gw.list("ipam/ip-addresses/", {"interfaces": r["id"], "depth": 0}, cap=25)
    data = {
        "device": d.get("name"), "name": r.get("name"), "type": disp(r.get("type")), "enabled": r.get("enabled"),
        "mode": disp(r.get("mode")), "mtu": r.get("mtu"), "mac_address": r.get("mac_address"),
        "description": r.get("description"), "lag": disp(r.get("lag")), "untagged_vlan": disp(r.get("untagged_vlan")),
        "status": disp(r.get("status")), "cabled": bool(r.get("cable")),
        "connected_to": disp(r.get("connected_endpoint")), "reachable": r.get("connected_endpoint_reachable"),
        "ip_addresses": [ip.get("address") for ip in ips],
    }
    summary = (f"{d.get('name')} {r.get('name')}: {data['type']}, "
               f"{'enabled' if r.get('enabled') else 'disabled'}, {len(data['ip_addresses'])} IP(s)"
               f"{', connected to ' + data['connected_to'] if data['connected_to'] else ''}.")
    return Response.build(summary, data, scope=f"device:{d.get('name')}")


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _device, name="nautobot_device", description=_DEVICE_DESC, annotations=ro("Device detail"))
    register_tool(mcp, _device_interfaces, name="nautobot_device_interfaces",
                  description=_INTERFACES_DESC, annotations=ro("Device interfaces"))
    register_tool(mcp, _interface, name="nautobot_interface", description=_INTERFACE_DESC, annotations=ro("Interface detail"))
    register_tool(mcp, _device_config_context, name="nautobot_device_config_context",
                  description=_CONFIG_CONTEXT_DESC, annotations=ro("Device config context"))
    register_tool(mcp, _list_devices, name="nautobot_list_devices", description=_LIST_DESC, annotations=ro("List devices"))
