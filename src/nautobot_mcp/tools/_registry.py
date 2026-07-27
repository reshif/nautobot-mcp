"""The single tool lifecycle owner (identical pattern to the Meraki server).

Every tool is a pure `async def _x(app, ...) -> ToolResult`. This adapts it into
an MCP tool once: ctx->app, whole-tool timeout, exception->ToolResult (never
raised across MCP), response-size budget, meta.elapsed_ms, one structured log.
Registration is one line: register_tool(mcp, _x, name=..., description=..., annotations=...).
"""
from __future__ import annotations

import asyncio
import inspect
import time
import typing
from collections.abc import Awaitable, Callable
from inspect import Parameter, Signature
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from ..context import get_app
from ..core.errors import GatewayError, NautobotValidationError, ResolutionError
from ..core.observability import get_logger
from ..core.progress import Progress
from ..core.response import ErrorKind, Response, ToolResult, enforce_budget

# handler params the registrar injects rather than exposing in the tool schema
_INJECTED = ("progress",)

# Genuine execution failures — flag these with the protocol's isError so any client
# (not just LLMs reading our structured error) knows the call failed. Ambiguous/
# not-found are NOT failures: the tool ran and is guiding the caller to refine input.
_HARD_ERRORS = frozenset({ErrorKind.TIMEOUT, ErrorKind.API_ERROR, ErrorKind.UNEXPECTED})

_logger = get_logger("nautobot_mcp.tools")
Handler = Callable[..., Awaitable[ToolResult]]
# the adapted MCP tool may also return CallToolResult (hard errors carry the isError flag)
Wrapped = Callable[..., Awaitable["ToolResult | CallToolResult"]]


def register_tool(mcp: FastMCP, handler: Handler, *, name: str, description: str, annotations: ToolAnnotations) -> None:
    mcp.add_tool(_adapt(handler, name), name=name, description=description, annotations=annotations)


def _adapt(handler: Handler, name: str) -> Wrapped:
    tool_params = _tool_params(handler, name)
    wants_progress = "progress" in inspect.signature(handler).parameters

    async def wrapper(ctx: Context, **kwargs: Any) -> ToolResult | CallToolResult:
        app = get_app(ctx)
        if wants_progress:
            kwargs["progress"] = Progress(ctx)
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(handler(app, **kwargs), timeout=app.settings.tool_timeout_seconds)
        except ResolutionError as exc:
            return _fail(name, started, exc.kind, exc.message, choices=exc.choices,
                         summary=exc.message + (" Ask the user which one they mean." if exc.choices else ""))
        except asyncio.TimeoutError:
            msg = f"{name} timed out after {app.settings.tool_timeout_seconds:.0f}s."
            return _fail(name, started, ErrorKind.TIMEOUT, msg)
        except NautobotValidationError as exc:
            choices = [{"field": k, "error": v} for k, v in exc.fields.items()] or None
            return _fail(name, started, exc.kind, exc.message, operation=exc.operation, choices=choices,
                         summary=f"Invalid request — {exc.message}. Fix the field(s) and retry.")
        except GatewayError as exc:
            return _fail(name, started, exc.kind, exc.message, operation=exc.operation,
                         summary=f"Nautobot API error — {exc.message}")
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            _logger.exception("tool.unexpected_error", extra={"tool": name})
            return _fail(name, started, ErrorKind.UNEXPECTED, f"{type(exc).__name__}: {exc}",
                         summary=f"Unexpected error in {name} — {type(exc).__name__}: {exc}", level="error")
        else:
            enforce_budget(result, app.settings.max_response_chars)
            result.meta.elapsed_ms = _elapsed(started)
            _log(name, result.meta.elapsed_ms, "ok", "info")
            return result

    ctx_param = Parameter("ctx", Parameter.POSITIONAL_OR_KEYWORD, annotation=Context)
    wrapper.__signature__ = Signature([ctx_param, *tool_params], return_annotation=ToolResult)  # type: ignore[attr-defined]
    wrapper.__name__ = name
    wrapper.__doc__ = handler.__doc__
    ann = {p.name: p.annotation for p in tool_params if p.annotation is not Parameter.empty}
    ann["ctx"] = Context
    ann["return"] = ToolResult
    wrapper.__annotations__ = ann
    return wrapper


def _tool_params(handler: Handler, name: str) -> list[Parameter]:
    params = list(inspect.signature(handler).parameters.values())
    if not params or params[0].name != "app":
        raise TypeError(f"{name}: handler must take (app: AppContext, ...) first")
    # include_extras=True keeps Annotated[..., Field(description=...)] metadata so per-parameter
    # descriptions reach the generated input schema (without it, __future__ string hints are stripped).
    hints = typing.get_type_hints(handler, include_extras=True)
    return [p.replace(annotation=hints.get(p.name, p.annotation))
            for p in params[1:] if p.name not in _INJECTED]


def _fail(name: str, started: float, kind: ErrorKind, message: str, *, operation: str | None = None,
          choices: list[dict[str, Any]] | None = None, summary: str | None = None,
          level: str = "warning") -> ToolResult | CallToolResult:
    result = Response.error(kind, message, operation=operation, choices=choices, summary=summary)
    result.meta.elapsed_ms = _elapsed(started)
    _log(name, result.meta.elapsed_ms, f"error:{kind.value}", level, operation=operation)
    if kind in _HARD_ERRORS:
        # keep the structured error (validated against outputSchema) AND raise the isError flag
        return CallToolResult(
            content=[TextContent(type="text", text=result.summary)],
            structuredContent=result.model_dump(mode="json"),
            isError=True,
        )
    return result


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _log(tool: str, elapsed_ms: int | None, outcome: str, level: str, **fields: Any) -> None:
    getattr(_logger, level)("tool=%s outcome=%s elapsed_ms=%s", tool, outcome, elapsed_ms,
                            extra={"tool": tool, "outcome": outcome, "elapsed_ms": elapsed_ms, **fields})
