# S5b attachment R2: Clear applicability and shared sampler repairs

This candidate repairs both P1 findings from `/root/s5a_final_review` on
`b0de6a55814f7c799d551c40fbd5c82227707cd3`, in the same isolated worktree and
`t3/wasm-graph-session-attach` branch. The reviewed whole/source diff hashes were
`191d4d14d8235b04015b4966fe40d9c28afe5976d3bdc0af543d03197a6e4a18` /
`0e826735ef757cfd23763b35afe24277cc30a2a0a4e2f6959ef85a3dbc3ebb9b`.
`review.json` records the findings, adopted parent contract and disposition.
A new independent final review is required before any integration/PR/push.
No remote mutation, publication, credential operation or history rewrite occurs.

## P1 Escape: repaired with Rust facts and synchronous local admission

`GraphInteractionState::can_clear` contains the exact predicate formerly inside
Clear: selection nonempty OR any of the three highlight sets nonempty. Clear
itself reuses that predicate. Focus, pins and transient hover do not apply;
hidden/unresolvable/foreign retained refs still apply. No TypeScript projection,
count, visual state or DOM content decides this.

The existing shared serializer adds `clear.action.u32`, index0/U32/count2,
`[version1, applicable0|1]`, from the same post-operation state clone used for
selection and focus-action projection. Successful publications, same-revision
updates and exact retries include it; OPEN/Poll do not. No outcome layout,
reserved focus word, C/WASM function signature or ABI version changes.

The strict browser decoder requires exact shape/version/boolean and installs
the fact atomically with the complete semantic/GPU result. Missing or malformed
facts preserve the preceding picture and snapshot while blocking input until
refresh. The real old ABI35 shipping module without this fact fails closed,
closes the opened session and leaves its borrowed Worker usable for ordinary
composition; the old artifact is only a labelled negative control.

Escape first frames and locally admits Clear synchronously. When the latest
accepted Rust fact applies, it calls `preventDefault` before keydown returns.
No observer runs between fact choice and local admission, no KeyboardEvent is
retained asynchronously, and there is no `stopPropagation`. Busy, stale,
terminal, disposed and locally refused states do not consume an old fact.

The adopted timing contract is applicability plus local acceptance, **not a
reservation for eventual Rust success**. A subsequent definitive Rust refusal
reports the error and preserves prior state although the native browser default
has already been cancelled. The actual trusted dialog proof includes that
exception; this is not the historical late-preventDefault gap or a scope waiver.

`controller-final.json` records actual `keyboard.press("Escape")` and trusted
native dialog events. Its no-cancellation control closes the dialog and fires
trusted `cancel`; selected/applicable Clear keeps it open and subsequently
clears Rust selection. Empty/focus-only, busy/stale, missing/malformed fact,
terminal, disposed surface and failed local lane admission permit the native
default. The definitive Clear refusal leaves the dialog open, retains selection
and reports `GF_INTERACTION_INVALID`. Key flags are observed synchronously on
bubbling keydown and actual dialog open/cancel behavior is asserted, rather than
waiting for a synthetic event's later `defaultPrevented` property.

## P1 sampler isolation: repaired at the shared GL boundary

GLHost now resets both textures and samplers on units0–2 before and after passes.
The graph painter's integer piece→edge reference texture uses unit2. A neighbor's
LINEAR sampler previously changed texture completeness and image channels
without any GL error. The shared reset now isolates this resource alongside the
ordinary chart units0/1; the graph renderer and raw geometry/style contract stay
unchanged.

The actual shipped ESM/Worker/WASM journey binds a LINEAR WebGLSampler on the
existing shared host's unit2 and refreshes. Dirty and clean repeats each have
**zero changed image channels**, with all sampler/texture bindings on units0–2
cleared. No mask, tolerance or golden changes are used. The complementary raw
GPU probe verifies exact WebGL pixels before/after real context restoration,
with dirty samplers both before and after restoration, plus active-unit0,
GL_NO_ERROR, double disposal, host release and context release.

`sampler-negative.log` preserves the deliberate two-unit negative control from
the scoped implementation probe: 4,820 changed channels initially / 4,816 after
restoration, with sampler2 left bound. This raw negative control predates the
captured positive command and is not a separately qualified shipping artifact.
The positive `sampler-raw` command records zero differences throughout.

The existing structural unit-reset contract initially failed because it still
required2. Its repair changes the reviewed expectation to3 and additionally
inventories the graph adapter's bounded computed texture-helper units, requiring
sampler reset as well. This strengthens the tripwire; no pixel threshold changes.

## Fresh actual production output

