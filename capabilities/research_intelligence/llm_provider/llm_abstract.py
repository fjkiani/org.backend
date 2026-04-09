"""
Groq-backed LLM bridge for research_intelligence (replaces oncology api.services.llm_provider).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from groq import Groq


@dataclass
class LLMResponse:
    text: str


class LLMProvider(str, Enum):
    """Legacy enum values from oncology stack; all resolve to Groq here."""

    GROQ = "groq"
    COHERE = "cohere"
    OPENAI = "openai"


class GroqLLMProvider:
    def __init__(self) -> None:
        self._model = os.environ.get(
            "RESEARCH_INTEL_GROQ_MODEL",
            os.environ.get("ZETA_CORE_GROQ_MODEL", "llama-3.3-70b-versatile"),
        )
        self._temp_default = float(
            os.environ.get(
                "RESEARCH_INTEL_GROQ_TEMPERATURE",
                os.environ.get("ZETA_CORE_GROQ_TEMPERATURE", "0.2"),
            )
        )

    def is_available(self) -> bool:
        return bool(os.environ.get("GROQ_API_KEY", "").strip())

    async def chat(
        self,
        *,
        message: Optional[str] = None,
        prompt: Optional[str] = None,
        system_message: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        user = message if message is not None else prompt
        if user is None:
            raise ValueError("chat() requires message= or prompt=")
        key = os.environ.get("GROQ_API_KEY", "").strip()
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")

        temp = float(temperature if temperature is not None else self._temp_default)

        def _call() -> str:
            client = Groq(api_key=key)
            messages = []
            if system_message:
                messages.append({"role": "system", "content": system_message})
            messages.append({"role": "user", "content": user})
            r = client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temp,
                max_tokens=max_tokens,
            )
            return (r.choices[0].message.content or "").strip()

        text = await asyncio.to_thread(_call)
        return LLMResponse(text=text)


def get_llm_provider(provider: Optional[LLMProvider] = None) -> GroqLLMProvider:
    _ = provider
    return GroqLLMProvider()
