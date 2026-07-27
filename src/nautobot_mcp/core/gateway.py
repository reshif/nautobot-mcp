"""Anti-corruption layer around the Nautobot REST API — the one HTTP seam.

Every request flows through here, so concurrency limiting, timeouts, logging,
and error normalization happen exactly once (DRY). Tools call
`gateway.get("dcim/devices/", {...})` / `gateway.list("dcim/devices/", {...})`
and never touch httpx or see an httpx exception. Because tools depend on this
duck-typed interface, `tests/fakes.FakeGateway` substitutes for it offline.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .errors import NautobotApiError, NautobotTimeoutError, NautobotValidationError
from .observability import get_logger
from .pagination import PAGE_LIMIT

_logger = get_logger(__name__)

# 4xx statuses that mean "the caller can fix the request" (vs a server/transport failure)
_VALIDATION_STATUS = frozenset({400, 422})


# status codes worth one automatic retry (transient upstream/proxy conditions)
_RETRY_STATUS = frozenset({502, 503, 504})


class NautobotGateway:
    def __init__(self, client: httpx.AsyncClient, *, max_concurrent: int = 8,
                 timeout_seconds: float = 20.0, max_retries: int = 2) -> None:
        self._client = client
        self._sem = asyncio.Semaphore(max_concurrent)
        self._timeout = timeout_seconds
        self._max_retries = max(0, max_retries)

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Single GET (relative path or absolute `next` URL). Returns parsed JSON."""
        return await self._send("GET", path, params=params, retryable=True)

    async def post(self, path: str, json_body: dict[str, Any] | None = None) -> Any:
        """POST returning parsed JSON — used only for read-style endpoints (GraphQL, saved-query run).

        Not retried: even read-style POSTs (GraphQL) are not guaranteed idempotent upstream.
        """
        return await self._send("POST", path, json_body=json_body or {}, retryable=False)

    async def _send(self, method: str, path: str, *, params: dict[str, Any] | None = None,
                    json_body: dict[str, Any] | None = None, retryable: bool) -> Any:
        """The one HTTP call site: concurrency + timeout + bounded retry + error normalization."""
        operation = f"{method} {path.split('?')[0]}"
        attempts = (self._max_retries + 1) if retryable else 1
        async with self._sem:
            for attempt in range(1, attempts + 1):
                started = time.monotonic()
                try:
                    resp = await self._client.request(method, path, params=params, json=json_body, timeout=self._timeout)
                    resp.raise_for_status()
                    data = resp.json()
                except httpx.TimeoutException as exc:
                    if attempt < attempts:
                        await self._backoff(operation, attempt, "timeout")
                        continue
                    _logger.warning("nautobot.timeout", extra={"operation": operation})
                    raise NautobotTimeoutError(operation, self._timeout) from exc
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status in _RETRY_STATUS and attempt < attempts:
                        await self._backoff(operation, attempt, f"http_{status}")
                        continue
                    if status in _VALIDATION_STATUS:  # caller can fix it — self-correcting, don't retry
                        fields = _fields(exc.response)
                        raise NautobotValidationError(operation, status, _detail(exc.response), fields) from exc
                    _logger.warning("nautobot.api_error", extra={"operation": operation, "status": status})
                    raise NautobotApiError(operation, status, _detail(exc.response)) from exc
                except httpx.HTTPError as exc:
                    if attempt < attempts:
                        await self._backoff(operation, attempt, "transport")
                        continue
                    raise NautobotApiError(operation, None, str(exc)) from exc
                _logger.debug("nautobot.call", extra={"operation": operation, "attempt": attempt,
                                                       "elapsed_ms": int((time.monotonic() - started) * 1000)})
                return data

    async def _backoff(self, operation: str, attempt: int, reason: str) -> None:
        delay = min(0.25 * (2 ** (attempt - 1)), 2.0)  # 0.25s, 0.5s, capped
        _logger.warning("nautobot.retry", extra={"operation": operation, "attempt": attempt, "reason": reason, "delay": delay})
        await asyncio.sleep(delay)

    async def list(self, path: str, params: dict[str, Any] | None = None, cap: int | None = None) -> list[dict[str, Any]]:
        """GET a list endpoint, following `next` up to `cap` items.

        Tolerates the two shapes Nautobot returns: the paginated `{results, next}`
        envelope and (a few action endpoints) a bare list.
        """
        params = dict(params or {})
        params.setdefault("limit", PAGE_LIMIT)
        results: list[dict[str, Any]] = []
        url: str | None = path
        first = True
        while url:
            data = await self.get(url, params if first else None)
            if isinstance(data, list):  # bare-list endpoint (e.g. available-ips) — no pagination
                results.extend(data)
                break
            if not isinstance(data, dict):
                break
            results.extend(data.get("results") or [])
            if cap is not None and len(results) >= cap:
                return results[:cap]
            url = data.get("next")
            first = False
        return results[:cap] if cap is not None else results

    async def count(self, path: str, params: dict[str, Any] | None = None) -> int | None:
        """Total match count for a filtered list endpoint (one cheap GET, limit=1)."""
        data = await self.get(path, {**(params or {}), "limit": 1})
        return data.get("count") if isinstance(data, dict) else None


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict):
            return body.get("detail") or str(body)[:200]
        return str(body)[:200]
    except Exception:
        return (resp.text or "")[:200]


def _fields(resp: httpx.Response) -> dict[str, Any]:
    """Per-field validation messages from a 4xx body, e.g. {'site': ['Unknown filter field']}."""
    try:
        body = resp.json()
        return {k: v for k, v in body.items() if k != "detail"} if isinstance(body, dict) else {}
    except Exception:
        return {}
