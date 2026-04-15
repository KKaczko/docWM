# webMethods Documentation Generator

`wm-docgen` scans webMethods Integration Server package artifacts, extracts service
steps and dependencies from `flow.xml`, extracts signatures from `node.ndf`, and
generates JSON plus a MkDocs Material documentation portal.

The project supports two input modes:

- Real package trees with `manifest.v3` and `ns/`.
- Reconstructed synthetic services from orphan artifacts such as the current
  root-level `flow(1).xml` and `node.ndf`.

Synthetic structure is always marked as inferred in JSON and generated Markdown.

## Install

```bash
python3 -m pip install -e ".[dev]"
```

## Build Documentation

```bash
wm-docgen build --source . --out build/docgen --docs docs --processes examples/processes.yml
```

Outputs:

- `build/docgen/services.json`
- `docs/services/...`
- `docs/processes/...`
- `docs/reports/summary.md`
- `mkdocs.yml`

Preview the portal after installing the dev dependencies:

```bash
mkdocs serve
```

## Commands

```bash
wm-docgen scan --source . --json build/docgen/services.json
wm-docgen validate --source .
wm-docgen fetch-samples --out examples/public-samples
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

## Tests

```bash
python3 -m pytest
```
