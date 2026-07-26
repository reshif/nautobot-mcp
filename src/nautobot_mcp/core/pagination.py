"""Pagination policy for Nautobot's limit/offset + `next` list responses."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

PAGE_LIMIT = 50  # per-request page size when walking a list endpoint


def cap(items: Sequence[Any], limit: int) -> tuple[list[Any], bool]:
    items = list(items)
    return items[:limit], len(items) > limit
