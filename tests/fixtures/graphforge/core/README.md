# Immutable GraphForge Core result corpus

XYG owns result dispositions. These are authentic Core-produced Arrow results
and native algorithm descriptors, not an editor's rendering ledger.
`spec/graphforge-compatibility.json` pins exact source/package identities and every
retained file by SHA-256 and byte length. Core `0.6.0-rc.5` source is
`aaa573f446bbed5b8d7577c9a9824ddd6664e840`.

The Linux x64 native runtime generated 112 Arrow fixtures without a failure,
covering 96 algorithm descriptors and search/base/Cypher/schema outputs.
`contracts.tsv` is the deterministic Rust-test projection of `descriptors.json`
and the result manifest; the Python checker verifies that projection. Rust
checks each descriptor's schema version and canonical fields, then composes
every algorithm through the shared engine. Embeddings use explicit parallel
coordinates; `bfs_depth`/`dijkstra_cost` use a source/target/cost table because
Core returns no path. UUIDs remain canonical text in table cells.

Qualification covers result-schema composition only. It does not select the
Core/XYG launch cohort or qualify Hub, CLI, VSIX, supported-platform, or public
registry publication. The release declaration deliberately leaves
`selectedLaunchPairing` unset. Core #1095 selects a later immutable candidate;
that candidate requires its own authentic corpus and affected qualification.

Reproduce on Linux x64 with Node 20+ in a clean temporary directory:

```bash
npm pack @curatelabs/graphforge@0.6.0-rc.5
npm pack @curatelabs/graphforge-linux-x64-gnu@0.6.0-rc.5
sha256sum *.tgz
mkdir -p node_modules/@curatelabs/graphforge node_modules/@curatelabs/graphforge-linux-x64-gnu
tar -xzf curatelabs-graphforge-0.6.0-rc.5.tgz --strip-components=1 -C node_modules/@curatelabs/graphforge
tar -xzf curatelabs-graphforge-linux-x64-gnu-0.6.0-rc.5.tgz --strip-components=1 -C node_modules/@curatelabs/graphforge-linux-x64-gnu
```

The tarball SHA-256 values must match `packages` in the declaration before
loading either package; npm's registry SHA-512 integrities are retained there
too. From the checkout, use absolute temporary package/output paths:

```bash
node scripts/gen_graphforge_result_fixtures.cjs /absolute/temp/node_modules/@curatelabs/graphforge /absolute/temp/results
node -e 'const {GraphForge}=require(process.argv[1]); process.stdout.write(JSON.stringify(new GraphForge().algorithmDescriptorContracts(),null,2)+"\n")' /absolute/temp/node_modules/@curatelabs/graphforge > /absolute/temp/descriptors.json
```

Produce the Rust projection alongside that captured output:

```bash
python3 - /absolute/temp <<'PYTHON'
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
descriptors = json.loads((root / "descriptors.json").read_text())
manifest = json.loads((root / "results/manifest.json").read_text())
lines = ["algorithm\tverb\talgorithm_version\tresult_schema_version\tbase"]
for item in descriptors:
    lines.append("\t".join(str(value) for value in (
        item["algorithm"], item["verb"], item["algorithmVersion"],
        item["resultSchemaVersion"], manifest["fixtures"][item["algorithm"]]["base"],
    )))
(root / "contracts.tsv").write_text("\n".join(lines) + "\n")
PYTHON
```

The generator emits synthetic identities afresh, so regenerated IPC bytes are
not expected to have the retained run's hashes. Review a regenerated corpus as
new evidence, retain its manifest/descriptors from the same invocation, and
refresh the declaration hashes deliberately. Do not relabel retained bytes as a
new Core version. After recording a new corpus, the checks are:

```bash
python3 scripts/check_graphforge_compatibility.py --tag xyg-v0.6.0-rc.1 --core-version 0.6.0-rc.5
cargo test -p xyg-engine graphforge::
uv run pytest -q tests/test_graphforge_compatibility.py tests/test_graphforge.py
```

The historical `../results` corpus remains Core 0.5.2 for existing cross-host
byte-parity regression tests. `../extension/RESULT_SCHEMAS.md` is historical
provenance; XYG no longer uses it to define product dispositions.
