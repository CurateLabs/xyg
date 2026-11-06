# Public graph notebook progressive layout — R2 implementation candidate

Workspace: `/home/ubuntu/.t3/worktrees/xyg/t3-56fb3ea2`, sole implementation writer.
Branch: `t3/graph-widget-progressive-layout`.
Accepted base: `1bd2e11efedfc28f923b0da1ffa2aeb81089dc27`.
Continuation start: `864cafec83663177047b91bbcbe15de8c09a54a1`.
Human author: David Spencer. No child agents, push, PR, GitHub mutation or watch.
Parent owns independent review and delivery. This receipt is implementation
proof, not independent approval or #1015/#35/#36/#108 closure.

R1 and every byte of its [original receipt](../graph-widget-progressive-2026-11-06/README.md)
remain in history. The parent rejected R1's geometry-only default renderer as a
material regression. R2 supersedes that route rather than hiding it behind an
opt-in or describing lost generic behavior as unsupported.

## Responsible integration and final path

Accepted main's path was `graphforge_chart` → `_graph_chart` → eager legend
`chart.figure()` or `Chart.widget()` → `FigureWidget(self.figure())` → graph mark
→ `run_layout(iterations=300)` → synchronous payload build. R1 bypassed this with
GPU-v1 geometry only and lost the generic notebook presentation/channel.

R2 uses `Chart.widget()` → private `GraphWidget(FigureWidget)` → the existing
`GraphLayoutController` retained native ForceState. Its asynchronous observer
compiles the original declarative chart on a build worker using native source-f64
checkpoint positions and `layout="preset"`. No second force run occurs. The same
Rust geometry/style/label/LOD/membership/offset encoding and original ChartView
and `channel.handle_message` own presentation and interaction. This preserves the
mark's original algorithm/seed/options (default force, 300 steps) instead of
R1's separate implicit CoSE path. `63_graph_controller.ts` was traced; its explicit
WASM GPU/companion contract is not the generic notebook's presentation contract.
A transport-neutral extraction there would not preserve the original compiler,
legend and authored controls. The existing force-controller seam fits this route;
no new layout, identity or selection implementation was introduced.

All GraphForge graph compositions use this path, including layers, themes,
styles, CSS dimensions, callbacks and authored children/axes. The original mark,
composition legend and static Figure cache are preserved. Non-graph composition
hosts and explicit static/batch APIs are unchanged. Full GraphSession semantic
refs remain separate work; the opaque private transport itself is unchanged.

One native publication is outstanding until paint ACK. Exact readout/selection
replies may hold that one pending picture briefly so old requests are resolved
against their exact displayed Figure. At most displayed and pending snapshots
are retained. Once ACK retires a picture, its revision is refused. Instance and
mount epoch stamp every request/reply; each widget has separate native state,
workers and callbacks. Native row-space changes invalidate cached masks/targets,
never remap inferred identities. GPU refresh drops old hover/neighborhood handles
before drawing and binds surviving targets to fresh GPU objects.

Notebook comm traffic can arrive from a different loop than the mount. Owner-loop
marshaling is required for messages, cancellation and Python mutations. Before
initial paint mutations queue; `view_state()` has empty version-1 ranges until
native computation supplies a home domain, and retains the prior cache on
remount. Saved-widget spec/buffers retain the accepted picture without a second
binary send. Close/rerender cancels cooperatively at native chunk boundaries;
failures use `XYG_GRAPH_WORKER_FAILED` and retain the last picture without fallback.
The existing 30-second budget is unchanged and includes delivery wait time.

## Raw proof and scope

- `focused-tests.log`: **166 passed in 8.45s**, covering this route plus existing
  widget/channel/view-state, native force controller, composition and gate tests.
  Native checks cover node and every routed source edge, including the property
  fixture's parallel pair and self-loop, through existing Rust route/CSR identity;
  exact batch terminal positions; layered/custom theme/style/CSS/axis controls;
  cached view state; queued Python row selection; stale/foreign ownership;
  rerender; stable failure; thread/loop ownership; saved state without duplicate
  trait buffer sync; and two-widget independence.
- `report-verifier-tests.log`: focused receipt/path/workflow negative checks.
- `check-ci.log`: **770 passed in 372.72s**, plus the workflow/queue verifier.
  This suite ran during implementation; final workflow verification and receipt
  negative tests were also run after the final narrow changes. The existing
  `test` job and Release surfaces aggregate are reused. No job/status, merge-group
  trigger, queue requirement, compatibility inventory or resource gate was added
  or weakened. Notebook test tooling is pinned only in the existing CI step.
- `notebook.json` / `notebook.log`: real JupyterLab, IPython, anywidget binary
  comm and Chromium; two public widgets, 39 observed native checkpoints from
  step 1 through step 300, trusted keyboard/navigation while unfinished, exact
  kernel node callbacks, Python-origin row selection, default title/composition
  legend, reset and stationary final pointer callback, and closure of both.
  `pageErrors` is empty. Initial screenshot is sampled during unfinished layout;
  the first passive DOM-observed checkpoint is step 1. No paint budget is inferred
  from polling time, and no ACK is artificially held for inspection.
