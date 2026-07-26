"""Optional P2 tools: `nautobot_jobs`, `nautobot_circuits` (off by default)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .._shared import AppContext, Response, ToolResult, Trimmer, disp, filters, register_tool, ro

_JOBS_DESC = (
    "Recent Nautobot job results (automation runs): name, status, start/finish, user, and log "
    "counts. Use for 'did the last sync job succeed?' or 'recent automation failures'."
)
_CIRCUITS_DESC = (
    "List circuits (WAN/transit) from the source of truth, optionally filtered by provider or "
    "location. Shows circuit id, provider, type, status, and terminations."
)


async def _jobs(app: AppContext, status: str | None = None, limit: int = 20) -> ToolResult:
    gw = app.gateway
    t = Trimmer(min(limit, app.settings.max_items))
    params: dict = {"depth": 1, "ordering": "-date_created"}
    if status:
        params["status"] = status
    rows = await gw.list("extras/job-results/", params, cap=min(limit, app.settings.max_items) + 1)
    items = [{
        "name": r.get("name"), "status": disp(r.get("status")), "date_created": r.get("date_created"),
        "date_done": r.get("date_done"), "user": disp(r.get("user")),
        "logs": {"error": r.get("error_log_count"), "warning": r.get("warning_log_count"),
                 "success": r.get("success_log_count")},
    } for r in t.rows(rows)]
    return Response.build(f"{len(items)} recent job result(s).", {"jobs": items},
                          scope="jobs", count=len(items), truncated=t.truncated)


async def _circuits(app: AppContext, provider: str | None = None, location: str | None = None,
                    status: str | None = None) -> ToolResult:
    gw = app.gateway
    t = Trimmer(app.settings.max_items)
    params = {"depth": 1, **filters(("provider", provider), ("location", location), ("status", status))}
    rows = await gw.list("circuits/circuits/", params, cap=app.settings.max_items + 1)
    items = [{"cid": r.get("cid"), "provider": disp(r.get("provider")), "type": disp(r.get("circuit_type")),
              "status": disp(r.get("status")), "tenant": disp(r.get("tenant"))} for r in t.rows(rows)]
    return Response.build(f"{len(items)} circuit(s).", {"circuits": items},
                          scope="circuits", count=len(items), truncated=t.truncated)


_LIFECYCLE_DESC = (
    "Hardware/software lifecycle compliance (requires the Device Lifecycle Management app): devices "
    "whose software version is past end-of-support. Optionally scope to a location or a look-ahead "
    "window (days). Use for 'what's past end-of-support / needs upgrading?'."
)


async def _lifecycle_report(app: AppContext, location: str | None = None, days_ahead: int = 0) -> ToolResult:
    from datetime import datetime, timedelta, timezone
    gw = app.gateway
    t = Trimmer(app.settings.max_items)
    cutoff = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    params: dict = {"nautobot_device_lifecycle_mgmt_software_version_end_of_support_date__lt": cutoff, "depth": 1}
    if location:
        params["location"] = location
    rows = await gw.list("dcim/devices/", params, cap=app.settings.max_items + 1)
    items = [{"name": r.get("name"), "software_version": disp(r.get("software_version")),
              "location": disp(r.get("location")), "role": disp(r.get("role"))} for r in t.rows(rows)]
    scope = f"location:{location}" if location else "org"
    return Response.build(f"{len(items)} device(s) past software end-of-support (as of {cutoff}) [{scope}].",
                          {"cutoff": cutoff, "devices": items}, scope=scope, count=len(items), truncated=t.truncated)


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _jobs, name="nautobot_jobs", description=_JOBS_DESC, annotations=ro("Job results"))
    register_tool(mcp, _circuits, name="nautobot_circuits", description=_CIRCUITS_DESC, annotations=ro("Circuits"))
    register_tool(mcp, _lifecycle_report, name="nautobot_lifecycle_report", description=_LIFECYCLE_DESC, annotations=ro("Lifecycle / EoX report"))
