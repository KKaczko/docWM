from __future__ import annotations

from pathlib import Path

from wm_docgen.discovery import scan_source
from wm_docgen.models import Step


def test_orphan_artifacts_parse_steps_and_invokes(tmp_path: Path) -> None:
    _write_orphan_flow(tmp_path / "flow.xml")
    _write_node(tmp_path / "node.ndf")
    result = scan_source(tmp_path)

    assert len(result.services) == 1
    service = result.services[0]
    assert service.id == "synthetic.current:flow_1"
    assert service.structure_inferred is True
    assert service.source_files["flow"].endswith("flow.xml")
    assert service.source_files["node"].endswith("node.ndf")

    steps = _flatten_steps(service.steps)
    assert steps[0].kind == "FLOW"
    assert {step.kind for step in steps} >= {"FLOW", "SEQUENCE", "MAP", "MAPINVOKE", "INVOKE", "BRANCH", "LOOP", "EXIT"}
    assert any(step.comment == "try - catch" for step in steps)
    assert any(step.comment == "call external service" for step in steps)

    service_calls = [edge for edge in service.dependencies if edge.dependency_type == "service_call"]
    assert len(service_calls) == 3
    targets = [edge.target_service_id for edge in service_calls]
    assert "pub.list:sizeOfList" in targets
    assert "pub.flow:clearPipeline" in targets
    assert "pkg.external:run" in targets
    assert {edge.kind for edge in service_calls} >= {"pub_service", "external_service"}

    warning_codes = {issue.code for issue in service.warnings}
    assert "INFERRED_STRUCTURE" in warning_codes


def test_node_signature_extracts_document_references(tmp_path: Path) -> None:
    _write_orphan_flow(tmp_path / "flow.xml")
    _write_node(tmp_path / "node.ndf")
    result = scan_source(tmp_path)
    service = result.services[0]

    assert service.inputs[0]["name"] == "input"
    assert service.inputs[0]["rec_ref"] == "pkg.docs:Input"
    assert service.outputs[0]["name"] == "output"
    refs = {ref.ref for ref in service.document_references}
    assert "pkg.docs:Input" in refs


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


def test_java_service_and_document_type_discovery(tmp_path: Path) -> None:
    package = tmp_path / "PkgA"
    java_node = package / "ns" / "pkg" / "tools" / "doJava"
    document_node = package / "ns" / "pkg" / "docs" / "Order"
    java_node.mkdir(parents=True)
    document_node.mkdir(parents=True)
    (package / "manifest.v3").write_text("<?xml version=\"1.0\"?>\n<Values version=\"2.0\"/>", encoding="utf-8")
    _write_java_node(java_node / "node.ndf")
    _write_document_node(document_node / "node.ndf")

    result = scan_source(tmp_path)

    services = {service.id: service for service in result.services}
    assert services["pkg.tools:doJava"].service_type == "java_service"
    assert services["pkg.tools:doJava"].inputs[0]["name"] == "input"
    assert "JAVA_SOURCE_NOT_FOUND" in {issue.code for issue in services["pkg.tools:doJava"].warnings}

    documents = {document.id: document for document in result.document_types}
    assert documents["pkg.docs:Order"].fields[0]["name"] == "orderId"
    assert documents["pkg.docs:Order"].node_type == "record"


def test_dynamic_invocation_warns_without_inferred_edge(tmp_path: Path) -> None:
    package = tmp_path / "PkgA"
    dynamic_service = package / "ns" / "pkg" / "flow" / "dynamic"
    dynamic_service.mkdir(parents=True)
    (package / "manifest.v3").write_text("<?xml version=\"1.0\"?>\n<Values version=\"2.0\"/>", encoding="utf-8")
    _write_dynamic_flow(dynamic_service / "flow.xml")
    _write_node(dynamic_service / "node.ndf")

    result = scan_source(tmp_path)
    service = result.services[0]

    targets = [edge.target_service_id for edge in service.dependencies if edge.dependency_type == "service_call"]
    assert targets == ["pub.flow:invoke"]
    assert "pkg.target:run" not in targets
    assert service.dynamic_invocations[0].invoker_service == "pub.flow:invoke"
    assert "pkg.target:run" in service.dynamic_invocations[0].candidate_values
    assert "DYNAMIC_INVOKE_TARGET_UNKNOWN" in {issue.code for issue in service.warnings}


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


def _write_orphan_flow(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<FLOW VERSION="3.0" CLEANUP="true">
  <COMMENT>root</COMMENT>
  <SEQUENCE TIMEOUT="" EXIT-ON="SUCCESS">
    <COMMENT>try - catch</COMMENT>
    <MAP MODE="STANDALONE">
      <COMMENT>calculate list size</COMMENT>
      <MAPINVOKE SERVICE="pub.list:sizeOfList" VALIDATE-IN="$none" VALIDATE-OUT="$none">
        <MAP MODE="INVOKEINPUT">
          <MAPCOPY FROM="/items;3;1" TO="/fromList;3;1"/>
        </MAP>
      </MAPINVOKE>
    </MAP>
    <BRANCH LABELEXPRESSIONS="true">
      <LOOP NAME="%count% != 0" IN-ARRAY="/items">
        <INVOKE SERVICE="pkg.external:run" VALIDATE-IN="$none" VALIDATE-OUT="$none">
          <COMMENT>call external service</COMMENT>
        </INVOKE>
        <EXIT FROM="$loop" SIGNAL="SUCCESS"/>
      </LOOP>
    </BRANCH>
    <INVOKE SERVICE="pub.flow:clearPipeline" VALIDATE-IN="$none" VALIDATE-OUT="$none"/>
  </SEQUENCE>
</FLOW>
""",
        encoding="utf-8",
    )


def _write_java_node(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Values version="2.0">
  <value name="svc_type">java</value>
  <value name="svc_subtype">default</value>
  <record name="svc_sig" javaclass="com.wm.util.Values">
    <record name="sig_in" javaclass="com.wm.util.Values">
      <array name="rec_fields" type="record" depth="1">
        <record javaclass="com.wm.util.Values">
          <value name="field_name">input</value>
          <value name="field_type">string</value>
          <value name="field_dim">0</value>
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


def _write_document_node(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Values version="2.0">
  <value name="node_type">record</value>
  <value name="node_subtype">document</value>
  <value name="node_comment">Order document</value>
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


def _write_dynamic_flow(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<FLOW VERSION="3.0" CLEANUP="true">
  <INVOKE SERVICE="pub.flow:invoke" VALIDATE-IN="$none" VALIDATE-OUT="$none">
    <MAP MODE="INPUT">
      <MAPSET FIELD="/serviceName;1;0">
        <DATA ENCODING="XMLValues" I18N="true">
          <Values version="2.0">
            <value name="xml">pkg.target:run</value>
          </Values>
        </DATA>
      </MAPSET>
    </MAP>
  </INVOKE>
</FLOW>
""",
        encoding="utf-8",
    )


def _flatten_steps(steps: list[Step]) -> list[Step]:
    flattened: list[Step] = []
    for step in steps:
        flattened.append(step)
        flattened.extend(_flatten_steps(step.children))
    return flattened
