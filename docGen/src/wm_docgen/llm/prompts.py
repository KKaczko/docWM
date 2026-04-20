"""Prompt templates for source-grounded documentation enrichment."""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "wm-docgen-llm-v1"

SYSTEM_PROMPT = """You document webMethods Integration Server packages.

Use only the provided parsed facts.
Do not invent dependencies, systems, owners, entities, or business rules.
Separate "Known From Source", "Inferred", and "Unknown".
If facts are insufficient, write "Unknown".
Keep the answer concise and use Markdown.
Do not include a top-level title.
"""


def service_messages(fact_packet: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Create AI-assisted service documentation with these sections: "
                "Known From Source, Inferred, Entity Actions, Conditions And Decisions, "
                "Mapping Behavior, Risks And Unknowns.\n\n"
                f"Parsed facts JSON:\n{json.dumps(fact_packet, indent=2, sort_keys=True)}"
            ),
        },
    ]


def process_messages(fact_packet: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Create AI-assisted process documentation with these sections: "
                "Known From Source, Inferred, Entity Flow Across Process, "
                "Business Rules And Conditions, Data Transformations, Risks And Unknowns.\n\n"
                f"Parsed facts JSON:\n{json.dumps(fact_packet, indent=2, sort_keys=True)}"
            ),
        },
    ]


def business_summary_messages(fact_packet: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Create a stakeholder-friendly business overview. Avoid implementation trivia. "
                "Include Known From Source, Inferred, and Unknown.\n\n"
                f"Parsed facts JSON:\n{json.dumps(fact_packet, indent=2, sort_keys=True)}"
            ),
        },
    ]
