"""Parser for webMethods node.ndf metadata and service signatures."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from wm_docgen.models import DocumentReference, ValidationIssue
from wm_docgen.xml_utils import direct_value


@dataclass(slots=True)
class NodeParseResult:
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    document_references: list[DocumentReference] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)


class NodeParser:
    def parse(self, path: Path, service_id: str) -> NodeParseResult:
        result = NodeParseResult()
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            result.issues.append(
                ValidationIssue(
                    code="NODE_XML_PARSE_ERROR",
                    severity="error",
                    message=f"Cannot parse node.ndf XML: {exc}",
                    file=str(path),
                    service_id=service_id,
                )
            )
            return result

        if root.tag != "Values":
            result.issues.append(
                ValidationIssue(
                    code="NODE_ROOT_UNSUPPORTED",
                    severity="warning",
                    message=f"Expected Values root in node.ndf, found {root.tag!r}.",
                    file=str(path),
                    path=f"/{root.tag}",
                    service_id=service_id,
                )
            )

        svc_sig = root.find("./record[@name='svc_sig']")
        if svc_sig is None:
            result.issues.append(
                ValidationIssue(
                    code="NODE_SIGNATURE_MISSING",
                    severity="warning",
                    message="node.ndf does not contain svc_sig metadata.",
                    file=str(path),
                    service_id=service_id,
                )
            )
            return result

        sig_in = svc_sig.find("./record[@name='sig_in']")
        sig_out = svc_sig.find("./record[@name='sig_out']")
        if sig_in is not None:
            result.inputs = _parse_record_fields(sig_in, path, "node.sig_in", result.document_references)
        if sig_out is not None:
            result.outputs = _parse_record_fields(sig_out, path, "node.sig_out", result.document_references)
        result.document_references = _dedupe_document_refs(result.document_references)
        return result


def _parse_record_fields(
    record: ET.Element,
    file_path: Path,
    context: str,
    refs: list[DocumentReference],
    prefix: str = "",
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for array in record.findall("./array[@name='rec_fields']"):
        for child_record in array.findall("./record"):
            field_name = direct_value(child_record, "field_name") or child_record.attrib.get("name") or ""
            field_path = f"{prefix}/{field_name}" if prefix and field_name else field_name or prefix
            field = _record_to_field(child_record)
            field["path"] = field_path
            field["children"] = _parse_record_fields(child_record, file_path, context, refs, field_path)
            if field.get("rec_ref"):
                refs.append(
                    DocumentReference(
                        ref=field["rec_ref"],
                        source=str(file_path),
                        context=context,
                        field_path=field_path or None,
                    )
                )
            fields.append(field)
    return fields


def _record_to_field(record: ET.Element) -> dict[str, Any]:
    return {
        "name": direct_value(record, "field_name") or record.attrib.get("name") or "",
        "node_type": direct_value(record, "node_type"),
        "field_type": direct_value(record, "field_type"),
        "field_dim": direct_value(record, "field_dim"),
        "rec_ref": direct_value(record, "rec_ref"),
        "comment": direct_value(record, "node_comment"),
    }


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
