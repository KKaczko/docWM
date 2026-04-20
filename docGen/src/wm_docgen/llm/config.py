"""LLM enrichment configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

import yaml


@dataclass(slots=True)
class LlmConfig:
    provider: str = "none"
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1"
    api_key_env: str | None = None
    api_key: str | None = None
    temperature: float = 0.1
    timeout_seconds: int = 120
    enabled_sections: list[str] = field(
        default_factory=lambda: ["service_summary", "process_summary", "entity_flow"]
    )
    cache_dir: Path = Path("build/docgen/llm-cache")
    refresh_cache: bool = False
    fact_limit: int = 40


def load_llm_config(
    config_path: Path | None,
    *,
    provider: str = "none",
    base_url: str | None = None,
    model: str | None = None,
    api_key_env: str | None = None,
    timeout_seconds: int | None = None,
    cache_dir: Path | None = None,
    refresh_cache: bool = False,
) -> LlmConfig:
    data = {}
    if config_path and config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        data = raw.get("llm", raw if isinstance(raw, dict) else {})

    configured_provider = str(data.get("provider") or "none")
    requested_provider = str(provider or "")
    effective_provider = requested_provider if requested_provider and requested_provider != "none" else configured_provider
    default_base_url = "http://localhost:11434/v1" if effective_provider == "openai-compatible" else "http://localhost:11434"
    resolved_api_key_env = str(data.get("api_key_env") or "") or None
    direct_api_key = str(data.get("api_key") or "") or None

    config = LlmConfig(
        provider=effective_provider,
        base_url=str(data.get("base_url") or default_base_url),
        model=str(data.get("model") or "llama3.1"),
        api_key_env=resolved_api_key_env,
        api_key=direct_api_key or (os.environ.get(resolved_api_key_env) if resolved_api_key_env else None),
        temperature=float(data.get("temperature", 0.1)),
        timeout_seconds=int(data.get("timeout_seconds", 120)),
        enabled_sections=[str(value) for value in data.get("enabled_sections", [])]
        or ["service_summary", "process_summary", "entity_flow"],
        cache_dir=Path(data.get("cache_dir") or "build/docgen/llm-cache"),
        refresh_cache=bool(data.get("refresh_cache", False)),
        fact_limit=int(data.get("fact_limit", 40)),
    )

    if provider and provider != "none":
        config.provider = provider
    if base_url:
        config.base_url = base_url
    if model:
        config.model = model
    if api_key_env:
        config.api_key_env = api_key_env
        config.api_key = os.environ.get(api_key_env)
    if timeout_seconds is not None:
        config.timeout_seconds = timeout_seconds
    if cache_dir:
        config.cache_dir = cache_dir
    if refresh_cache:
        config.refresh_cache = True
    return config
