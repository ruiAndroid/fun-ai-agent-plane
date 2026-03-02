from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class WorkflowSpec:
    workflow_id: str
    name: str
    skill_id: str
    model_profile: Optional[str] = None
    description: str = ""
    config: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    display_name: str
    workflows: Dict[str, WorkflowSpec] = field(default_factory=dict)
    default_workflow_id: Optional[str] = None
    mcp_servers: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillSpec:
    skill_id: str
    description: str
    prompt_template: str = ""
    version: str = "1.0.0"


@dataclass(frozen=True)
class MCPServerSpec:
    server_id: str
    transport: str
    endpoint: str
    description: str = ""


@dataclass(frozen=True)
class ModelProfileSpec:
    model_id: str
    provider: str
    model_name: str
    base_url: str = ""
    api_key_env: str = ""
    timeout_seconds: int = 30
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    supports_tools: bool = False
    supports_vision: bool = False
    cost_tier: str = "standard"


@dataclass(frozen=True)
class RuntimeBundle:
    agent: AgentSpec
    workflow: WorkflowSpec
    skill: SkillSpec
    mcp_servers: List[MCPServerSpec]
    primary_model: Optional[ModelProfileSpec]
