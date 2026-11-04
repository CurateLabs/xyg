# Explicit retained WASM graph attachment: bounded S5b candidate

This isolated implementation starts at
`7e99ec5da586572d411996599cf37f25dc5566c7` on
`t3/wasm-graph-session-attach`. It adds the experimental
`attachWasmGraphSession` helper: complete XYGF ingress, explicit session camera,
one retained Worker command lane, GPU-v1 paint, keyboard focus/selection/clear,
and the Rust-paged companion. Parent review, integration, PR and push remain
separate. No remote mutation, publication, credential operation, history rewrite,
Rust/C/WASM signature change or budget adjustment occurred.

**Literal synchronous Escape-default suppression remains an acceptance gap.**
The Worker returns the actual Clear outcome asynchronously. Calling
`preventDefault()` only after Rust reports `state_changed` sets the event's
later observable flag, but cannot cancel an already executed native browser
default. The empty Escape journey is proven unsuppressed. This candidate does
not substitute a TypeScript clearability rule or claim the stronger synchronous
behavior. The parent was informed before such a policy could be invented.

## Implemented boundaries

`63_graph_controller.ts` exports only through `60_entries.ts`. It accepts a
borrowed packaged Worker, nonzero exact-u64 bigint instance ID, complete XYGF,
existing optional load inputs and seven exact camera f64s. Its surface is
`ready`, `refreshRender(camera?)`, `snapshot()` and asynchronous idempotent
`dispose()`. A caller owning the Worker awaits attachment disposal before
Worker disposal. Only initially Owned/unlinked state is exposed. Camera scale
may have either nonzero sign; Rust owns numeric admission and layout.

The internal transport retains exact request bytes through resolution and
separates lifetime token, Worker request ID, instance ID, bigint operation
sequence, render revision and outer Worker sequence. XYGR does not echo instance
ID; the transport authenticates correspondence using its issued request and
lifetime envelope, not an invented XYGR field. Every command is serialized and
non-cancellable. Duplicate attachment and competing ordinary/temporal/geographic
lanes reject before retained session mutation, on both main and Worker sides.
The 60-second lost-reply watchdog terminates the Worker with unknown mutation
outcome; it never treats the command as cancelled or retries selection silently.

Semantic and all 33 GPU-v1 sections validate before upload or installation.
Raw f32/u8 columns, 60-byte style records and piece→edge/head→piece/frame→node
indices are consumed directly through GLHost. Rust has already mapped positions
to CSS screen space; the painter only reconstructs offsets/scales and applies
viewport/DPR presentation. The four base passes are frame→shaft→head→node,
followed by static focus emphasis. Every success repaints, including same-revision
style-only publication. Refusal or malformed output preserves the preceding
accepted camera, snapshot, companion and picture. Stale blocks further input
until explicit Render recovery.

Keyboard arrows forward Rust FocusStep ±1. Enter replaces focused selection;
Ctrl/Meta+Enter toggles; Escape forwards Clear with the timing limit above.
Tab/Shift+Tab remain native navigation. One UI action is outstanding; busy,
unsupported and stale-blocked input is not swallowed. The following table and
polite live region use Rust's rows, aligned candidate refs and summary as text.
Row/cell separators split before escape decoding. Previous/Next pages contain
50 rows. Ordinary interaction replies use the Rust wire's default page zero;
the host does not reinterpret or synthesize a persistent engine page.

Complete selection/provenance, changed refs, focus/action facts, authoritative
outcome count, summary and companion decode without eagerly materializing CPU
geometry or source flags. u64 fields remain bigint; absent and present-empty
result IDs remain distinct. The global selected count need not equal the
resolvable projection length.

## Actual proof

All command records include argv, working directory, selected environment,
start/end timestamps, exit status and SHA-256 of unmodified combined raw logs.
`run.py` refuses overwriting records. The decisive final runs are:

| Record | Actual result |
| --- | --- |
| `client-build-final` | Typecheck, shader lint and fresh shipping ESM/IIFE/module/classic Worker build pass |
| `shipping-package-final` | Actual unchanged normal WASM optimizer/packager passes both hard gates |
| `paired-assets` | Both asset sets, manifest hashes/versions, inline WASM and embedded classic Worker agree |
| `shipping-tests-final` | All 13 native/WASM replay and package tests pass; zero skips |
| `foundation-final` | Full unfiltered strict-CSP foundation passes; `XYG_WASM_FOUNDATION_ONLY` explicitly unset |
| `controller-watchdog` | 14 actual packaged ESM/Worker/WASM strict-CSP journeys pass; zero skips |
| `wire-gpu-tests` | 11 wire/semantic/GPU boundary regressions pass; zero skips |
| `gpu-paint` | Real WebGL four-pass visibility, DPR=2, signed/nonidentity camera, focus repaint and exact context restoration pass |
| `encoder` | Browser encoder bytes equal the existing Node codec |
| `canonical-graph` | Existing canonicalScene GraphForge browser journey passes unchanged |
| `geo-controller` | Existing 101-row/three-page geographic controller journey passes unchanged |
| `contracts-corrected` | 69 ownership/API/package/native-session contract tests pass |
| `api-inventory` | Regenerated preparation inventory passes with 685 actual review gaps |

