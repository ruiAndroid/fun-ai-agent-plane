import os
from dataclasses import dataclass
from pathlib import Path


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


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    parsed = value.strip().lower()
    if parsed in ("1", "true", "yes", "on"):
        return True
    if parsed in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{name} must be a boolean value")


def _load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.exists() or not env_path.is_file():
        return

    try:
        content = env_path.read_text(encoding="utf-8")
    except OSError:
        return

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


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
    agent_dir: str
    skills_dir: str
    mcp_dir: str
    model_dir: str
    enforce_agent_registry: bool
    llm_execution_mode: str
    gateway_base_url: str
    gateway_token: str
    gateway_anthropic_version: str


def load_settings() -> Settings:
    env_file = os.getenv("PLANE_ENV_FILE", ".env.production")
    _load_env_file(env_file)

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
        agent_dir=os.getenv("PLANE_AGENT_DIR", "./agents"),
        skills_dir=os.getenv("PLANE_SKILLS_DIR", "./skills"),
        mcp_dir=os.getenv("PLANE_MCP_DIR", "./mcp"),
        model_dir=os.getenv("PLANE_MODEL_DIR", "./models"),
        enforce_agent_registry=_read_bool("PLANE_ENFORCE_AGENT_REGISTRY", False),
        llm_execution_mode=os.getenv("PLANE_LLM_EXECUTION_MODE", "off"),
        gateway_base_url=os.getenv(
            "GATEWAY_BASE_URL",
            os.getenv("LLM_GATEWAY_BASE_URL", "https://api.ai.fun.tv/v1"),
        ),
        gateway_token=os.getenv(
            "GATEWAY_TOKEN",
            os.getenv("LLM_GATEWAY_TOKEN", ""),
        ),
        gateway_anthropic_version=os.getenv(
            "GATEWAY_ANTHROPIC_VERSION",
            os.getenv("LLM_GATEWAY_ANTHROPIC_VERSION", "2023-06-01"),
        ),
    )


settings = load_settings()
