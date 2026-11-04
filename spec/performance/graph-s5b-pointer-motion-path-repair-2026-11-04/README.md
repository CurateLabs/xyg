# S5b pointer motion-path eligibility repair — 2026-11-04

This is a narrow local repair of the independent `s5a_final_review`
REQUEST_CHANGES on candidate `27c9dc3bb9e8f4c7cda190249b43a397b3a9bfcc`.
The review identified one P1: CSS motion paths can rotate the canvas while
computed `transform` and individual `rotate` remain `none`, so the preceding
rectangle mapping admits incorrect SelectAt coordinates. This receipt adds the
actual before/after proof without altering that candidate, its history, original
receipt or any recorded failure. A new parent independent final review is
required before integration, PR or push. No remote action accompanies this work.

Worktree: `/home/ubuntu/.t3/worktrees/xyg/t3-5009d7d3`;
branch: `t3/graph-pointer-selection`; human author David Spencer.

## Repair boundary

The only production change is three lines in `63_graph_controller.ts`:
inside the existing canvas/ancestor/shadow-host walk, reject computed
`offsetPath !== "none"` before coordinate mapping. Motion distance, rotation and
anchor act separately from `DOMMatrix(transform)`. Rejecting every active path
covers their combinations without implementing motion geometry or hit policy,
including an axis-aligned path. Default motion properties with no active path
remain eligible; all29 preceding journeys, including ordinary CSS scale,
border/padding/offset, signed camera and DPR2, still pass.

There are no Rust, wire/encoder, Worker, GPU, API, dependency, arena, package-gate,
profile/compiler/optimizer/export or guard changes. Authoritative design/API
contracts and the generated capability matrix explicitly mark active motion
paths on canvas/ancestors unsupported. The inventory refresh changes only
source provenance/hashes; declarations, classifications and685 gaps are unchanged.

## Actual before failure and after proof

`before-identity.json` verifies all301 parent build inputs and all15 actual
artifact hashes before the reproduction. The runtime used the actual shipped27
ESM/Worker/WASM bytes. All9205 historical performance files (including the
original pointer receipt and earlier9033 files) were compared with their committed
bytes and hashed. `preservation.json` records the final recheck, all unchanged.
No historical log is reconstructed or rewritten.

`before.json` records both real pre-fix mis-picks. The added regressions use the
existing Rust geometry fixture: source node1 has published CSS center[170,150].
A test-only transparent DOM probe follows the same CSS motion as the canvas,
or inherits the ancestor motion, and the browser measures its transformed point.
It provides a visual-coordinate oracle only; it is not shipped hit policy.
`elementFromPoint` must be CANVAS, and a real Playwright `mouse.click` must deliver
a trusted event whose target is that exact canvas. Thus a click off the canvas
cannot masquerade as successful rejection.

Both fixtures use:

```css
offset-path: path("M 450 150 L 700 150");
offset-distance: 0px;
offset-rotate: 30deg;
offset-anchor: 0px 0px;
```

The test records computed `transform:none`, `rotate:none`, the active path and
all motion properties. The browser-measured point is
[530.2243041992188,1078.90380859375]; the trusted click delivers client(530,1078).
The old controller incorrectly submits operation1 at approximately
[207.88056441534303,114.68224579152249], empties an accepted nonempty selection,
changes the canvas pixel digest and consumes the event default.
Canvas commands increase124→125; ancestor commands129→130 in the retained runs.

`regression-before-guard` runs the actual rejection assertion against those old
shipping bytes and **fails**, exit1, at125≠124. Its raw stdout/stderr and printed
trusted-event/snapshot/pixel result remain intact. The initial observational
baseline uses an explicit `XYG_GRAPH_MOTION_BASELINE=1` mode to assert the known
bad behavior; its31 expected observations are not passing repair acceptance.

`before-native-default.json` additionally wraps the surface in a real native
link. The old controller cancels both clicks: `defaultPrevented:true`, and the
fragment default action does not occur. This strengthens the baseline without
changing the existing negative proof. `baseline-inputs.json` binds the first
baseline harness; `proof-inputs.json` binds the final harness with the native
link assertion. All raw failures remain append-only.

`controller.json` records **31 passing strict-CSP shipping journeys, zero skips**:
all29 preceding journeys plus separate canvas and ancestor motion-path cases.
Both repeat the same visible-point/trusted-CANVAS requirements. After the guard:

- Command count, all Worker-product counts and selection-event count stay unchanged.
- The complete accepted Rust snapshot and full-canvas SHA256 pixel digest stay identical.
- Rust CPU/GPU geometry and membership bytes stay identical.
- `defaultPrevented` remains false and the actual native link default updates
  the fragment to `#motion-path-canvas` or `#motion-path-ancestor`.

The guard therefore preserves both the last accepted graph publication and the
browser's native default. No synthetic-only event, relaxed mask/tolerance,
off-canvas click, hidden waiver or motion-matrix approximation supplies the proof.

## Shipping and replay qualification

