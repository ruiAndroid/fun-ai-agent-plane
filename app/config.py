import os
from dataclasses import dataclass


def _read_int(name: str, default: int, minimum: int = 1) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return parsed


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    worker_count: int
    queue_max_size: int
    max_global_concurrency: int
    max_tenant_concurrency: int
    max_agent_concurrency: int
    token_delay_ms: int
    heartbeat_seconds: int


def load_settings() -> Settings:
    return Settings(
        host=os.getenv("PLANE_HOST", "0.0.0.0"),
        port=_read_int("PLANE_PORT", 8100, minimum=1),
        worker_count=_read_int("PLANE_WORKER_COUNT", 6, minimum=1),
        queue_max_size=_read_int("PLANE_QUEUE_MAX_SIZE", 1000, minimum=1),
        max_global_concurrency=_read_int("PLANE_MAX_GLOBAL_CONCURRENCY", 64, minimum=1),
        max_tenant_concurrency=_read_int("PLANE_MAX_TENANT_CONCURRENCY", 12, minimum=1),
        max_agent_concurrency=_read_int("PLANE_MAX_AGENT_CONCURRENCY", 8, minimum=1),
        token_delay_ms=_read_int("PLANE_TOKEN_DELAY_MS", 80, minimum=1),
        heartbeat_seconds=_read_int("PLANE_HEARTBEAT_SECONDS", 15, minimum=1),
    )


settings = load_settings()

