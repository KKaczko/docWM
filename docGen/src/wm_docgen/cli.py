"""Command line interface for wm-docgen."""

from __future__ import annotations

import argparse
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

    if args.command == "fetch-samples":
        written = fetch_samples(args.out)
        for path in written:
            print(path)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
