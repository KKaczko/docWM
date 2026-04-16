"""Parser for webMethods flow.xml files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from wm_docgen.models import (
    DependencyEdge,
    DocumentReference,
    DynamicInvocation,
    Step,
    ValidationIssue,
)
from wm_docgen.xml_utils import compact_xml

STEP_TAGS = {"FLOW", "SEQUENCE", "MAP", "MAPINVOKE", "INVOKE", "BRANCH", "LOOP", "EXIT"}
MAPPING_OPERATION_TAGS = {"MAPSET", "MAPCOPY", "MAPDELETE"}
DEFAULT_DYNAMIC_INVOKERS = {
    "pub.flow:invoke",
    "pub.flow:invokeWithPipeline",
    "tundra.service:invoke",
}
SERVICE_FIELD_HINTS = {"service", "servicename", "$service", "$servicename"}
KNOWN_PAYLOAD_TAGS = {
    "COMMENT",
    "MAPTARGET",
    "MAPSOURCE",
    "DATA",
    "Values",
    "record",
    "array",
    "value",
    "null",
}


@dataclass(slots=True)
class FlowParseResult:
    root_step: Step | None = None
    dependencies: list[DependencyEdge] = field(default_factory=list)
    document_references: list[DocumentReference] = field(default_factory=list)
    dynamic_invocations: list[DynamicInvocation] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)


class FlowParser:
    def __init__(self, dynamic_invokers: set[str] | None = None) -> None:
        self.dynamic_invokers = dynamic_invokers or DEFAULT_DYNAMIC_INVOKERS

    def parse(self, path: Path, service_id: str) -> FlowParseResult:
        result = FlowParseResult()
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            result.issues.append(
                ValidationIssue(
                    code="FLOW_XML_PARSE_ERROR",
                    severity="error",
                    message=f"Cannot parse flow XML: {exc}",
                    file=str(path),
                    service_id=service_id,
                )
            )
            return result

        if root.tag != "FLOW":
            result.issues.append(
                ValidationIssue(
                    code="FLOW_ROOT_UNSUPPORTED",
                    severity="error",
                    message=f"Expected FLOW root, found {root.tag!r}.",
                    file=str(path),
                    path=f"/{root.tag}",
                    service_id=service_id,
                )
            )
            return result

        result.root_step = self._parse_step(root, path, service_id, "0", f"/{root.tag}", result)
        result.document_references = _dedupe_document_refs(_extract_rec_refs(root, path, "flow"))
        return result

    def _parse_step(
        self,
        element: ET.Element,
        file_path: Path,
        service_id: str,
        step_id: str,
        xml_path: str,
        result: FlowParseResult,
    ) -> Step:
        comment = _child_comment(element)
        service = element.attrib.get("SERVICE")
        step = Step(
            id=step_id,
            kind=element.tag,
            name=element.attrib.get("NAME"),
            comment=comment,
            attributes=dict(element.attrib),
            service=service,
        )

        if service:
            step_name = step.name or step.kind
            result.dependencies.append(
                DependencyEdge(
                    source_service_id=service_id,
                    target_service_id=service,
                    kind="unclassified",
                    dependency_type="service_call",
                    raw_target=service,
                    step_id=step_id,
                    evidence=f"{step.kind} {step_name}",
                )
            )
            if service in self.dynamic_invokers:
                dynamic_invocation = _dynamic_invocation(element, service_id, service, step_id)
                result.dynamic_invocations.append(dynamic_invocation)
                result.issues.append(
                    ValidationIssue(
                        code="DYNAMIC_INVOKE_TARGET_UNKNOWN",
                        severity="warning",
                        message=(
                            f"Dynamic invocation via {service!r} at step {step_id}; "
                            "target cannot be resolved statically."
                        ),
                        file=str(file_path),
                        path=xml_path,
                        service_id=service_id,
                    )
                )

        child_step_index = 0
        for child in element:
            if child.tag == "COMMENT":
                continue
            child_path = f"{xml_path}/{child.tag}[{child_step_index}]"
            if child.tag in STEP_TAGS:
                child_step_id = f"{step_id}.{child_step_index}"
                step.children.append(
                    self._parse_step(child, file_path, service_id, child_step_id, child_path, result)
                )
                child_step_index += 1
            elif child.tag in MAPPING_OPERATION_TAGS:
                step.mapping_operations.append(_mapping_operation(child))
            elif child.tag in KNOWN_PAYLOAD_TAGS:
                continue
            else:
                result.issues.append(
                    ValidationIssue(
                        code="UNSUPPORTED_FLOW_NODE",
                        severity="warning",
                        message=f"Unsupported flow node {child.tag!r} under {element.tag!r}.",
                        file=str(file_path),
                        path=child_path,
                        service_id=service_id,
                    )
                )
        return step


def _child_comment(element: ET.Element) -> str | None:
    for child in element:
        if child.tag == "COMMENT":
            value = (child.text or "").strip()
            return value or None
    return None


def _mapping_operation(element: ET.Element) -> dict[str, Any]:
    return {
        "kind": element.tag,
        "attributes": dict(element.attrib),
        "raw_xml": compact_xml(element),
    }


def _dynamic_invocation(
    element: ET.Element, source_service_id: str, invoker_service: str, step_id: str
) -> DynamicInvocation:
    candidate_fields: list[str] = []
    candidate_values: list[str] = []
    for candidate in element.iter():
        for name, value in candidate.attrib.items():
            if name == "SERVICE" and value == invoker_service:
                continue
            if _looks_like_service_field(name) or _looks_like_service_field(value):
                candidate_fields.append(f"{candidate.tag}@{name}={value}")
        if candidate.tag == "value":
            field_name = candidate.attrib.get("name", "")
            text = (candidate.text or "").strip()
            if _looks_like_service_field(field_name):
                candidate_fields.append(f"value@name={field_name}")
            if _looks_like_service_id(text):
                candidate_values.append(text)

    return DynamicInvocation(
        source_service_id=source_service_id,
        invoker_service=invoker_service,
        step_id=step_id,
        evidence=compact_xml(element, max_chars=1200),
        candidate_fields=sorted(set(candidate_fields)),
        candidate_values=sorted(set(candidate_values)),
    )


def _looks_like_service_field(value: str) -> bool:
    normalized = value.strip().lower().replace("_", "").replace("-", "")
    if normalized in SERVICE_FIELD_HINTS:
        return True
    path_parts = [part.split(";", 1)[0] for part in normalized.split("/") if part]
    return any(part in SERVICE_FIELD_HINTS for part in path_parts)


def _looks_like_service_id(value: str) -> bool:
    if not value or ":" not in value:
        return False
    namespace, name = value.rsplit(":", 1)
    return bool(namespace and name and "." in namespace and "/" not in value)


def _extract_rec_refs(root: ET.Element, file_path: Path, context: str) -> list[DocumentReference]:
    refs: list[DocumentReference] = []
    for element in root.iter("value"):
        if element.attrib.get("name") != "rec_ref":
            continue
        ref = (element.text or "").strip()
        if ref:
            refs.append(DocumentReference(ref=ref, source=str(file_path), context=context))
    return refs


def _dedupe_document_refs(refs: list[DocumentReference]) -> list[DocumentReference]:
    seen: set[tuple[str, str, str, str | None]] = set()
    unique: list[DocumentReference] = []
    for ref in refs:
        key = (ref.ref, ref.source, ref.context, ref.field_path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique
