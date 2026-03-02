from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    system_prompt: str
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model_name: str
