"""End-to-end tests through the real MCP layer (in-memory client<->server session).

Unlike the handler tests, these exercise registration, schema generation, annotations,
serialization, resources, and prompts exactly as a client sees them — the only coverage
of the signature-surgery registrar at the protocol boundary.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from nautobot_mcp.completions import register_completions
from nautobot_mcp.config import Settings
from nautobot_mcp.context import AppContext, clear_process_app, set_process_app
from nautobot_mcp.core.resolver import Resolver
from nautobot_mcp.prompts import register_prompts
from nautobot_mcp.resources import register_resources
from nautobot_mcp.tools import register_all
from tests.fakes import FakeGateway

_DEVICE_ROWS = [{"id": "d1", "name": "ams01-edge-01", "status": {"display": "Active"},
                 "role": {"display": "edge"}, "location": {"display": "AMS01"}}]


def _settings(**over) -> Settings:
    os.environ.setdefault("NAUTOBOT_URL", "https://demo.example.com")
    os.environ.setdefault("NAUTOBOT_TOKEN", "x" * 40)
    return Settings(**over)  # type: ignore[call-arg]


def _server(gw: FakeGateway, settings: Settings) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_server: FastMCP):
        app = AppContext(gateway=gw, resolver=Resolver(gw, 120), settings=settings)
        set_process_app(app)
        try:
            yield app
        finally:
            clear_process_app()

    mcp = FastMCP("nautobot-test", lifespan=lifespan)
    register_all(mcp, settings)
    register_resources(mcp, settings)
    register_prompts(mcp, settings)
    register_completions(mcp, settings)
    return mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_list_tools_exposes_described_schemas_and_readonly_annotations():
    mcp = _server(FakeGateway(), _settings())
    async with create_connected_server_and_client_session(mcp, raise_exceptions=True) as session:
        resp = await session.list_tools()
        tools = {t.name: t for t in resp.tools}
        assert "nautobot_device" in tools and "nautobot_query" in tools

        dev = tools["nautobot_device"]
        # every parameter is described, and read-only/idempotent annotations are advertised
        assert dev.inputSchema["properties"]["device"]["description"]
        assert dev.annotations and dev.annotations.readOnlyHint is True
        assert dev.annotations.idempotentHint is True
        # returning a Pydantic ToolResult yields a structured output schema
        assert dev.outputSchema and dev.outputSchema.get("type") == "object"

        # closed sets surface as enums the model can't get wrong
        assert set(tools["nautobot_status_overview"].inputSchema["properties"]["group_by"]["enum"]) == {
            "status", "role", "location"}

        # injected params (progress) must never leak into a tool's public schema
        sr = tools["nautobot_site_report"].inputSchema["properties"]
        assert "progress" not in sr and "location" in sr


async def test_call_tool_returns_structured_content():
    gw = FakeGateway(list_map={"dcim/devices/": _DEVICE_ROWS})
    mcp = _server(gw, _settings())
    async with create_connected_server_and_client_session(mcp, raise_exceptions=True) as session:
        result = await session.call_tool("nautobot_query", {"object_type": "devices"})
        assert result.isError is False
        assert result.structuredContent is not None
        assert result.structuredContent["data"]["object_type"] == "devices"
        assert result.structuredContent["summary"].endswith("devices.")
        assert result.structuredContent["meta"]["count"] == 1


async def test_call_tool_unknown_object_type_self_corrects():
    mcp = _server(FakeGateway(), _settings())
    async with create_connected_server_and_client_session(mcp, raise_exceptions=True) as session:
        result = await session.call_tool("nautobot_query", {"object_type": "nope"})
        sc = result.structuredContent
        # not-found is a self-correction signal, NOT a tool failure -> isError stays false
        assert result.isError is False
        assert sc["error"]["kind"] == "target_not_found"
        assert sc["error"]["choices"], "should return the valid object types to choose from"


async def test_ambiguous_name_returns_choices_not_elicitation():
    # Design decision: ambiguity is resolved by returning candidate choices (works for every
    # client and lets an LLM agent self-correct) rather than an elicitation round-trip.
    two = [{"id": "d1", "display": "ams01-edge-01"}, {"id": "d2", "display": "ams01-edge-02"}]
    mcp = _server(FakeGateway(list_map={"dcim/devices/": two}), _settings())
    async with create_connected_server_and_client_session(mcp, raise_exceptions=True) as session:
        result = await session.call_tool("nautobot_device", {"device": "ams01-edge"})
        assert result.isError is False  # not a failure — a disambiguation prompt
        err = result.structuredContent["error"]
        assert err["kind"] == "ambiguous_target"
        assert {c["display"] for c in err["choices"]} == {"ams01-edge-01", "ams01-edge-02"}


async def test_call_tool_api_error_sets_iserror_but_keeps_structured_error():
    from nautobot_mcp.core.errors import NautobotApiError

    def boom(_params):
        raise NautobotApiError("GET dcim/devices/", 500, "boom")

    mcp = _server(FakeGateway(list_map={"dcim/devices/": boom}), _settings())
    async with create_connected_server_and_client_session(mcp, raise_exceptions=True) as session:
        result = await session.call_tool("nautobot_query", {"object_type": "devices"})
        # genuine execution failure -> protocol isError flag set...
        assert result.isError is True
        # ...and the structured error is still there for the LLM to read
        assert result.structuredContent["error"]["kind"] == "api_error"


async def test_resources_and_prompts_registered_with_titles():
    gw = FakeGateway(list_map={"dcim/locations/": [{"id": "l1", "name": "AMS01", "device_count": 3}]})
    mcp = _server(gw, _settings())
    async with create_connected_server_and_client_session(mcp, raise_exceptions=True) as session:
        resources = {str(r.uri): r for r in (await session.list_resources()).resources}
        assert "nautobot://locations" in resources

        prompts = {p.name: p for p in (await session.list_prompts()).prompts}
        assert "site_inventory" in prompts and prompts["site_inventory"].title

        read = await session.read_resource("nautobot://locations")  # type: ignore[arg-type]
        assert "AMS01" in read.contents[0].text


async def test_prompt_argument_completion_suggests_real_values():
    from mcp.types import PromptReference
    gw = FakeGateway(list_map={"dcim/locations/": [
        {"id": "l1", "name": "AMS01"}, {"id": "l2", "name": "AMS02"}, {"id": "l3", "name": "LON01"}]})
    mcp = _server(gw, _settings())
    async with create_connected_server_and_client_session(mcp, raise_exceptions=True) as session:
        result = await session.complete(
            ref=PromptReference(type="ref/prompt", name="site_inventory"),
            argument={"name": "location", "value": "AMS"},
        )
        assert set(result.completion.values) == {"AMS01", "AMS02"}  # filtered by the partial value
