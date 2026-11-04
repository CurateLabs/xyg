# Property-default repository metadata repair

This append-only continuation repairs two repository gates found by the parent
on exact source `81c9f7f170f448e7b8b98e2bd1cd613ee56f38f1`. The existing
[shipping qualification](../graph-property-default-package-2026-11-03/README.md)
is retained by complete source and artifact identity proof. Passing that
shipping qualification did not establish that these repository metadata gates
passed. No production source, build input, package limit or artifact changed in
this continuation, and no production build or browser suite was rerun.

## Before failures and bounded repair

The new `before-ownership.command.json` and `before-inventory.command.json`
record the original argv, environment, times, raw log hashes and **exit 1** on
exact `81c9f7f1`, before merging or editing metadata:

- `uv run python scripts/verify_ownership.py`: unclassified production source
  `crates/xyg-engine/src/graph_style/property.rs`; add one explicit machine
  ownership entry and its human ledger row.
- `uv run python scripts/check_release_inventory.py`: API contract drift in
  `cAbi, definitions`; review and regenerate the preparation inventory.

A normal `--no-ff --no-commit` merge of reviewed parent
`8a5922af4b33bfd67f2aefe71f613847d6fdcb08` produced merge commit
`d9141fbb5d80a52046dff005d16768b2e751f668`. All three mandatory full-worktree
checks passed before committing (`merge-hooks`, `merge-ruff-check`,
`merge-ruff-format`). There were no merge conflicts. The merged S6 roadmap
retains #1087's actual landing at f156569f. ABI 399, generated declarations,
property helper ABI 399, the reviewed CSS and 1,878/765-KiB gates stay exact.
`parent-review.json` verifies both supplied increment hashes and records the
parent-reported completed `s5a_final_review` approval of 8a. This is not approval
of the new integrated diff.

The ownership repair adds exactly one `rust-engine`, `Rust safe engine`,
`keep-rust` entry and the corresponding human row. It uses the existing
parity-policy rationale, with no ignored path or blanket exception. Ownership
now classifies **505 tracked production files**.

`inventory-delta.json` records the reviewed semantic change before official
`--write` regeneration:

- C ABI **398 → 399**, **537 → 538 symbols**, adding only
  `size_t xyg_graph_semantic_chrome_rgba8(uint8_t theme, uint8_t * out, size_t out_cap)`
  and updating the native signature/manifest digests.
- Definitions for generated Node `ABI_VERSION` and the referenced
  `assertAbiVersion` default change **398 → 399**. No other semantic contract
  section changes; the remaining snapshot differences are generation-time
  provenance/source hashes.
- The actual generator reports **685 explicit review gaps**, with no added or
  removed gap, export classification change, or stability promise. The
  snapshot remains `preparation-only-not-a-freeze`; baseline freeze is
  unaccepted. A successful default check does not accept #108.

The current inventory guide records this update. Earlier 99-case prose,
its separately appended 101-case erratum, and all preceding failed package
receipts remain unchanged.

## Nine current checks

Each command has an exact `.command.json` record and a losslessly compressed
raw `.log.gz`. `checks.json` verifies all nine exits are zero:

| Record | Command | Result |
| --- | --- | --- |
| inventory-write | `uv run python scripts/check_release_inventory.py --write` | PASS; 685 explicit gaps |
| inventory-check | `uv run python scripts/check_release_inventory.py` | PASS; preparation only |
| ownership | `uv run python scripts/verify_ownership.py` | PASS; 505 files |
| native-declarations | `uv run python scripts/gen_abi_manifest.py --check` | PASS; 538 symbols, ABI 399 |
| wasm-declarations | `uv run python scripts/gen_wasm_abi.py --check` | PASS; unchanged |
| typecheck | `uv run ty check python` | PASS |
| final-hooks | `uv run --with pre-commit pre-commit run --all-files` | PASS |
| final-ruff-check | `uv run ruff check .` | PASS |
| final-ruff-format | `uv run ruff format --check .` | PASS |

These are the named repository metadata checks, not a claim that every
repository acceptance gate or release prerequisite is complete.

