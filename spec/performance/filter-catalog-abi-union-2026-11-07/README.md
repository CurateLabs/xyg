# Combined indexed filtering and temporal catalog

This normal merge joins reviewed filtering/graph/native parent
`c90fcd3047e4cac69c307ffe1f27c37c4d69c0f8` and reviewed catalog/cancellation
parent `b8000a60900d4685969a6d68f55324e561199df5`. Their bounded product reviews
are complete; this new combined diff still requires independent review,
current-main integration, hosted CI and the merge queue. No issue or milestone
completion is claimed.

## ABI compatibility and preserved product behavior

Both parents independently used native ABI402 and WASM36 for different
additive exports. The official generators now describe their complete union:
**545 native symbols at ABI403 and 67 required WASM exports at ABI37**.
Every common signature remains identical. The XYFC, XYFR, XYTM, Scene and
painter product contracts retain their existing versions and bytes.
`native-symbol-union.json` and `wasm-export-union.json` record these checks.
Four actual Python/Node loader controls reject the two parent ABI402 native
libraries before generated binding. Actual public Workers also reject both
parent WASM36 modules with the ABI37 mismatch error before export binding.
A shared numeric ABI label alone never establishes compatible artifacts.

The ten current ABI402 fixtures are byte-identical in both parents. Complete
402 and 401 predecessors are retained here before official regeneration to
403. Every packet, case, digest and non-ABI field remains unchanged. The
historical399→401 chain, append-only401→403 tests and new402→403 tests remain
in ordinary pytest discovery. The five Node producers emit JSON on stdout;
the procedure captures that separately from stderr before writing each file.
An initial successful producer invocation that merely logged stdout is not
credited as fixture regeneration.

Rust remains the sole filtering, membership, admission and temporal Scene
compiler. Hosts retain their thin framing, source ownership and dispatch
roles; the shared density and Scene renderers remain in use. Parent protection
covers **16,487 exact entries and 42 explicit combined paths**, with no missing
parent path. All historical performance/temporal/release blobs remain intact;
the preparation inventory is the declared release-metadata exception.
`union-seams.json` checks the unique **68-file** Node command, **531** ownership
entries, **698** exact parent-union preparation gaps, and Python composition
AST preservation. The `Chart` class retains its first-parent `filter_session`
method and every second-parent common method; comparing entire class ASTs
without accounting for this added method was an initial inspection-helper
failure, not a product failure.

The final whole-worktree type check found the catalog adapter assigning an
undeclared internal Figure field. A type-only import and annotation now declare
that existing composition reference, preserving absent-field behavior for
ordinary figures and every method body. After correction,276 Python cases
passed with one browser-discovery skip; that exact PNG case subsequently passed
with an explicit installed Chromium path. An additional89 catalog/lifecycle/ABI
checks passed on actual Python3.11.17. The failed type check is retained separately;
this is the only runtime-module integration follow-up beyond the parent union.

## Single-module packaging

Native release optimization remains Cargo's O3 default. The wasm32-only
configuration uses O2 and LLVM inlining threshold50 with unchanged optimizer
passes, exports, features, resource defaults, runtime guards, tolerances and
deadlines. Normal packaging passes the unchanged **1,927,168 raw / 786,432
Node22 gzip6** limits:

| Artifact | SHA256 | Bytes |
| --- | --- | ---: |
| Native ABI403 | `ed21f677c9e474814e408f534893befc4e53f0ab05bb40ae82c54ace0cff74ff` | 6,234,104 |
| WASM ABI37 | `8217a9ec41d2de69ff30e1ec4193f8564483afcddd4fb33af13eede725bbf3d1` | 1,871,162 raw |
| Node22 gzip6 | Bound by the size log | 771,398 |

The same combined O3/50 source failed normal packaging at **1,927,322 raw /
788,701 gzip6**; O3/40 also failed gzip at792,793. Those failed logs, source
recipes and raw modules remain archived. An optimizer inspection initially
used the exhausted default temporary directory; the disk-backed retry passed.
No failed package, setup attempt or missing-output run receives pass credit.

The unchanged existing `benchmarks/bench_wasm_profiles.mjs` compares the same
O3/50 and O2/50 source with ABBA order: **14 admitted complete outputs are
identical**, with the same100k geographic-interaction resource refusal.
Observed O2/O3 median ratios range **0.951–1.102**. A supplemental reproducible
procedure covers both complete filter corpora, including capacity failures,
and all six temporal families at100/1000/4000 rows: **20 byte-identical cases**,
ratios **0.784–1.128**. Samples and slower cases remain in the reports. These
are shared-VM local compiler diagnostics, not a browser latency, reliable
completion or competitor win. The broad benchmark's gzip field uses level9;
only the separately recorded Node22 gzip6 measurement qualifies packaging.

## Fresh functional evidence

