"""IPAM tools: `nautobot_ip_lookup`, `nautobot_prefix`, `nautobot_list_prefixes`, `nautobot_vlans`."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ._shared import AppContext, Collector, Response, ToolResult, Trimmer, disp, filters, ref, register_tool, ro

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


async def _ip_lookup(app: AppContext, address: str) -> ToolResult:
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


async def _prefix(app: AppContext, prefix: str, include_available: bool = True) -> ToolResult:
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


async def _list_prefixes(app: AppContext, location: str | None = None, role: str | None = None,
                         status: str | None = None, tenant: str | None = None,
                         namespace: str | None = None, within: str | None = None) -> ToolResult:
    gw = app.gateway
    t = Trimmer(app.settings.max_items)
    params = {"depth": 1, **filters(
        ("location", location), ("role", role), ("status", status),
        ("tenant", tenant), ("namespace", namespace), ("within_include", within))}
    rows = await gw.list("ipam/prefixes/", params, cap=app.settings.max_items + 1)
    items = [{"prefix": r.get("prefix"), "status": disp(r.get("status")), "role": disp(r.get("role")),
              "namespace": disp(r.get("namespace")), "vlan": disp(r.get("vlan")), "tenant": disp(r.get("tenant"))}
             for r in t.rows(rows)]
    return Response.build(f"{len(items)} prefix(es).", {"prefixes": items}, scope="ipam",
                          count=len(items), truncated=t.truncated)


async def _vlans(app: AppContext, location: str | None = None, vlan_group: str | None = None,
                 vid: int | None = None, status: str | None = None) -> ToolResult:
    gw = app.gateway
    t = Trimmer(app.settings.max_items)
    params = {"depth": 1, **filters(
        ("location", location), ("vlan_group", vlan_group), ("vid", vid), ("status", status))}
    rows = await gw.list("ipam/vlans/", params, cap=app.settings.max_items + 1)
    items = [{"vid": r.get("vid"), "name": r.get("name"), "status": disp(r.get("status")),
              "vlan_group": disp(r.get("vlan_group")), "role": disp(r.get("role")), "tenant": disp(r.get("tenant"))}
             for r in t.rows(rows)]
    return Response.build(f"{len(items)} VLAN(s).", {"vlans": items}, scope="ipam",
                          count=len(items), truncated=t.truncated)


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _ip_lookup, name="nautobot_ip_lookup", description=_IP_DESC, annotations=ro("IP address lookup"))
    register_tool(mcp, _prefix, name="nautobot_prefix", description=_PREFIX_DESC, annotations=ro("Prefix detail"))
    register_tool(mcp, _list_prefixes, name="nautobot_list_prefixes", description=_LIST_PREFIXES_DESC, annotations=ro("List prefixes"))
    register_tool(mcp, _vlans, name="nautobot_vlans", description=_VLANS_DESC, annotations=ro("List VLANs"))
