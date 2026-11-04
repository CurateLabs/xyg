# Final candidate sync for the bounded 1k Node render proof

This receipt prepares a local reviewable merge candidate. It changes no production
behavior and reuses the previous proof's source/artifact identity only. There is
no new browser/native build, browser run, timing result or performance acceptance.
The [original handoff](../graph-node-first-paint-1k-2026-11-04/HANDOFF.md), every raw
measurement byte, and both histories remain intact. Parent owns external final
review, pre-push hooks, stacked PR creation on #1092 and all GitHub/publication work.
No push, PR, GitHub mutation or root-worktree change is part of this task.

## Exact histories and merge

- Before sync: `7195d070843d507757213e7816862072eed9f39b`, the complete bounded
  1k proof/harness/spec/evidence commit.
- Incoming reviewed/pushed parent and intended PR base:
  `2568ac711d912625d54d083e38b29d51b415ad5c` (#1092). Its parents are the old
  production base `207ebdbdaa2ec8b0360c571683eb0fa6165e02c0` and accepted main
  `d6fcacfd482d425a731c5b1ebd492e32dc8a15b4` (#1091).
- The accepted-main tree is exactly the reviewed controller tree at
  `c3013b30bf97ce63b1f381a71d4ca1be38e75427`:
  `4cde4a0ea4f24125d5c2bdafc2c1bde72cd263eb`.
- `git merge --no-commit --no-ff 2568ac711d912625d54d083e38b29d51b415ad5c`
  merged without conflicts. The final normal merge commit keeps 7195 and 2568 as
  its two parents. No reset, rebase or history discard was used.

These facts are local Git identity checks, recorded in `before-sync.json`, not
new CI observations. The parent's statement that fresh main CI was pending is
not upgraded to a passing CI claim by this receipt.

## Permitted changes and official generators

Compared with 7195, the merge takes the parent's exact
`spec/design/browser-wasm.md`, `spec/design/graph-interaction.md` and new
`graph-s5b-pointer-accepted-main-sync-2026-11-04/` receipt directory. It retains
7195's exact four proof-related specification edits and its complete existing
`graph-node-first-paint-1k-2026-11-04/` directory.

The official capability generator was rerun with `--write` and `--check`:
`spec/api/capability-matrix.md` and `docs/styling/capabilities.md` remain
byte-identical to both parents. The official API inventory inspector was rerun
with `--write` and its normal check. Compared with **both** parents, the only
changed inventory fields are `sourceProvenance` and `sourceSha256`. Against
2568, the only refreshed source hash is `spec/design/host-parity.md`; against
7195, it is that file plus the incoming `spec/design/browser-wasm.md`.
Generation-time `sourceProvenance.baseCommit` is 7195 because generation
occurred during the uncommitted merge. This is the official inspector's working-
tree provenance convention, not a claim that the incoming source was absent.

Every declaration, contract hash, classification, acceptance field and all
**685** explicit gaps are exactly unchanged. The inventory remains preparation
only, with an unaccepted freeze. No criterion is reclassified or silently closed.
`preservation.json` records the exact field/path comparisons.

Other additions are confined to this append-only sync directory: command/raw
logs, complete parent file/hash identities, the sync capture/verifier helpers,
this handoff, checks and review-diff reproduction instructions. All production,
build, contract generators, ABI declarations, tests and runtime harnesses outside
the explicitly named specification/provenance changes remain exact.

## Complete preservation and provenance

`complete-parent-file-identities.json` records mode, Git blob, SHA-256 and current
SHA-256 for all **12,713** files in 7195 and **12,708** files in 2568. It checks
the complete historical receipt union byte-for-byte, not just selected screenshots.
All **86** original proof-directory files are exact, including old raw captures,
full-source positions, painter specs/buffers, PNGs, command outputs, original
harnesses and all eight focused proof inputs.

`before-sync.json` and `preservation.json` also bind all **8** locally existing
native/generated-client runtime artifact hashes. In particular, the native
library remains the reused exact parent artifact:
`3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6`.
The final original proof's complete producer-input hashes match the current
files exactly. No Rust checkpoint implementation/import, mapper, hover contract,
force CPU control, module gate, budget, dependency, compiler, optimizer or build
profile changed. No native artifact was rebuilt or substituted.

The new verifier's initial runs exposed local helper mistakes: an incorrect
assumption about the official provenance field name, string/byte handling,
and an over-strict parent comparison that omitted the intentionally retained
7195 specification edits. Raw failures and exact initial verifier sources are
retained. The corrected verifier requires each retained spec to equal 7195 and
each incoming spec to equal 2568; it does not grant a general difference waiver.
Those helper corrections change no old evidence or production implementation.

## Validation and timing limits

Command records contain exact argv, cwd, timestamps, exit status, relevant
non-secret environment and raw stdout/stderr hashes. `checks.json` records the
completed check outcomes. The required validation is:

- Full naming suite: 149 tests, plus a separate whole-repository
  `scripts/check_stale_names.py` audit after the new JSON evidence exists.
- Affected API inventory/ownership/WASM declaration generator suite: 61 tests.
- The unchanged original eight focused proof checks, replayed against unchanged
  archived measurements. This is not a browser measurement rerun.
- Official API inventory and capability checks, ownership audit, native and WASM
  declaration generation checks.
- Full-worktree all-files pre-commit, Ruff check and Ruff format check before the
  merge commit. Parent must rerun pre-push gates before any push.

No naming waiver is added or broadened. A real auditor failure must remain an
explicit blocker unless its existing exact exception already applies. Raw
command failures, if any, are retained rather than replaced with a successful
claim. No full Python/browser suite was run or implied.

The original raw timing bases remain distinct. Node checkpoint arrival uses
host `performance.now` from `/start`; visible pixel/GPU/ACK times use page
`performance.now` from `beginGraph`; startup and pointer/pan observations use
runner time. The unchanged final unheld record has checkpoint **302.61 ms**,
visible-frame observation **887.90 ms**, GPU readiness **966.80 ms**, and only
steps **1 and 401** with one **570.00 ms** painted interval. Those are original
observations, not new measurements of this merge candidate. The held initial
trusted click/pan and replacement-camera reset remain separate inspection facts.

This is still only partial 1k evidence. Missing acceptance includes unheld initial
trusted response, sustained progressive presentations/cadence, the rest of the
rendered size ladder and public hosts, browser progressive scheduling/attachment,
and Python notebook/widget delivery plus rerender/dispose cancellation. Literal
async `composeGraphForge` issue wording still needs explicit resolution against
the adopted synchronous static/batch API and default Worker-backed live route.
There is no #35/#36/#108/M4, release, PyPI/npm or competitor-performance acceptance.

## Final review diff identities

The full final merge commit SHA and SHA-256 of four deterministic binary
full-index review diffs are returned in the final handoff message. They are
computed **after** commit, outside the tracked tree to avoid self-referential
receipt hashes. `review-diff-contract.json` records the exact commands and
bases: whole tree and non-receipt paths, each against 2568 and 7195. Non-receipt
means all paths except `spec/performance/**`; it includes every design and API
inventory change. These hashes identify the complete candidate for parent
external review, not independent review approval by this implementing agent.
