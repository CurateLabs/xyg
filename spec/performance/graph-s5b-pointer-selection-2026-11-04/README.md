# Bounded S5b primary-click selection — 2026-11-04

Local candidate on `t3/graph-pointer-selection`, isolated worktree
`/home/ubuntu/.t3/worktrees/xyg/t3-5009d7d3`, based on approved parent
`11e2aa4defd76c6d5f6aeaa40ecf4af806c33d38`. Parent independent final review is
required before integration or publication. No PR, push, queue, issue closure,
deployment, credential or hardware operation accompanies this candidate.
All historical receipts remain unchanged.

## Scope and before/after evidence

The production diff touches only `63_graph_controller.ts` and
`63_graph_session_wire.ts`. Existing Rust SelectAt operation1 picks the accepted
publication and atomically owns Replace/Add/Toggle, identity and membership.
The encoder adds internal operation1 and exactly two finite raw f64 coordinates;
all previous framing guards remain. No public method, alias, picked-target
interface, Rust signature, wire section/version, Worker or GPU change is added.

`before.json` records an actual Playwright mouse click on a Rust-published node
at client(478,149): command count remains2 and selection remains0. The old
production controller/encoder were still unchanged; `artifact-reuse.json`
records all301 approved input hashes verified before edits. Baseline build,
package and browser command logs are retained. All17 original journeys pass
alongside that negative control (18 cases total). This does not reconstruct any
missing historical log or assert an independently captured baseline ESM hash.

`controller-accepted.json` records29 packaged strict-CSP journeys, zero skips:
all17 originals plus12 bounded pointer journeys. Mouse input uses Playwright
`mouse.click`, with trusted delivered events recorded. Test-only readers obtain
coordinates from Rust CPU paint sections and ownership/member tables; they do
not ship in the client or supply a TypeScript hit-test implementation. Browser
client-coordinate rounding is observed directly; raw f64 requests must match
the actually delivered content coordinates, including fractional scaled values.
The narrow route fixture uses a signed-capable camera with Y scale100 so Rust's
parallel offsets and self-loop are visible; an ordinary CSS display scale4
makes its stroke-band mouse deliveries inspectable. No golden, tolerance or
existing mask/threshold was weakened.

The new journeys cover exact node UUID Replace/Shift Add/Ctrl and Meta Toggle,
including Toggle precedence with Shift; persisted parallel lanes and self-loop;
filled derived arrowhead with exact result ID, BigInt path/order and original
result row; compound frame band versus empty interior; and clipped shaft gap
missing the edge while the covering node retains ownership. Blank Replace
empties selection but preserves Rust highlight planes; blank Add/Toggle are
noops. A test-only operation12 transport edit seeds a real External highlight;
that operation is not added to the controller vocabulary or captured replay.

A held primary SelectAt preserves the preceding picture/snapshot until accepted.
Busy Escape and another real click produce no commands or replay. Acceptance
repaints at the same revision with byte-identical CPU/GPU geometry/membership and
unchanged nonempty Rust logical focus. Signed camera, DPR2, CSS axis-aligned
scale, border-box sizing, border/padding, offsets and scrolling map correctly;
a real padding click submits no command. Unsupported transforms, Alt and
secondary buttons pass through. Stale, malformed GPU/Clear fact, wrong-instance
refusal and typed budget refusal retain last good state; only explicit successful
refresh re-enables stale input. Disposal during a held click immediately removes
the listener and suppresses late events/painting; terminal input, two Workers,
observer exceptions, keyboard/dialog Escape, samplers and context restoration
remain covered. Each accepted mouse action is observed to send only
`graph.session.interact`/op1, with raw `coordinates.f64`; legacy CPU pick/CSR/
selection-mask traps remain installed.

`pointer-accepted.png` is the actual selected-node canvas with CSS border/padding,
scale and signed camera. Five-source aggregate selection is compared with exact
Rust member UUIDs. The51-source aggregate exercises the typed selection-cap
refusal seam; neither fixture is a scale/performance benchmark.

## Honest refusal/scale limits

The10001-source pressure fixture returns actual `GF_INTERACTION_BUDGET` during
initialization at the unchanged default16MiB arena. It is not a successful large
render/pick and no arena increase was made to bypass it. SelectionTooLarge and
one budget error path are tested using explicitly labelled **pre-execution**
Worker reply seams, before Rust can mutate state. This proves controller refusal
handling, not an actual10001-member browser SelectAt cap refusal. Existing
native/WASM shipping tests retain actual Rust transaction/cap proofs. The
initial pressure failure and corrected, explicitly bounded expectations remain
in the raw development logs.

Exact hover is deferred: private `hover_at` source lists, selection order,
changed refs, flags and lowest-edge keyboard focus cannot supply a query-scoped
aggregate-render-edge PickTarget/membership receipt. Pan/zoom gestures,
brush/lasso, disclosure, move/pin/relayout, temporal/link/update/force, public
host attachment and legacy removal remain outstanding. Broader S5b/S6/S7,
#36/M4/#108 and release acceptance remain open. API inventory regeneration still
reports685 explicit gaps and is not an accepted freeze.

