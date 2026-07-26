"""Tests for the power/added tools: query, graphql, saved_query, audit, config-context."""
from __future__ import annotations

from types import SimpleNamespace

from nautobot_mcp.core.resolver import Resolver
from nautobot_mcp.tools.audit import _object_changes
from nautobot_mcp.tools.devices import _device_config_context
from nautobot_mcp.tools.graphql import _graphql, _saved_query
from nautobot_mcp.tools.query import _query
from tests.fakes import FakeGateway


def app(gw, max_items=200):
    return SimpleNamespace(gateway=gw, resolver=Resolver(gw, 120), settings=SimpleNamespace(max_items=max_items))


async def test_query_known_type_projects():
    gw = FakeGateway(list_map={"dcim/racks/": [{"id": "r1", "name": "rack-1", "status": {"display": "Active"}}]})
    r = await _query(app(gw), "racks")
    assert r.data["object_type"] == "racks"
    assert r.data["results"][0] == {"id": "r1", "name": "rack-1", "status": "Active"}


async def test_query_unknown_type_lists_choices():
    r = await _query(app(FakeGateway()), "widgets")
    assert r.error is not None and r.error.choices and len(r.error.choices) > 30


async def test_graphql_ok_and_errors():
    gw = FakeGateway(post_map={"graphql/": {"data": {"devices": [{"name": "d1"}]}}})
    r = await _graphql(app(gw), "{ devices { name } }")
    assert r.data["data"]["devices"][0]["name"] == "d1" and "devices" in r.summary

    gw2 = FakeGateway(post_map={"graphql/": {"data": None, "errors": [{"message": "bad field"}]}})
    r2 = await _graphql(app(gw2), "{ nope }")
    assert r2.data["errors"] and "error" in r2.summary.lower()


async def test_saved_query_runs_by_name():
    gw = FakeGateway(
        list_map={"extras/graphql-queries/": [{"id": "q1", "name": "Branches"}]},
        post_map={"extras/graphql-queries/q1/run/": {"data": {"locations": []}}},
    )
    r = await _saved_query(app(gw), "Branches")
    assert "Branches" in r.summary and "locations" in r.data["data"]


async def test_object_changes_filters_and_projects():
    gw = FakeGateway(list_map={"extras/object-changes/": [
        {"time": "t", "action": "update", "user_name": "ops", "changed_object_type": "dcim.device",
         "object_repr": "ams01", "change_context": "web"}]})
    r = await _object_changes(app(gw), object_type="device", user="ops", days=30)
    assert r.data["changes"][0]["object_repr"] == "ams01" and "type=device" in r.data["filters"]


async def test_config_context():
    gw = FakeGateway(
        list_map={"dcim/devices/": [{"id": "d1", "name": "ams01"}]},
        get_map={"dcim/devices/d1/": {"config_context": {"ntp": ["1.2.3.4"], "snmp": {}}}},
    )
    r = await _device_config_context(app(gw), "ams01")
    assert r.data["config_context"]["ntp"] == ["1.2.3.4"] and "ntp" in r.summary
