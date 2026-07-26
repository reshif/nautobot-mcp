"""Environment-driven settings.

Two required vars keep conventional names (`NAUTOBOT_URL`, `NAUTOBOT_TOKEN`);
everything else uses the `NAUTOBOT_MCP_` prefix.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NAUTOBOT_MCP_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    url: str = Field(validation_alias="NAUTOBOT_URL")
    token: str = Field(validation_alias="NAUTOBOT_TOKEN")

    transport: Literal["stdio", "streamable-http", "sse"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    streamable_http_path: str = "/mcp"
    json_response: bool = False
    stateless_http: bool = False

    max_items: int = 200
    max_response_chars: int = 60_000
    resolver_cache_ttl: int = 120
    request_timeout_seconds: float = 20.0
    tool_timeout_seconds: float = 45.0
    max_concurrent_requests: int = 8
    max_retries: int = 2  # automatic retries for GET on timeout / 502-504 / transport error
    verify_tls: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    enable_optional_tools: bool = False

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_level(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v

    @field_validator("url", "token")
    @classmethod
    def _not_blank(cls, v: str, info: ValidationInfo) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be empty — set it in .env")
        return v.strip().rstrip("/") if info.field_name == "url" else v.strip()

    @field_validator("streamable_http_path")
    @classmethod
    def _abs_path(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError(f"streamable_http_path must start with '/', got {v!r}.")
        return v

    @model_validator(mode="after")
    def _timeouts(self) -> Settings:
        if self.tool_timeout_seconds < self.request_timeout_seconds:
            raise ValueError("tool_timeout_seconds must be >= request_timeout_seconds")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    get_settings.cache_clear()
