"""Workflow tools — job-driven, multi-endpoint answers (not object dumps).

These are the source-of-truth equivalents of the Meraki workflow tools:
- data_quality_audit : SoT hygiene sweep (what's undocumented?)
- site_report        : one-call site picture (devices by role/status, IPAM, gaps)
- device_readiness   : deployment/documentation checklist for a device
- rack               : rack elevation + free capacity
- ip_allocate        : next free IP(s) / subnet in a prefix (read-only suggestion)
"""
from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

from ._shared import AppContext, Collector, Response, ToolResult, count_by, disp, register_tool, ro

_AUDIT_DESC = (
    "Source-of-truth data-quality audit: counts of documentation gaps — devices missing a primary "
    "IP, without a rack, platform, or software version; prefixes without a role; unassigned IP "
    "addresses. Optionally scope to a location. Use for 'how good is our documentation?' or "
    "'what's missing for <site>?'."
)
_SITE_DESC = (
    "One-call site report: the location, its devices grouped by role and status, IPAM footprint "
    "(prefixes, VLANs), racks, and a data-quality mini-summary. Use for 'give me the full picture "
    "of <site>' or a site handoff/review."
)
_READINESS_DESC = (
    "Deployment/documentation readiness checklist for ONE device: is its role, type, platform, "
    "location, rack+position, primary IP, serial, software version set; are interfaces present; is "
    "it Active? Returns pass/fail per check plus recent changes. Use before deploying/handing off a device."
)
_RACK_DESC = (
    "Rack elevation and capacity for ONE rack: mounted devices by unit, occupied vs free rack "
    "units, and utilization. Pass the rack NAME. Use for capacity/placement questions."
)
_ALLOCATE_DESC = (
    "Suggest free IP space in a prefix (read-only — Nautobot is the source of truth, so this "
    "proposes, it does not reserve). Pass a prefix CIDR; get the next `count` available IPs, and the "
    "available child prefix blocks. Use for 'what's the next free IP/subnet in <prefix>?'."
)


# --- data quality audit ----------------------------------------------------
_CHECKS = [
    ("devices_missing_primary_ip", "dcim/devices/", {"has_primary_ip": "false"}, True),
    ("devices_without_rack", "dcim/devices/", {"rack__isnull": "true"}, True),
    ("devices_without_platform", "dcim/devices/", {"platform__isnull": "true"}, True),
    ("devices_without_software_version", "dcim/devices/", {"has_software_version": "false"}, True),
    ("prefixes_without_role", "ipam/prefixes/", {"role__isnull": "true"}, True),
    ("ip_addresses_unassigned", "ipam/ip-addresses/", {"has_interface_assignments": "false"}, False),
]


