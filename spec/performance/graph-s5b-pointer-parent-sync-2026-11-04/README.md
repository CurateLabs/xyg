# Bounded pointer attachment: normal parent sync — 2026-11-04

This is a local **normal merge**, without rebasing or rewriting either input:

- Approved pointer candidate `b61031c3cf95da3ddb42948dda915cdddc70f2b1`.
- Approved current attachment parent `5a5da8d936112467db8e1c676c131fc67edea0c8`.

The parent reports completed new independent `s5a_final_review` approval of
both inputs, including a separate actual31-journey rerun on b610. Those are
input approvals, not review of this new merge. A **new parent independent final
sync review** remains required before integration or a separate pointer stack
branch/PR based on #1091. This work stops at a clean local merge candidate;
there is no root modification, push, PR, queue operation, issue closure or
publication. Human author: David Spencer.

Worktree `/home/ubuntu/.t3/worktrees/xyg/t3-5009d7d3`,
branch `t3/graph-pointer-selection`.

## Imported status and exact conflict resolution

The incoming parent is the normal merge of approved11e2 with property parent
`68ee59f1475068d6782790a410b7da7878e0ff39`. Its only two nonreceipt changes
relative11e2 are browser-design prose and inventory metadata. `merge-inputs.json`
verifies the supplied input whole/source binary/full-index diff hashes:

| Approved input | Base | Whole SHA256 | Nonreceipt SHA256 |
| --- | --- | --- | --- |
| b610 pointer |11e2 |`526c384fc7581c6c59dffbf99875a12742bd389af3aa92c154c97fb5693e5cc1` |`0b9bd26eb6902d796ab80f23890748392c4c23c0d749ae065153b85551dbc35f` |
|5a5 parent |68ee |`5f00c379a79c1964ac730176b0e175504080030d62d81bd9c9a30a072910d976` |`2a6229b59f989793e0a64864ae753a394f6e894715c803ceb2d55e4a953b7dba` |

The recorded `git merge --no-commit 5a5...` returns the expected exit1 for
conflicting inventory provenance/body hashes. The browser prose merges
normally. Resolution uses the official inventory generator from the retained
pointer inventory, preserving all declarations/classifications. Its only delta
from b610 is generation base b610 and the new browser-design body hash. There
are still685 explicit gaps and no accepted preparation-baseline freeze.

The browser design imports the parent distinction between **historical native
property home-view/caption/theme failures** and the subsequent **current six
unmasked image-pair passes**, while keeping broader #935 scope open. It imports
the actual #1089 main landing at
`a0636c27ec48c50eb1eafa2c99122d165d266c28`, 2026-11-04 02:22:11Z, with the
property main-sync evidence. This does not claim #1090 or #1091 has landed on
main or that fresh CI/controller acceptance exists.

The imported summary names the bounded **primary-click/keyboard/GPU/companion**
attachment. It does not restore an overspecific keyboard-only summary. Every
existing pointer/motion-path paragraph and the pointer capability matrix stays
byte-identical to b610. No other nonreceipt path changes.

## Complete preservation and actual qualified reuse

`verify-preservation.py` verifies **2797 protected tracked nonreceipt paths**
against b610 and rejects extra nonreceipt paths. Only the two declared metadata
paths may differ; it reconstructs their exact allowed resolution. This protects
all production Rust/TS/controller/codec, the canvas/ancestor motion-path guard,
Worker/GPU/build/package inputs, tests/fixtures, real31-journey harness,
negative geometry, lifecycle/traps, captured19-request bytes, public APIs,
declarations, specification policy and pointer capability matrix.

`preservation.json` verifies every historical file from both inputs against its
original Git blob and records actual SHA256 hashes:

- b610:9301 historical `spec/performance/` files.
- 5a5:9129 historical files.
- Complete union:9397 distinct historical files, including common history.

All original27 pointer evidence, motion-path before failures, current qualified
31-journey proof, old naming/CI/build failures and both parents' sync receipts
remain immutable. No missing log is reconstructed or failed result relabelled.

`source-artifact-preservation.json` verifies **all301 b610 production inputs**
and **all15 actual qualified artifacts** on disk. Both paired asset sets,
module/classic Workers, manifests/inline assets, native core and raw/optimized
WASM are byte-identical. The sync does not build or replace any asset. Node22
recompression checks the actual optimized module's gzip6 bytes without writing
or substituting a diagnostic module.

| Actual qualified artifact | Bytes | SHA256 |
| --- | ---: | --- |
| Native core |6108424 |`3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6` |
| Raw WASM target |2120259 |`3f53a4747010f6cfc9e7f308c73d35a81d68cd2f6ffecaafb1860aa3cf9053b0` |
| Optimized shipping WASM |1922723 |`6ebbdb7f7e6859ad9a08bd2c0237c62aaa6147df8c683b080959b42e7d2fb273` |
| Node22 gzip6 |783181 |`5ed44e4d8802ddcdfb48dbe0aded7206d8228e9f9970a868b2bb8aaec35e5d4a` |

