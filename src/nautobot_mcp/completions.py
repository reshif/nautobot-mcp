"""Argument completion for prompt parameters.

Lets a client autocomplete real Nautobot values as the user fills a prompt argument:
`location` → cached site names; `device` → live name-prefix search. Backed by the
process-scoped AppContext (completion handlers, like resources, don't receive Context).
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import Completion, CompletionArgument, PromptReference

from .config import Settings
from .context import process_app
from .core.observability import get_logger

_logger = get_logger(__name__)
_MAX = 25  # spec allows up to 100; keep suggestion lists tight


async def _location_values(value: str) -> list[str]:
    rows = await process_app().resolver.reference("dcim/locations/", cap=1000)
    names: list[str] = [str(r["name"]) for r in rows if r.get("name")]
    return [n for n in names if not value or value.lower() in n.lower()]


async def _device_values(value: str) -> list[str]:
    params = {"name__ic": value} if value else {}
    rows = await process_app().gateway.list("dcim/devices/", params, cap=_MAX)
    return [str(r["name"]) for r in rows if r.get("name")]


# prompt-argument name -> value provider
_PROVIDERS = {"location": _location_values, "device": _device_values}


def register_completions(mcp: FastMCP, _settings: Settings) -> None:
    @mcp.completion()
    async def complete(ref, argument: CompletionArgument, context):  # noqa: ANN001 — SDK-typed callback
        if not isinstance(ref, PromptReference):
            return None
        provider = _PROVIDERS.get(argument.name)
        if provider is None:
            return None
        try:
            values = (await provider(argument.value or ""))[:_MAX]
        except Exception:  # noqa: BLE001 — completion is best-effort; never surface an error to the client
            _logger.debug("completion.failed", extra={"argument": argument.name})
            return None
        return Completion(values=values, total=len(values), hasMore=False)
