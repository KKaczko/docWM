"""Filesystem discovery for real and reconstructed webMethods packages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from wm_docgen.flow_parser import FlowParser
from wm_docgen.graph import classify_dependencies
from wm_docgen.models import DocumentType, Package, ScanResult, Service, ValidationIssue
from wm_docgen.node_parser import NodeParser
from wm_docgen.validation import validate_scan_result
from wm_docgen.xml_utils import direct_value, safe_slug, service_id_to_parts


@dataclass(slots=True)
class ServiceArtifact:
    service_id: str
    package_name: str
    namespace_path: str
    service_name: str
    flow_path: Path | None
    node_path: Path | None
    service_type: str
    structure_inferred: bool
    inference_notes: list[str]
    package_root: Path


@dataclass(slots=True)
class DocumentArtifact:
    document_id: str
    package_name: str
    namespace_path: str
    name: str
    node_path: Path
    package_root: Path


def scan_source(source: Path, service_id_override: str | None = None) -> ScanResult:
    source = source.resolve()
    artifacts, documents, packages, discovery_issues = discover_service_artifacts(source, service_id_override)
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
    for document in documents:
        document_type = _parse_document_artifact(document, node_parser)
        result.document_types.append(document_type)
        result.validation_issues.extend(document_type.warnings)

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
) -> tuple[list[ServiceArtifact], list[DocumentArtifact], list[Package], list[ValidationIssue]]:
    artifacts: list[ServiceArtifact] = []
    documents: list[DocumentArtifact] = []
    packages: list[Package] = []
    issues: list[ValidationIssue] = []
    package_roots = _find_package_roots(source)
    covered_roots: list[Path] = []

    for package_root in package_roots:
        package_name = package_root.name
        packages.append(Package(name=package_name, root_path=str(package_root), structure_inferred=False))
        covered_roots.append(package_root)
        ns_root = package_root / "ns"
        consumed_nodes: set[Path] = set()
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
            else:
                consumed_nodes.add(node_path)
            artifacts.append(
                ServiceArtifact(
                    service_id=service_id,
                    package_name=package_name,
                    namespace_path=namespace_path,
                    service_name=service_name,
                    flow_path=flow_path,
                    node_path=node_path,
                    service_type="flow_service",
                    structure_inferred=False,
                    inference_notes=[],
                    package_root=package_root,
                )
            )
        for node_path in sorted(ns_root.rglob("node.ndf")):
            if node_path in consumed_nodes:
                continue
            node_kind = _classify_node(node_path)
            node_id, namespace_path, node_name = _service_id_from_ns_path(ns_root, node_path)
            if node_kind == "java_service":
                java_path, java_issue = _find_java_source(package_root, node_name, node_id)
                source_notes = [] if java_path else ["Java implementation source could not be uniquely resolved."]
                artifact = ServiceArtifact(
                    service_id=node_id,
                    package_name=package_name,
                    namespace_path=namespace_path,
                    service_name=node_name,
                    flow_path=None,
                    node_path=node_path,
                    service_type="java_service",
                    structure_inferred=False,
                    inference_notes=source_notes,
                    package_root=package_root,
                )
                artifacts.append(artifact)
                if java_issue:
                    issues.append(java_issue)
            elif node_kind == "document_type":
                documents.append(
                    DocumentArtifact(
                        document_id=node_id,
                        package_name=package_name,
                        namespace_path=namespace_path,
                        name=node_name,
                        node_path=node_path,
                        package_root=package_root,
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        code="UNKNOWN_NODE_TYPE",
                        severity="warning",
                        message="node.ndf is neither a supported service nor a document type.",
                        file=str(node_path),
                        service_id=node_id,
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
                    service_type="flow_service",
                    structure_inferred=True,
                    inference_notes=notes,
                    package_root=source,
                )
            )

    return artifacts, documents, packages, issues


def _parse_artifact(artifact: ServiceArtifact, flow_parser: FlowParser, node_parser: NodeParser) -> Service:
    source_files = {}
    if artifact.flow_path:
        source_files["flow"] = str(artifact.flow_path)
    if artifact.node_path:
        source_files["node"] = str(artifact.node_path)
    if artifact.service_type == "java_service":
        java_path, _java_issue = _find_java_source(artifact.package_root, artifact.service_name, artifact.service_id)
        if java_path:
            source_files["java"] = str(java_path)
    service = Service(
        id=artifact.service_id,
        package=artifact.package_name,
        namespace_path=artifact.namespace_path,
        name=artifact.service_name,
        source_files=source_files,
        service_type=artifact.service_type,
        structure_inferred=artifact.structure_inferred,
        inference_notes=list(artifact.inference_notes),
    )

    if artifact.flow_path:
        flow_result = flow_parser.parse(artifact.flow_path, artifact.service_id)
        if flow_result.root_step is not None:
            service.steps.append(flow_result.root_step)
        service.dependencies.extend(flow_result.dependencies)
        service.document_references.extend(flow_result.document_references)
        service.dynamic_invocations.extend(flow_result.dynamic_invocations)
        service.warnings.extend(flow_result.issues)

    if artifact.node_path:
        node_result = node_parser.parse(artifact.node_path, artifact.service_id)
        service.node_type = node_result.metadata.get("node_type")
        service.node_subtype = node_result.metadata.get("node_subtype") or node_result.metadata.get("svc_subtype")
        service.node_comment = node_result.metadata.get("node_comment")
        service.inputs = node_result.inputs
        service.outputs = node_result.outputs
        service.document_references.extend(node_result.document_references)
        service.warnings.extend(node_result.issues)

    service.document_references = _dedupe_document_refs(service.document_references)
    return service


def _parse_document_artifact(artifact: DocumentArtifact, node_parser: NodeParser) -> DocumentType:
    result = node_parser.parse(artifact.node_path, artifact.document_id, expect_signature=False)
    return DocumentType(
        id=artifact.document_id,
        package=artifact.package_name,
        namespace_path=artifact.namespace_path,
        name=artifact.name,
        source_files={"node": str(artifact.node_path)},
        node_type=result.metadata.get("node_type"),
        node_subtype=result.metadata.get("node_subtype"),
        node_comment=result.metadata.get("node_comment"),
        fields=result.fields,
        document_references=result.document_references,
        warnings=result.issues,
    )


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


def _classify_node(node_path: Path) -> str:
    try:
        root = ET.parse(node_path).getroot()
    except ET.ParseError:
        return "unknown_node"
    svc_type = (direct_value(root, "svc_type") or "").lower()
    if svc_type == "java":
        return "java_service"
    if svc_type:
        return "unknown_node"
    if root.find("./record[@name='svc_sig']") is not None:
        return "unknown_node"
    if root.findall(".//array[@name='rec_fields']") or direct_value(root, "node_type") == "record":
        return "document_type"
    return "unknown_node"


def _find_java_source(
    package_root: Path, service_name: str, service_id: str
) -> tuple[Path | None, ValidationIssue | None]:
    candidates = sorted(path for path in package_root.rglob("*.java") if path.stem == service_name)
    if len(candidates) == 1:
        return candidates[0], None
    if not candidates:
        return None, ValidationIssue(
            code="JAVA_SOURCE_NOT_FOUND",
            severity="warning",
            message="Java service implementation source could not be found by service name.",
            file=str(package_root),
            service_id=service_id,
        )
    return None, ValidationIssue(
        code="JAVA_SOURCE_AMBIGUOUS",
        severity="warning",
        message="Multiple Java source files match the service name; implementation source is unresolved.",
        file=str(package_root),
        service_id=service_id,
    )


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


def document_doc_path(document_id: str) -> Path:
    namespace, name = service_id_to_parts(document_id)
    namespace_parts = [safe_slug(part) for part in namespace.split(".") if part]
    return Path(*namespace_parts, f"{safe_slug(name)}.md") if namespace_parts else Path(f"{safe_slug(name)}.md")
