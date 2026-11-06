# #36 R9: exact CI Clippy repair and automated receipt compatibility

**Local repair of the two CI test lints and Greptile's valid unwired-test P2.**
New independent final review and actual rerun CI remain required before parent
push/reply-resolution or integration. No production source/artifact, package
budget, runtime arena, compiler/profile/optimizer/dependency/export/validator/
tolerance or public hover/controller/scheduler/event change. The 685 preparation
gaps, #36/M4/#108, public hover and baseline freeze remain **UNACCEPTED**.

## Exact base, findings and preserved original failure

Direct parent is exact approved/pushed R8
`8b231d70d03e53e380f7198b4f618c0f33ec9ddf`; reviewed Buffer comparison parent remains
`6e240f4bd3189640779fd684e97072923cbfb9c8`. No unreviewed Buffer R4/main sync,
reset/rebase/history rewrite, root edit, child push/PR/GitHub mutation occurs.
The parent reports exact R8 FINAL APPROVE by `s5a_final_review`, with no blockers:
2,569 non-spec files,15 artifacts,93 receipt files,34 logs and10,886 unchanged
history files except the explicitly authorized R7 README wording correction.
That approval covers R8, not this future CI/test repair.

Parent-created PR1095 targets the Buffer branch. This child only repairs local
source; the app registers the existing PR with this thread as required by its
orchestration contract, without mutating GitHub. Parent retains push, review
reply/thread resolution and future independent final review ownership.

Actual GitHub run41788401132 / Test (Rust + Python + JS) job126436313771:
`cargo test --workspace` **passed**; exact
`cargo clippy --workspace --all-targets -- -D warnings` failed **two**
`cloned_ref_to_slice_refs` assertions in internal `picked.rs` (lines29/59).
The root-downloaded complete350,509-byte job log is copied byte-exact, including
ANSI/timestamps, as `job-126436313771.log`; SHA256
`27f298b4d77662e769909ce2f671e272eb5a93975a5e8921c63a62de4a7bc726`.
`ci-failure-source.json` records the supplied source path and exact provenance.
Later host/consumer artifact-upload failures are cascades from skipped producer
steps. They are not an authorization to weaken `if-no-files-found`, Release
surfaces, failure propagation or any CI/package guard.

Greptile's actual8b231 review summary had4/5 confidence and a validP2:
thread `PRRT_kwDOTxX6Es6ze30I`, comment4464570959, at
`js/test/graph-picked-golden-migration.test.mjs`. The migration test was manually
run but absent from explicit CI/normal test command lists. Thus future receipt
compatibility regressions could pass normal CI. No remote review is re-fetched
or replied to by this child; the parent-supplied finding is recorded here.

## Narrow repair

Two Rust assertions now compare borrowed slices using `std::slice::from_ref`
against decoded/selected reference slices. They retain full exact-ref equality,
remove only unnecessary test-side clone arrays, and add no lint allowance or
validation bypass. No whole-repository Rust formatting occurs.

The existing **GraphForge native/WASM equivalence** step in the existing Test
job gains one normal automated command:

```bash
node --test packages/xy-node/test/graph-session-wire.test.mjs js/test/graph-picked-golden-migration.test.mjs
```

It follows native core build, JS client build, single-producer WASM artifact
download and paired-asset verification; the step already exports the exact
just-built native library. Existing normal producer and all other equivalence
commands are unchanged. The migration test uses the committed actual browser
capture and exact pre-existing raw-section comparisons, while the session test
retains full native/WASM/expected reply comparisons. No test body/fixture,
section filtering, golden normalization, skip or relaxed identity check is added.

The **existing** workflow verifier now pins this named step's active full
command list and its prerequisite order. Negative regressions remove each test,
comment/echo/mask the command, skip/make advisory the step, or move it ahead of
native/client/verified-WASM readiness. These fail the existing workflow gate.
This is no new job/status/framework or second WASM producer. `merge_group`,
non-canceling merge-group concurrency, `Release surfaces`, upload failure rules
and package/export/version guards are preserved. The readiness and graph receipt
specs document the automated command and normal reproduction.

## Actual scoped proof and protected identities

- Exact workspace/all-targets Clippy passes with `-D warnings`; no lint allowances.
- **152 Rust interaction tests pass**, zero failures/ignores, including exact
  frozen R2 transcript and the repaired assertions.
- Exact new automated Node command: **8 passed**, zero failures/skips, using the
  actual existing shipping module/native; diagnostic/capture override selectors
  are unset. This is real byte replay, not a comment or CI-text-only assertion.
- **13 focused workflow mutation regressions pass**; complete required
  `make check-ci` passes its verifier and all **770 regressions** (zero skips).
- Official inventory regeneration/check, ownership and naming checks are fresh;
  final results and mandatory full-worktree hooks/Ruff are recorded here.

`verify-protection.py` / `protected-identity.json` verify **all285 production
input hashes and15 qualified artifacts unchanged**, plus **all552 current
R1–R8 receipt files exact**. The R8-approved correction to R7 README is preserved
exactly as it stood at8b231; no further README/history edit is made. All other
inherited performance files remain unchanged against8b231. The two test-only
Rust assertion edits are separately matched to the exact intended replacements;
they are not claimed to be byte-identical. Inventory contracts/classifications
remain identical with685preparation gaps; only source provenance is refreshed.

