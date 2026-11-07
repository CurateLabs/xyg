# Native frozen temporal graph acquisition checkpoint

This candidate implements the ordered first checkpoint of the original #45
frozen HTML/PNG/SVG task. Full #45 / milestones 4–7 and **rendered artifact
acceptance remain open**. No HTML/PNG/SVG adapter or public WASM freeze API is
claimed. The next seam is specified in
[temporal-graph-frozen.md](../../design/temporal-graph-frozen.md#evidence-and-next-seam).
The full original export task has not been replaced by metadata acceptance.

## Source and provenance

Original accepted parent: `084b3c1b7c393e135476aab9610bf8334767b2ac`.
Fetched accepted main included #1111 as `ae104cf3` and was fast-forwarded.
Reviewed #1110 head `2cb7f0a13ec0af3a00b9dcfd2b104a2c579b7ac9` was locally
merged in `4d1d284fa786532376db2b96200bc3fdced343db`, after mandatory hooks/Ruff.
At the fetch used to select this source, #1110 was not on accepted main;
this receipt records a local reviewed-history dependency, not its delivery.
No rebase/reset/force, children, paid/hosted jobs, push, PR, tags, GitHub mutation,
or watch was used. Final independent review/delivery belongs to the parent.

[identities.json](identities.json) records actual native/source/client/WASM
hashes, environment, raw/gzip byte counts and snapshots. The native library is
preserved as [libxyg_core.so.gz](libxyg_core.so.gz); generated client/WASM assets
remain ignored build artifacts. Native ABI402 adds four functions via the
official declaration generator. Every older signature and earlier packet payload
is retained; `fixture-transition.json` records the current 401→402 metadata-only
fixture refresh. `predecessor401/` preserves authentic complete401 JSON bytes,
checked against the unmodified historical #1110 399→401 receipt. Historical
notebook receipts retain their actual producer ABIs; the current verifier uses
the generated current ABI, tested at402. `current-bindings.json` is a successor
Core qualification binding, with explicit historical bindings; source producers
and Arrow receipts have not been rewritten to claim different bytes. The Core
corpus test also exercises Git CRLF conversion while bound files retain LF.

## Functional evidence

- Rust uses the actual private accepted frame and `TemporalGraph::freeze`,
  capturing canonical visible UUID membership and persistent selection/focus/pins.
  A graph-instance token and frame revision prevent cross-instance/stale acquisition.
- Public Python `TemporalGraph.freeze` and Node `TemporalGraph.freeze` return
  independent native lifetimes. Their canonical snapshot bytes compare exactly
  across actual native host calls on the shared boundary/history fixture.
- Source disposal and later scrubs/state changes preserve old snapshots.
  Short native output writes no bytes. Malformed input, internally rechecksummed
  bad membership/topology/focus, stale revisions, invalid window/timezone,
  one-byte-under decode admission, 256-handle capacity and released handles refuse.
- Actual existing bound GraphSession capture retains the original XYGF and XYGR
  bytes plus camera, positions, routed loop/parallel-edge pieces and resolved
  styles/state. Both hosts exercise this native route. Cross-owner binding,
  stale publication and source mismatches refuse. Subsequent state/camera changes
  cannot rewrite the frozen prior publication. Frame-time and publication-time
  state are recorded distinctly; no renderer silently substitutes one for another.
- Engine tests cover cancellation refusal and exact output admission. No concurrent
  native cancellation latency, massive/aggregate or accessibility claim is made.
- Normal pytest discovers the Python tests; the explicit Node list includes the
  new module. Existing graph SVG/PNG, graph-session, ABI, notebook-verifier and
  workflow controls are run alongside it. Release surfaces/merge_group are preserved.

Native/compiler checks and bounded runtime results are in the compressed logs.
`frame-*.xyfg`, `retained.xyfg`, `retained-later.xyfg` and the Node snapshot JSON
are inspectable actual binary/hex outputs; they are provenance/publication data,
not rendered exports. All three rendered-format recovery/pixel/vector proofs,
normal Scene binding, render/output admission, browser/WASM attachment and package
proof of the eventual freeze API remain next-checkpoint requirements. The current
WASM rebuild only verifies preservation of the existing shipped capabilities/caps.

## Reproduction

Use Node22, Rust1.96.0, a short disk-backed TMPDIR, `CARGO_BUILD_JOBS=2`, and the
project uv environment. Build before exercising newly generated host bindings:

```bash
uv sync --group dev
cargo test -p xyg-engine temporal_graph
cargo build -p xyg-core --release
python3 scripts/gen_abi_manifest.py --check
uv run pytest tests/test_temporal_graph_frozen.py tests/test_temporal_graph_native.py -q
npm ci --prefix packages/xy-node
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/temporal-graph-frozen.test.mjs
uv run python examples/temporal_graph_freeze.py /path/to/frame.xyfg
uv run pytest tests/test_cross_host_abi_transition.py tests/test_graphforge_contract_corpus.py tests/test_graph_notebook_report.py -q
uv run pytest tests/test_graph_static_export.py -k 'not browser' -q
make check-ci
npm ci
node js/build.mjs
npm run build:wasm
uv run python scripts/verify_wasm_assets.py
uv run python spec/performance/temporal-graph-freeze-2026-11-07/capture.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Early logs retain actual failures, including missing native artifacts before the
first build, a Node assertion using the wrong error-property name, and initial
Rust/type/admission fixes. Those failures are not counted as passing evidence.
Focused fresh runtime and final gate logs supersede them. This checkpoint makes
no competitor performance or rendered-customization superiority claim.

## Passing focused results

| Check | Result |
| --- | --- |
| Rust temporal graph / frozen engine | 15 passed |
| Native existing GraphSession FFI controls | 9 passed |
| Fresh Python acquisition/temporal/transition/notebook controls | 112 passed |
| Node public freeze / temporal / existing graph controls | 72 passed |
| Existing fixed graph native SVG/PNG controls | 23 passed, 3 browser tests deselected |
| Actual native/WASM existing session wire replay | 8 passed |
| Current Core qualification and Git CRLF proof | 7 passed |
| `make check-ci` | workflow verification plus 772 passed |
| Clippy `-D warnings` | passed |
| Mandatory hooks / full Ruff check / format check | passed |

The broad early regression run recorded 832 passes and one failure caused by
loading the pre-camera native artifact before the updated build completed
(`KeyError: render.camera`); the current acquisition module subsequently passed
in full with exact camera/publication capture. The broad run is not labelled an
all-green current-artifact run. The fresh focused logs above establish the final
checkpoint and the existing exporter/ABI gates independently. Browser foundation
logs/report qualify preservation of existing WASM/controller journeys, not the
new native-only acquisition attachment. No timing or scale win is claimed.

The successor Core binding initially exposed a missing LF rule for the newly
hash-bound `spec/design/graph-mark.md`. The actual Git CRLF conversion test
failed on that file alone. Its explicit LF rule and fresh successor hashes
repair that failure; the historical evidence files are unchanged.
