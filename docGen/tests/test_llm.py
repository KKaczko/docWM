from __future__ import annotations

import json
from pathlib import Path

from wm_docgen.cli import main
from wm_docgen.discovery import scan_source
from wm_docgen.docs import generate_docs
from wm_docgen.llm.cache import LlmCache, cache_key
from wm_docgen.llm.config import LlmConfig, load_llm_config
from wm_docgen.llm.enrichment import enrich_with_llm
from wm_docgen.llm.facts import process_fact_packet, service_fact_packet
from wm_docgen.llm.ollama_client import OllamaClient
from wm_docgen.llm.openai_compatible_client import OpenAICompatibleClient
from wm_docgen.processes import analyze_processes, load_processes


ROOT = Path(__file__).resolve().parents[1]


def test_service_and_process_fact_packets_are_grounded() -> None:
    result = scan_source(ROOT / "examples" / "sample-packages")
    processes = load_processes(ROOT / "examples" / "processes.yml")
    analyses = analyze_processes(processes, result.services)
    submit_order = next(service for service in result.services if service.id == "com.example.order:submitOrder")

    service_packet = service_fact_packet(submit_order, limit=10)
    process_packet = process_fact_packet(analyses[0], result, limit=10)

    assert service_packet["service_id"] == "com.example.order:submitOrder"
    assert service_packet["invoked_services"]["items"][0]["target"] == "com.example.customer:validateCustomer"
    assert service_packet["mapping_facts"]["items"]
    assert service_packet["dynamic_invocations"]["items"]
    assert process_packet["process_id"] == "order-submission"
    assert "com.example.order:submitOrder" in process_packet["services"]["items"]


def test_llm_config_cli_overrides_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "llm.yml"
    config_path.write_text(
        """llm:
  provider: ollama
  base_url: http://configured:11434
  model: configured-model
  temperature: 0.2
  timeout_seconds: 10
""",
        encoding="utf-8",
    )

    config = load_llm_config(
        config_path,
        provider="ollama",
        base_url="http://cli:11434",
        model="cli-model",
        timeout_seconds=20,
        cache_dir=tmp_path / "cache",
    )

    assert config.provider == "ollama"
    assert config.base_url == "http://cli:11434"
    assert config.model == "cli-model"
    assert config.timeout_seconds == 20
    assert config.temperature == 0.2
    assert config.cache_dir == tmp_path / "cache"


def test_openai_compatible_config_reads_api_key_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "secret-token")
    config_path = tmp_path / "llm.yml"
    config_path.write_text(
        """llm:
  provider: openai-compatible
  base_url: https://server/ollama/v1
  model: configured-model
  api_key_env: OLLAMA_API_KEY
""",
        encoding="utf-8",
    )

    config = load_llm_config(config_path, provider="openai-compatible")

    assert config.provider == "openai-compatible"
    assert config.base_url == "https://server/ollama/v1"
    assert config.model == "configured-model"
    assert config.api_key_env == "OLLAMA_API_KEY"
    assert config.api_key == "secret-token"


def test_llm_cache_hit_avoids_http(monkeypatch, tmp_path: Path) -> None:
    result = scan_source(ROOT / "examples" / "sample-packages")
    processes = load_processes(ROOT / "examples" / "processes.yml")
    analyses = analyze_processes(processes, result.services)

    class FakeClient:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        def chat(self, **kwargs):
            FakeClient.calls += 1
            return "## Known From Source\nGenerated once."

    monkeypatch.setattr("wm_docgen.llm.enrichment.OllamaClient", FakeClient)
    config = LlmConfig(provider="ollama", cache_dir=tmp_path / "cache")

    enrich_with_llm(result, analyses, config)
    assert FakeClient.calls > 0
    first_call_count = FakeClient.calls

    result_again = scan_source(ROOT / "examples" / "sample-packages")
    analyses_again = analyze_processes(processes, result_again.services)
    enrich_with_llm(result_again, analyses_again, config)
    assert FakeClient.calls == first_call_count


def test_ollama_client_sends_non_streaming_chat(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"message":{"content":"ok"}}'

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("wm_docgen.llm.ollama_client.urlopen", fake_urlopen)

    client = OllamaClient(base_url="http://localhost:11434", timeout_seconds=7)
    content = client.chat(model="llama3.1", messages=[{"role": "user", "content": "hi"}], temperature=0.1)

    assert content == "ok"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["options"]["temperature"] == 0.1
    assert captured["timeout"] == 7