Native SHA256:
`0deea9029e4a328dc15aa2d86873a203f12b8911e1c89c274f14270b31a3f880`.
Optimized shipping WASM SHA256:
`e3ef33b58820675f4c201a2b81ad23b3665090442210aa22fcee28a269884a96`.
Actual1,926,555 raw /785,546 Node22gzip6 bytes remain under the exact authorized
**1,927,168 /786,432-byte (1882/768-KiB) limits**, with **613/886-byte headroom**.
No additional allowance or size experiment. ABI399/538symbols, WASM35, GPU-v1,
Scene34 and painter17 remain unchanged.

No native/WASM/client release producer or full browser run is repeated. R8
qualified runtime/package/CSP/capture proof is reused only for identical
production inputs/artifact bytes. Fresh Clippy/152Rust and active CI command/
workflow tests prove the new changes. This does not claim remote CI success or
approval of the new candidate. The original failed CI log stays a failure.
This repair is committed directly on the 8b231 lineage before any parent sync.
A later, separately recorded normal merge of explicitly reviewed parent
`74195403ccd18c760e3d20a18f024daab95d711a` is now authorized by the parent;
that integration requires fresh protected-identity checks and its own human
merge commit after mandatory hooks/Ruff. It is not part of this repair commit.

## Environment and exact reproduction

`run.py` preserves actual argv/cwd/environment/timing/status and complete
combined-output SHA256, refusing overwrites. Node22.23.4 at
`/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin`,
Rust1.96.0, project uv/Python and all existing build settings are unchanged.
The existing actual artifacts must match the recorded identities before reuse;
otherwise this proof is inapplicable and normal producer qualification is needed.

```bash
cargo clippy --workspace --all-targets -- -D warnings
env -u XYG_PICK_CORPUS cargo test -p xyg-engine graphforge::interaction --lib -- --nocapture
uv run make check-ci
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
node --test packages/xy-node/test/graph-session-wire.test.mjs js/test/graph-picked-golden-migration.test.mjs
uv run python scripts/check_release_inventory.py
uv run python scripts/verify_ownership.py
uv run python scripts/check_stale_names.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The normal CI step exports the equivalent `GITHUB_WORKSPACE` native path; the
exact local automated command/selected environment is in its command record.
No entire long Python/browser suite is requested or claimed. Use fresh receipt
outputs when reproducing; do not overwrite R1–R9 evidence. No TASKS change,
AI attribution, PR/push/GitHub/root mutation or premature review resolution.
Parent owns a new independent final source/policy review before any push.

## Additional aggregate failure evidence and parent steering

The root-downloaded complete **27,415-byte** Release surfaces job126439951835
log from the same run41788401132 is preserved byte-exact as
`job-126439951835.log`, SHA256
`d2be47cf7ac100ec9889b0b9cf8b0cca44d10959585c57d7b2eb9a7b4f2fa4ff`.
Its actual dependency results show **test=failure, wheels=skipped**; all other
applicable WASM assets/foundation/Python floor/conformance/Scene/matplotlib/
sdist/install jobs succeeded. `aggregate-cascade.json` binds the supplied source
and diagnosis: this is the Clippy cascade, not a new release-policy defect.
The aggregate, wheels and upload guards are unchanged. Neither preserved failed
CI job is converted into a pass by the successful local repair.

The parent reports completed FINAL APPROVE by `m4_defaults_audit` for exact
74195403 (parents reviewed 6e240 and accepted main 3ebf70c3), with product/build/
test/Buffer-guard bytes identical to 6e240. Only scheduling status, inventory
provenance and new receipt evidence differ. This report authorizes the subsequent
sync, not a review of this child repair or the future combined tip. Parent owns
new full independent review before push or resolving the Greptile thread.

## Final local repair disposition (before authorized parent sync)

- Exact workspace/all-targets Clippy: **PASS**, with warnings denied.
- Rust interaction: **152 passed**, zero failures/ignores.
- Exact newly automated shipping wire/migration command: **8 passed**, zero skips.
- Focused workflow mutations: **13 passed**; full `make check-ci`: **770 passed**.
- Metadata regressions: **226 passed**, including all **149 naming regressions**
  and the seven narrow external-module guard cases. Official inventory/check,
  ownership **513**, capability and unchanged whole-repository naming gate pass.
- Mandatory all-files hooks, Ruff check and Ruff format check: **PASS**. Their
  final rerun after this receipt's prose is retained separately.
- Production inputs/artifacts remain exact; no release rebuild or browser replay
  is performed or required for this CI/test-only repair. Both original CI failure
  logs and all prior receipt bytes remain immutable. Remote CI and new independent
  final review of the combined future sync remain pending.

`source.patch` contains the entire seven-path nonreceipt repair against 8b231;
`source-identity.json` binds its full binary/full-index SHA256
`817972d474d7261b84d8fb1665f3395af57f657e10b3a9ce21ae2fb0034128cd`.
The parent-approved 741954 sync is deliberately subsequent to this human repair
commit and will have separate raw proof and lineage, preserving this receipt.
