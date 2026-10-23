# Core-owned schema and algorithm descriptor corpus (#936)

`contracts.tsv` is exported from GraphForge Core's actual `Algorithm::result_schema`
and `algorithm_descriptor_contracts()` at immutable Core commits in
`provenance.json` (0.5.2) and `0.6.0-rc.5/provenance.json` (rc.5). Source hashes and corpus SHA-256 are recorded. No schemas or
algorithm mappings are recreated in the exporter: it compiles the pinned Core
registry and descriptor iterator with a tiny test-only Rust error shell. Core
code is never linked into the XYG runtime. The source is Apache-2.0, as is XYG.

CI sparsely checks out exactly that Core source pin, regenerates in check mode,
and fails on any changed schema or descriptor fact. Rust then requires the
corpus to match XYG's runtime ledger and the real result fixtures in `../results` and `../results-0.6.0-rc.5`.
Updating the pin without all required ledger/schema/IPC evidence fails closed.

```bash
python3 scripts/sync_graphforge_contract_corpus.py --core-repo /path/to/graphforge
# Deliberate qualification only; do not infer a broad version range:
python3 scripts/sync_graphforge_contract_corpus.py --core-repo /path/to/graphforge \
  --ref <immutable-core-commit> --write
cargo test -p xyg-engine --lib graphforge::ledger
```

The release declaration is `python/xyg/graphforge-compatibility.json`. A test
binds it to this corpus, its exact Core version and real IPC manifest. The exact 0.5.2 and 0.6.0-rc.5 releases are qualified; no interval or
artifact installation pairing is implied. A new version is qualified only after the matching corpus, all new/changed algorithm
fixtures, ledger mappings, and native/Python/Node/WASM evidence pass.

`../derived/pagerank-schema-v2.arrow` and `path-cost-schema-v2.arrow` change only the schema-version metadata
of Core's real 0.5.2 PageRank and rc.5 path-cost tables. It is a rejection fixture, **not evidence of
another Core release**. Regenerate with
`uv run python scripts/gen_graphforge_derived_fixtures.py`; the Python, Node and
real WASM hosts must return the same value-free unsupported-schema diagnostic.

The corpus, provenance, result manifests/generation record, hashed CJS generator,
and runtime compatibility declaration must retain LF bytes across checkouts.
Their scoped `.gitattributes` rules preserve the recorded SHA-256 values and
byte-identical packaged declarations even with Windows `core.autocrlf=true` and
`core.eol=crlf`. Arrow IPC binaries are unaffected. The regression test performs
an actual Git checkout into a temporary repository and proves an unpinned text
control converts to CRLF while all nine hash-bound evidence files stay unchanged:

```bash
uv run pytest tests/test_graphforge_contract_corpus.py -q
```
