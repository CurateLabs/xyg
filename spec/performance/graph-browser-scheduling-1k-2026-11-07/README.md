# Public browser scheduling: two 1k views, ordinary replies

Correctness-only bounded #35/#36 evidence. Live #35/#36/#1015 bodies and #35's
reopening comments were read on 2026-11-07. Their remaining acceptance is not
closed. Independent review and Integrate delivery belong to the parent.

Workspace `/home/ubuntu/.t3/worktrees/xyg/t3-41a17c25`, branch
`t3/browser-progressive-scheduling`, dispatch base
`74195403ccd18c760e3d20a18f024daab95d711a`. Accepted main
`80e841542462eaf5509ac90e1f17a80cae974164` was incorporated normally as
`235c03a43575c9484ecd5384ed9b1f629e8a9647`, preserving parent history.
The two conflicts were resolved with accepted main's updated scheduling status
and the official API inventory generator. Full hooks and both Ruff checks
passed before starting the merge and again before its merge commit (logs here).
No reset, rebase, force push, remote mutation, publication or child agent was used.

The existing public shipping attachment schedules Rust retained continuation.
No product defect preventing this bounded path was reproduced, so the controller,
wire, Rust policy and public API remain unchanged. This change adds focused
headless proof and executes it from the existing full source-checkout WASM
foundation CI command. It adds no job, timing threshold or release waiver.
Legacy and staged-package/focused-density paths keep their declared scope.

`final-isolation.json` is the strongest focused run; `summary.json` is derived
from it by `collect.py`. `final.json.gz` and the earlier before/after probes are
preserved (raw JSON compressed losslessly where suffixed `.gz`). `ci-final.json.gz` and `foundation-final.log.gz` record execution through
the normal CI command with final assertions. `legacy.json.gz` records 69 existing
journeys and `wire.log.gz` records 20 wire/GPU/package tests (all passed, no skips).
`inventory.log.gz` and `ownership.log.gz` passed. The first launch raced the
packaging producer and failed with missing-WASM HTTP 404; its raw log is retained.
After packaging completed all real attachment probes passed. No fake module,
held reply, manual ACK, sampled substitute graph or host layout was used.

Each of two independent Workers receives the complete 1,000-node/1,000-edge
ring document and an explicit 384 MiB arena. Both paint initial pixels and many
advancing intermediate pictures and reach Rust done at tick 458. Animation
opportunity observations record pixel count and hash, current progress and time;
initial/intermediate/final PNG captures are retained for both views. These are
canvas presentation observations, not OS compositor timing. The first view
accepts trusted Playwright mouse clicks and a trusted host button invokes the
existing `refreshRender(camera)` pan route while Rust is unfinished. This proves
host camera input, not a canvas drag/pan gesture. A retry may miss moving geometry
or arrive during a busy operation; actual selection replies and admitted native
click events are recorded. The untouched second view keeps an empty selection
and its original camera. Commands stay on their claimed instance. Both disposal
promises settle, attachment DOM disappears, snapshots become null, and the
post-disposal observation finds no new frames. The host's own pan button is
outside attachment cleanup and disappears when the harness removes its container.

Final focused observations (VM with capture/observer overhead): initial
publications 217/554 ms after worker creation began; first animation pixel samples
360/663 ms; 60/59 samples with distinct hashes, 58 distinct unfinished steps each.
Pick replies 135/130 ms and host pan 130 ms; cleanup 8/2 ms. Maximum sampled
heartbeat gaps 333/626 ms and paint intervals 461/431 ms. These measurements
establish no latency budget, user experience or competitor performance win.
Wire payload totals, timestamps and Chromium page heap metrics are in the raw
report. Page heap excludes Worker/WASM/GPU memory; explicit arena limits are
admission parameters, not measured peak resident memory. `workerStartupMs` spans
Worker ready resolution and may include main-thread scheduling delay. Startup measures new Workers on an already loaded page, after the small
initial fixture and refusal probes; the module cache may be warm. Browser-process
and cold-module first paint remain unproved.

The unchanged default 16 MiB refuses 1k with `GF_INTERACTION_BUDGET`. The bounded
10k attempt at the unchanged 384 MiB ceiling also refuses at initialization;
no 10k rendered rung or giant follow-up job is claimed. No admission cap, ABI,
tolerance or gate changed. Shipping module remains 1,927,032 raw bytes and
786,115 Node 22 gzip-level-6 bytes under unchanged 1882/768 KiB caps.
`environment.json` distinguishes system Python 3.14.4 and uv Python 3.12.15 and
binds the locally built WASM/client artifacts and source input hashes.
No native host library was used by these browser proofs. Native/WASM parity
is not reasserted from the prior epsilon-based receipt: policy remains bitwise
f64 and this slice adds no parity algorithm or tolerance.

The old 1k focus refusal is not reclassified as repaired: the single keyboard
probe here was not admitted while busy, and no 1k keyboard focus acceptance is
claimed. Full rendered 10k/100k/1M, notebook off-kernel/update/cancellation and
frontends (#1015), broader #36 and #35 lifecycle/host acceptance, independent
review, milestones 4–7 and release acceptance remain open. This task adds no
comparative performance claim and needs no fabricated competitor measurements.

Reproduce from the repository root:

```bash
export PATH=/home/ubuntu/.cargo/bin:/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
export CARGO_BUILD_JOBS=2
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
npm ci
uv sync --group dev
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
XYG_GRAPH_SCHEDULING_ONLY=1 XYG_GRAPH_SESSION_REPORT=/tmp/scheduling.json node scripts/graph_session_controller_wasm_smoke.mjs
XYG_GRAPH_SCHEDULING_REPORT=/tmp/ci-graph.json node scripts/wasm_foundation_smoke.mjs
XYG_GRAPH_SESSION_REPORT=/tmp/legacy.json node scripts/graph_session_controller_wasm_smoke.mjs
node --test js/test/graph-session-controller-wire.test.mjs js/test/graph-session-gpu.test.mjs js/test/package-wasm-contract.test.mjs js/test/package-wasm-manifest.test.mjs
uv run python scripts/check_release_inventory.py
uv run python scripts/verify_ownership.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Use new report paths to preserve these historical bytes. `collect.py` regenerates
this receipt's environment/summary from `final-isolation.json`; copy the receipt
before invoking it if retaining a separate environment. Committed source inputs
plus the canonical binary diff identify the candidate; final head/diff hash are
returned separately to avoid a self-referential receipt.
