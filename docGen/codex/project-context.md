# wm-docgen Project Context For Future Codex Sessions

Last updated: 2026-04-20

## Purpose

`wm-docgen` is a Python documentation generator for webMethods Integration
Server packages. It scans package folders, parses `flow.xml` and `node.ndf`,
extracts services, signatures, service calls, mappings, conditions, document
references, process scope, and generates a browsable MkDocs Material portal.

The parser is the source of truth. LLM output is optional enrichment only and
must not create dependencies, hide validation issues, or alter parsed facts.

## Original Product Goal

Build a production-grade documentation generator that can handle many
webMethods packages and services, not a single example file. The user may only
have partial sample artifacts locally, so the system must support:

- real package roots containing `manifest.v3` and `ns/`
- multiple packages inside one `packages/` folder
- orphan artifacts such as standalone `flow.xml` and `node.ndf`
- reconstructed synthetic services where structure is inferred
- mixing real and inferred data while clearly marking inferred structure

Do not overfit to one sample. Missing, unknown, or inferred data must be
reported explicitly.

## Public Sample Research

The original plan was based on publicly available webMethods-style samples:

- `Permafrost/Tundra`
- `johnpcarter/JcPublicTools`
- `ibm-wm-transition/webmethods-integrationserver-pgpencryption`
- `ibm-wm-transition/WxSAPIntegration`

The project includes a sample fetcher, but public samples should only be treated
as real packages when a fetched directory contains both `manifest.v3` and a
matching `ns/` tree.

## Current High-Level Flow

The main build path is:

```text
scan_source
  -> discover package/service/document artifacts
  -> parse flow.xml and node.ndf
  -> classify dependencies
  -> validate scan result
  -> load/analyze processes.yml
  -> optional LLM enrichment
  -> write build/docgen/services.json
  -> generate docs/
  -> generate mkdocs.yml
```

Normal builds are deterministic. Ollama/OpenAI-compatible enrichment only runs
when explicitly requested with `--llm`.

## Fresh Install

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

On Windows Git Bash:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

## Main Commands

List discovered service IDs:

```bash
wm-docgen list-services --source packages
wm-docgen list-services --source packages --format plain
wm-docgen list-services --source packages --include-documents
```

Scan only:

```bash
wm-docgen scan --source packages --json build/docgen/services.json
```

Validate:

```bash
wm-docgen validate --source packages
```

Build deterministic docs:

```bash
wm-docgen build \
  --source packages \
  --out build/docgen \
  --docs docs \
  --processes examples/processes.yml
```

Preview:

```bash
mkdocs serve
```

Run tests:

```bash
python -m pytest
```

Last known local test result after current changes:

```text
22 passed
```

## Important Files

- `src/wm_docgen/cli.py` - CLI commands.
- `src/wm_docgen/discovery.py` - package, service, Java service, document node, and synthetic artifact discovery.
- `src/wm_docgen/flow_parser.py` - `flow.xml` parser.
- `src/wm_docgen/node_parser.py` - `node.ndf` parser.
- `src/wm_docgen/graph.py` - dependency classification.
- `src/wm_docgen/processes.py` - `processes.yml` loading and process traversal.
- `src/wm_docgen/docs.py` - Markdown and `mkdocs.yml` generation.
- `src/wm_docgen/diagrams.py` - Mermaid diagram generation.
- `src/wm_docgen/models.py` - dataclass domain model.
- `src/wm_docgen/llm/` - optional LLM enrichment.
- `examples/processes.yml` - process config example.
- `examples/llm.yml` - native Ollama config example.
- `examples/openai-compatible-llm.yml` - OpenAI-compatible server config example.
- `examples/sample-packages/` - representative local sample package.
- `tests/` - parser, discovery, docs, CLI, process, and LLM tests.

## Domain Model

Core dataclasses are in `src/wm_docgen/models.py`:

- `Package`
- `Service`
- `Step`
- `DependencyEdge`
- `ExternalDependency`
- `DocumentReference`
- `DocumentType`
- `ProcessDefinition`
- `BusinessStep`
- `ValidationIssue`
- `DynamicInvocation`
- `EntityAction`
- `MappingFact`
- `ConditionFact`
- `LlmEnrichment`
- `ScanResult`

JSON output is written to `build/docgen/services.json`.

## JSON Output Shape

Top-level keys include:

- `packages`
- `services`
- `document_types`
- `dependencies`
- `external_dependencies`
- `validation_issues`
- `llm_enrichments`