`client-build` freshly typechecks/lints and builds the normal ESM/IIFE and both
Workers; `shipping-package` uses the unchanged normal producer; `paired-assets`
verifies paired copies/manifests/inline assets. `artifacts.json` accounts for
all301 final production inputs:300 are byte-identical to27, only the controller
differs. Of all15 artifact paths, only ESM/IIFE and their Python copies change.

Native core, raw WASM and optimized shipping WASM are actual reused qualified
bytes, not claimed fresh Rust compilations. Their SHA256 values remain:

- Core: `3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6`
- Raw WASM: `3f53a4747010f6cfc9e7f308c73d35a81d68cd2f6ffecaafb1860aa3cf9053b0`
- Optimized WASM: `6ebbdb7f7e6859ad9a08bd2c0237c62aaa6147df8c683b080959b42e7d2fb273`

Optimized size remains **1922723 raw / 783181 Node22 gzip6 bytes**. Existing
1878/765KiB gates (1923072/783360) retain349/179bytes headroom.
`shipping-module.wasm.gz` retains the actual optimized bytes. ABI399/WASM35/
GPUv1/Scene34/painter17 and XYGI/XYGR remain unchanged. No Rust rebuild or full
1970-test repeat is claimed; actual source/artifact identity supplies that proof.

The new run captures19 actual OPEN/Render/SelectAt requests and replies, including
17 SelectAt clicks. `capture-parity` proves that capture is byte-identical to the
immutable parent capture. `wire-shipping-final` explicitly replays the **new**
capture through the existing native/WASM test helpers, comparing complete XYGR
bytes with the browser replies. This retains full selection/provenance/focus/GPU
parity and the existing legacy-path traps.

| Command record | Actual result |
| --- | --- |
| `before`, `before-native-default` | Actual old-controller failures observed on canvas and ancestor;31 expected baseline observations |
| `regression-before-guard` | Required rejection assertion fails, exit1,125≠124 |
| `client-build`, `shipping-package`, `paired-assets`, `artifacts` | Normal shipping and unchanged binary/gate qualification pass |
| `controller` |31 shipping strict-CSP journeys pass, zero skips; original29 retained |
| `wire-shipping-final` |26 pass, zero skips:12 wire/GPU and14 shipping tests, retaining original13 shipping tests |
| `capture-parity` |New19-request/17-SelectAt capture equals parent; full native/WASM replay passes |
| `foundation` |Full unfiltered strict-CSP foundation passes; subset variable explicitly unset |
| `contracts` |88 focused host/ownership/API/package/ABI/capability tests pass, zero skips |
| `inventory`, `capability-matrix` |Current preparation inventory and generated matrix pass;685 gaps retained |
| `hooks`, `ruff-check`, `ruff-format` |Mandatory full-worktree precommit and Ruff checks pass |

Each command record retains argv, cwd, environment, timestamps, exit status and
SHA256 hashes for combined and separate raw stdout/stderr streams. `environment`
and browser JSON retain actual toolchain/package/browser versions. The earlier
`wire-shipping` check also passed26 tests while packaging was completing; the
final record reruns it after shipping/paired-asset qualification with the fresh
capture. Whole/source diff hashes are emitted with the committed handoff to
avoid a self-reference. `proof-inputs.json` binds final source/harness and receipt
hashes and both the reviewed-parent and original-foundation diff bases.

## Reproduction and remaining limits

Use the recorded Node22 directory on PATH:
`/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin`,
and set `XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
Run the exact recorded argv, for example:

```bash
node js/build.mjs
node js/package-wasm.mjs
python3 scripts/verify_wasm_assets.py
python3 spec/performance/graph-s5b-pointer-motion-path-repair-2026-11-04/verify_artifacts.py
node scripts/graph_session_controller_wasm_smoke.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" XYG_GRAPH_POINTER_CAPTURE="$PWD/spec/performance/graph-s5b-pointer-motion-path-repair-2026-11-04/captured-requests.json" node --test js/test/graph-session-controller-wire.test.mjs js/test/graph-session-gpu.test.mjs packages/xy-node/test/graph-session-wire.test.mjs js/test/package-wasm-contract.test.mjs js/test/package-wasm-manifest.test.mjs
env -u XYG_WASM_FOUNDATION_ONLY node scripts/wasm_foundation_smoke.mjs
uv run pytest tests/test_shared_glhost.py tests/test_verify_ownership.py tests/test_release_inventory.py tests/test_verify_wasm_assets.py tests/test_wasm_inline_artifact_contract.py tests/test_graph_session_abi.py tests/test_capability_registry.py -q
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

To reproduce the before failure separately, build the committed27 controller
with this test harness in an isolated checkout and run the recorded baseline or
rejection argv. Baseline mode must not be mistaken for corrected acceptance.
Use fresh receipt output paths/labels when recording repeats; preserve these files.

Broader M4/#36/#108, S5b/S6/S7, hover/picked-target projection, gestures,
public-host and release/competitor/scale acceptance remain open. The original
SelectionTooLarge pre-execution seam and10001-source default16MiB initialization
Budget limit are unchanged and remain explicit in the passing journeys. This
repair adds no large-selection, motion-path support or performance claim.
