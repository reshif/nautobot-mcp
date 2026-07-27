"""Reusable Annotated parameter types carrying LLM-facing descriptions.

One home for the parameter docs that repeat across tools (device, location, role,
status, …) so the generated input schemas describe every argument consistently.
Tool-specific parameters keep an inline `Annotated[T, Field(description=...)]`.
Requires the registrar to resolve hints with `include_extras=True`.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

# --- required identifiers (resolved name -> object; ambiguous -> candidate choices) ---
Device = Annotated[str, Field(description=(
    "Device NAME (not an ID), e.g. 'ams01-edge-01'. Resolved to an object; an ambiguous "
    "name returns candidate matches to choose from."))]
Location = Annotated[str, Field(description="Location/site NAME, e.g. 'AMS01' or 'AMS' (fuzzy).")]

# --- common optional filters (by NAME; None = don't filter) ---
OptLocation = Annotated[str | None, Field(description="Filter by location/site NAME, e.g. 'AMS01'.")]
OptRole = Annotated[str | None, Field(description="Filter by role NAME, e.g. 'edge', 'leaf', 'spine'.")]
OptStatus = Annotated[str | None, Field(description="Filter by status NAME, e.g. 'Active', 'Offline'.")]
OptTenant = Annotated[str | None, Field(description="Filter by tenant NAME.")]

# --- paging ---
OptLimit = Annotated[int | None, Field(description="Maximum rows to return (capped by the server's max_items).", ge=1)]
OptOffset = Annotated[int, Field(description="Row offset for pagination; use the `next_offset` from a truncated result to fetch the next page.", ge=0)]
