# Local default property graph widget candidate — incomplete acceptance

This append-only receipt belongs to the sole-writer implementation worktree
`/home/ubuntu/.t3/worktrees/xyg/t3-56fb3ea2`, branch
`t3/graph-widget-progressive-layout`. Accepted base is
`1bd2e11efedfc28f923b0da1ffa2aeb81089dc27`. The prepared branch started at
`74195403`; normal merge `eab93734` resolved two historical spec conflicts using
accepted main's versions. Full pre-commit/Ruff checks passed before that merge
commit. Human author: David Spencer. No GitHub mutation, push or PR was made.

## Exact entry point diagnosis

At accepted main, `_graphforge.graphforge_chart` → `_graph_chart` constructs a
`components.graph` mark. `_legend_items` may then call `chart.figure()` eagerly,
including the ordinary property fixture; otherwise `Chart.widget()` calls
`FigureWidget(self.figure())`. `Chart.figure` → `_apply_graph` →
`_marks_graph.graph` → `_graph.run_layout(iterations=300)` runs native force work
synchronously. `FigureWidget.__init__` then synchronously calls
`figure.build_payload_split()`. Neither `GraphLayoutController` nor private
`GraphSession` participates. Live issues #1015/#35/#36 and their comments were
read using `gh issue view --json body,comments`; the legacy default gh query
failed on retired projectCards. The current bridge/painter gap is a production
adapter gap, not a missing Rust algorithm or ABI.

The candidate defers legend application until explicit Figure compilation and
connects **only default unlayered property graphs with integral dimensions** to
`GraphWidget` → dedicated executor → existing `GraphSession` → retained Rust
one-tick seed/opcode15 → binary anywidget comm → existing XYGR/GPU-v1 decoder
and painter. Static compilation/export remains batch. Typed u64 header buffers
are explicit: generic NumPy inference rounds mixed large unsigned/scalar lists,
which initially caused intermittent native instance mismatches in two-widget
proof; explicit `<u8` construction fixes it without ABI changes.

## Proof and reproduction

Use Node 22 at
`/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin`
and `/home/ubuntu/.cargo/bin` on PATH. From this worktree:

```
uv sync --group dev
cargo build --release
npm ci
node js/build.mjs
uv pip install jupyterlab ipykernel
uv run pytest tests/test_graph_widget.py tests/test_graphforge.py tests/test_graph_session_python_transport.py -q
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome XYG_GRAPH_NOTEBOOK_REPORT=target/graph-notebook-report.json node scripts/graph_notebook_progressive_smoke.mjs
uv run python scripts/check_release_inventory.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The focused suite passed 63 tests in 3.06 seconds before final metadata edits.
The test blocks a worker with a bounded event while the event loop executes a
heartbeat; it separately exercises actual native progress, stale-mount refusal,
foreign-instance refusal/stable failure, two-widget isolation and rerender
suppression. This is not a large-data responsiveness measurement.
`notebook.json` and `notebook-pixels.json` are separate successful real
JupyterLab/IPython/anywidget native runs: 458 terminal native steps, 900×420
canvas, 415 nontransparent final pixels in the pixel run. Their first observed
step 41 is polling latency, not the initial step or a first-paint timing claim.
The later `notebook-frames.json` adds passive DOM observation of every presented
step and initial nontransparent pixels. No held ACK or fake model is used.
Known captured warnings are anywidget direct-render deprecation and SwiftShader
readback stalls. Failed development runs remain in owned `target/` logs; an
initial notebook assertion caught eager legend compilation, and initial Python
isolation proof caught the u64 framing error. Neither failed run is acceptance.

`environment.json` and `hashes.json` record versions and source/artifact hashes
at the evidence-producing working tree. Their git HEAD is the merge checkpoint,
**not a claim that the unstaged candidate bytes belonged to that commit**.
Generated paint bundles are untracked build artifacts; no WASM source, artifact,
resource cap, tolerance, ABI signature or package limit changed.

## Remaining acceptance and material limitations

This is an incomplete candidate for parent review, not completion of the task,
#1015, #35, #36, #108 or a release gate. The native viewer currently presents
geometry only. It has no pointer/keyboard/pan/selection adapter and therefore
has less interaction than the prior default generic widget. It omits the
composition legend/custom presentation. Configured/layered charts keep the
synchronous generic widget. Extending the retained path while preserving those
behaviors requires a native presentation and return-channel adapter; the browser
WASM attachment's richer interactions have not been factored into this bridge.

Still required: UUID roundtrip, exact pick/box/lasso, frontend coverage,
annotations/export parity, all configured public widget paths, required rendered
size ladder, timing budgets and trusted interaction, browser lifecycle race
proof, notebook smoke in the existing Release surfaces aggregate, and independent
parent review. The current notebook smoke proves only one small property graph,
progressive paint, another cell execution and disposal. Python native calls are
serialized by the existing private transport lock. There is no competitor
performance claim or new capability-matrix completion claim. Static HTML has no
kernel return channel, documented in the API contract.
