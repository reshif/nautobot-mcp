"""Offline fake for the NautobotGateway interface (get/post/list) — the DIP payoff.

Tools + resolver depend on `gateway.get/post/list`, so a fake that maps paths to
canned responses exercises real tool logic with no network. Paths match on the
leading endpoint (before any '?').
"""
from __future__ import annotations

from typing import Any


class FakeGateway:
    def __init__(self, get_map: dict[str, Any] | None = None, list_map: dict[str, Any] | None = None,
                 post_map: dict[str, Any] | None = None) -> None:
        self._get = get_map or {}
        self._list = list_map or {}
        self._post = post_map or {}

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        v = self._get.get(_base(path))
        return v(params) if callable(v) else (v if v is not None else {})

    async def post(self, path: str, json_body: dict[str, Any] | None = None) -> Any:
        v = self._post.get(_base(path))
        return v(json_body) if callable(v) else (v if v is not None else {})

    async def list(self, path: str, params: dict[str, Any] | None = None, cap: int | None = None) -> list:
        v = self._list.get(_base(path))
        rows = v(params) if callable(v) else (v or [])
        return rows[:cap] if cap else rows

    async def count(self, path: str, params: dict[str, Any] | None = None) -> int | None:
        data = await self.get(path, {**(params or {}), "limit": 1})
        if isinstance(data, dict) and "count" in data:
            return data.get("count")
        # fall back to the list map so tests can drive count() from list fixtures
        return len(await self.list(path, params))


def _base(path: str) -> str:
    return path.split("?")[0]
