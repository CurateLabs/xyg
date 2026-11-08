# Dense temporal clipped-support and cooperative scan continuation

Prepared checkout continuation of def2ae0110b85e6f0c75d638373d350cb06a4415,
normal-merged with root 6ad7cb76d1a02f3df759cffc4218baf26ab1378e. Both
parent histories and receipt directories are preserved exactly. No root artifact,
remote, issue, PR or publication is written by this worker. Independent final
review and delivery belong to root; #46/#38 and milestones 4–7 remain open.

The public XYTMv2 composition now uses Rust-owned XYTJ sessions and bounded
steps on native and actual browser Workers. Exact half-open observations and
clipped incident line-support IDs have separate bounded pages. Geometry uses
root's exact time-fraction and projected-y clipping semantics, including hi,
null gaps, repeats and signed/f64 extremes. Ready output remains private until
capacity-checked read/commit; cancellation, disposal, old replies, rejected
source claims and old waiter cancellation preserve the last accepted result.
Python and Node viewport changes cancel earlier public claims. The ordinary
Scene/StaticDocument/ChartView path paints and exports all six families.

The normative protocol, tier rules and explicit reservation boundaries are in
[temporal-catalog.md](../../design/temporal-catalog.md). Retained sources remain
sized by N. A 100k source fits the declared fixture; 1M at that viewport refuses
the operation working set before index allocation. Caller authoring objects,
constructor transients, language runtime overhead and unrelated host memory
are not claimed as measured Rust operation residency. No 100M/1B allocation,
FPS, competitor victory or all-host qualification is asserted.

The unchanged producer keeps O2/inline-threshold0/stripnone, pinned Binaryen132
O3/function-name reorder/stripdebug, all 551 native declarations/68 WASM
functions, ABI405/WASM38, and fixed raw/gzip6 caps. Actual code sharing covers
Scene endian appends, calendar arithmetic, packet readers and membership hash
updates. Existing shared sort dispatch is reused with identical ordering,
stability and native specialization. No graph/geo identity or policy is adopted.

Reproduce from this source with TMPDIR=/var/tmp and the explicit Node22/Chromium
paths in environment.json. Reuse dependency paths without changing borrowed
virtual environments; all Python tooling uses `uv run --no-sync` and exact
PYTHONPATH/native paths.

```
cargo build --release -p xyg-core
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
cargo test --workspace
uv run --no-sync pytest tests/test_temporal_catalog.py tests/test_graphforge_contract_corpus.py -q
npm test --prefix packages/xy-node
node scripts/temporal_catalog_wasm_parity.mjs packages/xy-client/dist/xyg-wasm.wasm
node scripts/gen_temporal_line_window_fixture.mjs
XYG_WASM_FOUNDATION_REPORT=$PWD/target/task-tmp/foundation.json node scripts/wasm_foundation_smoke.mjs
XYG_REQUIRE_CARGO=1 XYG_REQUIRE_WASM=1 uv build --wheel --out-dir target/task-tmp/dense-dist
uv run --no-sync --with pre-commit pre-commit run --all-files
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
```

The original direct six-family and root eight clipped-line goldens are inherited
contracts checked afresh. Independent Fraction/vector and pixel references,
source-order page oracles and loss/duplication/stale mutations test dense output.
Raw native/WASM comparisons cover all occupied observation/support pages in the
eight authored clipping cases, plus six-family metadata/Scene/member and stepped
control parity. Browser tests use real public Worker/composition/painter methods;
the normal foundation harness also retains root aggregate/frozen/GPU/filter and
default1k/10k controls. No parallel duplicate workflow or browser skip is added.

`checks.json` distinguishes fresh checks from inherited contracts. `failures.json`
and compressed logs retain unsuccessful package experiments, implementation
failures and the first normal Node timer-ordering failure; later success does
not erase them. Two existing Node skips are reported explicitly: a disabled
parsed-identity test and the tracked heatmap fill_opacity gap (#889). They are
unrelated to temporal/browser acceptance. The first browser/parity source
snapshots are archived separately; the final run includes additional exact
support membership oracles. `artifacts.json` binds fresh binaries and the normal
wheel; `raw-archives.json` preserves every captured raw byte/hash/archive mapping.

Core evidence has two exact parent manifests. For every changed parent-bound
source, predecessorSources points to its compressed exact original bytes;
historicalBindings preserves the union of both chains. LF/binary attributes and
an actual CRLF checkout test protect those bytes. The historical IPC producer,
112 Arrow fixtures and old receipts are never regenerated or rewritten.

Remaining broader acceptance: brush/controller/table integration, full AA and
keyboard/reduced-motion journeys, streaming, richer customization, five-view
budgets, source-language object/RSS qualification, 100M+/out-of-core evidence,
competitor comparisons and the installed notebook/application/VS Code host matrix.

The official release API inventory producer refreshes the preparation snapshot
for the public lifecycle methods. Semantic comparison passes; the strict global
classification gate remains open (1,064 unclassified project entries). This
refresh approves no release stability classification.