Each service includes identity, package, namespace, source files, inferred
structure marker, parsed steps, dependencies, inputs, outputs, document refs,
dynamic invocations, entity actions, mapping facts, condition facts, LLM
enrichment, and warnings.

## Discovery Behavior

Real package discovery:

- Looks for `manifest.v3`.
- A directory is a package root only if it also contains `ns/`.
- Service IDs are derived from paths under `ns/`.
- Example: `ns/com/company/order/submitOrder/flow.xml` becomes
  `com.company.order:submitOrder`.

Synthetic discovery:

- Used when standalone flow artifacts are found outside package roots.
- Default service ID for one orphan flow is `synthetic.current:flow_1`.
- Structure is marked inferred with warnings.
- CLI supports `--service-id` override for one orphan flow.

Java/document discovery:

- `flow_service`: has `flow.xml`.
- `java_service`: `node.ndf` indicates Java service metadata without `flow.xml`.
- `document_type`: document-only `node.ndf`.
- `unknown_node`: unsupported node shape, reported as a validation warning.

## Flow Parser Behavior

`flow.xml` support currently includes:

- nested `FLOW`, `SEQUENCE`, `MAP`, `MAPINVOKE`, `INVOKE`, `BRANCH`, `LOOP`, `EXIT`
- service dependency extraction from `SERVICE` attributes
- comments from `COMMENT`
- mapping operations from `MAPSET`, `MAPCOPY`, `MAPDELETE`
- condition facts from branch/sequence expressions and loop arrays
- entity actions from deterministic mapping/condition extraction
- document references from `rec_ref`
- warnings for unsupported flow XML nodes

Known dynamic invokers currently include:

- `pub.flow:invoke`
- `pub.flow:invokeWithPipeline`
- `tundra.service:invoke`

Dynamic invocation detection is conservative. It emits warnings and evidence,
but does not create guessed dependency edges.

## Node Parser Behavior

`node.ndf` support currently includes:

- top-level metadata such as `svc_type`, `svc_subtype`, `svc_sigtype`,
  `node_type`, `node_subtype`, `node_comment`
- recursive parsing of `svc_sig/sig_in` and `svc_sig/sig_out`
- field data such as `field_name`, `field_type`, `field_dim`, `rec_ref`,
  comments
- document references from `rec_ref`
- document-only nodes via `rec_fields`

The parser should remain resilient to partial or malformed metadata and emit
validation issues instead of silently ignoring unknowns.

## Dependency Classification

Dependency kinds:

- `internal` - target service exists in scan result
- `pub_service` - target starts with `pub.` or `wm.`
- `external_service` - target has service ID shape but is not in scan
- `document_reference` - dependency from `rec_ref`
- `unresolved` - malformed or empty target

Every dependency should be explicitly classified or reported.

## Process Documentation

Processes are configured in YAML:

```yaml
processes:
  - id: order-submission
    name: Order Submission
    entrypoints:
      - com.company.order:submitOrder
    business_description: >
      Receives and validates an order before billing and fulfillment.
    owners:
      - Order Management Team
    tags:
      - order
    business_steps:
      - name: Receive request
        description: Accept the order submission request.
        services:
          - com.company.order:submitOrder
```

Entrypoints define technical traversal. `business_steps` are annotations over
the traversal. Services reached by traversal but not listed in business steps
are supporting technical services, not errors.

Validation warnings:

- `PROCESS_ENTRYPOINT_MISSING`
- `BUSINESS_STEP_SERVICE_MISSING`
- `BUSINESS_STEP_SERVICE_NOT_REACHABLE`

Processes are optional. Without a useful `processes.yml`, the tool can still
generate service-level docs and reports.

## Documentation Output

Generated docs include:

- `docs/index.md`
- `docs/business-summary.md`
- `docs/services/...`
- `docs/documents/...`
- `docs/processes/...`
- `docs/reports/summary.md`
- `mkdocs.yml`

Service pages include:

- service identity and package data
- source files
- warnings
- inputs/outputs
- invoked services
- document references
- dynamic invocation risks
- parsed entity actions
- parsed conditions
- parsed mapping behavior
- optional AI-assisted interpretation
- Mermaid dependency diagram
- parsed step tree

Process pages include:

- business overview
- entrypoints
- business flow from `business_steps`
- traversed service list
- supporting technical services
- external dependencies
- dynamic invocation risks
- unknowns
- optional AI-assisted narrative
- Mermaid diagram

