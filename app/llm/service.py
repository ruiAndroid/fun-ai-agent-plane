from dataclasses import replace
from typing import Dict, Optional

from ..runtime import RuntimeBundle
from .adapters import MockLLMAdapter, OpenAICompatibleAdapter
from .types import LLMRequest, LLMResponse


class LLMService:
    def __init__(self, execution_mode: str = "off") -> None:
        self.execution_mode = execution_mode.strip().lower()
        self._adapters: Dict[str, object] = {
            "mock": MockLLMAdapter(),
            "openai-compatible": OpenAICompatibleAdapter(),
        }

    async def complete(
        self,
        runtime: RuntimeBundle,
        prompt: str,
        skill_prompt_override: Optional[str] = None,
    ) -> LLMResponse:
        profile = runtime.primary_model
        if profile is None:
            raise RuntimeError(f"Agent '{runtime.agent.agent_id}' has no configured model profile")
        if self.execution_mode == "off":
            raise RuntimeError("LLM execution is disabled (PLANE_LLM_EXECUTION_MODE=off)")
        if self.execution_mode == "mock":
            profile = replace(profile, provider="mock")

        system_prompt = self._system_prompt_for_skill(
            agent_id=runtime.agent.agent_id,
            workflow_id=runtime.workflow.workflow_id,
            skill_prompt=skill_prompt_override or runtime.skill.prompt_template,
        )
        provider = profile.provider.strip().lower()
        adapter = self._adapters.get(provider)
        if adapter is None:
            raise RuntimeError(f"Unsupported provider '{profile.provider}' for '{profile.model_id}'")
        request = LLMRequest(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=profile.max_tokens,
            temperature=profile.temperature,
        )
        return await adapter.complete(profile, request)

    def _system_prompt_for_skill(
        self, agent_id: str, workflow_id: str, skill_prompt: str
    ) -> str:
        if skill_prompt.strip():
            return skill_prompt.strip()
        return (
            f"You are agent '{agent_id}' running workflow '{workflow_id}'. "
            "Return concise, execution-focused answers."
        )
