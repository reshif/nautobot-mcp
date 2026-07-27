"""FastMCP application assembly + lifespan (one shared httpx client → gateway)."""
from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import httpx
from mcp.server.fastmcp import FastMCP

from .completions import register_completions
from .config import Settings, get_settings
from .context import AppContext, clear_process_app, set_process_app
from .core.gateway import NautobotGateway
from .core.observability import configure_logging, get_logger
from .core.resolver import Resolver
from .prompts import register_prompts
from .resources import register_resources
from .tools import register_all

_logger = get_logger(__name__)

_INSTRUCTIONS = (
    "Read-only Nautobot — the network source of truth (DCIM + IPAM). Pass human names "
    "(device, location/site, prefix, IP address, VLAN) to tools; IDs are resolved internally. "
    "Results use {summary, data, meta, error}; meta.partial=true means some data couldn't be "
    "fetched (see meta.warnings); meta.truncated=true means a large result was capped."
)


@contextlib.asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    s = get_settings()
    configure_logging(s.log_level)
    if not s.verify_tls:
        _logger.warning("nautobot_mcp.tls_verification_disabled — connections are not certificate-verified")
    client = httpx.AsyncClient(
        base_url=f"{s.url}/api/",
        headers={"Authorization": f"Token {s.token}", "Accept": "application/json"},
        verify=s.verify_tls,
        timeout=s.request_timeout_seconds,
    )
    _logger.info("nautobot_mcp.startup", extra={"url": s.url, "transport": s.transport})
    async with client:
        gw = NautobotGateway(client, max_concurrent=s.max_concurrent_requests,
                             timeout_seconds=s.request_timeout_seconds, max_retries=s.max_retries)
        app = AppContext(gateway=gw, resolver=Resolver(gw, s.resolver_cache_ttl), settings=s)
        set_process_app(app)
        try:
            yield app
        finally:
            clear_process_app()
            _logger.info("nautobot_mcp.shutdown")


def build_server(settings: Settings | None = None) -> FastMCP:
    s = settings or get_settings()
    mcp = FastMCP(
        "nautobot", instructions=_INSTRUCTIONS, lifespan=lifespan,
        host=s.host, port=s.port, streamable_http_path=s.streamable_http_path,
        json_response=s.json_response, stateless_http=s.stateless_http, log_level=s.log_level,
    )
    register_all(mcp, s)
    register_resources(mcp, s)
    register_prompts(mcp, s)
    register_completions(mcp, s)
    return mcp


def main() -> None:
    s = get_settings()
    configure_logging(s.log_level)
    build_server(s).run(transport=s.transport)
