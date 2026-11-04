# Buffer codec sync with actual accepted main

This append-only receipt records a normal merge of actual accepted main
`3ebf70c3aa5a351aeec3843da14ba2aa197b469e` into independently approved Buffer
sync `6e240f4bd3189640779fd684e97072923cbfb9c8`. Local Git verifies that main's
tree `9087e452eea598c7c38976f8442b4a53c74de59d` exactly equals reviewed parent
`7c581024f968519c074e990b4eb6a34ffe2fbd96`. The new commit has real parents
`6e240f4b` and `3ebf70c3`; its final identity and deterministic binary full-index
patch hashes are returned after commit outside the tracked tree.

## Parent reports and current acceptance

The parent reports #1093 merged at `2026-11-04T06:50:51Z` as the main commit
above, independent FINAL APPROVE of exact `6e240f4b` by `m4_defaults_audit`,
its push, and complete successful applicable CI by `06:52:01Z`, including the
required Release surfaces check. That is baseline evidence for `6e240f4b`.
The parent also reports #1094 auto-retargeted to main and conflicting, and a
CodeRabbit skipped/disabled automatic-review comment with no actionable finding.
These remote facts are parent-provided: this child makes no GitHub reads or
writes, changes no reviewer settings and starts no duplicate implementation.
`before-sync.json` and `baseline-ci-update.json` retain the reports separately
from the locally checked commit/tree/parent identities.

The new accepted-main candidate requires a new completed independent final
review before parent push, fresh parent pre-push checks and actual new main-based
CI before queueing or integration. Earlier approval/green CI does not approve or
qualify this commit. No queue readiness, milestone, M4/#108 or publishing
acceptance is claimed. The separate Rust child is not imported; its subsequent
sync must await this candidate's independent final review.

## Merge resolution and preservation

`merge-attempt.*` retains the actual exit 1 and `merge-conflicts.diff` captures
the original four-document and inventory conflicts. All incoming document
versions exactly equal `7c581024`, already integrated into `6e240f4b`. The
reviewed current Buffer qualifications are retained; only the current scheduling
status gains the actual-main landing, reviewed lineage and new-review/CI boundary.
The other three design documents are restored byte-identically to `6e240f4b`.
The official API inventory generator resolves the generation base using
`6e240f4b`; contracts, classifications, all 685 gaps and the unaccepted
preparation-only freeze remain unchanged. No generated declarations are
hand-edited. Only scheduling status, official inventory provenance and this
new directory change relative to `6e240f4b`.

`verify_sync.py` verifies that whole-tree scope, the actual normal parents,
main/reviewed tree equality, all inherited performance-file Git blob identities,
tracked worktree equality and prior merge lineage. It protects every original
1k, reviewed repair, parent-sync, Buffer, intermediate and first/second merge
receipt, including raw captures, failures, screenshots, geometry, source
snapshots and historical status text. It checks the intermediate 20-file
SHA-256 manifest, all six capture source maps and all eight runtime file hashes.
Every tracked byte outside `spec/` remains at the approved original Buffer
implementation `eb9ea4c78a5acec192cd6fd98d9edb86fa3ae48c`; the exact codec and
both regression-test files remain unchanged. `preservation.stdout` records the
actual counts, identities and source/artifact findings.

## Limited reuse of earlier proof

The historical 1k captures predate the Buffer codec fix. The complete Node tree
is not source-identical to those captures, and this sync is not a new first-paint
or interaction execution of the Buffer-fixed tree. Reuse is limited to the
individually checked producer/scheduler/Worker/painter sources, resolved source
snapshots and artifact bytes. The unchanged native composition producer returns
ordinary Uint8Array documents; Buffer decoding has independent pure regressions.

Native SHA-256 remains
`3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6`;
standalone client SHA-256 remains
`e8c3b4aeab6c28b80f67e35ba56003eb1a99704527f58d262acef0f876014dbf`.
Matching file bytes does not retroactively attest native origin, rebuild
history, current producer loading or mapped-memory identity. No actual browser
capture, native build, force proof or client build was rerun: relevant inputs
and artifacts are identical. Earlier raw clocks and measurements retain their
original scope, with no new performance or scale claim.

## Checks and reproduction

Separately named command receipts contain exact argv, environment, exit status
and raw output hashes; the copied `capture.py` refuses overwrites. Fresh checks
before the human-authored commit cover 25 pure codec tests, 61 scoped metadata
tests, 149 naming regression tests, whole-worktree naming, official inventory
regeneration/check, capability and identity audits, and required full-worktree
pre-commit/Ruff. `checks.json` records actual outcomes. The recorded merge
conflict is an expected command failure resolved above, not a passing gate.

```sh
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
uv run python spec/performance/node-buffer-codec-accepted-main-sync-2026-11-04/verify_sync.py --candidate HEAD
node --test packages/xy-node/test/graphforge-container.test.mjs
uv run pytest -q tests/test_release_inventory.py tests/test_verify_ownership.py tests/test_gen_wasm_abi.py
uv run pytest -q tests/test_stale_names.py
uv run python scripts/check_stale_names.py
uv run python scripts/check_release_inventory.py
uv run python scripts/gen_capability_matrix.py --check
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

No reset, rebase, discarded history, root-workspace mutation, push, PR, GitHub
mutation, issue closure or publication occurred. Full Python and repository-wide
Node/browser suites and big-endian execution were not run for this metadata
sync. Remaining host, rendered ladder and sustained-cadence work is unchanged.
