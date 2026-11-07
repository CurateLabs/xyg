# #36 R5: explicit functionality decision, production qualification blocked

**The exact parent-authorized size gates pass; R5 as a whole is NOT qualified.**
The existing captured-primary-click wire replay fails. No runtime repair,
fixture rewrite, comparison weakening, optimization experiment or further gate
allowance was attempted. The full source/test/policy patch is saved separately;
tracked sources are restored to reviewed parent `c3d2e4aa19bcfbf9940775819f03c71cc0934472`.
No unfinished runtime commit, PR, push, GitHub/root mutation or publication.

## Separate explicit parent decision

The parent explicitly authorizes exactly **1,882 KiB raw / 768 KiB Node22 gzip6**
(**1,927,168 / 786,432 bytes**) for required query-scoped actual PickTarget,
source/group identity, provenance and no-query typed Leave. This is a deliberate
functionality decision after completed independent assessments, not an inferred
allowance from a failed producer. Parent-reported completed reviews:

- `m4_defaults_audit`: independently assessed functionality and minimum limits.
- `s5a_final_review`: PASS on exact R4 patch
  `5383a32d4077dea01d8b9342068c1f20c0eaff6d5a7d7b5e4ef3580a637d3ef8`,
  with no blocking source-correctness finding. Reviewed R2 release/cfg(test)
  separation, query/leave/source/group/CSR/refusal/retry and helper guards;
  9 diagnostic cases, 468 steps, 430 full publications, 29 refusals, input hashes,
  command logs and preserved old receipts. Diagnostic proof was not shipping or
  integration approval. These completed reviews precede the parent's separate
  explicit decision; no new final R5 source/policy review has occurred here.

Retain R2 inline `Option<PickReceipt>`, combined counted CSR and borrowed refs.
R1–R4 receipts, archives, patches, failures and historical policies are immutable.

| Actual module | Raw bytes | gzip6 bytes | Disposition |
| --- | ---: | ---: | --- |
| 207 baseline | 1,922,723 | 783,181 | historical baseline, not a freeze acceptance |
| R1 | 1,927,577 | 785,926 | failed old gates |
| R2 | 1,926,555 | 785,546 | best minimal candidate, retained |
| R3 Arc | 1,928,323 | 785,601 | rejected, worse by 1,768 / 55 vs R2 |
| R5 fresh normal R2 build | 1,926,555 | 785,546 | exact R2 bytes; current size gates pass |

R2 reuse saves **1,022 raw / 380 gzip** over R1. Growth over 207 is
**3,832 / 2,365**. The former 1,878/765-KiB gates fail R2 by **3,483 / 2,186**;
1,881/767 still fails by **411 / 138**. The adopted exact 1,882/768 gates leave
**613 / 886**. No optimization search or future growth is authorized. Required
receipt facts cannot be dropped without narrowing the actual target/provenance/
Leave contract. Compiler/profile/optimizer/dependencies/exports/arena/guards/
validators/tolerances remain unchanged. Runtime bounds remain **16 MiB default /
384 MiB maximum**; the 10,000-selection corpus explicitly uses that existing
maximum and establishes no default-arena massive-graph claim.

Native ABI399 / 538-symbol manifest, WASM35, GPU-v1, Scene34 and painter17 are
unchanged. There is no C signature, public API, TypeScript interface, decoder
policy, browser scheduling/coalescing, public hover/event/tooltip/linking change.
**685 preparation gaps remain; baseline freeze remains UNACCEPTED.** This receipt
accepts neither #36, M4, #108, scale/performance nor release/publication.

## Source lineage and actual producer identities

The same isolated worktree/branch first ran normal `git merge --ff-only` from
`207ebdbdaa2ec8b0360c571683eb0fa6165e02c0` to reviewed parent
`c3d2e4aa19bcfbf9940775819f03c71cc0934472`. No reset/rebase/history discard or
root edit occurred. The parent has identical Rust production source to207.
The complete reviewed R4 patch applied cleanly, without doc conflicts or R3
Arc import. `production-source-freeze.json` binds pre-build source inputs.
The fresh native release matches exact R2; the normal WASM release/client/
optimizer/packager produces the exact R2 optimized hash under the new gates.
Nothing was copied from a rejected archive into a shipping path.

