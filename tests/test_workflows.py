"""Tests for the workflow tools (data-quality audit, readiness, site report, rack, allocate)."""
from __future__ import annotations

from types import SimpleNamespace

from nautobot_mcp.core.resolver import Resolver
from nautobot_mcp.tools.workflows import (
    _data_quality_audit,
    _device_readiness,
    _ip_allocate,
    _rack,
    _site_report,
    _vlan_allocate,
)
from tests.fakes import FakeGateway


def app(gw, max_items=200):
    return SimpleNamespace(gateway=gw, resolver=Resolver(gw, 120), settings=SimpleNamespace(max_items=max_items))


async def test_data_quality_audit_aggregates_counts():
    def counts(params):
        return {"count": 3}  # every check returns 3

    gw = FakeGateway(get_map={"dcim/devices/": counts, "ipam/prefixes/": counts, "ipam/ip-addresses/": counts})
    r = await _data_quality_audit(app(gw))
    assert set(r.data["findings"]) == {
        "devices_missing_primary_ip", "devices_without_rack", "devices_without_platform",
        "devices_without_software_version", "prefixes_without_role", "ip_addresses_unassigned"}
    assert all(v == 3 for v in r.data["findings"].values())
    assert r.data["ranked"][0] in r.data["findings"]


async def test_data_quality_audit_reports_progress_per_check():
    from nautobot_mcp.core.progress import Progress

    class Recorder(Progress):
        def __init__(self):
            super().__init__(None)
            self.steps: list[str] = []
            self.total = None

        def start(self, total):
            self.total = total

        async def step(self, message, *, advance=1.0):
            self.steps.append(message)

    gw = FakeGateway(get_map={"dcim/devices/": lambda p: {"count": 1},
                              "ipam/prefixes/": lambda p: {"count": 1},
                              "ipam/ip-addresses/": lambda p: {"count": 1}})
    rec = Recorder()
    await _data_quality_audit(app(gw), progress=rec)
    assert rec.total == 6 and len(rec.steps) == 6  # one step per check, total set upfront


async def test_vlan_allocate_suggests_next_free_vid():
    gw = FakeGateway(list_map={"ipam/vlans/": [{"vid": 1}, {"vid": 2}, {"vid": 3}]})
    r = await _vlan_allocate(app(gw), vlan_group="core", count=2)
    assert r.data["suggested_vids"] == [4, 5] and r.data["used_count"] == 3


async def test_vlan_allocate_requires_scope():
    r = await _vlan_allocate(app(FakeGateway()))
    assert r.error is not None and r.error.kind.value == "invalid_input"


async def test_device_readiness_flags_missing_fields():
    dev = {"id": "d1", "name": "ams01", "role": {"display": "backbone"}, "device_type": {"display": "X"},
           "location": {"display": "AMS"}, "status": {"display": "Active"}, "serial": "ABC",
           "primary_ip4": {"display": "10.0.0.1/32"}}  # missing platform, rack, software_version
    gw = FakeGateway(
        list_map={"dcim/devices/": [dev], "extras/object-changes/": []},
        get_map={"dcim/interfaces/": {"count": 12}},
    )
    r = await _device_readiness(app(gw), "ams01")
    assert r.data["ready"] is False
    failed = {c["name"] for c in r.data["checks"] if not c["pass"]}
    assert "Platform set" in failed and "Software version" in failed and "Rack + position" in failed
    assert "Role set" not in failed  # role is present


async def test_site_report_groups_devices():
    gw = FakeGateway(
        list_map={
            "dcim/devices/": [{"name": "d1", "role": {"display": "access"}, "status": {"display": "Active"}},
                              {"name": "d2", "role": {"display": "access"}, "status": {"display": "Planned"}}],
            "ipam/prefixes/": [{"prefix": "10.0.0.0/24"}], "ipam/vlans/": [{"vid": 10, "name": "v10"}],
            "dcim/racks/": [{"name": "R1"}],
        },
        get_map={"dcim/devices/": {"count": 1}, "dcim/locations/": {}},
    )
    # locations resolve: resolver.one('location') -> list dcim/locations/
    gw._list["dcim/locations/"] = [{"id": "l1", "name": "AMS01", "device_count": 2, "prefix_count": 1, "vlan_count": 1, "rack_count": 1}]
    r = await _site_report(app(gw), "AMS01")
    assert r.data["devices_by_role"] == {"access": 2}
    assert r.data["devices_by_status"] == {"Active": 1, "Planned": 1}
    assert r.data["racks"] == ["R1"]


async def test_ip_allocate_suggests_free_space():
    gw = FakeGateway(
        list_map={"ipam/prefixes/": [{"id": "p1", "prefix": "10.0.0.0/24", "namespace": {"display": "Global"}}]},
        get_map={"ipam/prefixes/p1/available-ips/": [{"address": "10.0.0.1/24"}, {"address": "10.0.0.2/24"}],
                 "ipam/prefixes/p1/available-prefixes/": [{"prefix": "10.0.0.0/25"}]},
    )
    r = await _ip_allocate(app(gw), "10.0.0.0/24", count=2)
    assert r.data["suggested_ips"] == ["10.0.0.1/24", "10.0.0.2/24"]
    assert r.data["available_prefix_blocks"] == ["10.0.0.0/25"]


async def test_rack_elevation_capacity():
    gw = FakeGateway(
        list_map={"dcim/racks/": [{"id": "r1", "name": "R1", "u_height": 4, "location": {"display": "AMS"}}]},
        get_map={"dcim/racks/r1/elevation/": [
            {"name": "U1", "occupied": True, "device": {"display": "sw1"}, "face": "front"},
            {"name": "U2", "occupied": False}, {"name": "U3", "occupied": False}, {"name": "U4", "occupied": False}]},
    )
    r = await _rack(app(gw), "R1")
    assert r.data["units_total"] == 4 and r.data["units_occupied"] == 1 and r.data["units_free"] == 3
    assert r.data["mounted"][0]["device"] == "sw1"
