import os
from typing import Protocol

import httpx

from ..runtime import ModelProfileSpec
from .types import LLMRequest, LLMResponse


class LLMAdapter(Protocol):
    async def complete(self, profile: ModelProfileSpec, request: LLMRequest) -> LLMResponse:
        ...


class MockLLMAdapter:
    async def complete(self, profile: ModelProfileSpec, request: LLMRequest) -> LLMResponse:
        text = (
            f"[mock:{profile.model_name}] "
            f"{request.prompt[:240].strip() or '(empty prompt)'}"
        )
        return LLMResponse(text=text, provider=profile.provider, model_name=profile.model_name)


class OpenAICompatibleAdapter:
    async def complete(self, profile: ModelProfileSpec, request: LLMRequest) -> LLMResponse:
        if not profile.api_key_env:
            raise RuntimeError(f"api_key_env is required for profile '{profile.model_id}'")
        api_key = os.getenv(profile.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(
                f"Missing API key for profile '{profile.model_id}'. Set env {profile.api_key_env}."
            )

        base_url = profile.base_url.strip() or "https://api.openai.com/v1"
        endpoint = base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": profile.model_name,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.prompt},
            ],
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        timeout = httpx.Timeout(profile.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"Model provider '{profile.provider}' returned empty choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"Model provider '{profile.provider}' returned empty content")

        return LLMResponse(
            text=content.strip(),
            provider=profile.provider,
            model_name=profile.model_name,
        )
