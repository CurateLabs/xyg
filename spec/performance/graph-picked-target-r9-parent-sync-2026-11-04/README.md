# #36 R9: reviewed Buffer parent sync after the CI repair

This receipt records the normal merge of exact explicitly reviewed parent
`74195403ccd18c760e3d20a18f024daab95d711a` **after** the separate human R9 repair
commit `f39edf76635e6e572aec64b6bcedc20cfed3f7eb`. It preserves both histories,
all existing runtime/artifact bytes and all prior receipt bytes. A new full
independent review of the combined final tip is required before parent push,
reply/P2 resolution or integration. Earlier parent approvals do not approve
this merge. The 685 preparation gaps, #36/M4/#108, public hover and baseline
freeze remain **UNACCEPTED**.

## Exact lineage and approval scope

- First parent: `f39edf76635e6e572aec64b6bcedc20cfed3f7eb`, whose sole parent is
  exact approved/pushed R8 `8b231d70d03e53e380f7198b4f618c0f33ec9ddf`.
- Second parent: exact reviewed `74195403ccd18c760e3d20a18f024daab95d711a`, with
  parents reviewed `6e240f4bd3189640779fd684e97072923cbfb9c8` and accepted main
  `3ebf70c3aa5a351aeec3843da14ba2aa197b469e` (the parent reports its tree is
  exactly reviewed 7c581024).
- The parent reports completed FINAL APPROVE by `m4_defaults_audit` for 741954,
  including 25 independent codec tests, metadata/naming/hooks and preservation
  of 10,429 historical files, six maps and eight artifacts. This receipt verifies
  local product/build/test identity against 6e240 rather than inferring it from
  the approval. No unreviewed later parent is imported.
- The original parent-reported hashes versus main remain historical facts:
  whole `32a0b62de9c9adf70f870997f21b0cb490d9fd03694c0f64ad05f4312769a9b5`,
  nonreceipt `6df89fe2bc3e7257f47f400c1ce380c661278b29be23ae2563785f1d651836ce`.

`normal-merge.command.json` / `.log` retain the actual `git merge --no-ff
--no-commit` invocation and its status **1**: only generated inventory provenance
conflicted. `inventory-conflict.txt`, all three `inventory-stage-*.txt` files
and `merge-conflicts.patch` preserve the failed attempt byte-exact. The official
`check_release_inventory.py --write` resolves the generated file from the
merged working tree; no manual inventory declaration/contract edit occurs.
The generation-time base is the first parent f39edf76. Contracts/classifications
and all 685 preparation gaps are unchanged. This normal conflict is not hidden
as an initially successful merge.

## Preserved current documents, source and proof

The incoming current scheduling document is retained exactly as reviewed. Its
Node captures remain partial historical 1k evidence, with the original native
artifact provenance limits. R2 receipt functionality, size-policy text and R7's
narrow verified fixture-module inventory exclusion remain exact to f39edf76.
The current CI/test repair remains exactly that committed before the sync:
only two borrowed-slice Rust assertions and the active existing automated strict
wire/golden-migration command, its workflow verifier/regressions and affected
current contracts. No future public hover API is invented.

`before-nonspec.json` binds all **2,569** existing non-spec files by Git mode and
blob, including symlinks. `before-history.json` binds all **11,039** existing
performance-history files. `incoming-history.json` binds every incoming history
file. Verification requires their exact index identities and a clean tracked
working tree, plus SHA256 equality for all **610 R1–R9 receipt files**, including
the two actual failed CI logs. The already authorized R8 correction of the R7
README is preserved exactly as it stood at 8b231; no new old-receipt edit or
blanket preservation exception occurs here. The new parent receipt is inherited
byte-exact. The R9 repair receipt is not amended during this sync.

The same **285** recorded production inputs and **15** qualified local shipping
artifacts must remain SHA256 exact. Thus the R8/R9 native/WASM/client/package/
CSP/browser-capture qualifications are reused only for unchanged relevant bytes.
There is no release/native/WASM/client producer or expensive browser rerun.
No runtime code, build setting, arena, compiler/profile/optimizer/dependency,
export, validation/tolerance, guard, public API, scheduler, hover event or size
allowance changes. ABI399/538 symbols, WASM35, GPU-v1, Scene34 and painter17
remain unchanged.

- Native SHA256:
  `0deea9029e4a328dc15aa2d86873a203f12b8911e1c89c274f14270b31a3f880`.
- Optimized shipping WASM SHA256:
  `e3ef33b58820675f4c201a2b81ad23b3665090442210aa22fcee28a269884a96`.
- Raw WASM SHA256:
  `f66281328c0ffa9a53db8ab4728ab9ed3d88f2f3ca8b58ecc6ac3db212e08231`.
- Reused actual optimized raw/Node22 gzip6 sizes: **1,926,555 / 785,546 bytes**.
  Exact approved caps **1,927,168 / 786,432 (1882/768 KiB)**; headroom **613/886**.
  No automatic additional allowance or further size experiment is authorized.

## Fresh scoped verification and reproduction

Command records retain actual argv/cwd/selected environment, timing, status and
complete raw output hashes. `checks.json` records the final results; original
failures are retained as failures. The normal merge's expected provenance
conflict is separately explained above. No diagnostic module or capture override
is used by the fresh automated wire command.

```bash
uv run python scripts/check_release_inventory.py --write
uv run python scripts/check_release_inventory.py
uv run python scripts/verify_ownership.py
uv run python scripts/gen_capability_matrix.py --check
uv run python scripts/verify_ci_workflow.py
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
node --test packages/xy-node/test/graph-session-wire.test.mjs js/test/graph-picked-golden-migration.test.mjs
uv run pytest -q tests/test_release_inventory.py tests/test_verify_ownership.py tests/test_gen_wasm_abi.py tests/test_capability_registry.py tests/test_stale_names.py
uv run python scripts/check_stale_names.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The fresh metadata suite includes all 149 naming regressions and the seven
external-module boundary cases. Fresh exact automated shipping wire/migration
replay proves the newly required active entry after the merge. The complete R9
`make check-ci` **770-pass**, exact workspace/all-targets Clippy and **152-pass**
Rust proof are reused only after their relevant CI/test/source/toolchain inputs
are verified unchanged. The verifier and mandatory hooks/Ruff run fresh here.
The new raw command records are authoritative for executed counts; no new
remote CI run, full browser acceptance or review approval is claimed.

Both original failed CI job logs remain in the earlier immutable R9 receipt:
Test job126436313771's two Clippy lints and Release surfaces job126439951835's
`test=failure, wheels=skipped` cascade. Aggregate/wheels/upload guards are exact;
they are not weakened in response to that cascade. Parent retains GitHub thread
resolution, push/PR/queue actions and new independent full combined-tip review.

Final commit parents, clean status and whole/nonreceipt binary/full-index diff
SHA256 versus 741954 and 8b231 are handed back outside the commit to avoid a
self-referential whole-diff hash. Source patches and protected-identity results
inside this receipt make the current scoped diff reviewable. No TASKS, root,
GitHub, child PR/push or history-rewrite action occurs.
