"""Dependency classification and graph helpers."""

from __future__ import annotations

from wm_docgen.models import DependencyEdge, ExternalDependency, Service


def classify_dependencies(services: list[Service]) -> tuple[list[DependencyEdge], list[ExternalDependency]]:
    known_service_ids = {service.id for service in services}
    all_edges: list[DependencyEdge] = []
    external_dependencies: dict[tuple[str, str, str], ExternalDependency] = {}

    for service in services:
        classified: list[DependencyEdge] = []
        for edge in service.dependencies:
            edge.kind = classify_service_target(edge.raw_target or edge.target_service_id, known_service_ids)
            classified.append(edge)
            all_edges.append(edge)
            if edge.kind in {"pub_service", "external_service", "unresolved"}:
                key = (service.id, edge.kind, edge.raw_target or edge.target_service_id)
                external_dependencies[key] = ExternalDependency(
                    id=f"{service.id}->{edge.raw_target or edge.target_service_id}",
                    kind=edge.kind,
                    name=edge.raw_target or edge.target_service_id,
                    source_service_id=service.id,
                    evidence=edge.evidence,
                )

        for doc_ref in service.document_references:
            doc_edge = DependencyEdge(
                source_service_id=service.id,
                target_service_id=doc_ref.ref,
                raw_target=doc_ref.ref,
                kind="document_reference",
                dependency_type="document_reference",
                evidence=doc_ref.context,
            )
            classified.append(doc_edge)
            all_edges.append(doc_edge)

        service.dependencies = classified

    return all_edges, list(external_dependencies.values())


def classify_service_target(target: str, known_service_ids: set[str]) -> str:
    if not target:
        return "unresolved"
    if target in known_service_ids:
        return "internal"
    if target.startswith("pub.") or target.startswith("wm."):
        return "pub_service"
    if ":" in target:
        return "external_service"
    return "unresolved"


def service_call_targets(service: Service, *, internal_only: bool = False) -> list[str]:
    targets: list[str] = []
    for edge in service.dependencies:
        if edge.dependency_type != "service_call":
            continue
        if internal_only and edge.kind != "internal":
            continue
        targets.append(edge.target_service_id)
    return targets