Business summary includes stakeholder-oriented process cards and optional
AI-assisted overview text.

## Mermaid Diagrams

Mermaid diagrams are emitted as fenced code blocks in Markdown:

````markdown
```mermaid
graph TD
...
```
````

The generator now writes `mkdocs.yml` with `pymdownx.superfences` custom
Mermaid fence. Without that config, MkDocs shows Mermaid as plain text.

Expected generated config:

```yaml
markdown_extensions:
- tables
- pymdownx.superfences:
    custom_fences:
    - name: mermaid
      class: mermaid
      format: !!python/name:pymdownx.superfences.fence_code_format
```

If diagrams still show as text:

1. Re-run `wm-docgen build`.
2. Restart `mkdocs serve`.
3. Hard-refresh the browser with `Ctrl+F5`.

## LLM Enrichment

LLM enrichment is optional. Deterministic build remains default:

```bash
wm-docgen build --source packages --out build/docgen --docs docs --processes examples/processes.yml
```

Native Ollama mode uses `/api/chat`:

```bash
wm-docgen build \
  --source packages \
  --out build/docgen \
  --docs docs \
  --processes examples/processes.yml \
  --llm ollama \
  --ollama-url http://localhost:11434 \
  --ollama-model llama3.1
```

OpenAI-compatible mode uses `/v1/chat/completions`:

```bash
export OLLAMA_API_KEY='your-key'

wm-docgen build \
  --source packages \
  --out build/docgen \
  --docs docs \
  --processes examples/processes.yml \
  --llm openai-compatible \
  --llm-api-base https://server/ollama/v1 \
  --llm-model MODEL_NAME \
  --llm-api-key-env OLLAMA_API_KEY
```

Git Bash test command for a remote Ollama/OpenAI-compatible server:

```bash
export OLLAMA_API_KEY='your-key'

wm-docgen llm-test \
  --llm openai-compatible \
  --llm-api-base https://server/ollama/v1 \
  --llm-model MODEL_NAME \
  --llm-api-key-env OLLAMA_API_KEY
```

OpenAI-compatible response extraction supports the standard path:

```text
choices[0].message.content
```

It also has a fallback that searches nested `message.content` values when a
server wraps `choices` unusually.

LLM behavior rules:

- LLM receives compact fact packets generated from parsed data.
- LLM output is labeled AI-assisted.
- LLM failures become warnings such as `LLM_ENRICHMENT_SKIPPED`.
- LLM output must not create dependencies or alter parser facts.
- Cache is stored under `build/docgen/llm-cache` by default.

## Current Test Coverage

Current tests cover:

- orphan synthetic flow/node parsing
- real package discovery
- service ID derivation
- Java service discovery
- document-only node discovery
- unsupported flow node warnings
- dynamic invocation warnings
- dependency classification
- process `business_steps`
- generated docs and MkDocs config
- Mermaid MkDocs config generation
- CLI list/build/scan
- native Ollama client
- OpenAI-compatible client
- LLM cache behavior
- LLM docs sections

## Known Production Risks / Recommended Next Work

Recommended before heavy production use:

1. Add `--exclude` for discovery so `--source .` can skip `.venv`, `build`,
   `docs`, `site`, `.git`, etc.
2. Add TLS/certificate options for corporate OpenAI-compatible servers:
   - `--llm-ca-cert`
   - possibly `--llm-insecure-skip-verify` as explicit opt-in only
3. Make `enabled_sections` actually control which LLM sections run.
4. Add warning/error if `--llm-api-key-env` is provided but the env var is
   missing.
5. Escape Markdown table cells to avoid broken tables when parsed text contains
   `|`, backticks, or newlines.
6. Reduce risk in `generate_docs()` cleanup. It currently deletes generated
   managed dirs such as `docs/services`.
7. Add a larger smoke test with many generated packages/services/documents.
8. Consider a `suggest-processes` command later to infer candidate process
   entrypoints, but keep it explicit and reviewable.

## Guidance For Future Agents

When changing this project:

- Keep parser output deterministic.
- Preserve additive JSON compatibility where possible.
- Add tests for any behavior change.
- Do not silently ignore unknown webMethods XML constructs.
- Do not infer dependencies unless explicitly marked and approved by a new
  feature.
- Keep LLM enrichment separate from parsing and graph building.
- Keep production package paths configurable; do not hard-code user package
  names.
- Avoid broad refactors until real package scans expose concrete pain points.
- Prefer small, reviewable changes in the touched module only.

