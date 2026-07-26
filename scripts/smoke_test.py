"""Live smoke test against a real Nautobot (validates field parsing).

    cd nautobot-mcp && pip install -e ".[dev]"
    # .env: NAUTOBOT_URL=https://demo.nautobot.com  NAUTOBOT_TOKEN=<demo token>
    python scripts/smoke_test.py                 # find/status/locations checks
    python scripts/smoke_test.py ams01-edge-01   # also device + interfaces + cabling
"""
from __future__ import annotations

import asyncio
import sys

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252

from nautobot_mcp.config import get_settings
from nautobot_mcp.context import AppContext
from nautobot_mcp.core.gateway import NautobotGateway
from nautobot_mcp.core.resolver import Resolver
from nautobot_mcp.tools.cabling import _cabling
from nautobot_mcp.tools.devices import _device, _device_interfaces
from nautobot_mcp.tools.find import _find
from nautobot_mcp.tools.ipam import _list_prefixes
from nautobot_mcp.tools.overview import _status_overview


async def show(label: str, coro) -> None:
    print(f"\n### {label}")
    try:
        r = await coro
    except Exception as exc:  # pure handlers raise GatewayError; the server would wrap it
        print(f"  RAISED {type(exc).__name__}: {exc}")
        return
    print(f"  {r.summary}")
    flags = []
    if r.error:
        flags.append(f"ERROR:{r.error.kind.value}")
    if r.meta.partial:
        flags.append(f"partial:{r.meta.warnings}")
    if flags:
        print(f"  flags: {' '.join(flags)}")


async def main(device: str | None) -> None:
    s = get_settings()
    print(f"Nautobot: {s.url}")
    client = httpx.AsyncClient(base_url=f"{s.url}/api/",
                               headers={"Authorization": f"Token {s.token}", "Accept": "application/json"},
                               verify=s.verify_tls, timeout=s.request_timeout_seconds)
    async with client:
        gw = NautobotGateway(client, max_concurrent=s.max_concurrent_requests, timeout_seconds=s.request_timeout_seconds)
        app = AppContext(gateway=gw, resolver=Resolver(gw, s.resolver_cache_ttl), settings=s)
        await show("find('edge')", _find(app, "edge"))
        await show("status_overview(status)", _status_overview(app, group_by="status"))
        await show("status_overview(location)", _status_overview(app, group_by="location"))
        await show("list_prefixes", _list_prefixes(app))
        if device:
            await show(f"device('{device}')", _device(app, device))
            await show(f"device_interfaces('{device}')", _device_interfaces(app, device))
            await show(f"cabling('{device}')", _cabling(app, device))
    print("\nDone. 'flags: ERROR/partial' above points at a field-shape/permission issue.")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
