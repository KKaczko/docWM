"""Domain model for parsed webMethods package documentation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    file: str | None = None
    path: str | None = None
    service_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DocumentReference:
    ref: str
    source: str
    context: str
    field_path: str | None = None
    inferred: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DependencyEdge:
    source_service_id: str
    target_service_id: str
    kind: str
    dependency_type: str = "service_call"
    raw_target: str | None = None
    step_id: str | None = None
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExternalDependency:
    id: str
    kind: str
    name: str
    source_service_id: str
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DynamicInvocation:
    source_service_id: str
    invoker_service: str
    step_id: str
    evidence: str
    candidate_fields: list[str] = field(default_factory=list)
    candidate_values: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Step:
    id: str
    kind: str
    name: str | None = None
    comment: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    service: str | None = None
    children: list["Step"] = field(default_factory=list)
    mapping_operations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "comment": self.comment,
            "attributes": dict(self.attributes),
            "service": self.service,
            "children": [child.to_dict() for child in self.children],
            "mapping_operations": list(self.mapping_operations),
        }


@dataclass(slots=True)
class Service:
    id: str
    package: str
    namespace_path: str
    name: str
    source_files: dict[str, str]
    service_type: str = "flow_service"
    node_type: str | None = None
    node_subtype: str | None = None
    node_comment: str | None = None
    structure_inferred: bool = False
    inference_notes: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    dependencies: list[DependencyEdge] = field(default_factory=list)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    document_references: list[DocumentReference] = field(default_factory=list)
    dynamic_invocations: list[DynamicInvocation] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "package": self.package,
            "namespace_path": self.namespace_path,
            "name": self.name,
            "source_files": dict(self.source_files),
            "service_type": self.service_type,
            "node_type": self.node_type,
            "node_subtype": self.node_subtype,
            "node_comment": self.node_comment,
            "structure_inferred": self.structure_inferred,
            "inference_notes": list(self.inference_notes),
            "steps": [step.to_dict() for step in self.steps],
            "dependencies": [edge.to_dict() for edge in self.dependencies],
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "document_references": [ref.to_dict() for ref in self.document_references],
            "dynamic_invocations": [item.to_dict() for item in self.dynamic_invocations],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }


@dataclass(slots=True)
class DocumentType:
    id: str
    package: str
    namespace_path: str
    name: str
    source_files: dict[str, str]
    node_type: str | None = None
    node_subtype: str | None = None
    node_comment: str | None = None
    fields: list[dict[str, Any]] = field(default_factory=list)
    document_references: list[DocumentReference] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "package": self.package,
            "namespace_path": self.namespace_path,
            "name": self.name,
            "source_files": dict(self.source_files),
            "node_type": self.node_type,
            "node_subtype": self.node_subtype,
            "node_comment": self.node_comment,
            "fields": list(self.fields),
            "document_references": [ref.to_dict() for ref in self.document_references],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }


@dataclass(slots=True)
class Package:
    name: str
    root_path: str
    services: list[str] = field(default_factory=list)
    structure_inferred: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BusinessStep:
    id: str
    name: str
    services: list[str]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProcessDefinition:
    id: str
    name: str
    entrypoints: list[str]
    business_description: str = ""
    owners: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    business_steps: list[BusinessStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScanResult:
    packages: list[Package] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)
    document_types: list[DocumentType] = field(default_factory=list)
    dependencies: list[DependencyEdge] = field(default_factory=list)
    external_dependencies: list[ExternalDependency] = field(default_factory=list)
    validation_issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "packages": [package.to_dict() for package in self.packages],
            "services": [service.to_dict() for service in self.services],
            "document_types": [document.to_dict() for document in self.document_types],
            "dependencies": [edge.to_dict() for edge in self.dependencies],
            "external_dependencies": [dep.to_dict() for dep in self.external_dependencies],
            "validation_issues": [issue.to_dict() for issue in self.validation_issues],
        }
