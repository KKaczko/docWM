"""Command line interface for wm-docgen."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from wm_docgen.discovery import scan_source
from wm_docgen.docs import generate_docs, write_json, write_mkdocs_config
from wm_docgen.processes import analyze_processes, load_processes
from wm_docgen.sample_fetcher import fetch_samples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wm-docgen")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan artifacts and write JSON.")
    scan_parser.add_argument("--source", type=Path, default=Path("."))
    scan_parser.add_argument("--json", type=Path, default=Path("build/docgen/services.json"))
    scan_parser.add_argument("--service-id", help="Override synthetic service id when scanning one orphan flow.")

    build_parser = subparsers.add_parser("build", help="Scan artifacts and generate docs.")
    build_parser.add_argument("--source", type=Path, default=Path("."))
    build_parser.add_argument("--out", type=Path, default=Path("build/docgen"))
    build_parser.add_argument("--docs", type=Path, default=Path("docs"))
    build_parser.add_argument("--processes", type=Path, default=Path("examples/processes.yml"))
    build_parser.add_argument("--service-id", help="Override synthetic service id when scanning one orphan flow.")
    build_parser.add_argument("--mkdocs", type=Path, default=Path("mkdocs.yml"))

    validate_parser = subparsers.add_parser("validate", help="Scan artifacts and print validation issues.")
    validate_parser.add_argument("--source", type=Path, default=Path("."))
    validate_parser.add_argument("--service-id", help="Override synthetic service id when scanning one orphan flow.")

    list_parser = subparsers.add_parser("list-services", help="List discovered service IDs.")
    list_parser.add_argument("--source", type=Path, default=Path("."))
    list_parser.add_argument("--service-id", help="Override synthetic service id when scanning one orphan flow.")
    list_parser.add_argument("--format", choices=["plain", "table", "json"], default="table")
    list_parser.add_argument("--include-documents", action="store_true")

    fetch_parser = subparsers.add_parser("fetch-samples", help="Download representative public sample artifacts.")
    fetch_parser.add_argument("--out", type=Path, default=Path("examples/public-samples"))

    args = parser.parse_args(argv)

    if args.command == "scan":
        result = scan_source(args.source, args.service_id)
        write_json(result, args.json)
        print(f"Wrote {args.json}")
        return 0

    if args.command == "build":
        result = scan_source(args.source, args.service_id)
        args.out.mkdir(parents=True, exist_ok=True)
        json_path = args.out / "services.json"
        processes = load_processes(args.processes)
        process_analyses = analyze_processes(processes, result.services)
        result.validation_issues.extend(issue for analysis in process_analyses for issue in analysis.issues)
        write_json(result, json_path)
        generate_docs(result, args.docs, process_analyses)
        write_mkdocs_config(args.mkdocs, args.docs, result, process_analyses)
        print(f"Wrote {json_path}")
        print(f"Wrote documentation to {args.docs}")
        print(f"Wrote MkDocs config to {args.mkdocs}")
        return 0

    if args.command == "validate":
        result = scan_source(args.source, args.service_id)
        for issue in result.validation_issues:
            location = f" {issue.file}" if issue.file else ""
            service = f" [{issue.service_id}]" if issue.service_id else ""
            print(f"{issue.severity.upper()} {issue.code}{service}{location}: {issue.message}")
        return 1 if any(issue.severity == "error" for issue in result.validation_issues) else 0

    if args.command == "list-services":
        result = scan_source(args.source, args.service_id)
        rows = _list_rows(result, include_documents=args.include_documents)
        if args.format == "plain":
            for row in rows:
                print(row["id"])
        elif args.format == "json":
            print(json.dumps(rows, indent=2, sort_keys=True))
        else:
            print(_format_table(rows))
        return 1 if any(issue.severity == "error" for issue in result.validation_issues) else 0

    if args.command == "fetch-samples":
        written = fetch_samples(args.out)
        for path in written:
            print(path)
        return 0

    return 2


def _list_rows(result, *, include_documents: bool) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for service in sorted(result.services, key=lambda item: item.id):
        rows.append(
            {
                "id": service.id,
                "package": service.package,
                "type": service.service_type,
                "source_files": ",".join(service.source_files.keys()),
                "dependency_count": len(service.dependencies),
                "warning_count": len(service.warnings),
            }
        )
    if include_documents:
        for document in sorted(result.document_types, key=lambda item: item.id):
            rows.append(
                {
                    "id": document.id,
                    "package": document.package,
                    "type": "document_type",
                    "source_files": ",".join(document.source_files.keys()),
                    "dependency_count": len(document.document_references),
                    "warning_count": len(document.warnings),
                }
            )
    return rows


def _format_table(rows: list[dict[str, object]]) -> str:
    headers = ["service_id", "package", "type", "source_files", "dependency_count", "warning_count"]
    normalized = [
        {
            "service_id": str(row["id"]),
            "package": str(row["package"]),
            "type": str(row["type"]),
            "source_files": str(row["source_files"]),
            "dependency_count": str(row["dependency_count"]),
            "warning_count": str(row["warning_count"]),
        }
        for row in rows
    ]
    widths = {
        header: max(len(header), *(len(row[header]) for row in normalized)) if normalized else len(header)
        for header in headers
    }
    lines = [
        "  ".join(header.ljust(widths[header]) for header in headers),
        "  ".join("-" * widths[header] for header in headers),
    ]
    for row in normalized:
        lines.append("  ".join(row[header].ljust(widths[header]) for header in headers))
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
