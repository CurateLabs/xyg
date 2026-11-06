# #36 R7: inventory P2 review disposition

**The P2 directory-name exclusion is removed. Final independent re-review of
the new source/policy candidate remains required before PR or integration.**
No Rust production, shipping artifacts, size policy, browser hover API or runtime
behavior changes. #36/M4/#108 and the 685 preparation gaps remain unaccepted;
baseline freeze remains **UNACCEPTED**.

## Review input and reproduced blocker

Parent-reported completed independent `s5a_final_review` returned
**REQUEST_CHANGES** on exact R6 commit
`01f1072985b891d75015290999381f66d901d049`, with one P2 blocker at
`scripts/check_release_inventory.py:468`. Before R7, any Rust path containing a
`tests` directory was omitted even if declared unconditionally as production.
The full reproduction creates `src/lib.rs` with `pub mod tests; pub mod live;`,
then identical environment lookups in `src/tests/mod.rs` and `src/live.rs`.
Only the live.rs lookup appeared. `reproduce-p2.py` and `p2-before.*` preserve
that actual failing assertion and complete output. `p2-after.*` proves both
production locations are now inventoried.

Prior completed review facts supplied by the parent: no other Rust/runtime/
package/capture blocker; independent 27 shipping/native-WASM/GPU/package/migration
tests pass with zero skips;22 source hashes,285 production inputs,15 artifacts,
313 historical receipt files and68 logs verified. The explicit 1882/768 policy and
613/886-byte actual headroom are accurate. R4 correctness remains applicable.
These prior facts are review evidence, not approval of the R7 repair.

Exact prior reviewed full binary/full-index diff hashes versus reviewed eb9:

- Whole: `d8a613b265350e11752a3b85d627adb31601858d6be5687806f3ae16266ba101`.
- Nonreceipt: `c626343fe2f7ce4ad8a51511a68036128b2448650b7c007127d226ab17eff746`.

R7 verifies both historical hashes, stays on the same isolated worktree/branch
and direct parent01f107, and imports no unreviewed Node/Buffer parent-sync work.
No root/push/PR/GitHub/publication or history-discard action occurs.

## Narrow repair and fail-closed boundary

The inspector reads every external Rust module irrespective of a directory
named `tests`. The only new whole-file exclusion requires the exact leading
**module-wide inner attribute `#![cfg(test)]` followed by a newline**. This is an
actual Rust conditional-compilation guard on the entire module, even if its
parent declares it unconditionally. It cannot be a later statement, outer
attribute, comment or arbitrary directory label. Missing/changed/unrecognized
prefixes scan conservatively; no filename waiver or general Rust parser is added.
Existing inline cfg(test) handling and existing binary-root policy are unchanged.

The actual corpus fixture `picked_checkpoint.rs` gains exactly that inner guard
plus one blank line. Its entire pre-existing body is byte-exact, and its parent
was already guarded by cfg(test). No production source/signature/guard, compiler,
optimizer/profile/dependency/export/arena/validator/tolerance changes.
The proposed parent-fingerprint approach mentioned during investigation was not
implemented; the self-contained Rust module guard is smaller and more direct.

Regression tests prove:

- Unconditional production `pub mod tests` and ordinary live modules retain
  identical environment lookup records, including public/unclassified status.
- An external fixture with a real leading inner cfg(test) guard is omitted.
- Removing that guard immediately restores scanning of the same file.
- Missing guards, cfg(not(test)), outer attributes, commented attributes and
  unrecognized placement all scan. Conservative over-inventory is intentional.
- The existing inline/ordinary-runtime test and actual corpus fixture remain
  valid. There is no claim of a new general Rust parser.

The normative inventory contract documents that exact boundary. Official
regeneration changes provenance/source hashes only: declarations, contracts,
classifications and685 preparation gaps are unchanged.

## Tracked ownership metadata correction

Fresh audit of the committed R6 candidate also reveals five newly tracked Rust
test files absent from the ownership ledger: picked, picked_checkpoint,
projection_probe, projection_reuse and representation. R6's pre-commit ownership
run operated on tracked files and did not see these then-untracked additions.
No old audit result is rewritten or promoted into exhaustive final proof.

R7 adds one exact JSON entry and human file-ledger row for each, using the
existing `rust-engine` policy/current owner/disposition/rationale unchanged.
No ownership exclusion, rule weakening, new policy or waiver is introduced.
`ownership-final` passes with 513 tracked files classified. The initial ownership
failure, initial metadata 225 pass / 1 failure and an intermediate ledger-format
failure (policy rationale/row placement) remain preserved. Final metadata tests
are rerun against the completed ledger. This is metadata repair, not an added
runtime product policy.

## Exact protected source/artifact scope

`verify-protected.py` / `protected-identity.*` / the JSON report bind:

- **All285 R6 production input hashes unchanged**, including actual Rust,
  browser/client/packager inputs. The external fixture is not part of that
  production list; its sole leading guard change is reported separately, with
  its old/current hash and exact-body assertion. No claim that every reviewed
  test/source file is byte-identical after this repair.
