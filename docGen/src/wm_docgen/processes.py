"""Process configuration loading and dependency traversal."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from wm_docgen.graph import service_call_targets
from wm_docgen.models import ProcessDefinition, Service, ValidationIssue


@dataclass(slots=True)
class ProcessAnalysis:
    definition: ProcessDefinition
    service_ids: list[str]
    dependencies: list[str]
    issues: list[ValidationIssue]


def load_processes(path: Path | None) -> list[ProcessDefinition]:
    if path is None or not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get("processes", data if isinstance(data, list) else [])
    processes: list[ProcessDefinition] = []
    for item in items:
        processes.append(
            ProcessDefinition(
                id=str(item["id"]),
                name=str(item.get("name") or item["id"]),
                entrypoints=[str(value) for value in item.get("entrypoints", [])],
                business_description=str(item.get("business_description") or ""),
                owners=[str(value) for value in item.get("owners", [])],
                tags=[str(value) for value in item.get("tags", [])],
            )
        )
    return processes


def analyze_processes(processes: list[ProcessDefinition], services: list[Service]) -> list[ProcessAnalysis]:
    service_by_id = {service.id: service for service in services}
    analyses: list[ProcessAnalysis] = []
    for process in processes:
        issues: list[ValidationIssue] = []
        visited: set[str] = set()
        stack = list(reversed(process.entrypoints))
        ordered: list[str] = []
        while stack:
            service_id = stack.pop()
            if service_id in visited:
                continue
            visited.add(service_id)
            service = service_by_id.get(service_id)
            if service is None:
                issues.append(
                    ValidationIssue(
                        code="PROCESS_ENTRYPOINT_MISSING",
                        severity="warning",
                        message=f"Process entrypoint or dependency {service_id!r} was not found in the scanned services.",
                        service_id=service_id,
                    )
                )
                continue
            ordered.append(service_id)
            targets = service_call_targets(service, internal_only=True)
            stack.extend(reversed([target for target in targets if target not in visited]))

        external_dependencies = []
        for service_id in ordered:
            service = service_by_id[service_id]
            for edge in service.dependencies:
                if edge.dependency_type == "service_call" and edge.kind != "internal":
                    external_dependencies.append(edge.target_service_id)
        analyses.append(
            ProcessAnalysis(
                definition=process,
                service_ids=ordered,
                dependencies=sorted(set(external_dependencies)),
                issues=issues,
            )
        )
    return analyses
