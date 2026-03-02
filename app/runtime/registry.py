from dataclasses import dataclass
from typing import Dict, List

from .loader import load_agents, load_mcp_servers, load_skills
from .types import AgentSpec, MCPServerSpec, RuntimeBundle, SkillSpec


@dataclass(frozen=True)
class RuntimeSnapshot:
    agents: Dict[str, AgentSpec]
    skills: Dict[str, SkillSpec]
    mcp_servers: Dict[str, MCPServerSpec]


class AgentRuntimeRegistry:
    def __init__(
        self,
        agent_dir: str,
        skills_dir: str,
        mcp_dir: str,
        enforce_agent_registry: bool = False,
    ) -> None:
        self.agent_dir = agent_dir
        self.skills_dir = skills_dir
        self.mcp_dir = mcp_dir
        self.enforce_agent_registry = enforce_agent_registry
        self._snapshot = RuntimeSnapshot(agents={}, skills={}, mcp_servers={})

    def reload(self) -> RuntimeSnapshot:
        self._snapshot = RuntimeSnapshot(
            agents=load_agents(self.agent_dir),
            skills=load_skills(self.skills_dir),
            mcp_servers=load_mcp_servers(self.mcp_dir),
        )
        return self._snapshot

    def snapshot(self) -> RuntimeSnapshot:
        return self._snapshot

    def resolve(self, agent_id: str) -> RuntimeBundle:
        agent = self._snapshot.agents.get(agent_id)
        if agent is None:
            if self.enforce_agent_registry:
                raise ValueError(f"Unknown agent_id '{agent_id}'. Add config under {self.agent_dir}.")
            agent = AgentSpec(agent_id=agent_id, display_name=agent_id)

        resolved_skills: List[SkillSpec] = []
        for skill_id in agent.skills:
            skill = self._snapshot.skills.get(skill_id)
            if skill:
                resolved_skills.append(skill)

        resolved_mcp: List[MCPServerSpec] = []
        for server_id in agent.mcp_servers:
            server = self._snapshot.mcp_servers.get(server_id)
            if server:
                resolved_mcp.append(server)

        return RuntimeBundle(agent=agent, skills=resolved_skills, mcp_servers=resolved_mcp)
