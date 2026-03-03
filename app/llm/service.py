from dataclasses import replace
from typing import Dict, Optional

from ..runtime import RuntimeBundle
from .adapters import GatewayMessagesAdapter, MockLLMAdapter, OpenAICompatibleAdapter
from .types import LLMRequest, LLMResponse


class LLMService:
    def __init__(
        self,
        execution_mode: str = "off",
        gateway_base_url: str = "https://api.ai.fun.tv/v1",
        gateway_token: str = "",
        gateway_anthropic_version: str = "2023-06-01",
    ) -> None:
        self.execution_mode = execution_mode.strip().lower()
        gateway_adapter = GatewayMessagesAdapter(
            default_base_url=gateway_base_url,
            default_token=gateway_token,
            anthropic_version=gateway_anthropic_version,
        )
        self._adapters: Dict[str, object] = {
            "mock": MockLLMAdapter(),
            "openai-compatible": OpenAICompatibleAdapter(),
            "gateway-messages": gateway_adapter,
            "anthropic-messages": gateway_adapter,
        }

    async def complete(
        self,
        runtime: RuntimeBundle,
        prompt: str,
        skill_prompt: Optional[str] = None,
    ) -> LLMResponse:
        profile = runtime.primary_model
        if profile is None:
            raise RuntimeError(f"Agent '{runtime.agent.agent_id}' has no model profile.")
        if self.execution_mode == "off":
            raise RuntimeError("LLM execution is disabled (PLANE_LLM_EXECUTION_MODE=off).")
        if self.execution_mode == "mock":
            profile = replace(profile, provider="mock")

        system_prompt = self._system_prompt_for_skill(
            agent_id=runtime.agent.agent_id,
            workflow_id=runtime.workflow.workflow_id,
            skill_prompt=skill_prompt or "",
        )
        provider = profile.provider.strip().lower()
        adapter = self._adapters.get(provider)
        if adapter is None:
            raise RuntimeError(
                f"Model '{profile.model_id}' uses unsupported provider '{profile.provider}'."
            )
        request = LLMRequest(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=profile.max_tokens,
            temperature=profile.temperature,
        )
        return await adapter.complete(profile, request)

    def _system_prompt_for_skill(self, agent_id: str, workflow_id: str, skill_prompt: str) -> str:
        if skill_prompt.strip():
            return skill_prompt.strip()
        return (
            f"You are agent '{agent_id}', currently running workflow '{workflow_id}'. "
            "Return concise and executable results."
        )
