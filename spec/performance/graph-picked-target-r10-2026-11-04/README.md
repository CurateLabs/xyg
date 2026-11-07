# #36 R10: normal sync with accepted Buffer main

This receipt records the normal merge of exact accepted main
`40c0cc5af2fead54684197c0ef90affbbff53519` into independently reviewed R9
`c318a0cb2a25bd18d21dc925eb234340b06ddbbb`. It changes no product/build/test
source or qualified artifact. The new combined tip needs its own completed
independent final review before parent push, and fresh main-based CI before
queueing or integration. The 685 preparation gaps, public hover, #36/M4/#108 and baseline
freeze remain **UNACCEPTED**.

## Actual identity and review lineage

- First parent: `c318a0cb2a25bd18d21dc925eb234340b06ddbbb`, with parents R9 repair
  `f39edf76635e6e572aec64b6bcedc20cfed3f7eb` and reviewed Buffer parent
  `74195403ccd18c760e3d20a18f024daab95d711a`.
- Second parent: accepted main `40c0cc5af2fead54684197c0ef90affbbff53519`, whose
  parent is accepted main `3ebf70c3aa5a351aeec3843da14ba2aa197b469e`.
- The accepted main tree is actually verified as
  `e4567bd0a9dc53798add2f63e10cea4d1d7a2984`, exactly the entire reviewed
  74195403 tree, including source, specs, fixtures and evidence. The parent
  reports #1094 merged on 2026-11-04 at **07:59:51Z**. No other parent is imported.
- The parent reports completed `s5a_final_review` FINAL APPROVE for exact c318,
  with no unresolved finding: both Clippy assertion repairs and active CI entry,
  13 workflow mutations, eight shipping wire/migration tests without skips,
  285 producer inputs, 15 artifacts, 610 earlier receipts, 104 manifest entries,
  35 logs, and coherent 152 Rust / 770 CI / 226 metadata proof. The parent then
  reran mandatory hooks/Ruff, pushed c318 and replied/resolved the prior Greptile
  P2. These are recorded parent actions, not child GitHub mutations.
- The subsequent parent wake reports **all applicable c318 remote CI completed
  SUCCESS**, including required Release surfaces and Linux/ARM/Windows wheels.
  `parent-remote-ci-update.json` records the supplied categories and CodeRabbit's
  disabled/skipped status with no finding. This supersedes the pending state
  recorded earlier in `before-sync.json`; neither record is rewritten. It is
  remote success for the reviewed pre-main-sync R9 head, not for this future R10
  tip. The parent reports PR1095 auto-retargeted main and conflicting before R10.

`normal-merge.command.json` / `.log` preserve the actual normal
`git merge --no-ff --no-commit` invocation and initial **exit 1**. Its sole
conflict was generated inventory `baseCommit` provenance. The original conflict,
all three Git stages and combined diff are retained in `inventory-conflict.txt`,
`inventory-stage-*.txt` and `merge-conflicts.patch`. The official generator
resolves the inventory from current merged sources, with generation-time base
c318. No manual contract/metadata declaration edit occurs. The current scheduling
spec records the accepted landing and R10 lineage while preserving all limits
on historical Node captures and artifact provenance.

## Protected source, history and shipping identity

`before-nonspec.json` binds all **2,569** existing non-spec files by exact Git
mode/blob, including symlinks. Every source, build setting, test, R7 narrow actual
fixture-module guard and ownership ledger, R9 borrowed-slice assertions, CI
entry, workflow verifier/regressions, trigger/concurrency/aggregate/upload guard
remains exact to c318. Only the current scheduling status document and official
inventory provenance may differ outside this new receipt.

`before-history.json` binds **11,130** inherited performance files;
`incoming-history.json` binds every accepted-main history file. Their index
identities and clean tracked worktree are verified. SHA256 checks independently
protect all **658 R1–R9 receipt files**, including R9's two original complete
failed CI logs. The single previously authorized R8 wording correction to R7
README remains exactly as approved at c318, together with its original snapshot
and explicit exception. No new historical edit occurs; original failed gates,
archives, captures, transcript, fixtures and logs remain failures/evidence at
their original state.

All **285** recorded production inputs and **15** qualified shipping artifacts
are verified SHA256 exact before reuse. No native/WASM/client producer or browser
rerun is performed. Reuse concerns identical relevant bytes and the previously
qualified runtime/package/paired/CSP/controller/capture proof; it adds no new
browser measurement, historical Node artifact-origin claim or product acceptance.

- Native SHA256:
  `0deea9029e4a328dc15aa2d86873a203f12b8911e1c89c274f14270b31a3f880`.
- Optimized shipping WASM SHA256:
  `e3ef33b58820675f4c201a2b81ad23b3665090442210aa22fcee28a269884a96`.
- Raw WASM SHA256:
  `f66281328c0ffa9a53db8ab4728ab9ed3d88f2f3ca8b58ecc6ac3db212e08231`.
- Unchanged actual optimized raw/Node22 gzip6 sizes: **1,926,555 / 785,546 bytes**.
  Exact approved **1882/768 KiB (1,927,168/786,432 bytes)** caps retain **613/886**
  bytes headroom. No further allowance or size experiment is authorized.

ABI399/538 symbols, WASM35, GPU-v1, Scene34 and painter17 remain unchanged. No
runtime, arena, profile/compiler/optimizer/dependency/export/validation/tolerance/
guard or public hover/controller/scheduler/event change is made.

## Scoped fresh proof and exact reproduction

`run.py` preserves actual argv, cwd, selected environment, timestamps, exit and
complete raw output SHA256, refusing overwrites. `checks.json` records final
executed results; the initial merge conflict remains a preserved failure with
its resolution recorded separately. Node22.23.4 and Rust1.96.0 toolchain settings
are unchanged. Fresh wire tests use actual qualified shipping module/native and
no diagnostic, capture or session-module override.

```bash
uv run python scripts/check_release_inventory.py --write
uv run python scripts/check_release_inventory.py
uv run python scripts/verify_ownership.py
uv run python scripts/gen_capability_matrix.py --check
uv run python scripts/verify_ci_workflow.py
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
node --test packages/xy-node/test/graph-session-wire.test.mjs js/test/graph-picked-golden-migration.test.mjs
uv run pytest -q tests/test_verify_ci_workflow.py -k 'receipt_compatibility or active_picked_target'
uv run pytest -q tests/test_release_inventory.py tests/test_verify_ownership.py tests/test_gen_wasm_abi.py tests/test_capability_registry.py tests/test_stale_names.py
uv run python scripts/check_stale_names.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The metadata suite includes the 149 naming regressions and seven verified-module
boundary cases. The unchanged workflow receives fresh verifier and focused
mutation proof. Its complete R9 `make check-ci` 770-pass result is reused after
input identity checks, as explicitly authorized instead of an expensive repeat.
The exact workspace/all-targets Clippy and 152 Rust tests are likewise unchanged
R9 proof, not new R10 executions. Mandatory full-worktree hooks/Ruff run fresh
before the human merge commit. Existing semantic-controller compatibility stays
byte-exact; no new public receipt/hover API is exposed.

Final commit parents, clean status, precise paths and whole/nonreceipt
binary/full-index diff SHA256 versus accepted main and c318 are handed back
outside the commit to avoid a self-referential hash. The source patches and
protected-identity records inside this receipt bind the reviewable scoped diff.
Parent owns new full independent final review, push, fresh main-based CI and
queue actions. No child root, push/PR/GitHub, TASKS or history-rewrite action.
