from dataclasses import dataclass
from typing import Dict, List, Optional

from .loader import load_agents, load_mcp_servers, load_model_profiles, load_skills
from .types import (
    AgentSpec,
    MCPServerSpec,
    ModelProfileSpec,
    RuntimeBundle,
    RuntimeStepBundle,
    SkillSpec,
    WorkflowSpec,
    WorkflowStepSpec,
)


@dataclass(frozen=True)
class RuntimeSnapshot:
    agents: Dict[str, AgentSpec]
    skills: Dict[str, SkillSpec]
    mcp_servers: Dict[str, MCPServerSpec]
    model_profiles: Dict[str, ModelProfileSpec]


class AgentRuntimeRegistry:
    def __init__(
        self,
        agent_dir: str,
        skills_dir: str,
        mcp_dir: str,
        model_dir: str,
        enforce_agent_registry: bool = False,
    ) -> None:
        self.agent_dir = agent_dir
        self.skills_dir = skills_dir
        self.mcp_dir = mcp_dir
        self.model_dir = model_dir
        self.enforce_agent_registry = enforce_agent_registry
        self._snapshot = RuntimeSnapshot(agents={}, skills={}, mcp_servers={}, model_profiles={})

    def reload(self) -> RuntimeSnapshot:
        self._snapshot = RuntimeSnapshot(
            agents=load_agents(self.agent_dir),
            skills=load_skills(self.skills_dir),
            mcp_servers=load_mcp_servers(self.mcp_dir),
            model_profiles=load_model_profiles(self.model_dir),
        )
        return self._snapshot

    def snapshot(self) -> RuntimeSnapshot:
        return self._snapshot

    def resolve(self, agent_id: str, workflow_id: Optional[str] = None) -> RuntimeBundle:
        agent = self._snapshot.agents.get(agent_id)
        if agent is None:
            if self.enforce_agent_registry:
                raise ValueError(
                    f"Unknown agent_id '{agent_id}'. Please add config under {self.agent_dir}."
                )
            default_workflow = WorkflowSpec(
                workflow_id="default",
                name="default",
                steps=[
                    WorkflowStepSpec(
                        step_id="default-step-1",
                        name="default-step",
                        skill_id="summarize-text",
                    )
                ],
            )
            agent = AgentSpec(
                agent_id=agent_id,
                display_name=agent_id,
                workflows={"default": default_workflow},
                default_workflow_id="default",
            )

        selected_workflow_id = (workflow_id or "").strip() or (agent.default_workflow_id or "")
        if not selected_workflow_id:
            if not agent.workflows:
                raise ValueError(f"Agent '{agent.agent_id}' has no workflows configured.")
            selected_workflow_id = next(iter(agent.workflows.keys()))

        workflow = agent.workflows.get(selected_workflow_id)
        if workflow is None:
            raise ValueError(
                f"Agent '{agent.agent_id}' has no workflow '{selected_workflow_id}'."
            )
        if not workflow.steps:
            raise ValueError(f"Workflow '{workflow.workflow_id}' has no steps.")

        resolved_steps: List[RuntimeStepBundle] = []
        for step in workflow.steps:
            skill = self._snapshot.skills.get(step.skill_id)
            if skill is None:
                raise ValueError(
                    f"Workflow '{workflow.workflow_id}' step '{step.step_id}' "
                    f"references unknown skill '{step.skill_id}'."
                )
            resolved_steps.append(RuntimeStepBundle(step=step, skill=skill))

        resolved_mcp: List[MCPServerSpec] = []
        for server_id in agent.mcp_servers:
            server = self._snapshot.mcp_servers.get(server_id)
            if server:
                resolved_mcp.append(server)

        primary_model: Optional[ModelProfileSpec] = None
        if workflow.model_profile:
            primary_model = self._snapshot.model_profiles.get(workflow.model_profile)
            if primary_model is None:
                # Fallback mode: use workflow.model_profile directly as gateway model id.
                primary_model = ModelProfileSpec(
                    model_id=workflow.model_profile,
                    provider="gateway-messages",
                    model_name=workflow.model_profile,
                )

        return RuntimeBundle(
            agent=agent,
            workflow=workflow,
            steps=resolved_steps,
            mcp_servers=resolved_mcp,
            primary_model=primary_model,
        )
