from __future__ import annotations

from pathlib import Path

from wm_docgen.discovery import scan_source
from wm_docgen.models import Step


ROOT = Path(__file__).resolve().parents[1]


def test_current_orphan_artifacts_parse_steps_and_invokes() -> None:
    result = scan_source(ROOT)

    assert len(result.services) == 1
    service = result.services[0]
    assert service.id == "synthetic.current:flow_1"
    assert service.structure_inferred is True
    assert service.source_files["flow"].endswith("flow(1).xml")
    assert service.source_files["node"].endswith("node.ndf")

    steps = _flatten_steps(service.steps)
    assert steps[0].kind == "FLOW"
    assert {step.kind for step in steps} >= {"FLOW", "SEQUENCE", "MAP", "MAPINVOKE", "INVOKE", "BRANCH", "LOOP", "EXIT"}
    assert any(step.comment == "try - catch" for step in steps)
    assert any(step.comment == "call oa.adapter.services.common:getProviderConnection" for step in steps)

    service_calls = [edge for edge in service.dependencies if edge.dependency_type == "service_call"]
    assert len(service_calls) == 43
    targets = [edge.target_service_id for edge in service_calls]
    assert "pub.list:sizeOfList" in targets
    assert "pub.flow:clearPipeline" in targets
    assert "oa.adapter.services.common:getProviderConnection" in targets
    assert {edge.kind for edge in service_calls} >= {"pub_service", "external_service"}

    warning_codes = {issue.code for issue in service.warnings}
    assert "INFERRED_STRUCTURE" in warning_codes


def test_current_node_signature_extracts_document_references() -> None:
    result = scan_source(ROOT)
    service = result.services[0]

    assert service.inputs[0]["name"] == "input"
    assert service.inputs[0]["rec_ref"] == (
        "oa.adapter.doc.geographicAddressManagement.geographicAddressValidation:"
        "docCreateGeographicAddressValidationInput"
    )
    assert service.outputs[0]["name"] == "output"
    assert service.outputs[0]["rec_ref"] == (
        "oa.adapter.doc.geographicAddressManagement.geographicAddressValidation:"
        "docCreateGeographicAddressValidationOutput"
    )
    refs = {ref.ref for ref in service.document_references}
    assert "oa.model.geographicAddressManagement:docGeographicAddress" in refs
    assert "pub.event:exceptionInfo" in refs


def test_real_package_discovery_and_internal_dependency_classification(tmp_path: Path) -> None:
    package = tmp_path / "PkgA"
    service_main = package / "ns" / "pkg" / "alpha" / "main"
    service_other = package / "ns" / "pkg" / "alpha" / "other"
    service_main.mkdir(parents=True)
    service_other.mkdir(parents=True)
    (package / "manifest.v3").write_text("<?xml version=\"1.0\"?>\n<Values version=\"2.0\"/>", encoding="utf-8")
    _write_flow(service_main / "flow.xml", "pkg.alpha:other")
    _write_node(service_main / "node.ndf")
    _write_flow(service_other / "flow.xml", "pub.flow:clearPipeline")
    _write_node(service_other / "node.ndf")

    result = scan_source(tmp_path)

    service_ids = {service.id for service in result.services}
    assert service_ids == {"pkg.alpha:main", "pkg.alpha:other"}
    assert result.packages[0].name == "PkgA"
    assert result.packages[0].structure_inferred is False
    main = next(service for service in result.services if service.id == "pkg.alpha:main")
    call_edges = [edge for edge in main.dependencies if edge.dependency_type == "service_call"]
    assert call_edges[0].target_service_id == "pkg.alpha:other"
    assert call_edges[0].kind == "internal"


def test_unsupported_flow_nodes_emit_warning(tmp_path: Path) -> None:
    (tmp_path / "flow.xml").write_text("<FLOW><CUSTOM /></FLOW>", encoding="utf-8")
    result = scan_source(tmp_path)

    codes = {issue.code for issue in result.validation_issues}
    assert "UNSUPPORTED_FLOW_NODE" in codes
    assert "INFERRED_STRUCTURE" in codes


def _write_flow(path: Path, target: str) -> None:
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<FLOW VERSION="3.0" CLEANUP="true">
  <COMMENT>fixture</COMMENT>
  <INVOKE SERVICE="{target}" VALIDATE-IN="$none" VALIDATE-OUT="$none">
    <COMMENT>call target</COMMENT>
  </INVOKE>
</FLOW>
""",
        encoding="utf-8",
    )


def _write_node(path: Path) -> None:
    path.write_text(
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
      <array name="rec_fields" type="record" depth="1">
        <record javaclass="com.wm.util.Values">
          <value name="field_name">output</value>
          <value name="field_type">string</value>
          <value name="field_dim">0</value>
        </record>
      </array>
    </record>
  </record>
</Values>
""",
        encoding="utf-8",
    )


def _flatten_steps(steps: list[Step]) -> list[Step]:
    flattened: list[Step] = []
    for step in steps:
        flattened.append(step)
        flattened.extend(_flatten_steps(step.children))
    return flattened
