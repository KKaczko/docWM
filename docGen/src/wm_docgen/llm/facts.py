"""Build compact fact packets for LLM enrichment."""

from __future__ import annotations

from typing import Any

from wm_docgen.models import ScanResult, Service
from wm_docgen.processes import ProcessAnalysis


def service_fact_packet(service: Service, *, limit: int = 40) -> dict[str, Any]:
    service_calls = [edge for edge in service.dependencies if edge.dependency_type == "service_call"]
    return {
        "service_id": service.id,
        "package": service.package,
        "service_type": service.service_type,
        "node_comment": service.node_comment,
        "inputs": _cap(service.inputs, limit),
        "outputs": _cap(service.outputs, limit),
        "invoked_services": _cap(
            [{"target": edge.target_service_id, "kind": edge.kind, "step_id": edge.step_id} for edge in service_calls],
            limit,
        ),
        "document_references": _cap([ref.to_dict() for ref in service.document_references], limit),
        "entity_actions": _cap([item.to_dict() for item in service.entity_actions], limit),
        "mapping_facts": _cap([item.to_dict() for item in service.mapping_facts], limit),
        "condition_facts": _cap([item.to_dict() for item in service.condition_facts], limit),
        "dynamic_invocations": _cap([item.to_dict() for item in service.dynamic_invocations], limit),
        "warnings": _cap([issue.to_dict() for issue in service.warnings], limit),
    }


def process_fact_packet(analysis: ProcessAnalysis, result: ScanResult, *, limit: int = 40) -> dict[str, Any]:
    service_by_id = {service.id: service for service in result.services}
    services = [service_by_id[service_id] for service_id in analysis.service_ids if service_id in service_by_id]
    return {
        "process_id": analysis.definition.id,
        "name": analysis.definition.name,
        "business_description": analysis.definition.business_description,
        "owners": analysis.definition.owners,
        "tags": analysis.definition.tags,
        "entrypoints": analysis.definition.entrypoints,
        "business_steps": [step.to_dict() for step in analysis.definition.business_steps],
        "services": _cap([service.id for service in services], limit),
        "external_dependencies": _cap(analysis.dependencies, limit),
        "dynamic_invocations": _cap([item.to_dict() for item in analysis.dynamic_invocations], limit),
        "entity_actions": _cap(
            [action.to_dict() for service in services for action in service.entity_actions],
            limit,
        ),
        "mapping_facts": _cap(
            [fact.to_dict() for service in services for fact in service.mapping_facts],
            limit,
        ),
        "condition_facts": _cap(
            [fact.to_dict() for service in services for fact in service.condition_facts],
            limit,
        ),
        "warnings": _cap(
            [issue.to_dict() for issue in analysis.issues] + [issue.to_dict() for service in services for issue in service.warnings],
            limit,
        ),
    }


def business_summary_fact_packet(processes: list[ProcessAnalysis], result: ScanResult, *, limit: int = 40) -> dict[str, Any]:
    return {
        "package_count": len(result.packages),
        "service_count": len(result.services),
        "document_type_count": len(result.document_types),
        "processes": _cap(
            [
                {
                    "process_id": analysis.definition.id,
                    "name": analysis.definition.name,
                    "business_description": analysis.definition.business_description,
                    "owners": analysis.definition.owners,
                    "tags": analysis.definition.tags,
                    "entrypoints": analysis.definition.entrypoints,
                    "business_steps": [step.to_dict() for step in analysis.definition.business_steps],
                    "service_count": len(analysis.service_ids),
                    "external_dependencies": analysis.dependencies,
                    "warning_count": len(analysis.issues) + sum(
                        1 for service in result.services if service.id in analysis.service_ids for _issue in service.warnings
                    ),
                }
                for analysis in processes
            ],
            limit,
        ),
    }


def _cap(items: list[Any], limit: int) -> dict[str, Any]:
    if len(items) <= limit:
        return {"items": items, "omitted_count": 0}
    return {"items": items[:limit], "omitted_count": len(items) - limit}