## Exact preservation and reused qualification

`verify-preservation.py` and `source-artifact-preservation.json` prove every
tracked nonreceipt path from qualified 81 is unchanged except the **five
explicit metadata paths** listed in the report: S6 roadmap, machine/human
ownership, preparation snapshot and inventory guide. This checks **2,784
unchanged paths**, including all production/build sources, scripts, tests,
toolchain/dependency/configuration inputs and native/WASM wire declarations.
There are no new nonreceipt paths. All **699** recorded shipping build inputs
retain source SHA-256
`ab3ff61f3cd3769a89d5d1bbf31b28f99031a80e9d686a3ae93a8ee1fd134a53`.

All **15** actual artifacts match their qualified hashes, including both
manifest/worker/inline asset sets, release native and WASM targets, and ESM/IIFE
bundles. Runtime arenas remain 16/384 MiB, native ABI 399/WASM 35/Scene 34/painter
17, with identical exports, imports, validation and package guards.

| Artifact | Actual bytes | SHA-256 |
| --- | ---: | --- |
| Optimized WASM | 1,922,561 | `e8011f779e70f58416a751f0067f279d1b9aa9515004c246e2f44c95af192651` |
| Shipping Node gzip6 | 783,148 | `d447f4e3f63a0b189f962d53cba34336224df6cb84e4cd5be7fa430f7366120a` |
| Native core | 6,108,248 | `e88b3f9458effea8f677d187e9e0e72fa4c3f26e43878c118aebf13494a37bad` |
| Browser ESM | 763,072 | `3b194aebda9a2d8f30e0503f01310d944efb72edcca4701777a3c211803ddf70` |
| Browser IIFE | 763,103 | `bdce4a092184e0feb745ea4ebfc57b3929b5ca795d5ec968f9a678e233efeea8` |

The unchanged 1,923,072/783,360-byte gates leave **511/212 bytes**. This does not
allow further growth. The prior failed old-gate package remains historical FAIL.

`reused-qualification.json` checks integrity of the original zero-exit command
records and raw logs. Source/artifact identity justifies reusing the actual 81
shipping proof: **13 tests, zero skips**, paired assets/manifests/inline checks,
full unfiltered strict-CSP foundation, offline inline smoke, both unchanged
Python default-property cases, **all six unmasked full-image pairs** under the
unchanged mean <3.5 / fraction-over-96 <.01 / geometry .01px thresholds, all 101
preservation requests, Python/Node byte parity (21 Python / 31 Node tests), and
86 focused package/client contracts. They were not rerun or relabeled as fresh
results of this metadata continuation.

The first new preservation audit (`preservation`, exit 1) mistakenly recompressed
with Python's zlib 1.3.2 instead of the packager's Node 22.23.4 zlib
1.3.1-e00f703. Its source and actual-artifact checks had already passed; the
compressor mismatch assertion failed. The raw failure is retained. The corrected
`preservation-shipping-gzip` audit uses the actual shipping `gzipSync` level 6
and passes, reproducing the exact qualified compressed hash and size. No shipping
artifact, compressor, budget or build flag was changed.

`historical-preservation.json` verifies all **8,501** historical receipt paths
from 81 and all **8,276** from 8a, including shared history, byte for byte against
their Git blobs. None was modified or deleted. `compression.json` binds every
new compressed log to its raw bytes; raw `.log` copies are ignored locally.

## Handoff and limits

Commands use project `uv` and the cached Node 22.23.4 path recorded in their
environment. Reproduce into a fresh receipt directory using the unchanged prior
`run.py` with `XYG_PACKAGE_RECEIPT=<new-directory>`; evidence scripts refuse to
overwrite outputs. The preservation script also needs a fresh output directory
(copy the script there before running from the repository root).

Parent **new independent final integrated review** is required before any PR,
push or integration. This implementation does not approve itself. No remote
mutation, history rewrite, PR, issue closure or publishing occurred. #935
intent/digest/safe-pair scope, #934, #36 S5b/S6/S7, M4 and #108 remain outside
this bounded metadata repair; there is no API freeze, performance win, broad
acceptance or publication claim.
