"""Tests for the app/power tools: graphql schema, generic plugin query, golden-config."""
from __future__ import annotations

from types import SimpleNamespace

from nautobot_mcp.core.resolver import Resolver
from nautobot_mcp.tools.graphql import _graphql_schema
from nautobot_mcp.tools.optional.golden_config import _config_compliance, _device_config
from nautobot_mcp.tools.query import OBJECT_TYPES
from tests.fakes import FakeGateway


def app(gw, max_items=200):
    return SimpleNamespace(gateway=gw, resolver=Resolver(gw, 120),
                           settings=SimpleNamespace(max_items=max_items, max_response_chars=60000))


def test_query_object_types_include_plugin_apps():
    # coverage assertion: the generic tool reaches the app surfaces.
    for k in ("config-compliance", "cves", "hardware-notices", "vpns", "virtual-servers"):
        assert k in OBJECT_TYPES and OBJECT_TYPES[k].endswith("/")


async def test_graphql_schema_root_and_type():
    gw = FakeGateway(post_map={"graphql/": lambda body: (
        {"data": {"__schema": {"queryType": {"fields": [{"name": "devices"}, {"name": "prefixes"}]}}}}
        if "__schema" in body["query"] else
        {"data": {"__type": {"name": "DeviceType", "fields": [{"name": "name", "type": {"name": "String"}}]}}})})
    r = await _graphql_schema(app(gw))
    assert r.data["query_fields"] == ["devices", "prefixes"]
    r2 = await _graphql_schema(app(gw), "DeviceType")
    assert r2.data["fields"][0]["name"] == "name"


async def test_config_compliance_device_summarizes():
    gw = FakeGateway(
        list_map={"dcim/devices/": [{"id": "d1", "name": "jcy-bb-01"}],
                  "plugins/golden-config/config-compliance/": [
                      {"rule": {"display": "dns"}, "compliance": False, "missing": True},
                      {"rule": {"display": "aaa"}, "compliance": True}]})
    r = await _config_compliance(app(gw), device="jcy-bb-01")
    assert r.data["features_total"] == 2 and r.data["compliant"] == 1
    assert r.data["non_compliant"][0]["rule"] == "dns"


async def test_device_config_truncates_large():
    big = "line\n" * 50000  # ~250k chars
    gw = FakeGateway(
        list_map={"dcim/devices/": [{"id": "d1", "name": "jcy-bb-01"}],
                  "plugins/golden-config/golden-config/": [{"backup_config": big, "intended_config": "short"}]})
    r = await _device_config(app(gw), "jcy-bb-01", "backup")
    assert r.data["length"] == len(big) and r.meta.truncated is True
    assert len(r.data["config"]) <= app(gw).settings.max_response_chars // 2
