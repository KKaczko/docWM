"""Artifact loading helpers."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET


def load_xml(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