`native-release` and `wasm-release` are fresh actual production compilations,
not reused binaries: normal release profile, pinned toolchain/configuration,
locked/offline existing dependencies. `client-build` freshly typechecks/lints
and builds the shipping ESM/IIFE/module/classic Worker. The unmodified normal
`shipping-package` producer passes both existing hard gates, and `paired-assets`
verifies both asset sets/manifests/inline WASM/classic Worker.

The actual optimized module is **1,922,723 raw / 783,181 Node22 gzip6 bytes**,
SHA-256 `6ebbdb7f7e6859ad9a08bd2c0237c62aaa6147df8c683b080959b42e7d2fb273`.
Growth is **162 raw / 33 gzip6 bytes** over the preceding candidate. Unchanged
1,878/765-KiB limits (1,923,072 / 783,360 bytes) leave **349/179 bytes** headroom.
`shipping-module.wasm.gz` retains the actual module. `artifacts.json` records
all 301 exact build-source hashes, fresh native/raw-WASM hashes and all paired
shipping asset hashes. No budget/arena/compiler/profile/optimizer/dependency,
package export or validation weakening occurred. ABI399/WASM35/GPUv1/Scene34/
painter17, XYGI and the existing XYGR fields remain unchanged; the new named
Clear section has its own version1.

## Validation and reproduction

`run.py` refuses overwriting evidence and retains argv, selected environment,
working directory, timestamps, exit status and SHA-256 of combined raw logs.
`environment` records actual compiler/Cargo/Node/Python/package versions.
The final source/harness hashes and new receipt's raw logs are independently
bound in `proof-inputs.json`; no historical receipt is edited.

| Command record | Actual result |
| --- | --- |
| `native-release`, `wasm-release` | Fresh actual release builds pass |
| `client-build`, `shipping-package`, `paired-assets` | Actual shipping production and unchanged gates pass |
| `rust-workspace` | Full workspace pass: 1,970 tests, zero failures/ignored |
| `rust-clear-state`, `rust-clear-wire`, `rust-interaction-nearby` | Focused predicate/publication tests and 143 nearby interaction tests pass |
| `shipping-tests` | Full original13 shipping tests pass, zero skips; native/WASM byte replay checks the new fact and OPEN/Poll exclusion |
| `wire-gpu-tests` | 11 strict wire/semantic/GPU regressions pass, zero skips |
| `controller-final` | 17 packaged strict-CSP journeys pass, zero skips, including real native dialog and dirty-neighbor paint |
| `sampler-raw` | Exact dirty/clean/restored/restored-dirty GPU pixels and lifecycle pass |
| `foundation` | Full unfiltered strict-CSP foundation passes; subset environment explicitly unset |
| `contracts-corrected` | 78 shared-host/ownership/API/package/ABI tests pass |
| `canonical-graph`, `geo-controller` | Existing canonical and geographic controller journeys pass |
| `api-inventory` | Preparation check passes; actual685 gaps remain explicit |

Run the exact recorded argv from the root with Node22 and the recorded cached
Chromium path. For example:

```bash
cargo build --release --locked --offline
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown --locked --offline
node js/build.mjs
node js/package-wasm.mjs
python3 scripts/verify_wasm_assets.py
node --test packages/xy-node/test/graph-session-wire.test.mjs js/test/package-wasm-contract.test.mjs js/test/package-wasm-manifest.test.mjs
node scripts/graph_session_controller_wasm_smoke.mjs
env -u XYG_WASM_FOUNDATION_ONLY node scripts/wasm_foundation_smoke.mjs
```

`contracts` preserves the initial failing two-unit expectation, followed by the
strict updated contract's passing run. The optional `rust-fmt` probe remains a
failed repository-wide formatting check: it reports thousands of existing style
differences (the first failing core file is byte-exact to the reviewed base), as
well as compact new test additions. No sweeping unrelated formatting was done;
this is not a claimed passing check. Required all-files hooks, Ruff check and
Ruff format checks are recorded separately before commit.

The initial focused Rust wire fixture briefly failed during development because
an operation11 test request incorrectly retained a highlight-plane header word;
only the fixture was corrected. That exploratory terminal output was not saved
as a raw file, and no reconstructed log is presented. All captured focused/full
Rust commands pass. No production behavior was changed for that fixture.

The receipt's source diff hash can exclude receipts; the whole receipt-inclusive
final diff hash is emitted with the committed handoff to avoid a self-reference.
The parent must review the new material diff. Broader S5b/S6/S7, #36/M4/#108,
hover/picked-ref projection, legacy attachment/removal and release/scale/
competitor acceptance remain open. This R2 slice claims no such completion or
performance win, and creates no PR or push.
