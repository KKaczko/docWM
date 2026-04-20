"""Parser for webMethods flow.xml files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from wm_docgen.models import (
    ConditionFact,
    DependencyEdge,
    DocumentReference,
    DynamicInvocation,
    EntityAction,
    MappingFact,
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
    entity_actions: list[EntityAction] = field(default_factory=list)
    mapping_facts: list[MappingFact] = field(default_factory=list)
    condition_facts: list[ConditionFact] = field(default_factory=list)
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

        for fact in _condition_facts(element, service_id, step_id):
            result.condition_facts.append(fact)
            for path in fact.referenced_paths:
                result.entity_actions.append(
                    _entity_action(
                        service_id=service_id,
                        action=fact.kind,
                        path=path,
                        step_id=step_id,
                        evidence=fact.evidence,
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
                operation = _mapping_operation(child)
                step.mapping_operations.append(operation)
                mapping_fact, entity_actions = _mapping_facts_and_actions(
                    child, service_id, step_id, operation["raw_xml"]
                )
                if mapping_fact:
                    result.mapping_facts.append(mapping_fact)
                result.entity_actions.extend(entity_actions)
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


def _mapping_facts_and_actions(
    element: ET.Element, service_id: str, step_id: str, evidence: str
) -> tuple[MappingFact | None, list[EntityAction]]:
    actions: list[EntityAction] = []
    if element.tag == "MAPCOPY":
        from_path = element.attrib.get("FROM")
        to_path = element.attrib.get("TO")
        fact = MappingFact(
            service_id=service_id,
            kind="MAPCOPY",
            step_id=step_id,
            evidence=evidence,
            from_path=from_path,
            to_path=to_path,
        )
        if from_path:
            actions.append(_entity_action(service_id, "copy_from", from_path, step_id, evidence))
            actions.append(_entity_action(service_id, "read", from_path, step_id, evidence))
        if to_path:
            actions.append(_entity_action(service_id, "copy_to", to_path, step_id, evidence))
            actions.append(_entity_action(service_id, "write", to_path, step_id, evidence))
        return fact, actions
    if element.tag == "MAPSET":
        field_path = element.attrib.get("FIELD")
        fact = MappingFact(
            service_id=service_id,
            kind="MAPSET",
            step_id=step_id,
            evidence=evidence,
            field_path=field_path,
            literal_value=_literal_xml_value(element),
        )
        if field_path:
            actions.append(_entity_action(service_id, "set", field_path, step_id, evidence))
            actions.append(_entity_action(service_id, "write", field_path, step_id, evidence))
        return fact, actions
    if element.tag == "MAPDELETE":
        field_path = element.attrib.get("FIELD")
        fact = MappingFact(
            service_id=service_id,
            kind="MAPDELETE",
            step_id=step_id,
            evidence=evidence,
            field_path=field_path,
        )
        if field_path:
            actions.append(_entity_action(service_id, "delete", field_path, step_id, evidence))
        return fact, actions
    return None, actions


def _condition_facts(element: ET.Element, service_id: str, step_id: str) -> list[ConditionFact]:
    facts: list[ConditionFact] = []
    if element.tag in {"BRANCH", "SEQUENCE"} and element.attrib.get("NAME"):
        expression = element.attrib["NAME"]
        if _looks_like_condition(expression):
            facts.append(
                ConditionFact(
                    service_id=service_id,
                    kind="condition",
                    expression=expression,
                    step_id=step_id,
                    evidence=compact_xml(element, max_chars=500),
                    referenced_paths=_referenced_paths(expression),
                )
            )
    if element.tag == "BRANCH" and element.attrib.get("SWITCH"):
        expression = element.attrib["SWITCH"]
        facts.append(
            ConditionFact(
                service_id=service_id,
                kind="branch_switch",
                expression=expression,
                step_id=step_id,
                evidence=compact_xml(element, max_chars=500),
                referenced_paths=_referenced_paths(expression) or [_clean_pipeline_path(expression)],
            )
        )
    if element.tag == "LOOP" and element.attrib.get("IN-ARRAY"):
        expression = element.attrib["IN-ARRAY"]
        facts.append(
            ConditionFact(
                service_id=service_id,
                kind="loop",
                expression=expression,
                step_id=step_id,
                evidence=compact_xml(element, max_chars=500),
                referenced_paths=[_clean_pipeline_path(expression)],
            )
        )
    return facts


def _entity_action(
    service_id: str, action: str, path: str, step_id: str, evidence: str
) -> EntityAction:
    entity_ref, field_path, inferred = _entity_from_path(path)
    return EntityAction(
        service_id=service_id,
        action=action,
        field_path=field_path,
        source_step_id=step_id,
        evidence=evidence,
        entity_ref=entity_ref,
        inferred=inferred,
    )


def _entity_from_path(path: str) -> tuple[str | None, str, bool]:
    clean_path = _clean_pipeline_path(path)
    entity_ref: str | None = None
    clean_parts: list[str] = []
    for raw_part in path.split("/"):
        if not raw_part:
            continue
        pieces = raw_part.split(";")
        if pieces[0]:
            clean_parts.append(pieces[0])
        for piece in pieces[1:]:
            if ":" in piece and piece not in {"0", "1", "2", "3", "4"}:
                entity_ref = piece
    if entity_ref:
        return entity_ref, "/" + "/".join(clean_parts), False
    if clean_parts:
        return clean_parts[0], clean_path, True
    return None, clean_path, True


def _literal_xml_value(element: ET.Element) -> str | None:
    values = []
    for value in element.iter("value"):
        text = (value.text or "").strip()
        if text:
            values.append(text)
    if len(values) == 1 and len(values[0]) <= 200:
        return values[0]
    return None


def _referenced_paths(expression: str) -> list[str]:
    paths: list[str] = []
    current: list[str] = []
    in_ref = False
    for char in expression:
        if char == "%":
            if in_ref and current:
                paths.append(_clean_pipeline_path("".join(current)))
            current = []
            in_ref = not in_ref
        elif in_ref:
            current.append(char)
    if expression.startswith("/"):
        paths.append(_clean_pipeline_path(expression))
    return sorted(set(path for path in paths if path))


def _clean_pipeline_path(path: str) -> str:
    if not path:
        return ""
    parts = []
    for part in path.split("/"):
        if not part:
            continue
        parts.append(part.split(";", 1)[0])
    return "/" + "/".join(parts) if path.startswith("/") else "/".join(parts)


def _looks_like_condition(expression: str) -> bool:
    markers = ["%", "$null", "==", "!=", ">", "<", "$default", "&&", "||"]
    return any(marker in expression for marker in markers)


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
