"""Hash-based LLM response cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class LlmCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> str | None:
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        content = data.get("content")
        return content if isinstance(content, str) else None

    def set(self, key: str, content: str, metadata: dict[str, Any]) -> None:
        path = self.cache_dir / f"{key}.json"
        path.write_text(
            json.dumps({"content": content, "metadata": metadata}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
