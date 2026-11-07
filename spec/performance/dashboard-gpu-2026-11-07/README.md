# Shared dashboard GPU storage candidate

Base: `084b3c1b7c393e135476aab9610bf8334767b2ac`. This is additive GPU work for
#111, not issue or milestone closure. No external review or delivery is claimed.

The hosted 32-chart small-scatter journey uses actual packaged WASM SHA256
`7bce0525a9688ae051ef0f13d9f55da1a1e9fef08b2449993673e8811aada3a1`.
Its independent driver-facing oracle records buffer storage via `BUFFER_SIZE`
and texture storage requests after the admission boundary. Every checkpoint
must match the production ledger exactly. It proves whole-chart hidden yield,
active rebuild, synchronous over-capacity refusal, per-chart zero-cap admission,
32 appends, context restoration, resize, hide/show, rapid replacement and zero
buffer/texture allocations after teardown. ARIA attributes and isolated focus
are checked. Captures show pressure and restored frames. These are logical
allocation bytes, not physical VRAM. The original pre-opt-in allocation is
reported separately; subsequent growth is bounded by reservations before GL.

The existing nine shared-host tests retain fixed-capacity exact RGBA and the
existing DPR growth RGB tolerance/alpha-exact assertions. They pass. The WASM
foundation smoke additionally exercises semantic stable IDs through whole-chart
resource eviction/rebuild. Scene-ID hydration now also runs on context rebuild.
The real native render and append smokes pass. The native Rust workspace tests
pass with disk-backed TMPDIR; the first run's 32 quota failures are preserved in
`rust-tmpquota-failed.log`. Initial Node tests encountered quota then a missing
explicit native library path; final commands use both TMPDIR and XYG_NATIVE_LIB.
Initial hook execution reformatted one Python source test; final hooks and Ruff
must pass before commit. Earlier CSP/worker-ready harness setup errors and the
scene-ID/cancellation test failures were corrected before the final runs.

Reproduce from the repository root (Node 22.23.4; Rust 1.96.0; Python 3.12):

```sh
uv sync --group dev
cargo build --release
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
# Provision the unchanged accepted-main WASM with the standard package build.
# verify_wasm_assets.py must succeed; no Rust/WASM source changes in this candidate.
export TMPDIR=/home/ubuntu/xgpu-tmp
mkdir -p "$TMPDIR"
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
node scripts/dashboard_gpu_smoke.mjs
node scripts/wasm_foundation_smoke.mjs
uv run pytest tests/test_shared_glhost.py -q
cargo test --workspace
uv run python scripts/render_smoke_nonumpy.py "$XYG_CHROMIUM"
uv run python scripts/append_stream_smoke.py "$XYG_CHROMIUM"
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/html.test.mjs packages/xy-node/test/scene.test.mjs packages/xy-node/test/stream.test.mjs packages/xy-node/test/no_browser_globals.test.mjs
```

The dashboard runner writes report, captures, hashes and console logs to
`target/task-tmp/gpu-admission` (override `XYG_GPU_REPORT_DIR` for a new receipt).
Raw build and Rust success logs are gzip-compressed without changing their bytes.
`checks.json` records the remaining inventory, ABI, asset, ownership and mandatory
hook commands/exits. `source-artifact-hashes.json` binds tested source and builds.
The unchanged WASM stays within 1882 KiB raw / 768 KiB gzip; no cap or flags changed.

Remaining #111/full M4–M7 acceptance: native CPU/source/WASM hierarchical budgets,
default resource-budget policy, multi-host release evidence and WebKit; real
mixed-scale/LOD/tile/graph pressure and selection/keyboard interaction journeys,
latency/high-water process memory gates, and independent parent review. This
32-small-scatter journey is not a representative mixed-family/large-data claim.
Graph storage is instrumented, but a new graph camera update refused for storage
propagates an explicit error to its controller and retains the last accepted
picture/state; callers must retry that update after admission. Desired chart
capacity remains a conservative high-water reservation until removal, so a
large former working set can stay ineligible after shrinking. Physical driver
memory, alignment/retirement, Canvas2D memory and CPU caches are outside this
logical GPU cap. No competitor or scale win is claimed. The issue's historical
Reflex acceptance wording conflicts with documented consumers; no Reflex
namespace, adapter or extra has been added. Old receipts remain untouched.
