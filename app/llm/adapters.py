import os
from typing import Any, Protocol

import httpx

from ..runtime import ModelProfileSpec
from .types import LLMRequest, LLMResponse


class LLMAdapter(Protocol):
    async def complete(self, profile: ModelProfileSpec, request: LLMRequest) -> LLMResponse:
        ...


class MockLLMAdapter:
    async def complete(self, profile: ModelProfileSpec, request: LLMRequest) -> LLMResponse:
        text = f"[mock:{profile.model_name}] {request.prompt[:240].strip() or '(empty prompt)'}"
        return LLMResponse(text=text, provider=profile.provider, model_name=profile.model_name)


class OpenAICompatibleAdapter:
    async def complete(self, profile: ModelProfileSpec, request: LLMRequest) -> LLMResponse:
        if not profile.api_key_env:
            raise RuntimeError(f"Model profile '{profile.model_id}' must set api_key_env.")
        api_key = os.getenv(profile.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(
                f"Model '{profile.model_id}' is missing API key. Set env {profile.api_key_env}."
            )

        base_url = profile.base_url.strip() or "https://api.openai.com/v1"
        endpoint = base_url.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
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

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(profile.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"Provider '{profile.provider}' returned empty choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"Provider '{profile.provider}' returned empty content.")

        return LLMResponse(
            text=content.strip(),
            provider=profile.provider,
            model_name=profile.model_name,
        )


class GatewayMessagesAdapter:
    def __init__(
        self,
        default_base_url: str,
        default_token: str,
        anthropic_version: str = "2023-06-01",
    ) -> None:
        self.default_base_url = default_base_url.strip() or "https://api.ai.fun.tv/v1"
        self.default_token = default_token.strip()
        self.anthropic_version = anthropic_version.strip() or "2023-06-01"

    def _resolve_token(self, profile: ModelProfileSpec) -> str:
        if profile.api_key_env:
            env_token = os.getenv(profile.api_key_env, "").strip()
            if env_token:
                return env_token
        return self.default_token

    async def complete(self, profile: ModelProfileSpec, request: LLMRequest) -> LLMResponse:
        api_token = self._resolve_token(profile)
        if not api_token:
            raise RuntimeError(
                "Gateway token is missing. Set GATEWAY_TOKEN (or LLM_GATEWAY_TOKEN)."
            )

        base_url = profile.base_url.strip() or self.default_base_url
        endpoint = base_url.rstrip("/") + "/messages"
        user_content = request.prompt
        if request.system_prompt.strip():
            user_content = (
                f"System instruction:\n{request.system_prompt.strip()}\n\n"
                f"User input:\n{request.prompt}"
            )
        payload: dict[str, Any] = {
            "model": profile.model_name,
            "messages": [{"role": "user", "content": user_content}],
            # The gateway examples require max_tokens.
            "max_tokens": request.max_tokens if request.max_tokens and request.max_tokens > 0 else 1024,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "anthropic-version": self.anthropic_version,
        }
        timeout = httpx.Timeout(profile.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        text = self._extract_text(data)
        if not text:
            raise RuntimeError("Gateway /v1/messages returned empty text content.")

        return LLMResponse(
            text=text,
            provider=profile.provider,
            model_name=profile.model_name,
        )

    def _extract_text(self, payload: dict[str, Any]) -> str:
        content = payload.get("content")
        if isinstance(content, str):
            return content.strip()

        if not isinstance(content, list):
            return ""

        chunks: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
        return "\n".join(chunks).strip()
