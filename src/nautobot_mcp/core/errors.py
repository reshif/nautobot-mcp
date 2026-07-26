"""Exception hierarchy — normalized into a ToolResult by the registrar.

- ResolutionError: a name couldn't be turned into exactly one object
  (AmbiguousTarget carries the candidate list for the model to pick).
- GatewayError: any Nautobot API failure, normalized by NautobotGateway so tool
  code never sees a raw httpx exception.
"""
from __future__ import annotations

from typing import Any

from .response import ErrorKind


class ResolutionError(Exception):
    kind: ErrorKind = ErrorKind.UNEXPECTED

    def __init__(self, message: str, choices: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.choices = choices


class AmbiguousTarget(ResolutionError):
    kind = ErrorKind.AMBIGUOUS_TARGET


class TargetNotFound(ResolutionError):
    kind = ErrorKind.TARGET_NOT_FOUND


class GatewayError(Exception):
    kind: ErrorKind = ErrorKind.API_ERROR

    def __init__(self, operation: str, message: str) -> None:
        super().__init__(f"{operation}: {message}")
        self.operation = operation
        self.message = message


class NautobotTimeoutError(GatewayError):
    kind = ErrorKind.TIMEOUT

    def __init__(self, operation: str, timeout_seconds: float) -> None:
        super().__init__(operation, f"timed out after {timeout_seconds:.0f}s")


class NautobotApiError(GatewayError):
    kind = ErrorKind.API_ERROR

    def __init__(self, operation: str, status: int | None, detail: str) -> None:
        super().__init__(operation, f"HTTP {status} — {detail}" if status else detail)
        self.status = status
