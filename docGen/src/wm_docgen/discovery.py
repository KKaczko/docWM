"""Filesystem discovery for real and reconstructed webMethods packages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from wm_docgen.flow_parser import FlowParser
from wm_docgen.graph import classify_dependencies
from wm_docgen.models import Package, ScanResult, Service, ValidationIssue
from wm_docgen.node_parser import NodeParser
from wm_docgen.validation import validate_scan_result
from wm_docgen.xml_utils import safe_slug, service_id_to_parts


@dataclass(slots=True)
class ServiceArtifact:
    service_id: str
    package_name: str
    namespace_path: str
    service_name: str
    flow_path: Path
    node_path: Path | None
    structure_inferred: bool
    inference_notes: list[str]
    package_root: Path


def scan_source(source: Path, service_id_override: str | None = None) -> ScanResult:
    source = source.resolve()
    artifacts, packages, discovery_issues = discover_service_artifacts(source, service_id_override)
    result = ScanResult(packages=packages)
    discovery_issues_by_service: dict[str, list[ValidationIssue]] = {}
    for issue in discovery_issues:
        if issue.service_id:
            discovery_issues_by_service.setdefault(issue.service_id, []).append(issue)
        else:
            result.validation_issues.append(issue)

    flow_parser = FlowParser()
    node_parser = NodeParser()
    for artifact in artifacts:
        service = _parse_artifact(artifact, flow_parser, node_parser)
        service.warnings = discovery_issues_by_service.get(service.id, []) + service.warnings
        result.services.append(service)
        result.validation_issues.extend(service.warnings)

    package_map = {package.name: package for package in result.packages}
    for service in result.services:
        package = package_map.get(service.package)
        if package and service.id not in package.services:
            package.services.append(service.id)

    result.dependencies, result.external_dependencies = classify_dependencies(result.services)
    validation_issues = validate_scan_result(result)
    result.validation_issues.extend(validation_issues)
    return result


def discover_service_artifacts(
    source: Path, service_id_override: str | None = None
) -> tuple[list[ServiceArtifact], list[Package], list[ValidationIssue]]:
    artifacts: list[ServiceArtifact] = []
    packages: list[Package] = []
    issues: list[ValidationIssue] = []
    package_roots = _find_package_roots(source)
    covered_roots: list[Path] = []

    for package_root in package_roots:
        package_name = package_root.name
        packages.append(Package(name=package_name, root_path=str(package_root), structure_inferred=False))
        covered_roots.append(package_root)
        ns_root = package_root / "ns"
        for flow_path in sorted(ns_root.rglob("flow.xml")):
            service_id, namespace_path, service_name = _service_id_from_ns_path(ns_root, flow_path)
            node_path = flow_path.with_name("node.ndf")
            if not node_path.exists():
                issues.append(
                    ValidationIssue(
                        code="NODE_FILE_MISSING",
                        severity="warning",
                        message="flow.xml has no sibling node.ndf; signature will be unknown.",
                        file=str(flow_path),
                        service_id=service_id,
                    )
                )
                node_path = None
            artifacts.append(
                ServiceArtifact(
                    service_id=service_id,
                    package_name=package_name,
                    namespace_path=namespace_path,
                    service_name=service_name,
                    flow_path=flow_path,
                    node_path=node_path,
                    structure_inferred=False,
                    inference_notes=[],
                    package_root=package_root,
                )
            )

    orphan_flows = _find_orphan_flows(source, covered_roots)
    if orphan_flows:
        synthetic_package = "synthetic.current"
        packages.append(
            Package(name=synthetic_package, root_path=str(source), structure_inferred=True)
        )
    for index, flow_path in enumerate(orphan_flows, start=1):
        default_service_id = "synthetic.current:flow_1" if len(orphan_flows) == 1 else f"synthetic.current:flow_{index}"
        service_id = service_id_override if service_id_override and len(orphan_flows) == 1 else default_service_id
        namespace_path, service_name = service_id_to_parts(service_id)
        node_path = _find_synthetic_node(flow_path, source)
        notes = [
            "No manifest.v3/ns package structure was found for this flow file.",
            "Package, namespace, and service name are inferred.",
        ]
        if node_path is None:
            issues.append(
                ValidationIssue(
                    code="NODE_FILE_MISSING",
                    severity="warning",
                    message="Synthetic service has no matching node.ndf; signature will be unknown.",
                    file=str(flow_path),
                    service_id=service_id,
                )
            )
        issues.append(
            ValidationIssue(
                code="INFERRED_STRUCTURE",
                severity="warning",
                message="Service structure is inferred because the artifacts are not inside a package ns tree.",
                file=str(flow_path),
                service_id=service_id,
            )
        )
        artifacts.append(
            ServiceArtifact(
                service_id=service_id,
                package_name="synthetic.current",
                namespace_path=namespace_path or "synthetic.current",
                service_name=service_name,
                flow_path=flow_path,
                node_path=node_path,
                structure_inferred=True,
                inference_notes=notes,
                package_root=source,
            )
        )

    return artifacts, packages, issues


def _parse_artifact(artifact: ServiceArtifact, flow_parser: FlowParser, node_parser: NodeParser) -> Service:
    service = Service(
        id=artifact.service_id,
        package=artifact.package_name,
        namespace_path=artifact.namespace_path,
        name=artifact.service_name,
        source_files={"flow": str(artifact.flow_path)},
        structure_inferred=artifact.structure_inferred,
        inference_notes=list(artifact.inference_notes),
    )
    if artifact.node_path:
        service.source_files["node"] = str(artifact.node_path)

    flow_result = flow_parser.parse(artifact.flow_path, artifact.service_id)
    if flow_result.root_step is not None:
        service.steps.append(flow_result.root_step)
    service.dependencies.extend(flow_result.dependencies)
    service.document_references.extend(flow_result.document_references)
    service.warnings.extend(flow_result.issues)

    if artifact.node_path:
        node_result = node_parser.parse(artifact.node_path, artifact.service_id)
        service.inputs = node_result.inputs
        service.outputs = node_result.outputs
        service.document_references.extend(node_result.document_references)
        service.warnings.extend(node_result.issues)

    service.document_references = _dedupe_document_refs(service.document_references)
    return service


def _find_package_roots(source: Path) -> list[Path]:
    roots = []
    for manifest in sorted(source.rglob("manifest.v3")):
        root = manifest.parent
        if (root / "ns").is_dir():
            roots.append(root)
    return _remove_nested_roots(roots)


def _remove_nested_roots(roots: list[Path]) -> list[Path]:
    cleaned: list[Path] = []
    for root in sorted(roots, key=lambda item: len(item.parts)):
        if any(_is_relative_to(root, existing) for existing in cleaned):
            continue
        cleaned.append(root)
    return cleaned


def _find_orphan_flows(source: Path, package_roots: list[Path]) -> list[Path]:
    flows: list[Path] = []
    for candidate in sorted(source.rglob("*.xml")):
        if any(_is_relative_to(candidate, root) for root in package_roots):
            continue
        if candidate.name != "flow.xml" and not candidate.name.lower().startswith("flow"):
            continue
        if _looks_like_flow(candidate):
            flows.append(candidate)
    return flows


def _looks_like_flow(path: Path) -> bool:
    try:
        for _event, element in ET.iterparse(path, events=("start",)):
            return element.tag == "FLOW"
    except ET.ParseError:
        return False
    return False


def _find_synthetic_node(flow_path: Path, source: Path) -> Path | None:
    sibling = flow_path.with_name("node.ndf")
    if sibling.exists():
        return sibling
    candidates = sorted(source.glob("node.ndf"))
    if len(candidates) == 1:
        return candidates[0]
    return None


def _service_id_from_ns_path(ns_root: Path, flow_path: Path) -> tuple[str, str, str]:
    relative_parent = flow_path.parent.relative_to(ns_root)
    parts = relative_parent.parts
    if not parts:
        return "root:flow", "", "flow"
    if len(parts) == 1:
        namespace_path = parts[0]
        service_name = parts[0]
    else:
        namespace_path = ".".join(parts[:-1])
        service_name = parts[-1]
    return f"{namespace_path}:{service_name}", namespace_path, service_name


def _dedupe_document_refs(refs):
    seen = set()
    unique = []
    for ref in refs:
        key = (ref.ref, ref.source, ref.context, ref.field_path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def service_doc_path(service_id: str) -> Path:
    namespace, name = service_id_to_parts(service_id)
    namespace_parts = [safe_slug(part) for part in namespace.split(".") if part]
    return Path(*namespace_parts, f"{safe_slug(name)}.md") if namespace_parts else Path(f"{safe_slug(name)}.md")
