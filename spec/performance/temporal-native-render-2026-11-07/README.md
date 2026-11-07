# Native retained temporal graph rendered continuation

Implementation base acquisition/codec: 59b1c38a337925a8bad11333ed8d04aea76a03e0.
Local first parent: bea7eab1 (full identity in checks.json). The local merge
preserves both accepted-main/public10k and acquisition ancestry. No producer
checkout, remote, issue, PR, merge queue, or milestone was mutated.

This candidate renders actual native SVG/PNG and offline inline-SVG HTML in
both Python and Node, exposes shared canonical XYGS/XYPB, and recovers exact
full XYFG only after regenerating and comparing the whole artifact. The
versioned carrier binds export format, scale and explicit focus RGBA. Node
and Python are thin native callers. There is no graph re-layout or re-routing.

Fresh commands, environment, source/native/artifact hashes, raw logs and output
artifacts are recorded alongside this file. Compressed logs preserve initial
failures as well as final runs. Acquisition-era receipts are inherited and
unchanged; their historical test counts are not presented as fresh candidate
proof. Current ABI403 fixtures differ from preserved complete ABI402 files
only at the ABI version field, with the older 399/401 histories still checked.
No WASM rebuild, source freshness, bundle freshness, or native/WASM rendered
parity is claimed by this native continuation. It uses no WASM/client artifact.
Neither WASM byte cap was changed.

## Reproduction

Set PATH to the supplied Node22 bin, ~/.cargo/bin and ~/.local/bin. Set TMPDIR
to a short disk directory. Build with CARGO_TARGET_DIR set to an isolated target:

```sh
cargo build --release -p xyg-core
export XYG_NATIVE_LIB="$CARGO_TARGET_DIR/release/libxyg_core.so"
export PYTHONPATH=python
export XYG_FROZEN_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
uv run pytest tests/test_temporal_graph_frozen.py tests/test_cross_host_abi_transition.py tests/test_graphforge_contract_corpus.py -q
node --test packages/xy-node/test/temporal-graph-frozen.test.mjs
cargo test -p xyg-engine temporal_graph_export
python3 scripts/gen_abi_manifest.py --check
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The offline HTML test runs Chromium with DNS blocked after scrub/disposal,
checks a painted node pixel against background, and runs scales 1/2 at DPR1/2.
It uses the ordinary discovered pytest module. Native Node tests run after
session/temporal destruction and validate all three artifacts and full recovery.

## Remaining acceptance / scope limits

P1: HTML is currently inline canonical SVG; the requested existing ChartView
XYPB framing is still required. Public WASM/browser acquisition and resolved CSS
focus capture are still required, as are native/WASM rendered parity and full
aggregate/massive scale evidence. This does not close #45 or milestones 4–7.

P1: Focus SDF offsets for marker shapes other than circle/square fail closed
instead of silently substituting scaled symbols. Independent visual vectors
for all semantic styles, focus, pins and frames are not complete. The phase
splitter has a direct independent distance oracle; current end-to-end fixture
coverage is bounded and is not a full dash/style matrix.

P2: Export and recovery reserve operation memory; #111 global process budget
remains outstanding. Recovery performs a full deterministic re-render, so
validation cost includes rasterization for PNG. No authenticity claim is made.

Independent review of this exact final Git export is the parent's responsibility;
this implementation agent did not independently approve its own change.
