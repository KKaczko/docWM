"""Minimal stdlib client for OpenAI-compatible chat endpoints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OpenAICompatibleError(RuntimeError):
    """Raised when an OpenAI-compatible endpoint cannot return usable content."""


@dataclass(slots=True)
class OpenAICompatibleClient:
    base_url: str
    timeout_seconds: int = 120
    api_key: str | None = None

    def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float) -> str:
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise OpenAICompatibleError(f"OpenAI-compatible HTTP error {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise OpenAICompatibleError(f"OpenAI-compatible connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise OpenAICompatibleError("OpenAI-compatible request timed out.") from exc
        except json.JSONDecodeError as exc:
            raise OpenAICompatibleError("OpenAI-compatible endpoint returned invalid JSON.") from exc

        content = _extract_message_content(data)
        if not content:
            raise OpenAICompatibleError("OpenAI-compatible response did not contain choices[].message.content.")
        return content


def test_openai_compatible(
    base_url: str,
    model: str,
    timeout_seconds: int = 120,
    api_key: str | None = None,
) -> str:
    client = OpenAICompatibleClient(base_url=base_url, timeout_seconds=timeout_seconds, api_key=api_key)
    return client.chat(
        model=model,
        messages=[
            {"role": "system", "content": "Reply with a short confirmation only."},
            {"role": "user", "content": "Say wm-docgen-ok."},
        ],
        temperature=0.0,
    )


def _extract_message_content(data: Any) -> str | None:
    content = _standard_message_content(data)
    if content:
        return content

    fallback: str | None = None
    for role, candidate in _walk_message_contents(data):
        if role == "assistant":
            return candidate
        if fallback is None:
            fallback = candidate
    return fallback


def _standard_message_content(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    return content.strip()


def _walk_message_contents(value: Any) -> Iterator[tuple[str | None, str]]:
    if isinstance(value, dict):
        message = value.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                role = message.get("role")
                yield (role if isinstance(role, str) else None, content.strip())
        for child in value.values():
            yield from _walk_message_contents(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_message_contents(child)
