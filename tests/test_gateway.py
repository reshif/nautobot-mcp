"""Gateway seam tests: retry-on-transient, bare-list tolerance, count(), error mapping."""
from __future__ import annotations

import httpx
import pytest

from nautobot_mcp.core.catalog import PATHS, RESOLVABLE
from nautobot_mcp.core.errors import NautobotApiError, NautobotTimeoutError
from nautobot_mcp.core.gateway import NautobotGateway


def _gw(handler, **kw) -> NautobotGateway:
    client = httpx.AsyncClient(base_url="http://nb/api/", transport=httpx.MockTransport(handler))
    return NautobotGateway(client, max_retries=kw.get("max_retries", 2), timeout_seconds=5)


async def test_get_retries_transient_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"detail": "unavailable"})
        return httpx.Response(200, json={"ok": True})

    gw = _gw(handler)
    gw._backoff = _noop_backoff(gw)  # skip real sleeps
    data = await gw.get("dcim/devices/")
    assert data == {"ok": True} and calls["n"] == 3


async def test_get_gives_up_after_retries_and_normalizes():
    def handler(_req):
        return httpx.Response(502, json={"detail": "bad gateway"})

    gw = _gw(handler, max_retries=1)
    gw._backoff = _noop_backoff(gw)
    with pytest.raises(NautobotApiError) as ei:
        await gw.get("dcim/devices/")
    assert ei.value.status == 502


async def test_non_retryable_4xx_raises_immediately():
    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        return httpx.Response(404, json={"detail": "nope"})

    gw = _gw(handler)
    with pytest.raises(NautobotApiError):
        await gw.get("dcim/devices/x/")
    assert calls["n"] == 1  # 404 is not retried


async def test_timeout_is_retried_then_normalized():
    def handler(_req):
        raise httpx.TimeoutException("slow")

    gw = _gw(handler, max_retries=1)
    gw._backoff = _noop_backoff(gw)
    with pytest.raises(NautobotTimeoutError):
        await gw.get("dcim/devices/")


async def test_list_tolerates_bare_list_response():
    def handler(_req):
        return httpx.Response(200, json=[{"address": "10.0.0.1/24"}, {"address": "10.0.0.2/24"}])

    gw = _gw(handler)
    rows = await gw.list("ipam/prefixes/1/available-ips/")
    assert [r["address"] for r in rows] == ["10.0.0.1/24", "10.0.0.2/24"]


async def test_count_reads_envelope_count():
    def handler(_req):
        return httpx.Response(200, json={"count": 42, "results": []})

    gw = _gw(handler)
    assert await gw.count("dcim/devices/", {"status": "Active"}) == 42


def test_catalog_is_single_source_of_truth():
    from nautobot_mcp.tools.query import OBJECT_TYPES
    assert OBJECT_TYPES is PATHS
    assert all(path in PATHS.values() for path, _ in RESOLVABLE.values())


def _noop_backoff(gw):
    async def _b(*_a, **_k):
        return None
    return _b
