"""IPAM tools: `nautobot_ip_lookup`, `nautobot_prefix`, `nautobot_list_prefixes`, `nautobot_list_vlans`."""
from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..core.errors import AmbiguousTarget, TargetNotFound
from ._params import OptLocation, OptOffset, OptRole, OptStatus, OptTenant
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

_IP_DESC = (
    "Look up an IP address in the source of truth: its status, DNS name, type/role, parent prefix, "
    "tenant, and — importantly — what device/interface it is assigned to. Pass the address (with or "
    "without mask, e.g. 10.0.0.1 or 10.0.0.1/24)."
)
_PREFIX_DESC = (
    "Detail for ONE prefix: status, role, namespace/VRF, VLAN, tenant, plus its child prefixes and "
    "the count of IP addresses within it. Pass the prefix in CIDR (e.g. 10.0.0.0/24)."
)
_LIST_PREFIXES_DESC = (
    "List prefixes, filtered by location, role, status, tenant, namespace, or contained-within a "
    "CIDR. Use for 'what subnets are at <site>?'. For one prefix's detail use nautobot_prefix."
)
_VLANS_DESC = (
    "List VLANs, filtered by location, VLAN group, VID, or status. Use for 'what VLANs are at "
    "<site>?' or to find a VLAN by number/name."
)
_VLAN_DESC = (
    "Detail for ONE VLAN: status, VLAN group, role, tenant, location, and the prefixes/subnets "
    "mapped to it. Pass the VLAN name or its VID number. Use for 'tell me about VLAN 100' or "
    "'what subnets are on the voice VLAN?'. For a list of VLANs use nautobot_list_vlans."
)


async def _ip_lookup(
    app: AppContext,
    address: Annotated[str, Field(description="IP address, with or without mask, e.g. '10.0.0.1' or '10.0.0.1/24'.")],
) -> ToolResult:
    gw = app.gateway
    c = Collector()
    flt = {"address": address} if "/" in address else {"host": address}
    rows = await gw.list("ipam/ip-addresses/", {**flt, "depth": 1}, cap=10)
    if not rows:
        return Response.build(f"No IP address found for '{address}'.", {"query": address}, scope="ipam")
    ip = rows[0]
    assigns = await c.get("assignments", gw.list("ipam/ip-address-to-interface/", {"ip_address": ip["id"], "depth": 1}, cap=25))
    assignments = [{
        "interface": disp(a.get("interface")),
        "device": disp((a.get("interface") or {}).get("device")) if isinstance(a.get("interface"), dict) else None,
        "primary": a.get("is_primary"),
    } for a in (assigns or [])]
    data = {
        "address": ip.get("address"), "host": ip.get("host"), "status": ref(ip.get("status")),
        "role": ref(ip.get("role")), "type": ip.get("type"), "dns_name": ip.get("dns_name"),
        "tenant": ref(ip.get("tenant")), "parent_prefix": ref(ip.get("parent")),
        "assignments": assignments, "other_matches": len(rows) - 1,
    }
    where = f"assigned to {assignments[0]['device']} / {assignments[0]['interface']}" if assignments else "unassigned"
    return Response.build(f"{ip.get('address')}: {disp(ip.get('status'))}, {where}.", data, scope="ipam", collector=c)


async def _prefix(
    app: AppContext,
    prefix: Annotated[str, Field(description="Prefix in CIDR notation, e.g. '10.0.0.0/24'.")],
    include_available: Annotated[bool, Field(description="If true, also return the first free IPs and available child blocks.")] = True,
) -> ToolResult:
    gw = app.gateway
    c = Collector()
    rows = await gw.list("ipam/prefixes/", {"prefix": prefix, "depth": 1}, cap=5)
    if not rows:
        return Response.build(f"No prefix found for '{prefix}'.", {"query": prefix}, scope="ipam")
    p = rows[0]
    children = await c.get("child prefixes", gw.list("ipam/prefixes/", {"parent": p["id"]}, cap=app.settings.max_items))
    ipc = await c.get("ip count", gw.get("ipam/ip-addresses/", {"parent": p["id"], "limit": 1}))
    data = {
        "prefix": p.get("prefix"), "status": ref(p.get("status")), "role": ref(p.get("role")),
        "type": p.get("type"), "namespace": ref(p.get("namespace")), "vlan": ref(p.get("vlan")),
        "rir": ref(p.get("rir")), "tenant": ref(p.get("tenant")), "ip_version": p.get("ip_version"),
        "ip_address_count": (ipc or {}).get("count"),
        "child_prefixes": [{"prefix": ch.get("prefix"), "status": disp(ch.get("status"))} for ch in (children or [])],
    }
    if include_available:  # delivery: find free space. These endpoints return a BARE list (not paginated).
        avail_ips = await c.get("available IPs", gw.get(f"ipam/prefixes/{p['id']}/available-ips/", {"limit": 10}))
        avail_pfx = await c.get("available prefixes", gw.get(f"ipam/prefixes/{p['id']}/available-prefixes/"))
        data["available"] = {
            "first_ips": [a.get("address") for a in (avail_ips or []) if isinstance(a, dict)][:10],
            "prefixes": [a.get("prefix") for a in (avail_pfx or []) if isinstance(a, dict)][:10],
        }
    summary = (f"{p.get('prefix')} ({disp(p.get('status'))}): {data['ip_address_count']} IPs, "
               f"{len(data['child_prefixes'])} child prefix(es)"
               f"{', first free IP ' + data['available']['first_ips'][0] if data.get('available', {}).get('first_ips') else ''}.")
    return Response.build(summary, data, scope="ipam", collector=c)