The unchanged1878/765KiB gates (1923072/783360 bytes) leave349/179bytes
headroom. ABI399/WASM35/GPUv1/Scene34/painter17 and all signatures/XYGI/XYGR
remain exact. There is no compiler/profile/optimizer/dependency/export/guard,
mask/tolerance or arena change.

`reused-qualification.json` verifies **95 historical command records** and
all their existing raw stream hashes/exits:29 R2 records,47 original pointer
records and19 motion-repair records. Of the29 R2 records, exactly28 are in the
original R2 qualification manifest; the additional record captures that manifest
itself. The verification explicitly checks those28 original record/log hashes
and exits. The first preservation probe mistakenly expected28 directory records
and failed; its log remains intact. The final probe distinguishes the original
28 qualification records from the29-file directory, rather than weakening or
reclassifying any recorded result.

This is **reuse of exact qualified source, binary and runtime proof**, not fresh
Rust/JS builds, packaging or browser/native-WASM runtime runs on this metadata
sync. The unchanged b610 proof includes:

- 31 actual packaged strict-CSP browser journeys, with the original29 positive
  selection/coordinate/lifecycle cases and both trusted motion-path rejections;
  old accepted snapshots/pixels and native link defaults are preserved.
- Full unfiltered strict-CSP foundation.
- 26 wire/shipping tests, including all original13 shipping tests and new full
  native/WASM/browser XYGR replay of19 actual requests,17 SelectAts.
- 88 focused contracts, with unchanged producer/harness/input/artifact bytes.

The historical R2 production/core qualification and original28 records remain
valid historical input evidence; b610's newer pointer controller/harness and
four ESM/IIFE copies are intentionally qualified by its own later records.
This sync does not claim the R2 keyboard-only client equals the pointer client.

## Fresh sync gates and reproduction

Fresh integrated validation is limited to what the two metadata changes affect:

| Command record | Actual result |
| --- | --- |
| `preservation-final` |2797 protected paths,9397 historical files,301 inputs,15 artifacts,95 historical records and685 inventory gaps verified |
| `naming-tests` |Full imported117-test naming suite passes |
| `naming-whole-repository` |Standalone whole-repository naming audit passes |
| `metadata-tests` |61 inventory/ownership/WASM-generator tests pass |
| `capability-matrix`, `inventory-check` |Generated matrix and preparation inventory pass |
| `ownership` |508 tracked production files classified; pass |
| `native-declarations`, `wasm-declarations` |538 native symbols/ABI399 and WASM declarations pass |
| `typecheck` |`uv run ty check python` passes |
| `hooks`, `ruff-check`, `ruff-format` |Mandatory full-worktree precommit/Ruff checks pass before commit |

The new receipt is append-only. `run.py` refuses existing labels and records
actual argv, cwd, selected environment, timestamps, exit and combined/separate
raw stdout/stderr SHA256 hashes. `checks.json` seals the final source and command
records. Whole/nonreceipt binary/full-index diff digests are emitted separately
with the normal merge commit to avoid self-reference.

Reproduce from the repository root using project UV and the recorded Node22
PATH. Copy the preservation script and merge-input manifest to a fresh receipt
directory or compare unchanged existing proof files; it never overwrites
nonidentical evidence. Use fresh labels and `XYG_ATTACHMENT_RECEIPT` for command
repeats. Exact gate argv are in the command records, for example:

```bash
python3 spec/performance/graph-s5b-pointer-parent-sync-2026-11-04/verify-preservation.py
uv run pytest -q tests/test_stale_names.py
uv run python scripts/check_stale_names.py
uv run pytest -q tests/test_release_inventory.py tests/test_verify_ownership.py tests/test_gen_wasm_abi.py
uv run python scripts/gen_capability_matrix.py --check
uv run python scripts/check_release_inventory.py
uv run python scripts/verify_ownership.py
uv run python scripts/gen_abi_manifest.py --check
uv run python scripts/gen_wasm_abi.py --check
uv run ty check python
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

This is the requested final parent sync for the bounded pointer stack; unrelated
future work is not included. Parent new independent final sync review,
pre-push hooks and any separate pointer PR based on #1091 remain parent-owned.
Broader S5b/S6/S7, M4/#36/#108, exact hover/picked-target, gestures/public hosts,
release/scale/competitor acceptance and the685 inventory gaps remain open.
The SelectionTooLarge pre-execution seam and default16MiB10001-source
initialization Budget limitation remain explicit; no closure/publication follows.
