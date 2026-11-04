# Local accepted-main candidate handoff

The normal merge parents are reviewed repair `562a2adfa97a6a3b5629d9ba5f98da564ba1e2b5`
and accepted main `2fbbe5f038032841bcb095a9e101421e25771496`, in that order.
The exact resulting commit and binary/full-index patch identities are emitted
outside this receipt after committing, avoiding self-referential hashes.

Incremental existing-file changes versus `562a`:

- `spec/design/graphforge-node-scheduling.md`: current accepted-main/review/CI status and sync link only.
- `spec/releases/0.6.0-api-inventory.json`: officially regenerated `sourceProvenance.baseCommit` only.
- This new append-only sync receipt contains all other additions.

Relative to accepted main, the existing reviewed four current proof-design docs,
API inventory provenance and original/pointer-sync/repair receipts remain in the
PR. Their production and contract changes remain empty. The full changed-path
lists and whole/nonreceipt binary diff hashes are returned for both bases in the
local review bundle after the commit. The prior repair and captures are unchanged.

Fresh checks: 23 focused, 61 metadata and 149 naming tests; official inventory
and capability checks; standalone whole-repository naming audit; mandatory
all-files pre-commit, Ruff lint and Ruff format. Raw commands/results are here.
`preservation-final.stdout` binds all 361 historical files, eight runtime files,
six source maps and exact main/pointer/repair/original histories. No browser or
force proof was rerun and no native/client artifact was built. The test-only
native loader cases load temporary fixture copies and do not attest a fresh
1k producer. Main's accepted tree equals the already reviewed pointer tree.

The final new merge diff needs completed independent review before parent
pre-push hooks, push and actual production CI. Both earlier Greptile P2 threads
were resolved by parent at `562a`; no child GitHub/thread writes were made.
Two skipped reviewer checks are not passing CI. Parent owns PR1093 and further
integration. The buffer sibling can follow this exact candidate after review.

Still open: partial 1k only; no unheld initial trusted interaction or sustained
real update cadence, no larger rendered ladder/public browser scheduler or
Python notebook/widget delivery/cancellation proof, and literal async compose
wording remains unresolved. No M4/#108/performance/package acceptance follows.
