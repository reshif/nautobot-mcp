# nautobot-mcp

A **read-only, production-shaped** Model Context Protocol server for **Nautobot** —
the network *source of truth* (DCIM + IPAM). Same architecture as the sibling
`meraki-mcp`: one response contract, one lifecycle owner, one API seam, resolution
baked in, response-size budget, read-only by default.

Built on the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) (`FastMCP`)
over Nautobot's REST API via `httpx`.

## Coverage strategy (grounded in the API)
Nautobot's OpenAPI schema (v3.1) has **678 GET operations across ~100 object types**. Wrapping
each as a tool would wreck LLM selection, so coverage is layered:
- **Power tools** (the breadth): `nautobot_graphql` (run a read-only GraphQL query — the ideal way
  to traverse the source of truth in one call), `nautobot_graphql_schema` (introspect root query
  fields / a type's fields so the model writes a *correct* query first), `nautobot_saved_query`
  (run a stored GraphQL query by name), and `nautobot_query` (generic reader over **75** curated
  object types via the uniform REST interface — including plugin apps: golden-config compliance,
  Device Lifecycle CVE/hardware/software, VPN, load-balancers — with `q` search + filter passthrough).
- **Workflow tools** (job-driven, multi-endpoint — the real value): `nautobot_data_quality_audit`
  (SoT hygiene: what's undocumented — missing primary IPs/racks/platforms/software, unassigned IPs),
  `nautobot_site_report` (one-call site picture: devices by role/status + IPAM + racks + gaps),
  `nautobot_device_readiness` (deployment/documentation checklist, GO/NO-GO), `nautobot_rack`
  (elevation + free U), `nautobot_ip_allocate` (next free IP/subnet suggestion).
- **Sharp purpose tools** (the common intents): `nautobot_find`, `nautobot_device`,
  `nautobot_device_interfaces`, `nautobot_device_config_context`, `nautobot_cabling`,
  `nautobot_list_devices`, `nautobot_location`, `nautobot_ip_lookup`,
  `nautobot_prefix` (+ available IPs/prefixes), `nautobot_list_prefixes`, `nautobot_vlans`,
  `nautobot_status_overview`, `nautobot_object_changes` (SoT audit log).
- **Optional (flagged, network-automation apps):** `nautobot_jobs`, `nautobot_circuits`,
  `nautobot_lifecycle_report` (EoX/end-of-support, Device Lifecycle app), and the Golden Config
  layer — `nautobot_config_compliance` (per-device or per-site: which config features are
  compliant vs failing, with missing/extra + remediation) and `nautobot_device_config` (the stored
  backup / intended / compliance config text). Enable with `NAUTOBOT_MCP_ENABLE_OPTIONAL_TOOLS=true`.

**Resources:** `nautobot://locations`, `nautobot://device-roles`, `nautobot://statuses`,
`nautobot://manufacturers`. **Prompts:** `/find`, `/device_report`, `/ip_lookup`, `/site_inventory`.
Every tool + power endpoint was **validated live against demo.nautobot.com**.

## Shape (mirrors meraki-mcp)
- **One contract** — every tool returns `ToolResult{summary, data, meta, error}`; payloads projected to declared fields (nested objects compacted via `ref`), arrays capped.
- **Response-size budget** — the registrar runs `enforce_budget` so no result overflows the agent context (flagged in `meta.truncated`/`meta.note`).
- **One seam** — all REST calls go through `NautobotGateway` (httpx + concurrency limit + timeout + **bounded retry** on transient timeout/502-504 + error normalization + logging); one `_send` owns the HTTP call site.
- **One catalog** — `core/catalog.py` is the single registry of object-type→REST-path knowledge; the generic query tool, the resolver, and the change-audit aliases all derive from it, so adding an object type or plugin app is a one-file edit.
- **Names in, IDs never invented** — the `Resolver` turns "ams01"/"AMS"/"10.0.0.0/24" into objects; ambiguity returns the candidate list.
- **Read-only** — no write tools.

## Run
```bash
uv sync                       # or: pip install -e ".[dev]"
cp .env.example .env          # NAUTOBOT_URL + NAUTOBOT_TOKEN (read-only)
uv run python -m nautobot_mcp # stdio (waits for an MCP client — normal)
# HTTP:  $env:NAUTOBOT_MCP_TRANSPORT="streamable-http"; uv run python -m nautobot_mcp
# Inspector:  uv run mcp dev src/nautobot_mcp/server.py:build_server
```
> Prefer `python -m nautobot_mcp` over the `nautobot-mcp` console script: on locked-down
> Windows, Application Control (Smart App Control / WDAC) can block the generated
> `nautobot-mcp.exe` shim (OS error 4551). `python -m` runs the trusted interpreter directly.

## Test it
1. **Offline gates:** `pytest -q` · lint `ruff check src tests scripts` · types `mypy` (strict-ish: `check_untyped_defs`, clean across all modules).
2. **Live smoke (public demo):** with `NAUTOBOT_URL=https://demo.nautobot.com` and the demo token in `.env`: `python scripts/smoke_test.py` (add a device name, e.g. `python scripts/smoke_test.py ams01-edge-01`).
3. **HTTP / Copilot Studio:** `NAUTOBOT_MCP_TRANSPORT=streamable-http nautobot-mcp` → `http://127.0.0.1:8000/mcp` (or `docker build -t nautobot-mcp . && docker run -p 8000:8000 -e NAUTOBOT_URL=... -e NAUTOBOT_TOKEN=... nautobot-mcp`). No auth yet (OAuth planned) — keep behind a tunnel/gateway.

> **Never commit a real token.** `.env` is git-ignored; `.env.example` holds a placeholder.
# nautobot-mcp
