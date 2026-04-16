from __future__ import annotations

import json
from pathlib import Path

from wm_docgen.cli import main
from wm_docgen.discovery import scan_source, service_doc_path
from wm_docgen.docs import generate_docs, write_json, write_mkdocs_config
from wm_docgen.models import DependencyEdge, Service
from wm_docgen.processes import analyze_processes, load_processes


ROOT = Path(__file__).resolve().parents[1]


def test_json_and_markdown_outputs_match_parsed_dependencies(tmp_path: Path) -> None:
    source = _sample_source(tmp_path)
    result = scan_source(source)
    service = result.services[0]
    docs_dir = tmp_path / "docs"
    json_path = tmp_path / "services.json"

    write_json(result, json_path)
    generate_docs(result, docs_dir, [])
    write_mkdocs_config(tmp_path / "mkdocs.yml", docs_dir, result, [])

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["services"][0]["id"] == service.id
    assert len([edge for edge in data["services"][0]["dependencies"] if edge["dependency_type"] == "service_call"]) == 2

    service_page = docs_dir / "services" / service_doc_path(service.id)
    markdown = service_page.read_text(encoding="utf-8")
    assert "pub.list:sizeOfList" in markdown
    assert "pkg.external:run" in markdown
    assert "```mermaid" in markdown
    assert "graph TD" in markdown


def test_process_config_generates_process_page(tmp_path: Path) -> None:
    source = ROOT / "examples" / "sample-packages"
    result = scan_source(source)
    processes_yml = ROOT / "examples" / "processes.yml"
    processes = load_processes(processes_yml)
    analyses = analyze_processes(processes, result.services)

    assert analyses[0].definition.entrypoints == ["com.example.order:submitOrder"]
    assert analyses[0].service_ids == [
        "com.example.order:submitOrder",
        "com.example.customer:validateCustomer",
        "com.example.billing:createInvoice",
    ]

    docs_dir = tmp_path / "docs"
    generate_docs(result, docs_dir, analyses)
    process_page = docs_dir / "processes" / "order-submission.md"
    markdown = process_page.read_text(encoding="utf-8")
    assert "Order Submission" in markdown
    assert "Business Flow" in markdown
    assert "Receive request" in markdown
    assert "com.example.order:submitOrder" in markdown
    assert "```mermaid" in markdown
    assert (docs_dir / "business-summary.md").exists()


def test_business_steps_warn_for_missing_and_unreachable_services(tmp_path: Path) -> None:
    processes_yml = tmp_path / "processes.yml"
    processes_yml.write_text(
        """processes:
  - id: order-submission
    name: Order Submission
    entrypoints:
      - pkg.order:submitOrder
    business_steps:
      - name: Receive request
        services:
          - pkg.order:submitOrder
      - name: Create invoice
        services:
          - pkg.billing:createInvoice
      - name: Missing service
        services:
          - pkg.missing:service
""",
        encoding="utf-8",
    )
    services = [
        Service(
            id="pkg.order:submitOrder",
            package="Pkg",
            namespace_path="pkg.order",
            name="submitOrder",
            source_files={},
            dependencies=[
                DependencyEdge(
                    source_service_id="pkg.order:submitOrder",
                    target_service_id="pkg.customer:validateCustomer",
                    kind="internal",
                )
            ],
        ),
        Service(
            id="pkg.customer:validateCustomer",
            package="Pkg",
            namespace_path="pkg.customer",
            name="validateCustomer",
            source_files={},
        ),
        Service(
            id="pkg.billing:createInvoice",
            package="Pkg",
            namespace_path="pkg.billing",
            name="createInvoice",
            source_files={},
        ),
    ]

    processes = load_processes(processes_yml)
    analyses = analyze_processes(processes, services)

    assert processes[0].business_steps[0].id == "Receive_request"
    assert analyses[0].supporting_service_ids == ["pkg.customer:validateCustomer"]
    codes = {issue.code for issue in analyses[0].issues}
    assert "BUSINESS_STEP_SERVICE_MISSING" in codes
    assert "BUSINESS_STEP_SERVICE_NOT_REACHABLE" in codes


