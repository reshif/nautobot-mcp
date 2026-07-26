"""Core infra tests (offline, no token)."""
from __future__ import annotations

import json

from nautobot_mcp.core.formatting import filters
from nautobot_mcp.core.resolver import Resolver
from nautobot_mcp.core.response import Collector, Response, ToolResult, enforce_budget
from tests.fakes import FakeGateway


def test_filters_drops_none_and_empty_keeps_zero():
    assert filters(("a", "x"), ("b", None), ("c", ""), ("d", 0)) == {"a": "x", "d": 0}


async def test_resolver_lookup_exact_then_fuzzy():
    calls: list[dict] = []

    def racks(params):
        calls.append(params)
        # exact name match returns nothing; fuzzy (name__ic) returns a row
        return [{"id": "r1", "name": "RACK-01"}] if "name__ic" in params else []

    gw = FakeGateway(list_map={"dcim/racks/": racks})
    rows = await Resolver(gw, 120).lookup("dcim/racks/", "rack-01", depth=1)
    assert rows and rows[0]["id"] == "r1"
    assert any("name" in c and "name__ic" not in c for c in calls)  # tried exact first
    assert any("name__ic" in c for c in calls)                       # then fuzzy


async def test_collector_marks_partial():
    c = Collector()

    async def ok():
        return {"x": 1}

    async def boom():
        raise RuntimeError("down")

    assert await c.get("ok", ok()) == {"x": 1}
    assert await c.get("bad", boom()) is None
    assert c.partial and any("bad" in w for w in c.warnings)


def test_response_meta():
    c = Collector()
    c.warnings.append("w")
    r = Response.build("s", {"a": 1}, scope="nautobot", count=2, collector=c)
    assert r.meta.scope == "nautobot" and r.meta.count == 2 and r.meta.partial


def test_enforce_budget_shrinks():
    r = ToolResult(summary="s", data={"rows": [{"i": i, "pad": "x" * 60} for i in range(1000)]})
    enforce_budget(r, max_chars=2000)
    assert len(r.data["rows"]) < 1000 and r.meta.truncated and r.meta.note
    assert len(json.dumps(r.data, default=str)) <= 2000
