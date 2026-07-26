"""Turn human strings (device / location / prefix / IP / VLAN names) into objects.

Nautobot list endpoints are filterable (`name`, `name__ic`, `address`, `prefix`),
so resolution is a targeted query — no need to cache the whole (large) inventory.
Small reference lists (locations, roles, statuses) are cached for resources.
Ambiguity returns the candidate list (self-correcting), like the Meraki design.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal

from .catalog import RESOLVABLE as _KINDS
from .errors import AmbiguousTarget, TargetNotFound

if TYPE_CHECKING:
    from .gateway import NautobotGateway

Kind = Literal["device", "location", "vlan", "prefix", "ip"]


class _TTLCache:
    def __init__(self, ttl: int) -> None:
        self._ttl = ttl
        self._value: Any = None
        self._at = 0.0
        self._lock = asyncio.Lock()

    async def get(self, loader: Callable[[], Awaitable[Any]]) -> Any:
        async with self._lock:
            now = time.monotonic()
            if self._value is None or (now - self._at) > self._ttl:
                self._value = await loader()
                self._at = now
            return self._value


class Resolver:
    def __init__(self, gateway: NautobotGateway, ttl: int = 120) -> None:
        self._gw = gateway
        self._ttl = ttl
        self._ref: dict[str, _TTLCache] = {}

    async def lookup(self, path: str, query: str, *, field: str = "name", fuzzy: bool = True,
                     depth: int = 0, cap: int = 25) -> list[dict[str, Any]]:
        """Exact match on `field`; if none (and `fuzzy`), fall back to `{field}__ic`.

        Returns the rows (possibly empty). The one place the exact→fuzzy pattern
        lives, so any endpoint (racks, saved queries, …) can reuse it.
        """
        rows = await self._gw.list(path, {field: query, "depth": depth}, cap=cap)
        if not rows and fuzzy:
            rows = await self._gw.list(path, {f"{field}__ic": query, "depth": depth}, cap=cap)
        return rows

    async def one(self, kind: Kind, query: str, depth: int = 0) -> dict[str, Any]:
        """Resolve a name/value to exactly one object (raises on none/ambiguous)."""
        path, field = _KINDS[kind]
        rows = await self.lookup(path, query, field=field, fuzzy=(field == "name"), depth=depth)
        if not rows:
            raise TargetNotFound(f"No {kind} matched '{query}'.")
        if len(rows) > 1:
            raise AmbiguousTarget(
                f"'{query}' matched {len(rows)} {kind}s.",
                [{"id": r.get("id"), "display": r.get("display")} for r in rows[:25]],
            )
        return rows[0]

    async def id(self, kind: Kind, query: str) -> str:
        return (await self.one(kind, query))["id"]

    async def search(self, query: str, kinds: list[Kind], per_kind: int = 10) -> dict[str, list[dict[str, Any]]]:
        """Fuzzy multi-type search for the `find` tool.

        IP/prefix endpoints 500 on an unparseable address, so they're only
        queried when the input looks like an IP/CIDR. Each kind is isolated:
        one type failing never sinks the whole search.
        """
        out: dict[str, list[dict[str, Any]]] = {}
        ipish = ("." in query) or (":" in query)
        for kind in kinds:
            if kind in ("ip", "prefix") and not ipish:
                continue
            path, field = _KINDS[kind]
            flt = {"name__ic": query} if field == "name" else {field: query}
            try:
                out[kind] = await self._gw.list(path, flt, cap=per_kind)
            except Exception:  # noqa: BLE001 — one type's failure shouldn't sink find
                out[kind] = []
        return out

    async def reference(self, path: str, cap: int = 500) -> list[dict[str, Any]]:
        cache = self._ref.setdefault(path, _TTLCache(self._ttl))
        return await cache.get(lambda: self._gw.list(path, {"depth": 0}, cap=cap))