| Fresh actual artifact | SHA-256 |
| --- | --- |
| native `target/release/libxyg_core.so` | `0deea9029e4a328dc15aa2d86873a203f12b8911e1c89c274f14270b31a3f880` |
| optimized shipping `packages/xy-client/dist/xyg-wasm.wasm` | `e3ef33b58820675f4c201a2b81ad23b3665090442210aa22fcee28a269884a96` |

`actual-production-artifacts.json` records all actual raw/module/native/client/
Worker/inline/manifest identities, size measurements and headroom.
`shipping-module.wasm.gz` is archived directly from the newly produced shipping
module, not substituted from an old receipt. R4's isolated rejected diagnostic
module is unused. Ignored outputs after restoration are **R5-produced retained
R2 candidate artifacts, NOT restored HEAD artifacts and NOT fully qualified**.
The raw WASM is freshly rebuilt R2, replacing the previous ignored R3 raw binary.
Historical Node1k proof and its `3a9` identities are unchanged, not rebound here.

Only test code differs from reviewed R4 beyond the cap policy/docs/metadata:
a distinct shipping replay asserts the actual default shipping module, forbids
`XYG_SESSION_WASM`, checks identity/manifest/caps, and retains all original replay
and capacity guards. Existing semantic-decoder test explicitly checks actual
SelectAt's five unknown sections remain raw and create no public pick property.
The inventory scanner excludes external Rust `tests/` modules as it already does
inline cfg(test) modules, with regression coverage; fixture selectors are not
production operator configuration. Official contracts/gap classification remain
unchanged, with fresh provenance hashes only.

## Actual checks and stop condition

| Recorded command label | Actual result |
| --- | --- |
| native-release / wasm-release / client-build / normal-package | PASS, normal unchanged producers except exact authorized cap constants |
| measure-v2 / paired-assets | PASS; exact R2 identities; 613/886 headroom; paired modules/inline/manifests |
| rust-interaction | **152 passed**, zero failures/ignores; frozen 756,232-byte R2 transcript exact |
| actual-query-corpus | PASS, fresh Rust corpus creation |
| shipping-parity | **9 passed**, zero skips/failures; **468 steps, 430 complete post-Open XYGR publications, 29 refusals** against fresh shipping module/native/engine |
| foundation | PASS, **full-foundation**, `XYG_WASM_FOUNDATION_ONLY` explicitly unset; no external requests |
| controller | PASS, **69 packaged strict-CSP journeys, zero skips**, includes old-same-ABI module fail-closed behavior |
| shipping-wire | **FAIL: 25 passed, 1 failed, zero skips**; captured primary-click replay described below |
| metadata-regressions | **220 passed**, including inventory/ownership/ABI/capability/naming tests |
| inventory-final-check / metadata-capability / ownership / naming | PASS; 685 preparation gaps unchanged |
| native-declarations / wasm-declarations / typing / python-host-audit | PASS |
| host-parity-audit | PASS, landing gates including 1,087 tests; 31 warnings |

The independent CSP/controller/parity runs were already in flight when the wire
failure was observed; their completed passing results are retained, not used to
normalize or override the failure. No subsequent normal qualification retry or
production repair was attempted. Inline file smoke and complete overall
qualification remain outstanding. Passing current size gates or subsets of
browser proof does not make R5 production/integration accepted.

### Required wire suite failure: historical bytes plus separate Buffer defect

`shipping-wire.log` preserves the exact actual failure:

```
not ok 26 - captured primary-click OPEN/Render/SelectAt requests replay full native/WASM XYGR bytes
RangeError: malformed XYGR container: text offsets
```

The unchanged shared helper compares complete bytes before decoding diagnostic
differences. The historical capture stores pre-receipt replies. Read-only
`captured-failure-diagnosis` replay found 18 post-Open requests: one Render reply
is byte-exact; **all 17 SelectAt replies differ solely by the five required new
pick sections**. No old section was removed or changed (decoded dtype/count/
value comparison). The old full containers cannot equal additive new receipts.
This diagnosis is not a replacement test or a passing qualification claim.
The complete actual/expected/request bytes are archived in
`captured-actual-replies.json.gz`; section-level facts in `captured-mismatch.json`.
No old capture, fixture, expected reply or comparison was changed.

