import json
from pathlib import Path
from typing import Dict, Iterable, List

from .types import AgentSpec, MCPServerSpec, SkillSpec


def _iter_json_files(directory: Path) -> Iterable[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def load_agents(directory: str) -> Dict[str, AgentSpec]:
    root = Path(directory)
    agents: Dict[str, AgentSpec] = {}
    for file_path in _iter_json_files(root):
        payload = _load_json(file_path)
        agent_id = str(payload.get("agent_id", "")).strip()
        if not agent_id:
            raise ValueError(f"agent_id is required: {file_path}")
        display_name = str(payload.get("display_name", agent_id)).strip() or agent_id
        skills = [str(item).strip() for item in payload.get("skills", []) if str(item).strip()]
        mcp_servers = [
            str(item).strip() for item in payload.get("mcp_servers", []) if str(item).strip()
        ]
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        agents[agent_id] = AgentSpec(
            agent_id=agent_id,
            display_name=display_name,
            skills=skills,
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
        version = str(payload.get("version", "1.0.0")).strip() or "1.0.0"
        skills[skill_id] = SkillSpec(skill_id=skill_id, description=description, version=version)
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
