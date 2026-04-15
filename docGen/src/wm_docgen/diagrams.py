"""Mermaid diagram generation."""

from __future__ import annotations

from wm_docgen.models import DependencyEdge, Service
from wm_docgen.xml_utils import safe_slug


def service_dependency_diagram(service: Service) -> str:
    lines = ["graph TD"]
    source_node = _node_id(service.id)
    lines.append(f'  {source_node}["{_escape_label(service.id)}"]')
    service_edges = [edge for edge in service.dependencies if edge.dependency_type == "service_call"]
    if not service_edges:
        lines.append(f'  {source_node} --> no_calls["No service calls detected"]')
        return "\n".join(lines)
    for edge in service_edges:
        target_node = _node_id(edge.target_service_id)
        label = edge.kind.replace("_", " ")
        lines.append(f'  {source_node} -->|{label}| {target_node}["{_escape_label(edge.target_service_id)}"]')
    return "\n".join(lines)


def process_dependency_diagram(service_ids: list[str], edges: list[DependencyEdge]) -> str:
    lines = ["graph TD"]
    included = set(service_ids)
    for service_id in service_ids:
        lines.append(f'  {_node_id(service_id)}["{_escape_label(service_id)}"]')
    for edge in edges:
        if edge.dependency_type != "service_call":
            continue
        if edge.source_service_id not in included:
            continue
        target = edge.target_service_id
        if edge.kind == "internal" and target not in included:
            continue
        target_node = _node_id(target)
        label = edge.kind.replace("_", " ")
        lines.append(f'  {_node_id(edge.source_service_id)} -->|{label}| {target_node}["{_escape_label(target)}"]')
    return "\n".join(lines)


def _node_id(value: str) -> str:
    return "n_" + safe_slug(value).replace(".", "_")


def _escape_label(value: str) -> str:
    return value.replace('"', '\\"')
