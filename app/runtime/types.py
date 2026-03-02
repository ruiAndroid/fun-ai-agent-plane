from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    display_name: str
    skills: List[str] = field(default_factory=list)
    mcp_servers: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillSpec:
    skill_id: str
    description: str
    version: str = "1.0.0"


@dataclass(frozen=True)
class MCPServerSpec:
    server_id: str
    transport: str
    endpoint: str
    description: str = ""


@dataclass(frozen=True)
class RuntimeBundle:
    agent: AgentSpec
    skills: List[SkillSpec]
    mcp_servers: List[MCPServerSpec]
