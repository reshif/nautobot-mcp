"""Tool-logic tests via FakeGateway + real Resolver (offline)."""
from __future__ import annotations

from types import SimpleNamespace

from nautobot_mcp.core.errors import AmbiguousTarget, TargetNotFound
from nautobot_mcp.core.resolver import Resolver
from nautobot_mcp.tools.devices import _device, _list_devices
from nautobot_mcp.tools.find import _find
from nautobot_mcp.tools.ipam import _ip_lookup
from nautobot_mcp.tools.overview import _status_overview
from tests.fakes import FakeGateway


def app(gw, max_items=200):
    return SimpleNamespace(gateway=gw, resolver=Resolver(gw, 120),
                           settings=SimpleNamespace(max_items=max_items))


async def test_device_detail_and_interface_count():
    gw = FakeGateway(
        list_map={"dcim/devices/": [{"id": "d1", "name": "ams01", "display": "ams01",
                                     "role": {"display": "backbone"}, "device_type": {"display": "DCS-7280"},
                                     "location": {"display": "AMS"}, "status": {"display": "Active"},
                                     "primary_ip4": {"display": "10.0.0.1/32"}}]},
        get_map={"dcim/interfaces/": {"count": 47}},
    )
    r = await _device(app(gw), "ams01")
    assert r.data["name"] == "ams01" and r.data["interface_count"] == 47
    assert r.data["role"] == {"display": "backbone"} and "ams01" in r.summary


async def test_resolver_ambiguous_and_missing():
    gw = FakeGateway(list_map={"dcim/devices/": [{"id": "a", "display": "x1"}, {"id": "b", "display": "x2"}]})
    try:
        await Resolver(gw, 60).one("device", "x")
        raise AssertionError("expected ambiguous")
    except AmbiguousTarget as e:
        assert len(e.choices) == 2
    gw2 = FakeGateway(list_map={"dcim/devices/": []})
    try:
        await Resolver(gw2, 60).one("device", "nope")
        raise AssertionError("expected not found")
    except TargetNotFound:
        pass


async def test_ip_lookup_reports_assignment():
    gw = FakeGateway(list_map={
        "ipam/ip-addresses/": [{"id": "ip1", "address": "10.0.0.1/32", "status": {"display": "Active"},
                                "dns_name": "r1", "parent": {"display": "10.0.0.0/24"}}],
        "ipam/ip-address-to-interface/": [{"is_primary": True,
                                           "interface": {"display": "Ethernet1", "device": {"display": "ams01"}}}],
    })
    r = await _ip_lookup(app(gw), "10.0.0.1")
    assert r.data["address"] == "10.0.0.1/32"
    assert r.data["assignments"][0]["device"] == "ams01" and r.data["assignments"][0]["interface"] == "Ethernet1"


async def test_find_multi_type():
    gw = FakeGateway(list_map={
        "dcim/devices/": [{"id": "d1", "display": "ams01", "name": "ams01"}],
        "dcim/locations/": [{"id": "l1", "display": "AMS", "name": "AMS"}],
        "ipam/prefixes/": [], "ipam/ip-addresses/": [], "ipam/vlans/": [],
    })
    r = await _find(app(gw), "am")
    assert r.data["device"][0]["name"] == "ams01" and r.data["location"][0]["name"] == "AMS"


async def test_status_overview_by_location_uses_device_count():
    gw = FakeGateway(list_map={"dcim/locations/": [{"name": "AMS", "device_count": 10},
                                                   {"name": "NYC", "device_count": 3}]})
    r = await _status_overview(app(gw), group_by="location")
    assert r.data["counts"] == {"AMS": 10, "NYC": 3}


async def test_list_devices_filters_projected():
    gw = FakeGateway(list_map={"dcim/devices/": [
        {"id": "d1", "name": "ams01", "role": {"display": "backbone"}, "status": {"display": "Active"},
         "location": {"display": "AMS"}, "device_type": {"display": "X"}}]})
    r = await _list_devices(app(gw), location="AMS", status="Active")
    assert r.data["devices"][0]["name"] == "ams01" and "location=AMS" in r.data["filters"]