`controller-watchdog.json` retains accepted identities/provenance/action facts,
Rust summaries, full command identity/stamp observations, case outcomes and
actual request paths. It proves real sentinel Tab entry/exit in both directions,
visible focus, Replace/Ctrl/Meta Toggle/Clear/empty Clear, reduced-motion static
paint, observer failure isolation, same-revision repaint with unchanged geometry,
Rust companion paging/Prev/Next/aligned row selection, duplicate/competing lane
refusal, wrong instance, stale recovery, malformed GPU last-good retention,
initial Render failure cleanup, queued/double disposal, two Workers, wrong
lifetime refusal, real context loss/restoration and no late events. A withheld
successful reply followed by Playwright clock advancement exercises the actual
60-second main-thread watchdog; the terminal command is not replayed. Actual
legacy CSR, CPU pick and selection-mask entry methods are instrumented to throw;
none are reached. `controller-focus.png` is an unmasked actual focus screenshot.

The GPU probe is complementary source-level generic-painter evidence, not a
second packaged module or substitute for the shipping journey. It observes
painted center/shaft/head/frame pixels without masks/tolerance/golden changes.
The shipping foundation itself remains unchanged. Its report records actual
asset/harness hashes. Reports ran on the implementation worktree before commit;
their HEAD/base fields are not claims that the new client was built from old
committed TypeScript. `source-inputs.json` binds all 301 actual build inputs;
`proof-inputs.json` binds harnesses, tests, fixtures and producers.

Two receipt commands deliberately remain failed evidence: `contracts` named a
nonexistent `tests/test_ownership.py` and ran no tests; the corrected command
uses `tests/test_verify_ownership.py` and passes. `provenance` incorrectly compared
Python's gzip implementation with the Node shipping gzip byte count; the
corrected capture uses the exact Node22 gzip6 implementation. Neither failure
is hidden or converted into a pass. Earlier development probes preceded this
qualification and do not replace its final-source records.

## Qualified Rust reuse and actual artifacts

No Rust source changed. The native library and unoptimized WASM were copied from
the parent's qualified requested-base checkout, not compiled afresh here.
`artifacts.json` checks all 240 Rust/compiler-config/optimizer inputs against
both the requested git base and the prior qualified `build-inputs.json`, and
checks exact native/raw-WASM/shipping-WASM hashes against the prior production
receipt. It also proves every historical receipt file remains byte-identical.
The prior native/WASM actual production commands and environment remain in
`graph-property-default-package-2026-11-03/`. Browser compilation, the real
shipping packager, paired validation and all relevant journeys are fresh here.

The optimized module is **1,922,561 raw / 783,148 Node gzip6 bytes**, SHA-256
`e8011f779e70f58416a751f0067f279d1b9aa9515004c246e2f44c95af192651`.
The unchanged 1,878/765-KiB gates leave **511/212 bytes** headroom.
`shipping-module.wasm.gz` contains those actual optimized shipping bytes;
`artifacts.json` records all paired assets and native/raw module hashes.
Native ABI399/WASM35/Scene34/painter17/GPU-v1/XYGI/XYGR, runtime arenas,
compiler/profile/optimizer/dependencies, package exports and validation guards
are unchanged. The actual final ESM is 792,822 bytes and Worker is 56,051 bytes;
no JavaScript startup, memory or speed improvement is claimed.

## Remaining limits

Broader S5b, S6/S7, #36, M4 and #108 acceptance remain open. The API inventory
is preparation with explicit experimental declarations and 685 review gaps,
not a stable/frozen baseline. This tiny/51-row browser proof establishes no
large/massive scale, interaction-latency, accessibility audit, competitor win,
or broad browser/release acceptance.

No temporal binding, linking, structural update, force scheduling, pointer,
hover, brush/lasso, disclosure, move/pin/relayout or legacy alias is exposed.
Other emphasis operations remain open. Exact hover/picked references need a
later Rust result projection; private hover lists, flags, selected refs and
nearest geometry cannot replace it. Legacy CSR remains required by ordinary
`spec.graph` until S6 provides its attachment/identity migration. No issue or
milestone is marked complete. The parent must obtain a new independent final
review before integration/PR/push.
