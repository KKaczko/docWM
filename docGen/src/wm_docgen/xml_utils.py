"""XML helpers shared by flow and node parsers."""

from __future__ import annotations

from xml.etree import ElementTree as ET


def direct_value(element: ET.Element, name: str) -> str | None:
    for child in element:
        if child.tag == "value" and child.attrib.get("name") == name:
            value = (child.text or "").strip()
            return value or None
    return None


def compact_xml(element: ET.Element, max_chars: int = 500) -> str:
    text = ET.tostring(element, encoding="unicode", short_empty_elements=True)
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def service_id_to_parts(service_id: str) -> tuple[str, str]:
    if ":" in service_id:
        namespace, name = service_id.rsplit(":", 1)
        return namespace, name
    if "." in service_id:
        namespace, name = service_id.rsplit(".", 1)
        return namespace, name
    return "", service_id


def safe_slug(value: str) -> str:
    slug = []
    for char in value:
        if char.isalnum():
            slug.append(char)
        elif char in {".", "-", "_"}:
            slug.append(char)
        else:
            slug.append("_")
    collapsed = "".join(slug).strip("._")
    return collapsed or "item"
