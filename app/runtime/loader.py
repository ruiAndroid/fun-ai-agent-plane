import json
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from .types import AgentSpec, MCPServerSpec, ModelProfileSpec, SkillSpec, WorkflowSpec


def _iter_json_files(directory: Path) -> Iterable[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def _parse_workflow_config(raw_config: Any) -> Dict[str, str]:
    if not isinstance(raw_config, dict):
        return {}
    return {str(key): str(value) for key, value in raw_config.items()}


def _parse_workflows(payload: dict, file_path: Path) -> Tuple[Dict[str, WorkflowSpec], str]:
    workflows: Dict[str, WorkflowSpec] = {}

    raw_workflows = payload.get("workflows")
    if raw_workflows is None:
        # Legacy compatibility: map skills + default_model_profile to workflow entries.
        default_model_profile = str(payload.get("default_model_profile", "")).strip() or None
        for skill_item in payload.get("skills", []):
            skill_id = str(skill_item).strip()
            if not skill_id:
                continue
            workflow_id = skill_id
            workflows[workflow_id] = WorkflowSpec(
                workflow_id=workflow_id,
                name=workflow_id,
                skill_id=skill_id,
                model_profile=default_model_profile,
            )
    elif isinstance(raw_workflows, list):
        for workflow_raw in raw_workflows:
            if not isinstance(workflow_raw, dict):
                raise ValueError(f"workflow item must be an object: {file_path}")
            workflow_id = str(workflow_raw.get("workflow_id", "")).strip()
            if not workflow_id:
                raise ValueError(f"workflow_id is required in workflows list: {file_path}")
            skill_id = str(workflow_raw.get("skill_id", "")).strip()
            if not skill_id:
                raise ValueError(f"skill_id is required for workflow '{workflow_id}': {file_path}")
            workflows[workflow_id] = WorkflowSpec(
                workflow_id=workflow_id,
                name=str(workflow_raw.get("name", workflow_id)).strip() or workflow_id,
                skill_id=skill_id,
                model_profile=str(workflow_raw.get("model_profile", "")).strip() or None,
                description=str(workflow_raw.get("description", "")).strip(),
                config=_parse_workflow_config(workflow_raw.get("config")),
            )
    elif isinstance(raw_workflows, dict):
        for workflow_id, workflow_raw in raw_workflows.items():
            workflow_id = str(workflow_id).strip()
            if not workflow_id:
                raise ValueError(f"workflow key cannot be empty: {file_path}")
            if not isinstance(workflow_raw, dict):
                raise ValueError(f"workflow '{workflow_id}' must be an object: {file_path}")
            skill_id = str(workflow_raw.get("skill_id", "")).strip()
            if not skill_id:
                raise ValueError(f"skill_id is required for workflow '{workflow_id}': {file_path}")
            workflows[workflow_id] = WorkflowSpec(
                workflow_id=workflow_id,
                name=str(workflow_raw.get("name", workflow_id)).strip() or workflow_id,
                skill_id=skill_id,
                model_profile=str(workflow_raw.get("model_profile", "")).strip() or None,
                description=str(workflow_raw.get("description", "")).strip(),
                config=_parse_workflow_config(workflow_raw.get("config")),
            )
    else:
        raise ValueError(f"workflows must be an array/object when provided: {file_path}")

    default_workflow_id = str(payload.get("default_workflow_id", "")).strip()
    if not default_workflow_id and workflows:
        default_workflow_id = next(iter(workflows.keys()))
    if default_workflow_id and default_workflow_id not in workflows:
        raise ValueError(
            f"default_workflow_id '{default_workflow_id}' not found in workflows: {file_path}"
        )
    return workflows, default_workflow_id


def load_agents(directory: str) -> Dict[str, AgentSpec]:
    root = Path(directory)
    agents: Dict[str, AgentSpec] = {}
    for file_path in _iter_json_files(root):
        payload = _load_json(file_path)
        if "prompt" in payload:
            raise ValueError(
                f"'prompt' is not allowed in agent config during development stage: {file_path}"
            )
        agent_id = str(payload.get("agent_id", "")).strip()
        if not agent_id:
            raise ValueError(f"agent_id is required: {file_path}")
        display_name = str(payload.get("display_name", agent_id)).strip() or agent_id
        mcp_servers = [
            str(item).strip() for item in payload.get("mcp_servers", []) if str(item).strip()
        ]
        workflows, default_workflow_id = _parse_workflows(payload, file_path)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        agents[agent_id] = AgentSpec(
            agent_id=agent_id,
            display_name=display_name,
            workflows=workflows,
            default_workflow_id=default_workflow_id or None,
            mcp_servers=mcp_servers,
            metadata={str(k): str(v) for k, v in metadata.items()},
        )
    return agents


def load_skills(directory: str) -> Dict[str, SkillSpec]:
    root = Path(directory)
    skills: Dict[str, SkillSpec] = {}
    for file_path in _iter_json_files(root):
        payload = _load_json(file_path)
        skill_id = str(payload.get("skill_id", "")).strip()
        if not skill_id:
            raise ValueError(f"skill_id is required: {file_path}")
        description = str(payload.get("description", "")).strip()
        prompt_template = str(payload.get("prompt_template", payload.get("prompt", ""))).strip()
        version = str(payload.get("version", "1.0.0")).strip() or "1.0.0"
        skills[skill_id] = SkillSpec(
            skill_id=skill_id,
            description=description,
            prompt_template=prompt_template,
            version=version,
        )
    return skills


def load_mcp_servers(directory: str) -> Dict[str, MCPServerSpec]:
    root = Path(directory)
    servers: Dict[str, MCPServerSpec] = {}
    for file_path in _iter_json_files(root):
        payload = _load_json(file_path)
        server_id = str(payload.get("server_id", "")).strip()
        if not server_id:
            raise ValueError(f"server_id is required: {file_path}")
        transport = str(payload.get("transport", "stdio")).strip() or "stdio"
        endpoint = str(payload.get("endpoint", "")).strip()
        if not endpoint:
            raise ValueError(f"endpoint is required: {file_path}")
        description = str(payload.get("description", "")).strip()
        servers[server_id] = MCPServerSpec(
            server_id=server_id,
            transport=transport,
            endpoint=endpoint,
            description=description,
        )
    return servers


def _to_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    parsed = str(value).strip().lower()
    if parsed in ("1", "true", "yes", "on"):
        return True
    if parsed in ("0", "false", "no", "off"):
        return False
    return default


def load_model_profiles(directory: str) -> Dict[str, ModelProfileSpec]:
    root = Path(directory)
    profiles: Dict[str, ModelProfileSpec] = {}
    for file_path in _iter_json_files(root):
        payload = _load_json(file_path)
        model_id = str(payload.get("model_id", "")).strip()
        if not model_id:
            raise ValueError(f"model_id is required: {file_path}")
        provider = str(payload.get("provider", "")).strip()
        if not provider:
            raise ValueError(f"provider is required: {file_path}")
        model_name = str(payload.get("model_name", "")).strip()
        if not model_name:
            raise ValueError(f"model_name is required: {file_path}")

        timeout_raw = payload.get("timeout_seconds", 30)
        try:
            timeout_seconds = int(timeout_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"timeout_seconds must be an integer: {file_path}") from exc
        if timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be > 0: {file_path}")

        max_tokens = payload.get("max_tokens")
        if max_tokens is not None:
            try:
                max_tokens = int(max_tokens)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"max_tokens must be an integer: {file_path}") from exc

        temperature = payload.get("temperature")
        if temperature is not None:
            try:
                temperature = float(temperature)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"temperature must be numeric: {file_path}") from exc

        profiles[model_id] = ModelProfileSpec(
            model_id=model_id,
            provider=provider,
            model_name=model_name,
            base_url=str(payload.get("base_url", "")).strip(),
            api_key_env=str(payload.get("api_key_env", "")).strip(),
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            temperature=temperature,
            supports_tools=_to_bool(payload.get("supports_tools"), False),
            supports_vision=_to_bool(payload.get("supports_vision"), False),
            cost_tier=str(payload.get("cost_tier", "standard")).strip() or "standard",
        )
    return profiles