async def _list_prefixes(
    app: AppContext, location: OptLocation = None, role: OptRole = None, status: OptStatus = None,
    tenant: OptTenant = None,
    namespace: Annotated[str | None, Field(description="Filter by IPAM namespace NAME (e.g. 'Global').")] = None,
    within: Annotated[str | None, Field(description="Only prefixes contained within this CIDR, e.g. '10.0.0.0/16'.")] = None,
    offset: OptOffset = 0,
) -> ToolResult:
    gw = app.gateway
    t = Trimmer(app.settings.max_items)
    params = {"depth": 1, "offset": offset, **filters(
        ("location", location), ("role", role), ("status", status),
        ("tenant", tenant), ("namespace", namespace), ("within_include", within))}
    rows = await gw.list("ipam/prefixes/", params, cap=app.settings.max_items + 1)
    items = [{"id": r.get("id"), "prefix": r.get("prefix"), "status": disp(r.get("status")), "role": disp(r.get("role")),
              "namespace": disp(r.get("namespace")), "vlan": disp(r.get("vlan")), "tenant": disp(r.get("tenant"))}
             for r in t.rows(rows)]
    return list_result(f"{len(items)} prefix(es).", items, kind="prefix", scope="ipam",
                       offset=offset, truncated=t.truncated)


async def _vlans(
    app: AppContext, location: OptLocation = None,
    vlan_group: Annotated[str | None, Field(description="Filter by VLAN group NAME.")] = None,
    vid: Annotated[int | None, Field(description="Filter by VLAN ID number, e.g. 100.")] = None,
    status: OptStatus = None,
    offset: OptOffset = 0,
) -> ToolResult:
    gw = app.gateway
    t = Trimmer(app.settings.max_items)
    params = {"depth": 1, "offset": offset, **filters(
        ("location", location), ("vlan_group", vlan_group), ("vid", vid), ("status", status))}
    rows = await gw.list("ipam/vlans/", params, cap=app.settings.max_items + 1)
    items = [{"id": r.get("id"), "vid": r.get("vid"), "name": r.get("name"), "status": disp(r.get("status")),
              "vlan_group": disp(r.get("vlan_group")), "role": disp(r.get("role")), "tenant": disp(r.get("tenant"))}
             for r in t.rows(rows)]
    return list_result(f"{len(items)} VLAN(s).", items, kind="vlan", scope="ipam",
                       offset=offset, truncated=t.truncated)


async def _vlan(
    app: AppContext,
    vlan: Annotated[str, Field(description="VLAN name (e.g. 'voice') or VID number (e.g. '100').")],
) -> ToolResult:
    gw = app.gateway
    q = vlan.strip()
    if q.isdigit():
        rows = await gw.list("ipam/vlans/", {"vid": int(q), "depth": 1}, cap=25)
    else:
        rows = await app.resolver.lookup("ipam/vlans/", q, depth=1, cap=25)
    if not rows:
        raise TargetNotFound(f"No VLAN matched '{vlan}'.")
    if len(rows) > 1:  # VID isn't globally unique — let the caller pick
        raise AmbiguousTarget(
            f"'{vlan}' matched {len(rows)} VLANs.",
            [{"id": r.get("id"), "display": f"VID {r.get('vid')} {r.get('name')} ({disp(r.get('vlan_group'))})"}
             for r in rows[:25]],
        )
    v = rows[0]
    prefixes = await gw.list("ipam/prefixes/", {"vlan_id": v["id"], "depth": 0}, cap=app.settings.max_items)
    data = {
        "vid": v.get("vid"), "name": v.get("name"), "status": disp(v.get("status")),
        "vlan_group": disp(v.get("vlan_group")), "role": disp(v.get("role")), "tenant": disp(v.get("tenant")),
        "location": disp(v.get("location")), "prefix_count": v.get("prefix_count"),
        "prefixes": [p.get("prefix") for p in prefixes],
    }
    summary = (f"VLAN {v.get('vid')} ({v.get('name')}): {disp(v.get('status'))}, "
               f"group {disp(v.get('vlan_group')) or '—'}, {len(data['prefixes'])} prefix(es) mapped.")
    return Response.build(summary, data, scope=f"vlan:{v.get('vid')}")


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _ip_lookup, name="nautobot_ip_lookup", description=_IP_DESC, annotations=ro("IP address lookup"))
    register_tool(mcp, _prefix, name="nautobot_prefix", description=_PREFIX_DESC, annotations=ro("Prefix detail"))
    register_tool(mcp, _list_prefixes, name="nautobot_list_prefixes", description=_LIST_PREFIXES_DESC, annotations=ro("List prefixes"))
    register_tool(mcp, _vlans, name="nautobot_list_vlans", description=_VLANS_DESC, annotations=ro("List VLANs"))
    register_tool(mcp, _vlan, name="nautobot_vlan", description=_VLAN_DESC, annotations=ro("VLAN detail"))