- **All15 qualified artifacts unchanged**, including the native core, raw WASM,
  paired optimized modules, clients, Workers, inline bootstraps and manifests.
- Native `0deea9029e4a328dc15aa2d86873a203f12b8911e1c89c274f14270b31a3f880`;
  optimized shipping WASM
  `e3ef33b58820675f4c201a2b81ad23b3665090442210aa22fcee28a269884a96`.
- **All R1–R6 receipt bytes remain exact**, including the actual fresh browser
  capture, frozen 756,232-byte R2 transcript, 9-case full replay corpus, rejected
  archives, failures, manifests and prior reviewed patches.

R6 qualified runtime/package/CSP/capture/native-WASM proof is reused only for
unchanged production inputs and exact artifacts. R7 has fresh inventory/test-
guard/metadata proof. No release/browser rebuild or repeated production/CSP
journey is needed; the focused Rust interaction suite verifies the guarded
fixture still compiles and executes with cfg(test).

The explicit parent functionality limits remain **1,882 KiB raw / 768 KiB gzip6 =
1,927,168 / 786,432 bytes**, actual 1,926,555 / 785,546, headroom 613/886. No additional
allowance, runtime arena change or size experiment. ABI399/538 symbols,
WASM35/GPU-v1/Scene34/painter17 remain unchanged. All historical measurements
remain historical; no failed old policy becomes a pass.

## Scoped commands, environment and preserved failures

`run.py` records actual argv/cwd/environment/timing/exit and complete combined
output SHA256 without overwriting earlier records. Node22.23.4, Rust1.96.0,
project uv/Python and all pinned build settings are unchanged. No secrets or
external mutation tools are used.

- `p2-before`: expected FAIL, production lookup under tests omitted.
- `p2-after`: PASS, both identical unguarded production modules inventoried.
- `focused-boundary-tests`: 7 passed, 19 deselected.
- `rust-interaction`: 152 passed, zero failures/ignores; frozen R2 transcript exact.
- `inventory-check`, `inventory-final-check`, capability checks and protected
  identity: PASS, 685 gaps and unchanged contract/classification records.
- `ownership-final`: PASS; initial failures retained as described above.
- Native/WASM declarations, typing, Python host audit and whole naming are
  rerun with recorded results; no runtime source translation or broad suite.
- Final full metadata regression results and mandatory all-files hooks/Ruff
  records are appended below before the human commit.

An initial local identity verifier incorrectly expected the changed test fixture
inside the285 production-input list. Its actual changed list was empty, raising
`AssertionError: []`; `initial-protected-scope-assumption.txt` retains the fact.
The corrected proof asserts all285 production inputs exact and separately checks
the test-only guard/body. No source/artifact comparison was weakened.

To reproduce the P2 against old code, run the unchanged `reproduce-p2.py` from a
fresh temporary working directory containing
`scripts/check_release_inventory.py` extracted with
`git show 01f1072985b891d75015290999381f66d901d049:scripts/check_release_inventory.py`.
Its pre-fix assertion should fail. From the current repository root the same
script passes. Other exact reproduction commands are in command records:

```
uv run pytest -q tests/test_release_inventory.py -k 'rust_runtime_switches or external_rust_modules'
uv run python scripts/check_release_inventory.py --write
uv run python scripts/check_release_inventory.py
uv run python scripts/verify_ownership.py
uv run pytest -q tests/test_release_inventory.py tests/test_verify_ownership.py tests/test_gen_wasm_abi.py tests/test_capability_registry.py tests/test_stale_names.py
env -u XYG_PICK_CORPUS cargo test -p xyg-engine graphforge::interaction --lib -- --nocapture
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Use a new output receipt/path for another run. Do not overwrite R1–R7 history.
No TASKS commit or whole-repo Rust formatting. Parent re-review of this final
source/policy candidate is required before any PR/integration. No broad public
hover, issue/milestone/release or freeze acceptance follows.


Final scoped results and handoff:

- Final metadata regressions: **226 passed**, zero failures; seven focused
  guard-boundary cases and152Rust interaction tests pass.
- Full-worktree hooks, Ruff check and Ruff format check all PASS
  (`precommit-hooks`, `precommit-ruff-check`, `precommit-ruff-format`).
- All **396** R1–R6 receipt files remain byte-exact after checks;
  all285production inputs and15qualified artifacts remain unchanged.
- Seven nonreceipt source/test/spec paths changed. Incremental nonreceipt diff
  SHA256 vs01f107: `f7a8875137ea1337093c5ce967a464b39c185e40db1d7c4386e2d7be2b251c28`.
  Cumulative nonreceipt SHA256 vseb9: `61ea77bca32e221073a2edbc2ed3b40d567bd2cc88584373074938ba4b10e0df`.
  The two exact patches and final source hashes are retained here.
- Direct parent is01f107; no unreviewed parent import or history rewrite.
  A human-authored local commit records the repair/evidence. Final commit,
  clean status and whole binary/full-index hashes against both01f107 andeb9
  are returned outside the commit to avoid self-referential receipt hashes.
- Parent **new independent re-review** remains required. No PR/push/GitHub/root
  mutation, runtime expansion, automatic allowance or broad acceptance.
