# Buffer codec merge of reviewed Node proof repair

Worktree: `/home/ubuntu/.t3/worktrees/xyg/t3-bd15da75`.
Buffer base: `eb9ea4c78a5acec192cd6fd98d9edb86fa3ae48c`.
Reviewed incoming repair: `562a2adfa97a6a3b5629d9ba5f98da564ba1e2b5`.

## Current state

The normal `--no-ff --no-commit` merge of the reviewed repair is staged without
conflicts. No sync commit has been created. The parent reports that #1092 landed
as main `2fbbe5f038032841bcb095a9e101421e25771496` with the accepted pointer tree,
and is preparing its own accepted-main sync. This child is waiting for that
candidate's independent final review before combining it into one final sync
commit. No unreviewed candidate or main commit was merged here. The incoming
repair's historical status/HANDOFF files remain immutable; the parent now reports
that `562a2ad` received independent APPROVE and was pushed.

Four current design documents qualify source reuse: the archived 1k captures
predate the Buffer codec change, so the combined Node package tree is not
source-identical. Captured clocks and measurements remain observations at their
recorded source state, never a new execution of this combined tree. Official
API inventory regeneration retains exactly the same contracts, 685 gaps and
preparation-only acceptance, updating provenance and current source hashes only.

## Protection and reuse scope

`verify-identities.py` is a read-only, task-specific identity audit.
`identity-checks.json` records exact inherited Git blob identities and current
tracked worktree equality for **10,283 preexisting performance files** from the
two tips. This includes all **86 original 1k files**, **70 original parent-sync
files**, **205 reviewed repair files** and **13 Buffer receipt files**. No
historical source, raw capture, failure, image or output artifact was changed.
The initial audit's mistaken lookup of a receipt-relative source at repository
root is retained in `failed-attempts/identity-v1.*`; the corrected audit resolves
both repository-relative and receipt-relative recorded source paths.

The codec and both affected test files are byte-identical to `eb9ea4c`. Against
the reviewed repair, these are the only three changed product/test files under
`packages`, `crates`, `js`, `python`, `scripts`, `tests` and `.github`.
The audit checks the recorded **28 unheld** and **10 held** producer/helper
source identities individually. It also verifies the same eight recorded
runtime file SHA-256 identities, including native
`3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6`
and standalone client
`e8c3b4aeab6c28b80f67e35ba56003eb1a99704527f58d262acef0f876014dbf`.
Matching bytes do not retroactively establish origin, a rebuild, or mapped-memory
identity. All capture/native origin limitations are retained.

No first-paint/force/browser proof was rerun: the incoming change is confined
to proof helpers, their receipts and current documentation/metadata. The codec
fix has its own regression proof. The native composition producer in unchanged
`graphforge.js` returns a fresh ordinary `Uint8Array` document; the defective
Buffer subclass copy is tested separately. Reused captures retain their exact
historical scope and are not claimed as timings for the combined package tree.

## Checks at this intermediate state

- Node 22 pure codec tests: **25/25 pass**, `codec-tests.tap`.
- Scoped release-inventory/ownership/WASM-declaration regression tests:
  **61 pass**, `metadata-tests.log`.
- Naming regression tests: **149 pass**, `naming-tests.log`.
- Official inventory regeneration: `inventory-write.log`.
- Identity audit: `identity-checks.json`, empty `identity-checks.stderr`.
- Official inventory and capability checks: pass (`inventory-check.log`,
  `capability-check.log`).
- Full-worktree pre-commit and both Ruff commands: pass (`hooks.log`,
  `ruff-check.log`, `ruff-format.log`).

The staged whitespace check reports two trailing-whitespace lines in the
incoming immutable `failed-attempts/native-platform-existing-package.log`.
They are preserved byte-for-byte rather than editing the historical failure.

Additional check logs in this directory record their actual command outcomes;
they do not authorize a commit while the reviewed parent sync is outstanding.
There is no new product behavior, benchmark, freeze, M4/#108, issue-closure or
publishing acceptance here. No push, PR, GitHub change or root-workspace change
was made. The parent must independently review the eventual final sync candidate.
