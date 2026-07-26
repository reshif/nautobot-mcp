"""Per-process application context shared with every tool call."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context

if TYPE_CHECKING:
    from .config import Settings
    from .core.gateway import NautobotGateway
    from .core.resolver import Resolver


@dataclass(slots=True)
class AppContext:
    gateway: NautobotGateway
    resolver: Resolver
    settings: Settings


def get_app(ctx: Context) -> AppContext:
    """The DI path used by tools."""
    return ctx.request_context.lifespan_context


# --- process-scoped holder (resources can't receive a Context in this FastMCP version) ---
_process_app: AppContext | None = None


def set_process_app(app: AppContext) -> None:
    global _process_app
    _process_app = app


def clear_process_app() -> None:
    global _process_app
    _process_app = None


def process_app() -> AppContext:
    if _process_app is None:
        raise RuntimeError("AppContext not initialized (server lifespan not started).")
    return _process_app