The exact combined source passed fresh native, client and wasm32 release
builds; seven engine filtering tests, two temporal Scene tests, **76 WASM-host
tests**, **194 affected Python tests**, and the full Node command (**1,112
passed, two existing skips**). Python includes all four required decoded-image
chart comparisons. **673 ABI checks**, packaged assets, strict all-target
engine Clippy and the Core/inventory/ownership checks passed.

The actual five-view Chromium journey passed **102 oracle groups, 400 exact
texture texels and19 canvas-coordinate probes**. Pointer and keyboard produce
the same fingerprint and pixels; indexed replies read zero canonical rows.
The two programmatic Worker streams compare44 and56 complete replies. The
public catalog has six complete native/WASM Scene oracles and six offline
Chromium HTML journeys with hostile title/script strings inert, exact u64
identity metadata and normal disposal.

The full strict-CSP source foundation passes both combined branches, the16
camera units, both bounded scheduling cases and all14 retained temporal cases.
The additional unchanged public10k harness also passed with60/59 painted
publications, both views converging at458 steps, unfinished trusted picking,
exact host-camera retention, isolation and cleanup. Complete browser/native/
WASM replay compared63 primary and60 peer replies, retaining all10000 primary
nodes and edges. Each Worker explicitly uses384MiB. The replay module
reaches46137344 linear bytes across both cases; this is neither isolated1k
usage nor process/GPU/RSS memory qualification.

Its final foundation report retains both the indexed-density and six-family catalog
proofs. New full-scope guards reject a missing/nonindexed filter proof or an
omitted catalog family;11 missing/corrupted-proof controls exercise the exact
harness block. Focused density-only execution retains its declared scope.
The first full run passed without a structured report because the inspection
wrapper used an unrecognized report variable; it is retained as a log-only
pass. The subsequent material harness guard/report change was validated with
the correct `XYG_WASM_FOUNDATION_REPORT` variable and a fresh full run.

`checks.json` binds current sources, immutable historical chains, all248 Rust
producer inputs, runtime artifacts, commands/exits, compressed/raw logs,
captures and reports. Generated client/Python copies match. Final metadata and source checks passed181 tests, including real Git LF/CRLF
conversion. The unchanged CI/merge-queue gate passed775 tests. Whole-worktree
hooks, Ruff check and Ruff format check passed. The first naming module run passed154 controls but failed its repository scan
on four historical spellings in the untracked local TASKS worksheet. Those
notes were reworded without changing the scanner, exemptions or historical
committed evidence. The complete rerun passed155 tests, including the actual repository scan.
None of these
results is assumed from parent receipts.

## Reproduction and remaining acceptance

Use Rust1.96, Node22.23.4, explicit `XYG_NATIVE_LIB` for this source, the
repository uv environment, installed Chromium via `XYG_CHROMIUM` and
`XYG_TEST_CHROMIUM`, and a short disk `TMPDIR=/var/tmp`.

```bash
cargo build --release
node js/build.mjs
npm run build:wasm
python3 scripts/gen_abi_manifest.py --check
python3 scripts/gen_wasm_abi.py --check
cargo test -p xyg-engine filter_tier_c --lib
cargo test -p xyg-engine temporal_scene --lib
cargo test -p xyg-wasm --lib
npm test --prefix packages/xy-node
uv run pytest -q tests/test_filter_tier_c.py tests/test_filter_tier_c_density.py tests/test_temporal_catalog.py tests/test_temporal_catalog_geo_integration.py tests/test_geo_temporal_binding.py tests/test_temporal_controller.py tests/test_cross_host_abi_transition.py tests/test_chunked_columns.py
python3 scripts/abi_smoke.py
node scripts/temporal_catalog_wasm_parity.mjs packages/xy-client/dist/xyg-wasm.wasm
node scripts/filter_tier_c_conformance.mjs --chromium "$XYG_CHROMIUM" --capture /var/tmp/combined-filter.png
XYG_WASM_FOUNDATION_REPORT=/var/tmp/combined-foundation.json node scripts/wasm_foundation_smoke.mjs
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

One-off profile, loader, HTML and provenance procedures are archived under
`procedures/`; decompress them into a task temporary directory in the source
checkout to reproduce their explicit commands. The broad profile reuses the
nine hash-bound Arrow inputs from the immutable46-inline50 evidence. No
external release or destructive transition occurs; intact parent branches and
source/artifact histories remain the rollback reference.

This merge does not include the separately reviewed mounted M6 correction,
newer trusted graph-keyboard continuation, GPU admission integration or frozen
export candidate. Their integration and any resulting ABI reconciliation are
separate required work. Original10k missing-reply collection failure remains
unexplained; later passes do not establish a repair or reliability. Filtering
still lacks massive/five-view50FPS, spill/paging, cooperative Worker interruption,
full native transport and broader compatibility. Catalog dense LOD, live
interaction/accessibility, streaming, timezones and complete customization
remain open. Default16MiB1k admission, larger graph ladders, global memory,
all-host/platform/export and competitor acceptance remain open. Whole#112,
#46 and milestones4–7 are not complete.
