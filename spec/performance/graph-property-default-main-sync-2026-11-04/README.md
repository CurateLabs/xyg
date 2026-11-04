# Property presentation synchronization with accepted main

Normal merge of accepted main `a0636c27ec48c50eb1eafa2c99122d165d266c28`
into the isolated property branch at
`cc60fd8ca93a4afca3f7d634cba55e0086a7c06f`. The parent reports #1089 actually
merged at **2026-11-04T02:22:11Z**. Its accepted entire tree
`af749a61ebe0e82ec190e2dfc8ca8b859143724e` is byte-exact to reviewed #1089
head `46c2573c285075eeb03d651966b511c866bd2ffb`, verified against local Git
objects. The actual merge time is recorded from the parent report, not inferred
from the earlier Git commit timestamp.

The parent root branch/worktree is not switched or modified. Controller and
pointer work are not imported. No remote action, push, PR update, queue action,
reset, rebase, history rewrite or issue closure is performed.

## Reviewed input and merge resolution

The parent reports final independent `m4_defaults_audit` approval of cc60.
`parent-identities.json` verifies the approved whole binary/full-index PR digest
against 46c2573c:
`1e5f1b1d5a06f62a06e43248804a2f652fad80ce940251c745bb9062133d72a2`,
and its nonreceipt digest:
`420dd8a56359fd83f47a864995571c1fc583c39ba2dfb1c017a2437dbdea216d`.
The 20 applicable cc60 CI checks were green on the former feature base. They
are historical checks; no fresh main-target CI run is performed or claimed here.
The new integrated main-sync candidate needs a new independent parent review.

`git merge --no-ff --no-commit a0636c27...` returned the expected conflict exit
1, preserved in `merge-main.json` and separate compressed raw stdout/stderr.
The only conflict was preparation-inventory provenance and the recorded
browser-spec body hash. The approved property ABI399 contracts were retained
and the unchanged official inspector regenerated the snapshot. Only its base
provenance and browser-spec source hash change; **every other inventory field**
is byte/structurally equal to cc60, including all contracts/digests,
classifications, **685 actual review gaps** and preparation-only acceptance.
Baseline freeze remains unaccepted.

The current browser specification truthfully records #1089's actual main
landing and exact reviewed tree. It distinguishes the preserved historical
native-property failures in #1089's receipts from the subsequent passing
property qualification. It links this sync receipt and leaves S5b controller
acceptance planned. No unrelated roadmap progress is introduced. S6's private
transport landing and the remaining planned public S6/S7 work stay unchanged;
#1091 main acceptance is not claimed.

Only two existing nonreceipt files change from cc60:
`spec/design/browser-wasm.md` and the preparation inventory snapshot. The
property implementation, browser/helper, all tests and fixtures, and the three
corrected naming files remain exact. Older main ABI398 declarations, helper
expectations and package limits do not replace the property ABI399 candidate.

## Complete source and historical preservation

`verify-preservation.py` checks every **2,787 tracked nonreceipt path** outside
the two explicit metadata files against cc60 Git blob identities. This protects
all Rust/Python/Node/browser/Worker production, complete build/configuration/
toolchain/dependency inputs, scripts, tests, fixtures, wire declarations,
corrected naming policy and remaining specs/docs. No new nonreceipt path is
introduced. `metadata-resolution.json` binds the exact two-file metadata diff,
accepted snapshot changes and the complete **20,079-byte** property helper,
SHA-256 `7b91a3c01770205f4738ca9b64f00802245b4a196e86981c6c98a8e60b695c6f`.

All **699 shipping build inputs** retain source SHA-256
`ab3ff61f3cd3769a89d5d1bbf31b28f99031a80e9d686a3ae93a8ee1fd134a53`.
No controller code, pointer repair, new layout pass, compiler/profile/optimizer,
dependency/export/guard, CI workflow or runtime change is introduced.

All **8,832 historical receipt files** from cc60 and all **8,409** from actual
accepted main are checked byte for byte against their Git blobs, including
shared history. Every actual-main receipt was already present through reviewed
46c2573c and stays exact. This preserves initial 47d4's P2 failure, the corrected
46 receipt, actual CI failures/logs, old property/package failures, the historical
99-case wording and appended 101-case erratum, original image evidence and
qualified shipping output. `historical-preservation.json` records each parent,
actual count and bound blob-manifest digest. No historical file is edited,
deleted, renamed or relabeled as a passing result.

## Actual qualified artifacts and evidence reuse

