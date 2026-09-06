from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.core.config import Settings
from app.models.enums import LLMProvider

logger = logging.getLogger("llm_router")

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass
class LLMResponse:
    content: str
    provider_used: LLMProvider
    raw: dict = field(default_factory=dict)


class LLMConfigurationError(RuntimeError):
    pass


class LLMAllProvidersFailedError(RuntimeError):
    pass


class _RetryableLLMError(RuntimeError):
    pass


class LLMRouter:
    def __init__(self, settings: Settings, http_client: Optional[httpx.AsyncClient] = None):
        self._settings = settings
        self._client = http_client or httpx.AsyncClient(timeout=30.0)
        if not settings.groq_configured() and not settings.gemini_configured():
            raise LLMConfigurationError(
                "No LLM provider configured. Set GROQ_API_KEY and/or GEMINI_API_KEY in your .env."
            )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.2,
        max_tokens: int = 1024, json_mode: bool = False,
    ) -> LLMResponse:
        last_error: Optional[Exception] = None

        if self._settings.groq_configured():
            try:
                return await self._call_groq(system_prompt, user_prompt, temperature, max_tokens, json_mode)
            except _RetryableLLMError as exc:
                logger.warning("Groq call failed (%s) -- falling back to Gemini", exc)
                last_error = exc
            except Exception as exc:
                logger.warning("Groq call raised unexpected error (%s) -- attempting Gemini fallback", exc)
                last_error = exc

        if self._settings.gemini_configured():
            try:
                return await self._call_gemini(system_prompt, user_prompt, temperature, max_tokens, json_mode)
            except Exception as exc:
                last_error = exc

        raise LLMAllProvidersFailedError(
            f"Both Groq and Gemini failed or are unconfigured for this call. Last error: {last_error}"
        )

    async def _call_groq(self, system_prompt, user_prompt, temperature, max_tokens, json_mode) -> LLMResponse:
        payload = {
            "model": self._settings.groq_model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "temperature": temperature, "max_completion_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self._settings.groq_api_key}", "Content-Type": "application/json"}
        try:
            resp = await self._client.post(GROQ_CHAT_URL, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise _RetryableLLMError(f"Groq timeout: {exc}") from exc
        except httpx.TransportError as exc:
            raise _RetryableLLMError(f"Groq transport error: {exc}") from exc

        if resp.status_code in _RETRYABLE_STATUS_CODES:
            raise _RetryableLLMError(f"Groq returned status {resp.status_code}: {resp.text[:300]}")
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return LLMResponse(content=content, provider_used=LLMProvider.GROQ, raw=data)

    async def _call_gemini(self, system_prompt, user_prompt, temperature, max_tokens, json_mode) -> LLMResponse:
        url = GEMINI_URL_TEMPLATE.format(model=self._settings.gemini_model, api_key=self._settings.gemini_api_key)
        payload: dict = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        try:
            resp = await self._client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Gemini timeout: {exc}") from exc
        resp.raise_for_status()
        data = resp.json()
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        return LLMResponse(content=content, provider_used=LLMProvider.GEMINI, raw=data)

    @staticmethod
    def parse_json_response(response: LLMResponse) -> dict:
        try:
            return json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM ({response.provider_used}) returned non-JSON content: {response.content[:500]}") from exc
