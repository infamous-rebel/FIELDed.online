"""Groq AI provider adapter.

Implements the FIELDed ``AIProvider`` interface using the Groq
Chat Completions API. Groq is OpenAI-compatible, so this provider
reuses the same protocol via ``httpx``.

This is used for Business Brain conversational intelligence.
AI remains proposal-only: outputs are validated before any effect.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.adapters.ai.base import AIProvider, AIResponse

_GROQ_API_BASE = "https://api.groq.com/openai/v1/"
_DEFAULT_TIMEOUT = 60.0
_DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(AIProvider):
    """AI provider backed by the Groq Chat Completions API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        api_base: str = _GROQ_API_BASE,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._api_base = api_base

    @property
    def provider_name(self) -> str:
        return "groq"

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AIResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        data = await self._chat_completion(
            messages, max_tokens=max_tokens, temperature=temperature
        )
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return AIResponse(
            content=content,
            model=data.get("model", self._model),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            },
            raw=data,
        )

    async def structured_output(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []

        system_content = system or ""
        system_content += (
            "\n\nYou MUST respond with a JSON object matching this schema: "
            + json.dumps(schema)
        )
        messages.append({"role": "system", "content": system_content.strip()})
        messages.append({"role": "user", "content": prompt})

        data = await self._chat_completion(
            messages,
            max_tokens=max_tokens,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = data["choices"][0]["message"]["content"]

        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Groq returned non-JSON structured output: {content[:200]}"
            ) from exc

        if not isinstance(result, dict):
            raise ValueError(
                f"Groq structured output is not an object: {type(result).__name__}"
            )

        return result

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
    ) -> AIResponse:
        """Multi-turn chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            system: Optional system instruction prepended to messages.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.
            response_format: Optional response format constraint.

        Returns:
            Structured AI response.
        """
        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        data = await self._chat_completion(
            full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
        )
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return AIResponse(
            content=content,
            model=data.get("model", self._model),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            },
            raw=data,
        )

    async def _chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float,
        response_format: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = self._api_base.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )

            if response.status_code not in (200, 201):
                raise RuntimeError(
                    f"Groq API error {response.status_code}: {response.text[:500]}"
                )

            return response.json()

        except httpx.TimeoutException as exc:
            raise RuntimeError("Groq API timeout") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Groq API error: {exc}") from exc
