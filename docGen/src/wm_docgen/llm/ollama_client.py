"""Minimal stdlib Ollama client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    """Raised when Ollama cannot return usable content."""


@dataclass(slots=True)
class OllamaClient:
    base_url: str = "http://localhost:11434"
    timeout_seconds: int = 120

    def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float) -> str:
        url = self.base_url.rstrip("/") + "/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise OllamaError(f"Ollama HTTP error {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise OllamaError(f"Ollama connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise OllamaError("Ollama request timed out.") from exc
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned invalid JSON.") from exc

        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama response did not contain message.content.")
        return content.strip()


def test_ollama(base_url: str, model: str, timeout_seconds: int = 120) -> str:
    client = OllamaClient(base_url=base_url, timeout_seconds=timeout_seconds)
    return client.chat(
        model=model,
        messages=[
            {"role": "system", "content": "Reply with a short confirmation only."},
            {"role": "user", "content": "Say wm-docgen-ok."},
        ],
        temperature=0.0,
    )