async def _data_quality_audit(app: AppContext, location: str | None = None) -> ToolResult:
    gw = app.gateway
    c = Collector()

    async def run(name, path, flt, loc_ok):
        params = dict(flt)
        if location and loc_ok:
            params["location"] = location
        n = await c.get(name, gw.count(path, params))
        return name, n

    pairs = await asyncio.gather(*(run(*chk) for chk in _CHECKS))
    findings = {name: n for name, n in pairs if n is not None}
    ranked = sorted(findings.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(findings.values())
    scope = f"location:{location}" if location else "org"
    summary = f"Data-quality gaps [{scope}], {total} total: " + ", ".join(f"{k}={v}" for k, v in ranked[:4]) + ("…" if len(ranked) > 4 else "")
    return Response.build(summary, {"scope": scope, "findings": findings, "ranked": [k for k, _ in ranked]},
                          scope=scope, collector=c)


# --- site report -----------------------------------------------------------
async def _site_report(app: AppContext, location: str) -> ToolResult:
    gw = app.gateway
    loc = await app.resolver.one("location", location, depth=1)
    c = Collector()
    name = loc.get("name")

    devices, prefixes, vlans, racks, missing_ip = await asyncio.gather(
        c.get("devices", gw.list("dcim/devices/", {"location": name, "depth": 1}, cap=app.settings.max_items)),
        c.get("prefixes", gw.list("ipam/prefixes/", {"location": name, "depth": 1}, cap=app.settings.max_items)),
        c.get("vlans", gw.list("ipam/vlans/", {"location": name, "depth": 1}, cap=app.settings.max_items)),
        c.get("racks", gw.list("dcim/racks/", {"location": name}, cap=app.settings.max_items)),
        c.get("missing primary IP", gw.count("dcim/devices/", {"location": name, "has_primary_ip": "false"})),
    )
    devices = devices or []
    by_role = count_by(devices, "role")
    data = {
        "location": {"name": name, "type": disp(loc.get("location_type")), "status": disp(loc.get("status")),
                     "counts": {k: loc.get(k) for k in ("device_count", "prefix_count", "vlan_count", "rack_count", "circuit_count")}},
        "devices_by_role": by_role,
        "devices_by_status": count_by(devices, "status"),
        "prefixes": [p.get("prefix") for p in (prefixes or [])][:app.settings.max_items],
        "vlans": [{"vid": v.get("vid"), "name": v.get("name")} for v in (vlans or [])][:app.settings.max_items],
        "racks": [r.get("name") for r in (racks or [])],
        "data_quality": {"devices_missing_primary_ip": missing_ip},
    }
    summary = (f"{name}: {len(devices)} devices ({', '.join(f'{k}={v}' for k, v in list(by_role.items())[:3])}), "
               f"{loc.get('prefix_count')} prefixes, {loc.get('vlan_count')} VLANs, {loc.get('rack_count')} racks; "
               f"{missing_ip} device(s) missing a primary IP.")
    return Response.build(summary, data, scope=f"location:{name}", collector=c)


# --- device readiness ------------------------------------------------------
async def _device_readiness(app: AppContext, device: str) -> ToolResult:
    gw = app.gateway
    d = await app.resolver.one("device", device, depth=1)
    c = Collector()
    ifaces, changes = await asyncio.gather(
        c.get("interfaces", gw.get("dcim/interfaces/", {"device_id": d["id"], "limit": 1})),
        c.get("recent changes", gw.list("extras/object-changes/", {"changed_object_id": d["id"]}, cap=5)),
    )
    iface_count = (ifaces or {}).get("count") or 0

    def chk(name, ok, detail):
        return {"name": name, "pass": bool(ok), "detail": detail}

    checks = [
        chk("Role set", d.get("role"), disp(d.get("role"))),
        chk("Device type set", d.get("device_type"), disp(d.get("device_type"))),
        chk("Platform set", d.get("platform"), disp(d.get("platform"))),
        chk("Location set", d.get("location"), disp(d.get("location"))),
        chk("Rack + position", d.get("rack") and d.get("position") is not None, {"rack": disp(d.get("rack")), "position": d.get("position")}),
        chk("Primary IP", d.get("primary_ip4") or d.get("primary_ip6"), disp(d.get("primary_ip4") or d.get("primary_ip6"))),
        chk("Serial", d.get("serial"), d.get("serial")),
        chk("Software version", d.get("software_version"), disp(d.get("software_version"))),
        chk("Status Active", disp(d.get("status")) == "Active", disp(d.get("status"))),
        chk("Has interfaces", iface_count > 0, iface_count),
    ]
    failed = [chk_["name"] for chk_ in checks if not chk_["pass"]]
    data = {"device": d.get("name"), "ready": not failed, "checks": checks,
            "recent_changes": [{"time": ch.get("time"), "action": ch.get("action"), "user": ch.get("user_name")} for ch in (changes or [])]}
    summary = (f"{d.get('name')}: {'READY' if not failed else 'NOT READY'}"
               + (f" — missing: {', '.join(failed)}" if failed else " — all documentation checks pass") + ".")
    return Response.build(summary, data, scope=f"device:{d.get('name')}", collector=c)


# --- rack elevation --------------------------------------------------------
async def _rack(app: AppContext, rack: str) -> ToolResult:
    gw = app.gateway
    rows = await app.resolver.lookup("dcim/racks/", rack, depth=1, cap=10)
    if not rows:
        return Response.build(f"No rack found for '{rack}'.", {"query": rack}, scope="dcim")
    r = rows[0]
    units = await gw.get(f"dcim/racks/{r['id']}/elevation/", {"depth": 1})
    unit_list = units.get("results", units) if isinstance(units, dict) else units
    occupied = [{"unit": u.get("name"), "face": u.get("face"), "device": disp(u.get("device"))}
                for u in (unit_list or []) if u.get("occupied")]
    total = len(unit_list or [])
    data = {"rack": r.get("name"), "location": disp(r.get("location")), "status": disp(r.get("status")),
            "u_height": r.get("u_height"), "units_total": total, "units_occupied": len(occupied),
            "units_free": total - len(occupied), "mounted": occupied[:app.settings.max_items]}
    return Response.build(f"{r.get('name')}: {len(occupied)}/{total} U occupied, {total - len(occupied)} free.",
                          data, scope=f"rack:{r.get('name')}")


# --- IP allocation suggestion ----------------------------------------------
async def _ip_allocate(app: AppContext, prefix: str, count: int = 1) -> ToolResult:
    gw = app.gateway
    c = Collector()
    rows = await gw.list("ipam/prefixes/", {"prefix": prefix, "depth": 1}, cap=5)
    if not rows:
        return Response.build(f"No prefix found for '{prefix}'.", {"query": prefix}, scope="ipam")
    p = rows[0]
    ips, blocks = await asyncio.gather(
        c.get("available IPs", gw.get(f"ipam/prefixes/{p['id']}/available-ips/", {"limit": min(count, 50)})),
        c.get("available prefixes", gw.get(f"ipam/prefixes/{p['id']}/available-prefixes/")),
    )
    free_ips = [str(a["address"]) for a in (ips or []) if isinstance(a, dict) and a.get("address")][:count]
    free_blocks = [str(a["prefix"]) for a in (blocks or []) if isinstance(a, dict) and a.get("prefix")][:10]
    data = {"prefix": p.get("prefix"), "namespace": disp(p.get("namespace")),
            "suggested_ips": free_ips, "available_prefix_blocks": free_blocks,
            "note": "Read-only suggestion — reserve it in Nautobot to make it authoritative."}
    summary = (f"{p.get('prefix')}: next {len(free_ips)} free IP(s): {', '.join(free_ips) or 'none'}"
               f"{'; free blocks: ' + ', '.join(free_blocks[:3]) if free_blocks else ''}.")
    return Response.build(summary, data, scope="ipam", collector=c)


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _data_quality_audit, name="nautobot_data_quality_audit", description=_AUDIT_DESC, annotations=ro("SoT data-quality audit"))
    register_tool(mcp, _site_report, name="nautobot_site_report", description=_SITE_DESC, annotations=ro("Site report"))
    register_tool(mcp, _device_readiness, name="nautobot_device_readiness", description=_READINESS_DESC, annotations=ro("Device readiness"))
    register_tool(mcp, _rack, name="nautobot_rack", description=_RACK_DESC, annotations=ro("Rack elevation"))
    register_tool(mcp, _ip_allocate, name="nautobot_ip_allocate", description=_ALLOCATE_DESC, annotations=ro("Suggest free IP space"))
