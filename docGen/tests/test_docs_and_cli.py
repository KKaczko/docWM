from __future__ import annotations

import json
from pathlib import Path

from wm_docgen.cli import main
from wm_docgen.discovery import scan_source, service_doc_path
from wm_docgen.docs import generate_docs, write_json, write_mkdocs_config
from wm_docgen.processes import analyze_processes, load_processes


ROOT = Path(__file__).resolve().parents[1]


def test_json_and_markdown_outputs_match_parsed_dependencies(tmp_path: Path) -> None:
    result = scan_source(ROOT)
    service = result.services[0]
    docs_dir = tmp_path / "docs"
    json_path = tmp_path / "services.json"

    write_json(result, json_path)
    generate_docs(result, docs_dir, [])
    write_mkdocs_config(tmp_path / "mkdocs.yml", docs_dir, result, [])

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["services"][0]["id"] == service.id
    assert len([edge for edge in data["services"][0]["dependencies"] if edge["dependency_type"] == "service_call"]) == 43

    service_page = docs_dir / "services" / service_doc_path(service.id)
    markdown = service_page.read_text(encoding="utf-8")
    assert "pub.list:sizeOfList" in markdown
    assert "oa.adapter.services.common:getProviderConnection" in markdown
    assert "```mermaid" in markdown
    assert "graph TD" in markdown


def test_process_config_generates_process_page(tmp_path: Path) -> None:
    result = scan_source(ROOT)
    processes_yml = ROOT / "examples" / "processes.yml"
    processes = load_processes(processes_yml)
    analyses = analyze_processes(processes, result.services)

    assert analyses[0].definition.entrypoints == ["synthetic.current:flow_1"]
    assert analyses[0].service_ids == ["synthetic.current:flow_1"]

    docs_dir = tmp_path / "docs"
    generate_docs(result, docs_dir, analyses)
    process_page = docs_dir / "processes" / "synthetic-geographic-address-validation.md"
    markdown = process_page.read_text(encoding="utf-8")
    assert "Synthetic Geographic Address Validation" in markdown
    assert "synthetic.current:flow_1" in markdown
    assert "```mermaid" in markdown


def test_cli_scan_writes_json(tmp_path: Path) -> None:
    output = tmp_path / "scan.json"
    exit_code = main(["scan", "--source", str(ROOT), "--json", str(output)])

    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["services"][0]["id"] == "synthetic.current:flow_1"


def test_cli_build_writes_docs_and_mkdocs_config(tmp_path: Path) -> None:
    out_dir = tmp_path / "build"
    docs_dir = tmp_path / "docs"
    mkdocs_path = tmp_path / "mkdocs.yml"
    exit_code = main(
        [
            "build",
            "--source",
            str(ROOT),
            "--out",
            str(out_dir),
            "--docs",
            str(docs_dir),
            "--processes",
            str(ROOT / "examples" / "processes.yml"),
            "--mkdocs",
            str(mkdocs_path),
        ]
    )

    assert exit_code == 0
    assert (out_dir / "services.json").exists()
    assert (docs_dir / "index.md").exists()
    assert (docs_dir / "reports" / "summary.md").exists()
    assert mkdocs_path.exists()