The capability gap maps to the repository's
[graph interaction comparison](../../design/graph-fork-requirements.md#3-competitive-matrix-core-viz-only)
and [existing multi-library evidence](../../benchmarks/results.md): exact
selection on the opt-in retained browser attachment was missing; this slice
supplies that behavior. The existing Sigma/vis/D3/Ogma/Plotly requirements and
Matplotlib/Seaborn/Plotly/Bokeh/Altair/Datashader/HoloViews/hvPlot comparison
scopes remain broader. None of those competitors was rerun here. There is no
competitor timing, massive-data, startup/memory/payload/export or multi-chart
performance win, and no S7 closure. The generated capability matrix links this
bounded exception without upgrading unrelated capabilities.

## Binary qualification and shipping

Before runtime proof, all301 approved R2 build inputs matched; approved actual
native and raw WASM binaries were copied from the parent worktree with their
actual paths/sizes/hashes retained in `artifact-reuse.json`. No fresh Rust build
is claimed. `artifacts.json` rechecks all301 final inputs: only the two intended
TypeScript files differ, with299 unchanged, including every Rust/build input.
Native SHA256 remains
`3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6`;
raw WASM remains
`3f53a4747010f6cfc9e7f308c73d35a81d68cd2f6ffecaafb1860aa3cf9053b0`.

The normal client builder freshly typechecks/lints/builds ESM/IIFE and both
Workers, then the unmodified normal shipping producer refreshes paired assets.
All15 approved artifact paths are hashed. Only the two ESM/IIFE files and their
Python copies change. The optimized production module remains **1922723 raw /
783181 Node22 gzip6 bytes**, SHA256
`6ebbdb7f7e6859ad9a08bd2c0237c62aaa6147df8c683b080959b42e7d2fb273`.
`shipping-module.wasm.gz` retains those actual bytes. Existing1878/765KiB gates
(1923072/783360) leave349/179bytes headroom. ABI399/WASM35/GPUv1/Scene34/
painter17, XYGI/XYGR, compiler/profile/optimizer/dependencies/exports/guards and
arena are unchanged. No diagnostic module substitutes for shipping acceptance.

## Captured bytes and validation

`captured-requests.json.gz` retains19 actual browser request/reply pairs:
OPEN, Render and17 SelectAts. `captured-accepted-requests.json` retains the final
uncompressed capture. The added test in the existing Node wire suite uses its
native/WASM helpers and compares **complete XYGR bytes**, including provenance,
focus and GPU sections, against the browser replies and each other. OPEN creates
the native session and its WASM acknowledgment matches the captured bytes;
Render/SelectAt outputs match native, WASM and captured replies in full.
Byte replay is separate from real mouse-delivery proof.

| Final command record | Actual result |
| --- | --- |
| `client-final`, `package-final`, `paired-final` | Normal production build, unchanged package gates, paired assets pass |
| `artifacts-final` |301 build inputs accounted for; reused binaries and unchanged optimized bytes/gates pass |
| `wire-final` |12 wire/semantic/GPU tests pass, zero skips |
| `shipping-tests-final` |All original13 shipping tests plus captured replay pass:14, zero skips |
| `controller-accepted` |29 strict-CSP packaged journeys pass, zero skips; all17 originals retained |
| `foundation-final` |Full unfiltered strict-CSP foundation passes; subset variable explicitly unset |
| `contracts-final` |88 shared-host/ownership/API/package/ABI/capability tests pass, zero skips |
| `api-inventory-final`, `capability-check` |Preparation inventory and generated capability checks pass;685 gaps remain |
| `hooks-final`, `ruff-check-final`, `ruff-format-final` |Full-worktree mandatory precommit checks pass |

Each command JSON records actual argv, cwd, selected environment, timestamps,
exit and combined raw log hash. The initial runner matched R2's combined
stdout/stderr capture. Later commands additionally retain separate `.stdout` /
`.stderr` streams and hashes; earlier separate streams are not reconstructed.
The baseline-only environment flag was not in the initial runner's allowlist;
its actual negative-control case is retained in `before.json`.
`environment-final.log` records actual Node22/Python/toolchain/package versions;
the browser report records Chromium156.0.8078.4. `proof-inputs.json` binds final
source/harness/receipt hashes; whole diff hashes are emitted in the local commit
handoff to avoid a self-reference.

Development logs remain append-only. Early route fixtures failed because the
unscaled Rust lane/loop geometry was smaller than the delivered mouse pixel;
fixtures were corrected using published geometry/camera and browser coordinates.
A highlight test initially compared an old selected bit as well; it now begins
with an explicitly empty selection and requires complete flags equality after
blank Replace. A repaint test initially reselected the already selected node;
it now clears first, requires actual pixel change and unchanged geometry/focus.
The initial Node shipping invocation omitted required `XYG_NATIVE_LIB`; the
corrected invocation uses the verified local core. The first contracts invocation
omitted Chromium (81pass/7skip); explicit cached Chromium yields88pass/0skip.
The first environment probe omitted Cargo's PATH and failed; its corrected probe
passes. The first artifact audit incorrectly demanded unchanged TypeScript;
the final audit explicitly accounts for only the intended two changes.

Reproduce from this worktree with the recorded Node22 directory on PATH and
`XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`:

```bash
node js/build.mjs
node js/package-wasm.mjs
python3 scripts/verify_wasm_assets.py
python3 spec/performance/graph-s5b-pointer-selection-2026-11-04/verify_artifacts.py
node --test js/test/graph-session-controller-wire.test.mjs js/test/graph-session-gpu.test.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/graph-session-wire.test.mjs js/test/package-wasm-contract.test.mjs js/test/package-wasm-manifest.test.mjs
node scripts/graph_session_controller_wasm_smoke.mjs
env -u XYG_WASM_FOUNDATION_ONLY node scripts/wasm_foundation_smoke.mjs
uv run pytest tests/test_shared_glhost.py tests/test_verify_ownership.py tests/test_release_inventory.py tests/test_verify_wasm_assets.py tests/test_wasm_inline_artifact_contract.py tests/test_graph_session_abi.py tests/test_capability_registry.py -q
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Use new output paths/labels when capturing a repeat; do not overwrite this receipt.
No expensive full Rust rebuild or1970-test repeat was performed: approved Rust
source/binary identity is proved instead, alongside actual required runtime gates.