`source-artifact-preservation.json` verifies all **15 actual existing shipping
artifacts** against the real production qualification at 81c9f7f1, preserved
through 7e99 and approved cc60. Both host-neutral/Python browser copies, workers,
manifests, inline bootstraps, release native library and unoptimized WASM release
target match their qualified hashes exactly.

| Artifact | Qualified actual bytes | SHA-256 |
| --- | ---: | --- |
| Optimized WASM | 1,922,561 | `e8011f779e70f58416a751f0067f279d1b9aa9515004c246e2f44c95af192651` |
| Shipping Node gzip6 | 783,148 | `d447f4e3f63a0b189f962d53cba34336224df6cb84e4cd5be7fa430f7366120a` |
| Native core | 6,108,248 | `e88b3f9458effea8f677d187e9e0e72fa4c3f26e43878c118aebf13494a37bad` |

Existing ESM remains
`3b194aebda9a2d8f30e0503f01310d944efb72edcca4701777a3c211803ddf70`;
IIFE remains
`bdce4a092184e0feb745ea4ebfc57b3929b5ca795d5ec968f9a678e233efeea8`.
Recompressing existing WASM bytes with the shipping Node 22.23.4 `gzipSync`
level 6 reproduces the qualified size/hash. The explicit **1,878/765-KiB**
gates remain **1,923,072 / 783,360 bytes**, leaving **511 / 212 bytes**.
ABI399/538 native symbols, WASM35/Scene34/painter17, imports/exports,
validation/guards and 16/384-MiB runtime bounds remain exact. Accepted main's
historical ABI398/1,838/751-KiB qualification does not override these separate
property functionality decisions. No further budget is authorized.

This is **reuse of actual production/browser qualification by complete source
and artifact identity**, not a fresh native/WASM build, shipping package run,
browser render, or stale-binary qualification claim. `reused-qualification.json`
verifies original zero-exit records and raw compressed log integrity for the
real producers, normal shipping packager, **13 shipping tests with zero skips**,
paired manifest/inline validation, full unfiltered strict-CSP foundation,
offline inline smoke, both default Python property cases, all **six unmasked
whole-image pairs**, all **101 preservation requests**, 21 Python / 31 Node
crosshost tests and 86 focused package/client tests. Source f64 positions,
identities, relationships, routes, arrows and legend remain unchanged. Original
mean <3.5, fraction-over-96 <.01 and geometry .01px thresholds stay exact.
No expensive production/browser rerun or performance win is claimed.

## Fresh metadata and naming checks

- Complete corrected naming suite: **117 passed**, including all 63 punctuation
  negatives and 12 complete-token positives.
- Final standalone whole-repository naming audit: PASS, including the completed
  staged receipt and all historical source manifests.
- Release-inventory, ownership and WASM-generator tests: **61 passed**.
- Ownership: PASS, **505** tracked production files classified.
- Native generated declarations: PASS, **538 symbols / ABI399**.
- WASM generated declarations: PASS, WASM35/Scene34/painter17 unchanged.
- Full Python source typing (`uv run ty check python`): PASS.
- Official preparation-inventory regeneration and default comparison: PASS,
  **685** explicit gaps, no semantic/classification/freeze acceptance change.
- Mandatory full-worktree pre-commit `--all-files`, Ruff check and Ruff format
  check: PASS before the normal merge commit.

`checks.json` binds primary validation argv, exits and raw output hashes;
`naming-integrated-final.json` records the final whole-repository audit after
receipt staging. These are scoped fresh local gates, not complete repository
acceptance or fresh main CI. Historical failing CI stays historical FAIL.

## Reproduction and handoff

The unchanged prior `graph-property-default-parent-sync-2026-11-04/run.py`
records argv, cwd, environment, times, exit and separate raw stdout/stderr,
losslessly retained as `.log.gz` with raw/gzip SHA-256. Ignored raw `.log`
copies remain local. Set `XYG_SYNC_RECEIPT=<fresh-directory>` and use a new
label to reproduce checks without overwrites. The preservation script writes
beside itself and refuses existing outputs; copy it into a fresh directory and
run from the repository root using project UV and the cached Node 22.23.4 path.

Final committed whole/nonreceipt binary/full-index hashes against actual main
and cc60 are returned separately to avoid a self-referential receipt digest.
Parent **new independent final sync review** is required before root integration,
pre-push hooks, push, dedicated main-target PR update, fresh main CI and queue
entry. Controller synchronization is separate. This implementation does not
approve itself or claim #1090/#1091 main acceptance, #935 intent/digest/safe-pair
closure, #36 S5b/S6/S7 completion, M4 or #108 acceptance, release freeze,
issue/milestone closure, publishing or publication.