def test_openai_compatible_client_sends_non_streaming_chat(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"choices":[{"choices":[{"message":{"role":"assistant","content":"ok"}}]}]}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("wm_docgen.llm.openai_compatible_client.urlopen", fake_urlopen)

    client = OpenAICompatibleClient(
        base_url="https://server/ollama/v1",
        timeout_seconds=9,
        api_key="secret-token",
    )
    content = client.chat(model="server-model", messages=[{"role": "user", "content": "hi"}], temperature=0.1)

    assert content == "ok"
    assert captured["url"] == "https://server/ollama/v1/chat/completions"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["temperature"] == 0.1
    assert captured["authorization"] == "Bearer secret-token"
    assert captured["timeout"] == 9


def test_ai_sections_render_when_enrichment_exists(monkeypatch, tmp_path: Path) -> None:
    result = scan_source(ROOT / "examples" / "sample-packages")
    processes = load_processes(ROOT / "examples" / "processes.yml")
    analyses = analyze_processes(processes, result.services)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, **kwargs):
            return "## Known From Source\nAI content."

    monkeypatch.setattr("wm_docgen.llm.enrichment.OllamaClient", FakeClient)
    enrich_with_llm(result, analyses, LlmConfig(provider="ollama", cache_dir=tmp_path / "cache"))

    docs_dir = tmp_path / "docs"
    generate_docs(result, docs_dir, analyses)

    service_page = docs_dir / "services" / "com" / "example" / "order" / "submitOrder.md"
    process_page = docs_dir / "processes" / "order-submission.md"
    business_page = docs_dir / "business-summary.md"
    assert "AI-Assisted Interpretation" in service_page.read_text(encoding="utf-8")
    assert "AI-Assisted Process Narrative" in process_page.read_text(encoding="utf-8")
    assert "AI-Assisted Business Overview" in business_page.read_text(encoding="utf-8")


def test_openai_compatible_enrichment_uses_openai_client(monkeypatch, tmp_path: Path) -> None:
    result = scan_source(ROOT / "examples" / "sample-packages")
    processes = load_processes(ROOT / "examples" / "processes.yml")
    analyses = analyze_processes(processes, result.services)

    class FakeClient:
        calls = 0

        def __init__(self, *, base_url, timeout_seconds, api_key):
            assert base_url == "https://server/ollama/v1"
            assert timeout_seconds == 12
            assert api_key == "secret-token"

        def chat(self, **kwargs):
            FakeClient.calls += 1
            return "## Known From Source\nOpenAI-compatible content."

    monkeypatch.setattr("wm_docgen.llm.enrichment.OpenAICompatibleClient", FakeClient)

    enrich_with_llm(
        result,
        analyses,
        LlmConfig(
            provider="openai-compatible",
            base_url="https://server/ollama/v1",
            model="server-model",
            api_key="secret-token",
            timeout_seconds=12,
            cache_dir=tmp_path / "cache",
        ),
    )

    assert FakeClient.calls > 0
    assert result.llm_enrichments[0].provider == "openai-compatible"


def test_cli_llm_test_uses_ollama_test_function(monkeypatch, capsys) -> None:
    monkeypatch.setattr("wm_docgen.cli.test_ollama", lambda *args: "wm-docgen-ok")

    exit_code = main(["llm-test", "--ollama-url", "http://localhost:11434", "--ollama-model", "llama3.1"])

    assert exit_code == 0
    assert "wm-docgen-ok" in capsys.readouterr().out


def test_cli_llm_test_uses_openai_compatible_test_function(monkeypatch, capsys) -> None:
    captured = {}
    monkeypatch.setenv("OLLAMA_API_KEY", "secret-token")

    def fake_test_openai_compatible(base_url, model, timeout_seconds, api_key):
        captured["base_url"] = base_url
        captured["model"] = model
        captured["timeout_seconds"] = timeout_seconds
        captured["api_key"] = api_key
        return "wm-docgen-ok"

    monkeypatch.setattr("wm_docgen.cli.test_openai_compatible", fake_test_openai_compatible)

    exit_code = main(
        [
            "llm-test",
            "--llm",
            "openai-compatible",
            "--llm-api-base",
            "https://server/ollama/v1",
            "--llm-model",
            "server-model",
            "--llm-api-key-env",
            "OLLAMA_API_KEY",
            "--llm-timeout",
            "17",
        ]
    )

    assert exit_code == 0
    assert "wm-docgen-ok" in capsys.readouterr().out
    assert captured == {
        "base_url": "https://server/ollama/v1",
        "model": "server-model",
        "timeout_seconds": 17,
        "api_key": "secret-token",
    }
