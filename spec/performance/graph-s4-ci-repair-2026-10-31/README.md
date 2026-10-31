# S4 temporal compatibility and CI contract repair

This is a new receipt over `504479e4b59db92cc7d960fa428508c67df9b95f`.
Earlier failed, diagnostic and passing receipts remain immutable snapshots.
The seven CI failures from run 41242527710 and Greptile comment 4433335870
identified gaps beyond the earlier local review. No prior local pass substitutes
for these gates. This repair establishes no S5, #36, M4 or release acceptance.

## Standalone temporal staging

S4 charged temporal retention in every `arena_resize`, while its creation/frame
retention admission applied only alongside a GraphSession. Thus a standalone
40,000-node graph could be accepted at 16 MiB and then reject even a 56-byte
frame or a small replacement. Independent actual optimized-WASM reproduction
also found the boundary at 32,760 nodes. Small controls and 40,000 at 64 MiB
worked; rejected malformed/entity-limit replacements preserved their owner.

The narrow fix charges both retained authorities during staging only when a
GraphSession exists. Co-owned create/frame pre-admission remains unchanged.
Standalone XYTG keeps its previous entity, staging, work and output bounds;
this is not a new standalone total-residency guarantee or capacity policy.

The new real-export regression stages create, frame, malformed replacement,
another frame proving the old owner survives, then a small replacement/frame,
at 32,760 and 40,000 nodes under the default 16 MiB. The corrected before test
fails with resource status 3. After the fix, all 73 WASM unit tests and five
integration tests pass, including co-owned budget and owner-revocation cases.
The initial test-helper compilation failure (the export returns a usize address,
requiring a pointer cast) is retained separately and is not the before proof.

## Native ABI and CI metadata

The `document` to `document_bytes` parameter rename preserved binary types but
changed a named C signature. Repository policy requires a native ABI bump for
every such change; the history-aware checker correctly rejected ABI 397.
Native ABI 398 and the official four generated outputs repair this violation.
The checker and its assertions remain unchanged. The earlier binary-type-only
review did not establish compliance with this stricter named-signature rule.
WASM ABI 35, Scene 34, painter 17 and the native 537-function set are unchanged.

`refresh_fixtures.py` runs the ten existing official producers against the rebuilt
native library. It permits only top-level `abi_version` changes from 396/397 to
398 and refuses any other parsed JSON change. The resulting proof binds old,
new and unchanged-data hashes. Five previously updated fixtures and five missed
fixtures must all agree; payloads, styles and geometry are not reblessed.

The ownership audit adds the five missing S4 Rust paths using existing
`rust-c-abi`, `rust-engine` and `rust-wasm-abi` policies, with matching human
ledger rows. No policy moves into a host or generated file. Current native ABI
prose and the preparation-only API inventory are updated; no release freeze.

## Verification and reproduction

`run.py` retains actual commands, exits, raw/gzip logs, hashes and timings in
fresh names. Node 22.23.4, Rust 1.96.0 and cached Chromium 156 are selected by
the runner. Proof before commit uses exact source hashes and
`artifactCommit:null`. Required final checks include the original ABI/ownership
and ten fixture suites, actual native/WASM replay, unchanged hard package gates,
paired production assets and the original full strict-CSP foundation. No
diagnostic artifact can satisfy shipping qualification. Results are appended
after those commands complete.


## Recorded result

- Native release build and workspace Clippy pass; core 67 tests and ABI smoke
  673 checks pass. ABI history/parity, ownership 498 paths, and the 375-test
  Python contract/fixture suites pass. The native session seam also passes.
- Production build passes the unchanged 1,817 KiB raw / 742 KiB gzip6 limits:
  1,860,254 / 759,013 bytes, leaving 354 / 795 bytes. SHA256 is
  `27835ac2610b53ffb79af2a2db1510547fe8be334cad0eebf06b347986bd9099`.
  There are 65 function exports, one memory, two globals, and zero imports.
- Seven actual production Node/WASM parity and standalone regression tests
  pass with zero skips. The complete original strict-CSP foundation passes,
  retaining all six screenshots; paired assets and release inventory pass.
- Full-worktree pre-commit hooks, Ruff check and Ruff format check pass.
- The broadened full Node run is **FAIL**: 1,477 pass, six fail, ten cancelled,
  two skip. Failures are in `geo-live-hierarchy-host.test.mjs` and
  `geom.test.mjs`; causality is under independent investigation. This receipt
  does not turn that run green or establish whole-package acceptance.
- `evidence.json` binds 52 changed nonreceipt sources, 14 generated artifacts,
  environment, commands, module metadata, and 2,493 historical evidence files
  proved byte-identical to the reviewed parent. `artifactCommit:null` records
  that generation preceded the final source commit.

The failed ownership attempt used a custom rationale and placed human rows
outside the bounded ledger; matching existing policy fields and moving rows
inside the ledger fixed it without changing the verifier. The first Node
regression expected invalid-argument status 1; the public contract is 2, so only
its assertion was corrected. Both failed runs remain in the raw logs.

Independent scoped review: `m4_s3_execution_plan` approved the product fix and
independently replayed the actual shipping module; `m4_s2_final_review` approved
the ABI, fixture and ownership subset. Final combined review is pending.
