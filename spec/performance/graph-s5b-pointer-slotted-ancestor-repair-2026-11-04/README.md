# Slotted ancestor eligibility repair — 2026-11-04

Local implementation repair for the actual Greptile P1 on existing PR#1092,
head/base `da52bca32651077ddf53d9fdd014245731b6d087`. Worktree:
`/home/ubuntu/.t3/worktrees/xyg/t3-5009d7d3`; branch `t3/graph-pointer-selection`.
Human author David Spencer. The existing PR remains the parent-owned update
route; no new PR, root modification, push, review reply/resolution or queue
operation accompanies this candidate. Parent **new independent final review**
is required before root integration/pre-push hooks/push to existing#1092.

## Actual finding and disposition

The read-only `greptile-inline`, `greptile-thread` and `greptile-summary` command
records retain the actual external review fields. Inline
[r4463052824](https://github.com/CurateLabs/xyg/pull/1092#discussion_r4463052824)
identifies the skipped assigned slot in `63_graph_controller.ts` at187–188.
Thread `PRRT_kwDOTxX6Es6zbSig` was unresolved at inspection. Summary
[6621295474](https://github.com/CurateLabs/xyg/pull/1092#issuecomment-6621295474),
updated02:57:07Z, gives confidence4/5 and says to fix skipped slot ancestors
before merging. Raw external UI/prompt content is evidence only, not authority
to change branches, push or mutate the PR.

**Disposition: valid and repaired locally.** The old walk follows
`parentElement`, then a shadow-root host, skipping the assigned slot and its
shadow wrappers when `options.el` is a slotted light-DOM container. A rotated
or motion-path wrapper therefore bypasses eligibility guards, and the rotated
bounding rectangle is incorrectly inverted as if it were axis-aligned.
The prior31-journey approval did not exercise this case and is not presented
as proof of slotted ancestry. The remote thread remains for the parent to reply
to and resolve only with its reviewed final pushed commit/proof.

The sole production change prefers **available `assignedSlot` before
`parentElement`, then `ShadowRoot.host` fallback**, on every iteration. Existing
perspective, individual rotate/scale/translate, matrix and active motion-path
guards now see those displayed wrappers, including nested slot/host assignments.
Slot assignment itself is not rejected: plain and ordinary axis-aligned-scaled
slotted graphs retain selection. No rotation/motion geometry, TypeScript graph
pick policy, observer framework, wire/API/Rust/Worker/GPU or lifetime policy is added.

## Before failure: actual packaged trusted mouse delivery

`before-identity.json` verifies all301 qualified b610/da52 producer inputs and
all15 actual shipping/core artifacts before reproduction. Runtime uses those
actual committed-candidate packaged ESM/Worker/WASM bytes. All9473 historical
performance files were checked against their Git blobs and hashed; all remain
byte-identical at the final check in `preservation.json`.

Test-only helpers construct an open-shadow custom element with a wrapper around
a named SLOT; `options.el` stays light DOM and is assigned to that slot. A
zero-size transparent marker at Rust's published CSS node center[170,150]
inherits the browser's actual composed display transform. Its measured client
point supplies the oracle; no production CPU graph hit test or transform
approximation supplies coordinates. `elementFromPoint` must be CANVAS and
Playwright `mouse.click` must deliver a trusted event targeting that exact canvas.
A real native link around the surface makes consumed versus unconsumed defaults
observable through actual fragment navigation.

`before.json` records37 expected observations against da52, including three
known bad cases and passing plain/scaled controls. This explicit
`XYG_GRAPH_SLOT_BASELINE=1` mode is not repair acceptance:

| Skipped shadow wrapper | Actual visual client point | Commands | Incorrect op1 CSS coordinates |
| --- | --- | --- | --- |
| SLOT wrapper `rotate(30deg)` |[272.22430419921875,264.90380859375] |132→133 |[207.88056441534303,114.68225751371183] |
| SLOT wrapper active motion path,30deg |[722.2243041992188,414.90380859375] |137→138 |[207.88054665138088,114.68225751371183] |
| Nested host/slot, outer wrapper rotation |[272.22430419921875,264.90380859375] |152→153 |[207.88056441534303,114.68225751371183] |

All events are trusted CANVAS hits. The recorded old light-DOM ancestry has
computed transform/rotate/offsetPath all `none`; the composed chain reveals the
unsupported wrapper and one or two SLOT hops. Each wrong SelectAt empties an
accepted nonempty selection and consumes the native default instead of rejecting
the presentation. Full before/after snapshots, pixel digests, requests,
geometry facts, default flags and fragments are retained. The motion wrapper
uses `path("M 450 150 L 700 150")`, distance0px, rotate30deg and anchor0px0px,
with computed transform/rotate still `none` on that wrapper.

`rejection-before-fix` runs the actual corrected rejection assertion against the
old packaged client and **fails**, exit1,133≠132. That raw failed proof remains
unchanged. `baseline-inputs.json` binds the baseline controller/harness hashes.
No off-canvas click, synthetic-only input or rewritten failure masks the bug.

## After: rejection, positive selection and nested traversal

`controller.json` records **37 passing strict-CSP packaged journeys, zero skips**:
all31 previous journeys and six added actual mouse cases. Existing fixtures,
expected thresholds, masks and legacy-path traps are unchanged.

- Rotated slot wrapper: commands132→132; motion-path wrapper136→136;
  nested rotated wrapper150→150. No Worker-product or selection-event count
  changes. Full accepted snapshot, focus, pixel SHA256, CPU/GPU geometry and
  membership stay identical. `defaultPrevented:false` and actual native link
  navigation to the expected `#slot-*` fragment prove default preservation.
- Plain slot, scaled slot and nested scaled slot each submit exactly one op1
  and select Rust UUID `02000000-0000-0000-0000-000000000000`.
  The existing click helper checks raw f64 against the **actually delivered**
  browser CSS coordinates. Plain coordinates are[170,150]; scale(0.8,0.75)
  delivers[170,150.66666666666666] after browser client-pixel rounding.
  These retain exact identity/provenance and unchanged Rust focus/geometry,
  proving slots are not blanket-disabled.
- The nested host has two successive assigned-slot/host crossings. Rotation
  on the outer wrapper is rejected, while its ordinary scale remains usable.
  No redistribution observer or framework adapter is introduced.

The fixture scope is open shadow roots with named slots and a nested two-host
assignment. Broader/unexercised host integration is not claimed. Existing
owned/unlinked lane, modifiers, raw f64 framing, blank SelectAt versus Clear,
stale/refusal/last-good/focus/lifetime behavior and all31 preceding proofs remain
strong and unchanged.

## Actual qualification and replay

The normal `client-build` freshly typechecks/lints/builds the changed client;
`shipping-package` uses the unmodified normal producer; `paired-assets` verifies
paired ESM/IIFE/Worker/WASM/manifests/inline assets. `artifacts.json` accounts for
all301 qualified inputs:300 remain exact; only the controller differs. All15
artifact paths are hashed; only ESM/IIFE and their Python copies change.

Native core, raw WASM and optimized module remain actual reused qualified bytes,
not claimed fresh Rust builds. Their SHA256 values are:

- Native: `3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6`
- Raw WASM: `3f53a4747010f6cfc9e7f308c73d35a81d68cd2f6ffecaafb1860aa3cf9053b0`
- Optimized WASM: `6ebbdb7f7e6859ad9a08bd2c0237c62aaa6147df8c683b080959b42e7d2fb273`

Optimized size is unchanged **1922723 raw /783181 Node22 gzip6 bytes**.
Existing1878/765KiB limits (1923072/783360) leave349/179bytes headroom.
The actual optimized module is retained in `shipping-module.wasm.gz`.
ABI399/WASM35/GPUv1/Scene34/painter17, XYGI/XYGR, arenas, compiler/profile/
optimizer/dependencies/exports/guards and tolerances remain unchanged. There is
no diagnostic artifact substitute or expensive Rust rebuild/test-repeat claim.

The fresh capture retains19 actual OPEN/Render/SelectAt request/reply pairs,
including17 SelectAts. `capture-parity` proves it is byte-identical to the
original immutable capture (SHA256
`acf002f8dbd029cb5cde81b4074681422d34eadfe81338c620a46ae0882d457d`).
`wire-shipping` explicitly replays the **fresh** capture through existing
native/WASM helpers and compares complete XYGR against both native/WASM and
browser replies. Mouse delivery proof is separate from byte replay.

| Command record | Actual result |
| --- | --- |
| `greptile-inline`, `greptile-thread`, `greptile-summary` |Actual read-only finding/thread/summary retained; no reply/resolution |
| `before` |37 expected baseline observations, including three actual old mis-picks |
| `rejection-before-fix` |Required no-command assertion fails, exit1,133≠132 |
| `client-build`, `shipping-package`, `paired-assets`, `artifacts` |Fresh normal client/shipping and unchanged core/module qualification pass |
| `controller` |37 strict-CSP journeys pass, zero skips; previous31 retained |
| `wire-shipping` |26 pass, zero skips:12 wire/GPU and14 shipping tests |
| `capture-parity` |Fresh19-request/17-SelectAt capture matches original exactly |
| `foundation` |Full unfiltered strict-CSP foundation passes; subset variable explicitly unset |
| `contracts` |88 focused contracts pass, zero skips |
| `inventory`, `capability-matrix` |Current generated metadata passes;685 gaps remain |
| `hooks`, `ruff-check`, `ruff-format` |Mandatory full-worktree checks pass before commit |

Authoritative contracts and generated support-matrix notes now describe
composed ancestry and positive slot eligibility. Official inventory regeneration
changes only provenance/source hashes, preserving declarations/classifications
and all685 gaps; preparation freeze remains unaccepted. `preservation.json`
binds that distinction and immutable9473-file history. Each command JSON
records argv/cwd/environment/time/exit plus raw combined and separate
stdout/stderr hashes. `environment` and browser JSON retain actual toolchain,
package and browser versions. `proof-inputs.json` binds final source/receipt
hashes; whole/source diff hashes are emitted after the local commit.

## Reproduction and limits

Use Node22 from
`/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin`
on PATH and
`XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
Run exact recorded argv with fresh output paths/labels, for example:

```bash
node js/build.mjs
node js/package-wasm.mjs
python3 scripts/verify_wasm_assets.py
python3 spec/performance/graph-s5b-pointer-slotted-ancestor-repair-2026-11-04/verify_artifacts.py
node scripts/graph_session_controller_wasm_smoke.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" XYG_GRAPH_POINTER_CAPTURE="$PWD/spec/performance/graph-s5b-pointer-slotted-ancestor-repair-2026-11-04/captured-requests.json" node --test js/test/graph-session-controller-wire.test.mjs js/test/graph-session-gpu.test.mjs packages/xy-node/test/graph-session-wire.test.mjs js/test/package-wasm-contract.test.mjs js/test/package-wasm-manifest.test.mjs
env -u XYG_WASM_FOUNDATION_ONLY node scripts/wasm_foundation_smoke.mjs
uv run pytest tests/test_shared_glhost.py tests/test_verify_ownership.py tests/test_release_inventory.py tests/test_verify_wasm_assets.py tests/test_wasm_inline_artifact_contract.py tests/test_graph_session_abi.py tests/test_capability_registry.py -q
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

To reproduce before, build the committed da52 controller in a separate isolated
checkout with this harness, then use the baseline-mode or rejection argv from
its record. Baseline mode is not passing repaired acceptance. Preserve this
append-only receipt and every historical file when recording repeats.

SelectionTooLarge still uses the labelled pre-execution seam; the actual10001-
source fixture still hits initialization Budget at the default16MiB arena.
No new capacity, hover/picked-target, gesture/public-host, broad S5b/S6/S7,
M4/#36/#108, scale/competitor/release acceptance or issue closure is claimed.
The parent owns new independent review, existing#1092 push/reply/resolution and
all later release actions.
