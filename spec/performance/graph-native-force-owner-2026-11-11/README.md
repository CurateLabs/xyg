# Native force-owner isolation checkpoint

Parent: `947d8fc9e26d7db74e4da24511768790cecdfd53`. This is bounded native
ownership work, not whole-issue, shipping or milestones 4–7 acceptance.

The shared native force registry now holds only brief lookup/removal locks.
Each handle owns a mutex-protected optional ForceState. Ticks on one handle
serialize; another handle can progress while that owner is busy. Destruction
waits for the owner, takes and drops its state, and then removes discovery.
Concurrent destruction also drains retirement: one returns true, another false.
Earlier lookup claims cannot revive the empty slot. Algorithm, seed, f64 math,
chunk size, wall deadline, ABI, exports, package caps and public builders remain
unchanged. This adds no global CPU/source/process memory qualification.

## Evidence

`checks.json` binds commands, artifacts and raw/compressed evidence. The
successor binding preserves every previous source/history chain and receipt.

| Check | Result |
| --- | --- |
| Corrected Rust workspace | 2,051 passed, including all four owner regressions |
| Explicit allocation ledger | Passed; this remains the WireSession fixture, not total process or concurrent force-registry memory |
| Strict workspace Clippy | Passed |
| Normal Node suite | 1,156 passed, two existing skips |
| Python controller/session/widget/region tests | 102 passed |
| Native ABI | 673 checks; both official generators current |
| Matching browser foundation | Passed, including seven Worker freezes, full export parity and aggregate proof |
| Actual JupyterLab4.6.5 1k + 1k | Passed: trusted UUID activation, accepted mask, independent peer and captured-owner/thread cleanup |
| Actual 100k + 1k notebook | **Failed**: peer wall deadline at step137; primary sampled alive at step9 while compiling; exact selection and cleanup passed |

The first draft removed discovery before draining its owner. A new concurrent
close regression failed that draft, because a second close could
return false before retirement. The corrected source retires before removal and
passes all four tests. Draft source/native bytes and passing-but-incomplete
checks remain preserved as draft evidence. A private mutation restoring the
old global tick lock fails the isolated owner-isolation test. A combined
mutation run also failed a teardown-control assertion; it is preserved and is
not credited as the originally expected three-pass/one-fail matrix. No product
test assertion was weakened.

The current module is **1,884,503 raw /786,337 Node22 gzip6 bytes**, under fixed
**1,927,168 /786,432** caps with only **95 gzip bytes** spare. Native405 has
551 declarations; WASM38 retains 68 functions and zero imports. Matching client
sources/artifacts remain parent-exact. Earlier measurements are historical.

One fresh full foundation passes on this rebuilt module. The earlier density
startup/aggregate first-paint context losses remain failed and unexplained;
this native registry correction establishes no GPU-loss reliability repair.
The unchanged 30-second notebook deadline remains a real acceptance gap.

Two private paint trials were rejected before this correction: wholly empty
semantic underpaint was ineligible for the actual trace; proving circle-only
endpoint spans preserved all pixels but CodSpeed reported **No Change**
(37.98 s versus 38.05 s, two rounds each). No prototype entered product source.
The passing 1k ownership control ran once through CodSpeed at 16.47 s, including
bootstrap/layout/teardown. None of these numbers establishes a speed win.

## Reproduce

Use explicit source/native selection, Node22, the recorded Chromium and disk
TMPDIR. Never synchronize a borrowed environment.

```bash
cargo test -p xyg-engine --lib native_force_owner -- --nocapture
cargo test --workspace
cargo test -p xyg-engine --test graph_session_memory -- --nocapture
cargo clippy --workspace --all-targets -- -D warnings
cargo build --release
npm run build:wasm
npm test --prefix packages/xy-node
uv run --no-sync pytest -q tests/test_graph_layout_controller.py tests/test_graph_session_python_transport.py tests/test_graph_widget.py tests/test_graph_widget_regions.py
python3 scripts/abi_smoke.py
node scripts/wasm_foundation_smoke.mjs
XYG_NOTEBOOK_SCALE=1000 codspeed exec -m walltime --warmup-time 0s --max-rounds 1 --name native-notebook-scale-1k-contract -- node benchmarks/bench_graph_native_notebook.mjs
```

The notebook harness derives existing force defaults and verifies the loaded native/client
hashes. The equivalent 100k acceptance remains failed, not an expected green
gate. Larger/all-host/interaction/accessibility/export/competitor and global
budget qualification remain open. Final provenance controls, mandatory hooks,
independent final-diff review, current-main/hosted CI and merge queue remain
required before delivery. The parent's 1,039 CI-contract pass is inherited
parent evidence, not a fresh run for this continuation.