def test_cli_scan_writes_json(tmp_path: Path) -> None:
    source = _sample_source(tmp_path)
    output = tmp_path / "scan.json"
    exit_code = main(["scan", "--source", str(source), "--json", str(output)])

    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["services"][0]["id"] == "synthetic.current:flow_1"


def test_cli_list_services_formats(tmp_path: Path, capsys) -> None:
    source = _sample_source(tmp_path)
    exit_code = main(["list-services", "--source", str(source), "--format", "plain"])
    plain = capsys.readouterr().out
    assert exit_code == 0
    assert plain.strip() == "synthetic.current:flow_1"

    exit_code = main(["list-services", "--source", str(source)])
    table = capsys.readouterr().out
    assert exit_code == 0
    assert "service_id" in table
    assert "warning_count" in table
    assert "synthetic.current:flow_1" in table

    exit_code = main(["list-services", "--source", str(source), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert data[0]["id"] == "synthetic.current:flow_1"

    package = tmp_path / "PkgA"
    document_node = package / "ns" / "pkg" / "docs" / "Order"
    document_node.mkdir(parents=True)
    (package / "manifest.v3").write_text("<?xml version=\"1.0\"?>\n<Values version=\"2.0\"/>", encoding="utf-8")
    _write_document_node(document_node / "node.ndf")
    exit_code = main(["list-services", "--source", str(tmp_path), "--format", "plain", "--include-documents"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "pkg.docs:Order" in output


def test_cli_build_writes_docs_and_mkdocs_config(tmp_path: Path) -> None:
    source = ROOT / "examples" / "sample-packages"
    out_dir = tmp_path / "build"
    docs_dir = tmp_path / "docs"
    mkdocs_path = tmp_path / "mkdocs.yml"
    exit_code = main(
        [
            "build",
            "--source",
            str(source),
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
    assert (docs_dir / "business-summary.md").exists()
    assert (docs_dir / "reports" / "summary.md").exists()
    assert mkdocs_path.exists()
    assert "Business Summary" in mkdocs_path.read_text(encoding="utf-8")


def _write_document_node(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Values version="2.0">
  <value name="node_type">record</value>
  <value name="node_subtype">document</value>
  <array name="rec_fields" type="record" depth="1">
    <record javaclass="com.wm.util.Values">
      <value name="field_name">orderId</value>
      <value name="field_type">string</value>
      <value name="field_dim">0</value>
    </record>
  </array>
</Values>
""",
        encoding="utf-8",
    )


def _sample_source(base: Path) -> Path:
    source = base / "source"
    source.mkdir()
    (source / "flow.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<FLOW VERSION="3.0" CLEANUP="true">
  <SEQUENCE TIMEOUT="" EXIT-ON="SUCCESS">
    <MAP MODE="STANDALONE">
      <MAPINVOKE SERVICE="pub.list:sizeOfList" VALIDATE-IN="$none" VALIDATE-OUT="$none"/>
    </MAP>
    <INVOKE SERVICE="pkg.external:run" VALIDATE-IN="$none" VALIDATE-OUT="$none"/>
  </SEQUENCE>
</FLOW>
""",
        encoding="utf-8",
    )
    (source / "node.ndf").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Values version="2.0">
  <record name="svc_sig" javaclass="com.wm.util.Values">
    <record name="sig_in" javaclass="com.wm.util.Values">
      <array name="rec_fields" type="record" depth="1">
        <record javaclass="com.wm.util.Values">
          <value name="field_name">input</value>
          <value name="field_type">recref</value>
          <value name="field_dim">0</value>
          <value name="rec_ref">pkg.docs:Input</value>
        </record>
      </array>
    </record>
    <record name="sig_out" javaclass="com.wm.util.Values">
      <array name="rec_fields" type="record" depth="1"/>
    </record>
  </record>
</Values>
""",
        encoding="utf-8",
    )
    return source
