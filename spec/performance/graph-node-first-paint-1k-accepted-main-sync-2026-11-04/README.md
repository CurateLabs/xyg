# Accepted-main sync of the bounded Node 1k proof

This receipt records a normal merge of accepted main
`2fbbe5f038032841bcb095a9e101421e25771496` into independently reviewed repair
`562a2adfa97a6a3b5629d9ba5f98da564ba1e2b5`. Main's tree
`3d52fdaf32b9981c9cc2db2fcb267eb63a79a279` exactly equals reviewed pointer
`2568ac711d912625d54d083e38b29d51b415ad5c`. Both histories are retained.
The sole merge conflict was the inventory generation base; `merge-conflict.diff`
and `merge-attempt.txt` retain its actual content and command outcome. The
official generator resolves it using the current reviewed repair as its base.

Only the current Node scheduling status paragraph and API inventory provenance
change outside this new receipt. Inventory contracts, classification, preparation
status, unaccepted freeze and all 685 gaps remain unchanged. Official capability
regeneration produces no changes. All 361 files in the original proof, pointer
sync and repair receipts remain byte exact, including raw timings, screenshots,
geometry, source snapshots, failed commands, old status text and manifests.

`verify_sync.py` checks the whole tracked tree against `562a`, permits only those
two existing paths and this new directory, hashes every historical proof file,
resolves all repair capture source versions and checks the eight existing runtime
files. It emits its report on stdout; `capture.py` retains separately named raw
command records without overwriting earlier evidence. `preservation.stdout` is
the complete protected file/hash and ancestry report. No production, build,
contract, ABI, test or runnable proof helper bytes change. The standalone naming
audit includes this new JSON evidence; no naming waiver is introduced.

## Prior evidence reused

The [repair README](../graph-node-first-paint-1k-review-repair-2026-11-04/README.md)
remains the current runtime reproduction entry point. Its unheld and held 1k
browser captures are reused by exact source, artifact and raw-byte identity.
No browser capture, force job, native build or client build is run for this sync.
Fresh focused tests inspect the archived results and exercise labelled test-only
ACK and loader/provenance cases; those cases are not browser/force observations.

The historical actual 1k producer selection was
`/home/ubuntu/.t3/worktrees/xyg/t3-00534fdb/target/release/libxyg_core.so`, ABI 399,
SHA256 `3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6`.
Fixture, bridge and force Worker observations and the independent runner binding
are retained unchanged. Native origin remains **unknown**, with known-parent byte
identity true. This sync rehashes the same current file; it makes no new runtime
selection observation for the graph proof and cannot establish whether an
outside-run build occurred. Focused test-only loader cases are separately exercised;
they do not reattest historical producer loading. The old conventional-path
hashes are not retroactive loader attestations.

The unheld observation retains host checkpoint arrival 360.866076 ms, browser
painted-pixel observation 884.5999999046326 ms and GPU readiness
958.6999998092651 ms. These have separate recorded clock origins and must not be
subtracted or compared as an optimization experiment. Only steps 1 and 401 were
presented, with one 524.4000000953674 ms browser interval. This is not sustained
cadence. Held inspection is separate: it deliberately holds initial ACK for
trusted pick/pan and checks the first replacement's camera reset. Scripted update
ACK regression coverage does not invent real intermediate force callbacks.

## Review and remote status

The parent reported independent approval of exact `562a` by `m4_notebook_plan`
(23 focused tests and all manifests/artifacts checked), successful parent hooks,
its push to PR #1093 and replies/resolution of both Greptile P2 threads. The
parent reported #1092 accepted at `2026-11-04T05:44:10Z` as the main commit above,
and #1093 automatically retargeted main. These remote facts are parent-provided;
this child makes no GitHub reads or writes. Local Git independently verifies the
commit/tree/ancestry identities.

The later wake reported remote `562a` conflicting with main and only CodeRabbit
SKIPPED and Macroscope SKIPPED. Those skips establish neither production CI nor
independent review. The disabled-autoreview comment is not a finding. Reviewer
settings are unchanged. This new sync candidate requires a completed independent
final review; parent then owns pre-push checks, push and actual production CI.
Prior approval does not approve this new diff. No merge-readiness claim follows.

## Reproduction and limits

From the repository root, put the documented Node 22 toolchain on PATH:

```sh
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
uv run python spec/performance/graph-node-first-paint-1k-accepted-main-sync-2026-11-04/verify_sync.py
uv run python scripts/check_release_inventory.py
uv run python scripts/gen_capability_matrix.py --check
uv run pytest -q tests/test_release_inventory.py tests/test_verify_ownership.py tests/test_gen_wasm_abi.py
uv run pytest -q tests/test_stale_names.py
uv run python scripts/check_stale_names.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Each `*.command.json` records exact argv, environment, exit and output hashes.
`focused-tests.command.json` records the exact unchanged 23-test invocation.
New command capture requires a new label/directory; do not rerun captures into
this frozen receipt. The verifier itself prints only and is safe to rerun.

Issue #35 remains partial: unheld initial trusted interaction, sustained real
progress cadence, the remaining rendered size ladder, public browser scheduler
and Python notebook/widget delivery/cancellation remain open. Literal async
`composeGraphForge` wording still needs resolution against the adopted explicit
synchronous contract. Retained opcode 15 does not provide those host schedulers.
No threshold, competitor win, scale win, #108/M4 acceptance, package qualification
or publication is established. Hardware and all production limits are unchanged.
