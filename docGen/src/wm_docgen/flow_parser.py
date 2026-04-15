"""Parser for webMethods flow.xml files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from wm_docgen.models import DependencyEdge, DocumentReference, Step, ValidationIssue
from wm_docgen.xml_utils import compact_xml

STEP_TAGS = {"FLOW", "SEQUENCE", "MAP", "MAPINVOKE", "INVOKE", "BRANCH", "LOOP", "EXIT"}
MAPPING_OPERATION_TAGS = {"MAPSET", "MAPCOPY", "MAPDELETE"}
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
    issues: list[ValidationIssue] = field(default_factory=list)


class FlowParser:
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
