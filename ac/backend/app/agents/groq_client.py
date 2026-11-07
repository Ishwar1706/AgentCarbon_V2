"""Minimal Groq (OpenAI-compatible) client for openai/gpt-oss-120b with retry + JSON parsing."""
from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from app.core.config import settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqClientError(RuntimeError):
    pass


def parse_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise GroqClientError("Model did not return a JSON object.")
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError as error:
            raise GroqClientError(f"Model returned invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise GroqClientError("Model JSON must be an object.")
    return value


class GroqClient:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.api_key = (api_key or settings.groq_api_key).strip()
        if not self.api_key:
            raise GroqClientError("GROQ_API_KEY is not configured.")
        self.model = model or settings.groq_model
        self._http = httpx.Client(timeout=settings.groq_request_timeout_seconds, transport=transport)
        self._sleep = sleep
        self.calls = 0
        self.total_tokens = 0

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
            "max_completion_tokens": settings.groq_max_completion_tokens,
            "reasoning_effort": settings.groq_reasoning_effort,
            "response_format": {"type": "json_object"},
        }
        if self.calls:
            self._sleep(settings.groq_call_delay_seconds)
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_error = "unknown error"
        for attempt in range(settings.groq_max_retries + 1):
            try:
                response = self._http.post(GROQ_URL, headers=headers, json=body)
            except httpx.HTTPError as error:
                last_error = f"network error: {error}"
                self._sleep(min(2 ** attempt, 20))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                wait = response.headers.get("retry-after")
                delay = float(wait) if wait and wait.replace(".", "", 1).isdigit() else min(2 ** (attempt + 1), 30)
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                self._sleep(min(delay + 0.5, 90))
                continue
            if response.status_code == 400 and "response_format" in body and (
                    "response_format" in response.text or "json" in response.text.lower()):
                body.pop("response_format")  # model/endpoint rejected JSON mode; parse from text instead
                last_error = f"HTTP 400: {response.text[:200]}"
                continue
            if response.status_code in (401, 403):
                raise GroqClientError("Groq rejected the API key (401/403). Check GROQ_API_KEY.")
            if response.status_code >= 400:
                raise GroqClientError(f"Groq error HTTP {response.status_code}: {response.text[:300]}")
            data = response.json()
            self.calls += 1
            self.total_tokens += int((data.get("usage") or {}).get("total_tokens", 0))
            choice = (data.get("choices") or [{}])[0]
            content = (choice.get("message") or {}).get("content") or ""
            if not content.strip():
                if choice.get("finish_reason") == "length" and body["max_completion_tokens"] < 8000:
                    body["max_completion_tokens"] *= 2  # reasoning used up the budget
                    last_error = "empty content (token limit); retrying with a larger budget"
                    continue
                raise GroqClientError("Model returned empty content.")
            return parse_json_object(content)
        raise GroqClientError(f"Groq request failed after retries: {last_error}")
