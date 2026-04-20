"""LLM enrichment orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from wm_docgen.llm.cache import LlmCache, cache_key
from wm_docgen.llm.config import LlmConfig
from wm_docgen.llm.facts import business_summary_fact_packet, process_fact_packet, service_fact_packet
from wm_docgen.llm.ollama_client import OllamaClient, OllamaError
from wm_docgen.llm.openai_compatible_client import OpenAICompatibleClient, OpenAICompatibleError
from wm_docgen.llm.prompts import PROMPT_VERSION, business_summary_messages, process_messages, service_messages
from wm_docgen.models import LlmEnrichment, ScanResult, ValidationIssue
from wm_docgen.processes import ProcessAnalysis


class ChatClient(Protocol):
    def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float) -> str:
        ...


@dataclass(slots=True)
class EnrichmentResult:
    issues: list[ValidationIssue]


def enrich_with_llm(result: ScanResult, processes: list[ProcessAnalysis], config: LlmConfig) -> EnrichmentResult:
    client = _client_for_config(config)
    if client is None:
        return EnrichmentResult(issues=[])

    cache = LlmCache(config.cache_dir)
    issues: list[ValidationIssue] = []

    for service in result.services:
        packet = service_fact_packet(service, limit=config.fact_limit)
        enrichment, issue = _enrich_target(
            client=client,
            cache=cache,
            config=config,
            target_id=service.id,
            target_type="service",
            packet=packet,
            messages=service_messages(packet),
        )
        if enrichment:
            service.llm_enrichment = enrichment
            result.llm_enrichments.append(enrichment)
        if issue:
            service.warnings.append(issue)
            issues.append(issue)

    for analysis in processes:
        packet = process_fact_packet(analysis, result, limit=config.fact_limit)
        enrichment, issue = _enrich_target(
            client=client,
            cache=cache,
            config=config,
            target_id=analysis.definition.id,
            target_type="process",
            packet=packet,
            messages=process_messages(packet),
        )
        if enrichment:
            analysis.llm_enrichment = enrichment
            result.llm_enrichments.append(enrichment)
        if issue:
            analysis.issues.append(issue)
            issues.append(issue)

    packet = business_summary_fact_packet(processes, result, limit=config.fact_limit)
    enrichment, issue = _enrich_target(
        client=client,
        cache=cache,
        config=config,
        target_id="business-summary",
        target_type="business_summary",
        packet=packet,
        messages=business_summary_messages(packet),
    )
    if enrichment:
        result.llm_enrichments.append(enrichment)
        # Store on the result via the conventional target id; docs look it up there.
    if issue:
        issues.append(issue)

    result.validation_issues.extend(issues)
    return EnrichmentResult(issues=issues)


def _enrich_target(
    *,
    client: ChatClient,
    cache: LlmCache,
    config: LlmConfig,
    target_id: str,
    target_type: str,
    packet: dict[str, Any],
    messages: list[dict[str, str]],
) -> tuple[LlmEnrichment | None, ValidationIssue | None]:
    key_payload = {
        "provider": config.provider,
        "base_url": config.base_url,
        "model": config.model,
        "temperature": config.temperature,
        "prompt_version": PROMPT_VERSION,
        "target_type": target_type,
        "packet": packet,
    }
    key = cache_key(key_payload)
    if not config.refresh_cache:
        cached = cache.get(key)
        if cached:
            return (
                LlmEnrichment(
                    target_id=target_id,
                    target_type=target_type,
                    provider=config.provider,
                    model=config.model,
                    content=cached,
                    prompt_version=PROMPT_VERSION,
                    cache_key=key,
                    from_cache=True,
                ),
                None,
            )

    try:
        content = client.chat(model=config.model, messages=messages, temperature=config.temperature)
    except (OllamaError, OpenAICompatibleError) as exc:
        return None, ValidationIssue(
            code="LLM_ENRICHMENT_SKIPPED",
            severity="warning",
            message=f"LLM enrichment skipped for {target_type} {target_id!r}: {exc}",
            service_id=target_id if target_type == "service" else None,
        )

    cache.set(key, content, {"target_id": target_id, "target_type": target_type, "model": config.model})
    return (
        LlmEnrichment(
            target_id=target_id,
            target_type=target_type,
            provider=config.provider,
            model=config.model,
            content=content,
            prompt_version=PROMPT_VERSION,
            cache_key=key,
            from_cache=False,
        ),
        None,
    )


def _client_for_config(config: LlmConfig) -> ChatClient | None:
    if config.provider == "ollama":
        return OllamaClient(base_url=config.base_url, timeout_seconds=config.timeout_seconds)
    if config.provider == "openai-compatible":
        return OpenAICompatibleClient(
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
            api_key=config.api_key,
        )
    return None