- `initial.png` / `final.png`: actual browser screenshots, copied from the
  producer's explicit `artifactDir` and checked against its SHA256 fields.
  The initial picture is nonterminal; the final picture follows Python row
  selection. Post-terminal pointer inspection is separate from progress evidence.
- `notebook-verifier.log`: the committed report verifier accepts the real report.
- `types.log`, `api-inventory.log`, `public-api.log`, `build-client.log.gz`: type/API
  checks and ordinary TypeScript/shader/minified bundle production (the raw
  colored build log is preserved byte-for-byte in gzip form). Inventory
  declarations match; differing generation-time source hashes are not a freeze.
- `hooks.log`: mandatory full-worktree pre-commit, Ruff check and format check
  immediately before the local implementation commit.

The selected native library is asserted in the actual kernel: explicit owned
`target/release/libxyg_core.so`, ABI **399**, SHA256 recorded in `notebook.json`.
This is selected-path evidence, not a hash of an assumed conventional file.
It is the native library built in R1 from accepted sources. `crates/`, toolchain,
ABI/generated contracts, optimizer flags, caps and tolerances were not edited in
R2. No WASM artifact was rebuilt or newly qualified; the native notebook route
does not need one, and approved WASM size gates remain unchanged.

`environment.json` records the actual environment and installed notebook test
tooling. `hashes.json` identifies current producer sources, reused seams, native
library, generated JS and receipt artifacts. Capture HEAD names R1 (`864cafec`):
**R2 source hashes describe working-tree bytes, not bytes already committed at
that HEAD**. Final candidate HEAD and canonical base-to-head diff hash are in the
implementation handoff. Generated bundles remain ignored and uncommitted.

## Reproducing in this worktree

```
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:/home/ubuntu/.cargo/bin:$PATH
uv sync --group dev
cargo build --release
npm ci
node js/build.mjs
uv pip install jupyterlab==4.6.5 ipykernel==7.4.0
uv run pytest tests/test_graph_widget.py tests/test_widget.py tests/test_channel.py tests/test_view_state.py tests/test_graph_layout_controller.py tests/test_graph_notebook_report.py tests/test_release_surface_gate.py tests/test_graphforge.py -q
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome XYG_GRAPH_NOTEBOOK_REPORT=target/graph-notebook.json node scripts/graph_notebook_progressive_smoke.mjs
.venv/bin/python scripts/verify_graph_notebook_report.py target/graph-notebook.json
make check-ci
uv run ty check
uv run python scripts/check_release_inventory.py
uv run python scripts/check_public_api.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

`cargo build --release` is setup for a fresh checkout; R2 reused the owned R1
native artifact because native sources are unchanged. CI selects Playwright's
installed Chromium and uses the same notebook/receipt verifier commands. Tests
create their Jupyter data/config/runtime and screenshots under owned `target/`.

## Development failures retained without retroactive acceptance

`development-failures/` contains separate failed stages, not final-diff results:

- `cross-loop-notebook.log` and `cross-loop-worker.log`: ACK delivery woke the
  wrong asyncio loop late and tripped the existing native wall timeout. Owner-loop
  dispatch fixes it; no limit was raised. The committed cross-loop test checks
  callback thread ownership and native progress through another notebook loop.
- `moving-target-check.log`: the smoke initially demanded two pointer/keyboard
  callbacks at a coordinate sampled before the moving point advanced. The final
  proof separates trusted unfinished keyboard/navigation from stationary final
  pointer verification; it does not pause layout or relabel terminal interaction
  as initial response.
- `retired-hover-buffer.json`: the stronger journey exposed a null `_fcId` from
  a cached hover target referencing a replaced GPU trace. The final adapter
  releases/rebinds those handles, and the final verified report has no page error.

A hook-capture attempt wrote its output into a tracked file while pre-commit
was checking for file modifications; `self-observing-hooks.log.gz` preserves that
refusal. Capture was moved to ignored `target/`, then every mandatory hook and
Ruff check was rerun successfully before committing.

R1's failures/proofs and these failed stages remain historical, with their own
runtime source and stage qualifications. They are not substituted for final proof.

## Remaining acceptance

This coherent scheduling/presentation slice does not complete #1015/#35/#36/#108.
Still unproven/unimplemented: full kind/UUID/per-layer result-id/row GraphSession
callback projection; UUID-origin widget selection; exact UUID box/lasso sets;
trusted routed-edge/loop/parallel notebook pointer journeys (native identity paths
are tested here); persistent source selection across changing Aggregate row
spaces; annotated/selected export parity; Notebook 7 and VS Code qualification;
and the required 1k/10k/100k/1M rendered responsiveness/cadence/resource ladder.
The five-node fixture and current composition ceilings prove no ladder rung or
performance leadership. Static HTML remains a batch snapshot with no kernel
return channel. No release freeze, version reservation, publication or issue
closure is claimed. Parent independent final review remains required.
