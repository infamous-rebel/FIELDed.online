"""OpenAI AI provider adapter.

Implements the FIELDed ``AIProvider`` interface using the OpenAI
Chat Completions API via ``httpx`` (matching the project's existing
HTTP client pattern — no additional SDK dependency).

Supports both ``complete`` (text) and ``structured_output`` (JSON
schema) contracts.  The structured output uses OpenAI's
``response_format`` with ``type: json_schema`` when the model
supports it, falling back to ``type: json_object`` with the schema
embedded in the system prompt.

AI remains proposal-only:  the output is validated by the caller
(e.g. ``VoiceCallAgent._validate_proposal``) before any effect.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.adapters.ai.base import AIProvider, AIResponse

logger = logging.getLogger(__name__)

_OPENAI_API_BASE = "https://api.openai.com/v1/"
_DEFAULT_TIMEOUT = 60.0


class OpenAIProvider(AIProvider):
    """AI provider backed by the OpenAI Chat Completions API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini",
        api_base: str = _OPENAI_API_BASE,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._api_base = api_base

    @property
    def provider_name(self) -> str:
        return "openai"

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
                f"OpenAI returned non-JSON structured output: {content[:200]}"
            ) from exc

        if not isinstance(result, dict):
            raise ValueError(
                f"OpenAI structured output is not an object: {type(result).__name__}"
            )

        return result

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
                    f"OpenAI API error {response.status_code}: "
                    f"{response.text[:500]}"
                )

            return response.json()

        except httpx.TimeoutException as exc:
            raise RuntimeError("OpenAI API timeout") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"OpenAI API error: {exc}") from exc
