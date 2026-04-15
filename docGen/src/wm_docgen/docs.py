"""Markdown and MkDocs output generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import yaml

from wm_docgen.diagrams import process_dependency_diagram, service_dependency_diagram
from wm_docgen.discovery import service_doc_path
from wm_docgen.models import ScanResult, Service, Step
from wm_docgen.processes import ProcessAnalysis
from wm_docgen.xml_utils import safe_slug


def write_json(result: ScanResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


def generate_docs(result: ScanResult, docs_dir: Path, process_analyses: list[ProcessAnalysis]) -> None:
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "services").mkdir(parents=True, exist_ok=True)
    (docs_dir / "processes").mkdir(parents=True, exist_ok=True)
    (docs_dir / "reports").mkdir(parents=True, exist_ok=True)

    (docs_dir / "index.md").write_text(_index_markdown(result), encoding="utf-8")
    for service in result.services:
        page_path = docs_dir / "services" / service_doc_path(service.id)
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(_service_markdown(service), encoding="utf-8")

    for analysis in process_analyses:
        page_path = docs_dir / "processes" / f"{safe_slug(analysis.definition.id)}.md"
        page_path.write_text(_process_markdown(analysis, result), encoding="utf-8")

    (docs_dir / "reports" / "summary.md").write_text(_summary_markdown(result), encoding="utf-8")


def write_mkdocs_config(path: Path, docs_dir: Path, result: ScanResult, processes: list[ProcessAnalysis]) -> None:
    nav: list[dict[str, object]] = [
        {"Home": "index.md"},
        {"Summary": "reports/summary.md"},
    ]
    if result.services:
        nav.append(
            {
                "Services": [
                    {service.id: str(Path("services") / service_doc_path(service.id))}
                    for service in sorted(result.services, key=lambda item: item.id)
                ]
            }
        )
    if processes:
        nav.append(
            {
                "Processes": [
                    {analysis.definition.name: f"processes/{safe_slug(analysis.definition.id)}.md"}
                    for analysis in processes
                ]
            }
        )
    config = {
        "site_name": "webMethods Documentation",
        "docs_dir": str(docs_dir),
        "theme": {"name": "material"},
        "markdown_extensions": ["tables", "fenced_code"],
        "nav": nav,
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _index_markdown(result: ScanResult) -> str:
    return "\n".join(
        [
            "# webMethods Documentation",
            "",
            f"- Packages: {len(result.packages)}",
            f"- Services: {len(result.services)}",
            f"- Dependencies: {len(result.dependencies)}",
            f"- Validation issues: {len(result.validation_issues)}",
            "",
            "Generated from parsed webMethods Integration Server artifacts.",
            "",
        ]
    )


def _service_markdown(service: Service) -> str:
    lines = [
        f"# {service.id}",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Package | `{service.package}` |",
        f"| Namespace | `{service.namespace_path}` |",
        f"| Service | `{service.name}` |",
        f"| Structure | {'inferred' if service.structure_inferred else 'real package path'} |",
        "",
    ]
    if service.inference_notes:
        lines.extend(["## Inference Notes", ""])
        lines.extend(f"- {note}" for note in service.inference_notes)
        lines.append("")

    lines.extend(["## Source Files", ""])
    for label, path in service.source_files.items():
        lines.append(f"- {label}: `{path}`")
    lines.append("")

    warnings = [issue for issue in service.warnings if issue.severity in {"warning", "error"}]
    if warnings:
        lines.extend(["## Warnings", ""])
        for issue in warnings:
            location = f" ({issue.file})" if issue.file else ""
            lines.append(f"- `{issue.code}`: {issue.message}{location}")
        lines.append("")

    lines.extend(["## Inputs", ""])
    lines.extend(_field_lines(service.inputs) or ["_Unknown._"])
    lines.extend(["", "## Outputs", ""])
    lines.extend(_field_lines(service.outputs) or ["_Unknown._"])
    lines.append("")

    lines.extend(["## Invoked Services", ""])
    service_calls = [edge for edge in service.dependencies if edge.dependency_type == "service_call"]
    if service_calls:
        lines.extend(["| Target | Kind | Step |", "| --- | --- | --- |"])
        for edge in service_calls:
            lines.append(f"| `{edge.target_service_id}` | `{edge.kind}` | `{edge.step_id or ''}` |")
    else:
        lines.append("_No service calls detected._")
    lines.append("")

    lines.extend(["## Document References", ""])
    if service.document_references:
        for ref in service.document_references:
            field = f" `{ref.field_path}`" if ref.field_path else ""
            lines.append(f"- `{ref.ref}` from {ref.context}{field}")
    else:
        lines.append("_No document references detected._")
    lines.append("")

    lines.extend(["## Dependency Diagram", "", "```mermaid", service_dependency_diagram(service), "```", ""])
    lines.extend(["## Steps", ""])
    for step in service.steps:
        lines.extend(_step_lines(step))
    lines.append("")
    return "\n".join(lines)


def _process_markdown(analysis: ProcessAnalysis, result: ScanResult) -> str:
    service_by_id = {service.id: service for service in result.services}
    process = analysis.definition
    process_edges = [edge for edge in result.dependencies if edge.source_service_id in analysis.service_ids]
    lines = [
        f"# {process.name}",
        "",
        process.business_description or "_No business description provided._",
        "",
        "## Entrypoints",
        "",
    ]
    lines.extend(f"- `{entrypoint}`" for entrypoint in process.entrypoints)
    lines.extend(["", "## Services", ""])
    if analysis.service_ids:
        lines.extend(f"- `{service_id}`" for service_id in analysis.service_ids)
    else:
        lines.append("_No services resolved for this process._")
    lines.extend(["", "## Dependencies", ""])
    if analysis.dependencies:
        lines.extend(f"- `{dependency}`" for dependency in analysis.dependencies)
    else:
        lines.append("_No external dependencies detected._")
    lines.extend(["", "## Diagram", "", "```mermaid", process_dependency_diagram(analysis.service_ids, process_edges), "```", ""])
    lines.extend(["## Risks And Unknowns", ""])
    risks = list(analysis.issues)
    for service_id in analysis.service_ids:
        risks.extend(service_by_id[service_id].warnings)
    if risks:
        for issue in risks:
            lines.append(f"- `{issue.code}`: {issue.message}")
    else:
        lines.append("_No process-specific risks detected._")
    lines.append("")
    return "\n".join(lines)


def _summary_markdown(result: ScanResult) -> str:
    lines = [
        "# Summary Report",
        "",
        "## Packages",
        "",
    ]
    if result.packages:
        lines.extend(["| Package | Services | Inferred |", "| --- | ---: | --- |"])
        for package in result.packages:
            lines.append(f"| `{package.name}` | {len(package.services)} | {package.structure_inferred} |")
    else:
        lines.append("_No packages discovered._")
    lines.extend(["", "## Validation Issues", ""])
    if result.validation_issues:
        lines.extend(["| Severity | Code | Message | Service |", "| --- | --- | --- | --- |"])
        for issue in result.validation_issues:
            lines.append(
                f"| {issue.severity} | `{issue.code}` | {issue.message} | `{issue.service_id or ''}` |"
            )
    else:
        lines.append("_No validation issues._")
    lines.append("")
    return "\n".join(lines)


def _field_lines(fields: list[dict[str, object]], depth: int = 0) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth
    for field in fields:
        name = field.get("name") or "(unnamed)"
        field_type = field.get("field_type") or "unknown"
        rec_ref = f" -> `{field['rec_ref']}`" if field.get("rec_ref") else ""
        lines.append(f"{indent}- `{name}` ({field_type}){rec_ref}")
        children = field.get("children")
        if isinstance(children, list):
            lines.extend(_field_lines(children, depth + 1))
    return lines


def _step_lines(step: Step, depth: int = 0) -> list[str]:
    indent = "  " * depth
    parts = [f"`{step.kind}`"]
    if step.name:
        parts.append(f"name=`{step.name}`")
    if step.service:
        parts.append(f"service=`{step.service}`")
    if step.comment:
        parts.append(f"comment={step.comment!r}")
    if step.mapping_operations:
        parts.append(f"maps={len(step.mapping_operations)}")
    lines = [f"{indent}- " + " ".join(parts)]
    for child in step.children:
        lines.extend(_step_lines(child, depth + 1))
    return lines
