# Final Buffer codec sync with reviewed accepted-main parent

This receipt finalizes the Buffer repair without rewriting either history.
The original Buffer commit is `eb9ea4c78a5acec192cd6fd98d9edb86fa3ae48c`.
The previously staged repair merge was completed as
`a7ae010fdf5f38fca2f9b8bba8ef4070139e2b39`, with normal parents `eb9ea4c`
and independently reviewed `562a2adfa97a6a3b5629d9ba5f98da564ba1e2b5`.
The second normal merge incorporates exact reviewed parent
`7c581024f968519c074e990b4eb6a34ffe2fbd96`, whose parents are `562a2ad` and
accepted main `2fbbe5f038032841bcb095a9e101421e25771496`.
Its final commit has real parents `a7ae010f` and `7c581024`; the final commit,
exact path lists and deterministic whole/nonreceipt patch hashes are reported
after commit outside the tracked tree to avoid self-reference.

## Review, conflict resolution and current status

The parent reports that exact `7c581024` received independent FINAL APPROVE
from `m4_notebook_plan` and was pushed after fresh parent hooks/Ruff. The two
supplied patch hashes against accepted main are independently reproduced in
`reviewed-parent-context.json`. This is incoming approval, not approval of the
combined Buffer sync candidate. Parent-reported green CI for old `eb9ea4c`
does not qualify either new merge. The remote Buffer branch was reported
conflicting after its parent updated. This child makes no GitHub reads or
writes and claims no new CI, queue readiness or main landing for the candidate.

The first merge preserved its existing staged state and passed fresh checks
before commit (`first-stage.md`, `first-checks.json`, `first-*` receipts).
The second merge conflicted only in the current scheduling evidence paragraph
and inventory generation base. `final-merge-attempt.*` retains the actual exit
1, and `final-merge-conflicts.diff` preserves both conflicts before resolution.
The scheduling document retains both parent-sync and Buffer evidence scopes,
updates review/CI status using the parent's reports and points here. The
official inventory generator resolves provenance using `a7ae010f`; contracts,
classifications, 685 gaps and unaccepted preparation-only freeze stay unchanged.
No generated API declaration was hand-edited.

## Exact preservation and limited evidence reuse

`verify-finalization.py` checks each normal merge's real parent identities,
accepted main's tree equality with reviewed pointer `2568ac71`, all inherited
performance-file Git blob identities and tracked worktree equality. It freezes
all 20 intermediate receipt files by SHA-256. In the second phase it additionally
protects every first-merge receipt and all 51 tracked incoming accepted-main
sync files (the directory count verified directly from Git).
The original 361 Node proof/history files, the original Buffer receipt, raw
captures, errors, screenshots, geometry and source snapshots remain exact.

Every product/build/test file under `packages`, `crates`, `js`, `python`,
`scripts`, `tests` and `.github` remains at the Buffer implementation tip. The
three Buffer implementation/test files are byte-identical to `eb9ea4c` and are
the only differences under those roots from the reviewed parent. The audit
rechecks all six captured source maps, including preparatory snapshots, and
all eight recorded native/client runtime file identities. Native SHA-256 remains
`3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6`;
standalone client SHA-256 remains
`e8c3b4aeab6c28b80f67e35ba56003eb1a99704527f58d262acef0f876014dbf`.

The entire Node package tree is not source-identical to the historical 1k
captures: they predate the Buffer numeric-copy fix. They remain observations
at their recorded state. Reuse is limited to the exact checked producer,
scheduler/Worker/painter sources, resolved capture snapshots and artifact bytes.
The native composition producer returns ordinary Uint8Array documents; the
Buffer subclass defect has separate pure codec regressions. There is no claim
that this combined tree was executed for first-paint timing, nor a fresh
producer-loading, native-origin, rebuild or mapped-memory attestation. No
costly browser capture, force proof, native build or client build was rerun:
the merge adds documentation/provenance and immutable receipts without changing
those relevant producer/artifact identities.

## Reproduction and checks

Use Node 22.23.4 from the supplied toolchain on PATH. The copied unchanged
`capture.py` preserves separately named command/environment/exit/output records;
it refuses to overwrite any earlier command receipt. Both commit phases run
fresh 25-test pure codec, 61-test metadata and 149-test naming suites; official
inventory regeneration/check; capability check; identity audit; and mandatory
whole-worktree pre-commit, Ruff check and Ruff format check. `first-checks.json`
and `final-checks.json` collect actual outcomes; raw `first-*` and `final-*`
files remain authoritative. The expected merge conflict is a recorded command
failure resolved above, not a passing validation check.

```sh
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
uv run python spec/performance/node-buffer-codec-finalization-2026-11-04/verify-finalization.py --prior a7ae010fdf5f38fca2f9b8bba8ef4070139e2b39 --incoming 7c581024f968519c074e990b4eb6a34ffe2fbd96 --candidate HEAD
node --test packages/xy-node/test/graphforge-container.test.mjs
uv run pytest -q tests/test_release_inventory.py tests/test_verify_ownership.py tests/test_gen_wasm_abi.py
uv run pytest -q tests/test_stale_names.py
uv run python scripts/check_release_inventory.py
uv run python scripts/gen_capability_matrix.py --check
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

No push, PR, GitHub mutation, issue closure, publication or root-workspace change
was performed. The parent must obtain independent final review of this exact
combined candidate, rerun fresh pre-push checks and obtain actual new sync CI.
The remaining M4/#108, host, rendered ladder and sustained-cadence requirements
are unchanged. Full Python and repository-wide Node/browser suites and
big-endian execution were not run for this metadata/history sync.
