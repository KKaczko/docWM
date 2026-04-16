"""Validation checks for parsed documentation data."""

from __future__ import annotations

from wm_docgen.models import ScanResult, ValidationIssue


def validate_scan_result(result: ScanResult) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for service in result.services:
        if service.service_type == "flow_service" and not service.steps:
            issues.append(
                ValidationIssue(
                    code="SERVICE_STEPS_MISSING",
                    severity="warning",
                    message="No flow steps were parsed for this service.",
                    service_id=service.id,
                )
            )
        for edge in service.dependencies:
            if edge.kind == "unclassified":
                issues.append(
                    ValidationIssue(
                        code="DEPENDENCY_UNCLASSIFIED",
                        severity="warning",
                        message=f"Dependency {edge.target_service_id!r} was not classified.",
                        service_id=service.id,
                    )
                )
            if edge.kind == "unresolved":
                issues.append(
                    ValidationIssue(
                        code="DEPENDENCY_UNRESOLVED",
                        severity="warning",
                        message=f"Dependency {edge.target_service_id!r} could not be resolved or classified as external.",
                        service_id=service.id,
                    )
                )
    return issues