The error instead of the byte-difference assertion is caused by the separately
reported unchanged Node Buffer numeric-decoder defect at
`packages/xy-node/src/graphforge-container.js:38`: `payload.slice().buffer` retains
a larger Buffer backing allocation. Read-only diagnosis reproduces its error on
the byte-identical old expected Buffer, whereas a plain Uint8Array decodes.
The separate isolated Buffer-fix child remains parent-owned and was not imported.
Fixing that decoder alone will expose the historical full-reply mismatch; it
will not make the old no-receipt expected bytes equal the new publication.
Parent decision is needed for the required current-capture proof while retaining
historical exact evidence, plus separately reviewed decoder repair. No broad
Node host acceptance is claimed.

### Preserved measurement-harness failure

`measure` failed with ENOENT because that new recording script assumed
`python/xyg/static/wasm-inline-worker.js` existed. Normal production intentionally
embeds the classic Worker in the inline bootstrap rather than copying that
standalone file to Python. The original script/log remain unchanged;
`measure-v2.mjs` records the actual existing asset set. No producer, asset,
validator or gate was changed. Normal packaging and paired verification pass.

## Environment, reproduction and safe final state

`run.py` records exact argv/cwd/selected environment/time/exit and unmodified
combined-output SHA256, refusing overwrites. Node22.23.4, Rust1.96.0/LLVM22.1.2,
pinned Binaryen132 `-O3 --all-features`, repository fat-LTO/one-codegen/strip and
WASM inline-threshold100 remain unchanged. Chromium156 cached repository workflow
is used. Python/uv versions and source/artifact hashes are recorded.

After a parent decision, reproduce in a new evidence directory, never overwrite
R1–R5. The saved patch is relative to `c3d2e4a`; all old receipts must remain for
the frozen R2 transcript. Restore/apply with normal `git apply --check` / apply.
Use Node22 at
`/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin`
and `/home/ubuntu/.cargo/bin` on PATH. The command records are authoritative:

```
cargo build --release -p xyg-core
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
python3 scripts/verify_wasm_assets.py
```

Run the recorded shipping-wire invocation with `XYG_SESSION_WASM` unset to
reproduce the preserved failure. The new receipt replay uses `XYG_PICK_CORPUS`
and `XYG_PICK_REPORT` with the **default freshly built shipping module**; it
forbids a module override. Full CSP explicitly unsets the foundation filter.
Fresh independent final source+policy review remains parent-owned before any
PR/integration or next browser phase. No integrated approval is inferred.

Final integrity, patch hash, checks and restored status are appended below.


Final recorded handoff:

- Full source/test/policy patch SHA256: `92bdd7f7c96be9ec04c75d90fe77adea03f3dccee4cf929cad94ffb7f0b7a358`.
  `full-nonreceipt.patch` has 22 changed paths, excludes every receipt directory,
  and `git apply --check` passes on restored c3d2. `source-inputs.json` binds all
  candidate file hashes; `r4-source-and-contract-preservation.json` proves exact
  reviewed Rust/toolchain/guard bytes and unchanged inventory contracts/685 gaps.
- Full-worktree `uv run --with pre-commit pre-commit run --all-files`,
  `uv run ruff check .`, and `uv run ruff format --check .` all PASS on the saved
  candidate (`final-hooks`, `final-ruff-check`, `final-ruff-format`).
- All **205** R1–R4 receipt files, including manifests and all failures, remain
  byte-exact (`prior-receipts-before.json` / `prior-receipts-after.json`).
- Final tracked HEAD **c3d2e4aa19bcfbf9940775819f03c71cc0934472**, clean tracked
  index/worktree; only R1–R5 receipt directories remain untracked. Sources were
  restored with scoped `git restore`, not reset/rebase. `baseline-status.txt`
  and restore/check records retain actual state. No commit was created.
- `final-binary-labels.json` explicitly identifies candidate native/raw/optimized
  shipping outputs as **NOT restored HEAD / NOT fully qualified**, and separately
  identifies the unused R4 rejected diagnostic module.
- `checks.json` retains every command result, including the failed recording
  script and actual required wire-suite failure. Nothing normalizes either run.
- Parent owns the next current-capture/Buffer-fix decision and independent final
  source/policy review. The authorized policy is retained in the saved patch;
  restoring baseline does not retract that parent decision. Overall R5 remains
  blocked, and there is no browser-hover phase or integration approval.
