"""Helpers for trimming raw Nautobot payloads to declared shapes."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def disp(obj: Any) -> Any:
    """Human label of a nested value, else the value itself.

    Handles both related objects (depth=1, `display`) and choice fields
    (`{value, label}`, as Nautobot renders enums like interface `type`/`mode`).
    """
    if isinstance(obj, dict):
        return obj.get("display") or obj.get("label") or obj.get("value")
    return obj


def filters(*pairs: tuple[str, Any]) -> dict[str, Any]:
    """Build a query-param dict from (key, value) pairs, dropping None/empty values."""
    return {k: v for k, v in pairs if v is not None and v != ""}


def pick(obj: Any, keys: Iterable[str]) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {}
    return {k: obj[k] for k in keys if k in obj}


def ref(obj: Any, keys: Iterable[str] = ("id", "display", "name")) -> Any:
    """Compact a nested related object (from depth=1) to a small reference."""
    if isinstance(obj, dict):
        return {k: obj[k] for k in keys if k in obj} or obj.get("display")
    return obj


def project(rows: Any, keys: Iterable[str], limit: int | None = None) -> tuple[list[dict[str, Any]], bool]:
    rows = list(rows) if isinstance(rows, list) else []
    truncated = False
    if limit is not None and len(rows) > limit:
        rows, truncated = rows[:limit], True
    return [pick(r, keys) for r in rows], truncated


class Trimmer:
    """Caps arrays to a limit and remembers whether anything was cut."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.truncated = False

    def rows(self, rows: Any, keys: Iterable[str] | None = None) -> list[dict[str, Any]]:
        rows = list(rows) if isinstance(rows, list) else []
        cut = len(rows) > self.limit
        rows = rows[:self.limit]
        self.truncated = self.truncated or cut
        return [pick(r, keys) for r in rows] if keys else rows


def count_by(items: Iterable[dict[str, Any]], key: str) -> dict[Any, int]:
    """Group-count rows by `key`; a nested related value collapses to its display."""
    out: dict[Any, int] = {}
    for it in items:
        v = it.get(key)
        if isinstance(v, dict):
            v = v.get("display") or v.get("name") or v.get("id")
        out[v] = out.get(v, 0) + 1
    return out


__all__ = ["disp", "filters", "pick", "ref", "project", "Trimmer", "count_by"]
