"""Golden Config intent tools (require the nautobot-golden-config app).

The network-automation power layer: per-device config compliance (compliant vs
non-compliant features + remediation) and the stored backup / intended /
compliance configs. Enabled with NAUTOBOT_MCP_ENABLE_OPTIONAL_TOOLS=true.
"""
from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

from .._shared import AppContext, Collector, Response, ToolResult, Trimmer, disp, register_tool, ro

_COMPLIANCE_DESC = (
    "Golden Config compliance for a device (or a location): which config features are compliant vs "
    "non-compliant, with what's missing/extra and the remediation. Use for 'is <device> config-"
    "compliant?' or 'compliance status at <site>?'. Requires the Golden Config app."
)
_CONFIG_DESC = (
    "Retrieve a device's stored config from Golden Config: the backup (as-built), intended "
    "(from templates), or compliance (diff) config. Pass the device NAME and kind. Config text is "
    "truncated to fit; ask for a specific kind. Requires the Golden Config app."
)
_CC = "plugins/golden-config/config-compliance/"
_GC = "plugins/golden-config/golden-config/"


async def _config_compliance(app: AppContext, device: str | None = None, location: str | None = None) -> ToolResult:
    gw = app.gateway
    c = Collector()
    t = Trimmer(app.settings.max_items)

    if device:
        d = await app.resolver.one("device", device)
        rows = await gw.list(_CC, {"device": d["id"], "depth": 1}, cap=app.settings.max_items)
        feats = [{"rule": disp(r.get("rule")), "compliant": bool(r.get("compliance")),
                  "missing": bool(r.get("missing")), "extra": bool(r.get("extra"))} for r in rows]
        bad = [f for f in feats if not f["compliant"]]
        data = {"device": d.get("name"), "features_total": len(feats),
                "compliant": len(feats) - len(bad), "non_compliant": t.rows(bad)}
        summary = f"{d.get('name')}: {len(feats) - len(bad)}/{len(feats)} features compliant" + \
                  (f"; failing: {', '.join(f['rule'] for f in bad[:5])}" if bad else " — fully compliant") + "."
        return Response.build(summary, data, scope=f"device:{d.get('name')}", truncated=t.truncated, collector=c)

    # location / org scope: list non-compliant records grouped by device
    params: dict = {"compliance": "false", "depth": 1}
    if location:
        params["device__location"] = location
    rows = await gw.list(_CC, params, cap=app.settings.max_items + 1)
    by_device: dict[str, int] = {}
    for r in rows:
        by_device[disp(r.get("device"))] = by_device.get(disp(r.get("device")), 0) + 1
    ranked = sorted(by_device.items(), key=lambda kv: kv[1], reverse=True)
    scope = f"location:{location}" if location else "org"
    return Response.build(f"{len(rows)} non-compliant feature(s) across {len(by_device)} device(s) [{scope}].",
                          {"scope": scope, "non_compliant_by_device": dict(ranked[:app.settings.max_items])},
                          scope=scope, count=len(rows), truncated=len(rows) > app.settings.max_items, collector=c)


async def _device_config(app: AppContext, device: str,
                         kind: Literal["backup", "intended", "compliance"] = "intended") -> ToolResult:
    gw = app.gateway
    d = await app.resolver.one("device", device)
    rows = await gw.list(_GC, {"device": d["id"]}, cap=1)
    if not rows:
        return Response.build(f"No Golden Config record for '{d.get('name')}'.", {"device": d.get("name")}, scope="golden-config")
    gc = rows[0]
    field = {"backup": "backup_config", "intended": "intended_config", "compliance": "compliance_config"}[kind]
    cfg = gc.get(field) or ""
    limit = app.settings.max_response_chars // 2
    truncated = len(cfg) > limit
    data = {"device": d.get("name"), "kind": kind, "length": len(cfg),
            "last_success": gc.get(f"{kind}_last_success_date"), "config": cfg[:limit]}
    return Response.build(f"{d.get('name')} {kind} config ({len(cfg)} chars{', truncated' if truncated else ''}).",
                          data, scope=f"device:{d.get('name')}", truncated=truncated)


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _config_compliance, name="nautobot_config_compliance",
                  description=_COMPLIANCE_DESC, annotations=ro("Config compliance"))
    register_tool(mcp, _device_config, name="nautobot_device_config",
                  description=_CONFIG_DESC, annotations=ro("Device stored config"))
