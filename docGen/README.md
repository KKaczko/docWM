# webMethods Documentation Generator

`wm-docgen` scans webMethods Integration Server package artifacts, extracts service
steps and dependencies from `flow.xml`, extracts signatures from `node.ndf`, and
generates JSON plus a MkDocs Material documentation portal.

The project supports two input modes:

- Real package trees with `manifest.v3` and `ns/`.
- Reconstructed synthetic services from orphan artifacts such as a standalone
  `flow.xml` and `node.ndf` pair.

Synthetic structure is always marked as inferred in JSON and generated Markdown.

## Install

```bash
python3 -m pip install -e ".[dev]"
```

## Build Documentation

```bash
wm-docgen build --source examples/sample-packages --out build/docgen --docs docs --processes examples/processes.yml
```

Outputs:

- `build/docgen/services.json`
- `docs/services/...`
- `docs/documents/...`
- `docs/processes/...`
- `docs/business-summary.md`
- `docs/reports/summary.md`
- `mkdocs.yml`

Preview the portal after installing the dev dependencies:

```bash
mkdocs serve
```

## Commands

```bash
wm-docgen scan --source packages --json build/docgen/services.json
wm-docgen list-services --source packages --format plain
wm-docgen validate --source packages
wm-docgen fetch-samples --out examples/public-samples
wm-docgen llm-test --ollama-url http://localhost:11434 --ollama-model llama3.1
wm-docgen llm-test --llm openai-compatible --llm-api-base https://server/ollama/v1 --llm-model MODEL_NAME --llm-api-key-env OLLAMA_API_KEY
```

Use `--service-id package.namespace:serviceName` when scanning one orphan flow if
you want to override the default synthetic identity.

## Public Sample Sources

The sample fetcher downloads representative artifacts from public repositories:

- `Permafrost/Tundra`
- `johnpcarter/JcPublicTools`
- `ibm-wm-transition/webmethods-integrationserver-pgpencryption`
- `ibm-wm-transition/WxSAPIntegration`

Downloaded samples are treated as real packages only when the fetched directory
contains both `manifest.v3` and a matching `ns/` tree.

## Current Parser Coverage

`flow.xml`:

- Preserves nested `FLOW`, `SEQUENCE`, `MAP`, `MAPINVOKE`, `INVOKE`, `BRANCH`,
  `LOOP`, and `EXIT` steps.
- Extracts `SERVICE` attributes from `MAPINVOKE` and `INVOKE`.
- Captures comments on steps.
- Captures `MAPSET`, `MAPCOPY`, and `MAPDELETE` as raw mapping operations.
- Emits validation warnings for unsupported flow nodes.

`node.ndf`:

- Extracts `svc_sig/sig_in` and `svc_sig/sig_out` fields where present.
- Captures `field_name`, `field_type`, `field_dim`, `node_comment`, and `rec_ref`.
- Keeps parsing resilient when metadata is incomplete.

Dependency classification:

- `internal`: target service exists in the scan.
- `pub_service`: built-in `pub.*` or `wm.*` services.
- `external_service`: syntactically valid service reference outside the scan.
- `document_reference`: document references discovered through `rec_ref`.
- `unresolved`: malformed or empty dependency target.

## Business Process Steps

Use `business_steps` in `processes.yml` to add ordered business context without
changing technical traversal from entrypoints.

```yaml
processes:
  - id: order-submission
    name: Order Submission
    entrypoints:
      - com.company.order:submitOrder
    business_description: >
      Receives and validates an order before billing and fulfillment.
    business_steps:
      - name: Receive request
        description: Accept the order submission request.
        services:
          - com.company.order:submitOrder
      - name: Create invoice
        services:
          - com.company.billing:createInvoice
```

The process page shows the business flow first, then supporting technical
services, external dependencies, dynamic invocation risks, and unknowns. The
portal also includes `business-summary.md` for stakeholder review.

## Production Helpers

List service IDs without opening JSON:

```bash
wm-docgen list-services --source packages --format plain
```

Show package/type/warning counts:

```bash
wm-docgen list-services --source packages
```

Include document-only nodes:

```bash
wm-docgen list-services --source packages --include-documents
```

The scanner also detects Java service `node.ndf` files without `flow.xml`,
document-only `node.ndf` files, and known dynamic invocation patterns such as
`pub.flow:invoke`. Dynamic invocation targets are reported as risks unless they
are statically visible; the tool does not invent dependency edges.

## Optional Ollama Enrichment

Normal builds are deterministic and do not call an LLM. To add local
AI-assisted explanations, run a build with Ollama enabled:

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

For OpenAI-compatible servers, such as an Ollama proxy exposed at
`/v1/chat/completions`, use `openai-compatible` and keep the API key in an
environment variable:

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

You can also use a config file:

```bash
wm-docgen build \
  --source packages \
  --out build/docgen \
  --docs docs \
  --processes examples/processes.yml \
  --llm ollama \
  --llm-config examples/llm.yml
```

OpenAI-compatible config example:

```bash
wm-docgen build \
  --source packages \
  --out build/docgen \
  --docs docs \
  --processes examples/processes.yml \
  --llm openai-compatible \
  --llm-config examples/openai-compatible-llm.yml
```

Useful flags:

- `--llm-cache build/docgen/llm-cache`
- `--refresh-llm`
- `--llm-timeout 120`
- `--llm-api-base https://server/ollama/v1`
- `--llm-model MODEL_NAME`
- `--llm-api-key-env OLLAMA_API_KEY`

LLM sections are clearly labeled as AI-assisted. Parsed dependencies, mappings,
conditions, and validation warnings remain the source of truth.

## Tests

```bash
python3 -m pytest
```
