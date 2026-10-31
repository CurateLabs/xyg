# S4 explicit package budget and shipping-asset validation

The parent adopts an independently reviewed functionality decision after the
[S4 review repair](../graph-s4-review-repair-2026-10-31/README.md). The previous
FAIL and diagnostic receipts remain unchanged. This new receipt must establish
real production packaging, paired assets and full strict-CSP foundation before
S4 PR readiness; it does not close #36, M4, #108 or release acceptance.

## Source, review and history

Reviewed repair commit: `cf81b750b0067ee76052d655bfdf40f628743fde`.
Whole S4 binary/full-index diff versus accepted S3:
`98fc19ad34fccf66d5110d80cfa1db862d3be8b140c9153f3f1260ddd10a054d`.
Independent correctness reviewers `m4_s2_final_review` and
`m4_s3_execution_plan` approved paint/exact identities and resource/atomic-owner
behavior respectively. The former independently passed 33 wire/native/actual
optimized-WASM/guard tests; the latter reproduced Stale for pre-frame Bind and
Unbind and recovery with the same unconsumed sequence after owner disposal.
`m4_s1_size_policy_review` verified evidence and both size experiments, then
recommended the minimal functionality limits below. These reviews establish
no shipping qualification by themselves. The old repair README's reference to
eight paint sections is a prose typo: implementation and normative table define
seven; this does not modify the historical receipt.

Normal merge `1cd5d42e1677e8ca5c50d92175597140de8ed554` incorporates actual
accepted main `be7eb1d012f01c56f4317646eaf32f4164adf7e9`. Its full tree remains
exactly the reviewed repair tree `1c138405a724a5595251e2e990e33b8b74376568`.
All 12 historical conflicts retain reviewed source; accepted main's tree equals
the original S3 base. An independent history-only review verified all 5,221
index entries, unchanged whole diff and no discarded accepted work. Merge
hooks/Ruff and conflicted paths are retained here. No rebase or history rewrite.

## Deliberate functionality budget

Accepted S3 measured 1,548,390 raw / 640,709 gzip6 bytes. S4 exposes the complete
shared session layout/render/pick/state/coordination/update transaction path to
WASM, with complete resolved paint transport, exact UTF-8 identity preservation,
owner validation and conservative admission. Its net addition is 311,860 raw /
118,299 gzip bytes. This is reachable functionality, not five wrapper functions.
Deleting required exports, paint or guards would violate the accepted contract.

After correctness repairs, exactly two isolated candidates were measured:
outlining the existing candidate clone (A), and replacing UUID formatting with
a fixed lowercase hex writer (B). A saved one gzip byte and was removed. B alone
saves 73 raw / 37 gzip bytes. There is no third or combined candidate, compiler,
profile, toolchain, dependency, optimizer or export-set change. The bounded pass
is exhausted; broader reductions require separately scoped engineering.

| Limit | Previous | Adopted | Final module | Headroom |
|---|---:|---:|---:|---:|
| Raw | 1,549,312 | 1,860,608 (1,817 KiB) | 1,860,250 | 358 |
| Gzip6 | 641,024 | 759,808 (742 KiB) | 759,008 | 800 |

These are the smallest next-KiB limits for the reviewed artifact. Both remain
hard gates; later growth requires another explicit decision. Runtime arenas
remain 16 MiB browser / 384 MiB maximum. This decision promises no runtime
speed, startup improvement, scale capacity or S5–S7 delivery.

## Verification

`run.py` is copied unchanged from the repair receipt. Each command uses a fresh
name, retains actual argv/exit/timing plus raw and deterministic gzip logs, and
refuses overwrites. Actual Node 22.23.4 and cached Chromium 156 are selected by
the runner. Commands run against the source hashes captured in `evidence.json`;
uncommitted proof uses `artifactCommit: null`. Final review must include this
policy/config/spec delta and the real shipping results added below.

### Actual shipping-source results

The fresh real `npm run build:wasm` passes, compiling the current source and
running the unchanged production optimization/validation path with the newly
adopted constants. Both production dist/static locations contain the WASM,
inline copy and version/hash manifest. Paired-asset verification passes for
bytes, SHA-256, ABI/Scene/painter versions and the inline copy.

Actual Node 22 recompression must reproduce 1,860,250 raw / 759,008 gzip6 bytes,
module SHA `25ee24fdf32ee8355598cff67da44e01556d0bb2914d5cc2d4ab4a3834c1769d`
and gzip SHA `5357262c8b2999858ffbf9953a7acd6cebc97d49440abbce1781ea860a1352f9`.
These are the independently reviewed bytes, now emitted through real shipping
paths rather than diagnostic staging. Export set remains 65 functions, zero
imports, WASM ABI 35 / Scene 34 / painter manifest 17; native remains ABI 397.

The original full foundation passes against production source-dist assets,
with strict CSP, local-only requests, actual Worker lifecycle, failure/recovery,
inline-negative controls, density no-refinement checks and all six screenshots.
It is not a subset or a staged diagnostic run. `artifactCommit:null` correctly
describes uncommitted source proof; exact source and asset hashes are retained.

Twelve shipping-byte-parity and package-contract tests pass with zero skips.
The five real native/optimized-WASM replays select the production module with
`diagnosticModule:false`, covering all operations, exact UTF-8 IDs/paint and the
unchanged 16 MiB arena, temporal frames/replacement, complete 20,000 changed refs
and request caps. Packaging still rejects wrong ABI, Scene, signature, start
functions, missing inputs and forbidden classic-worker APIs. No assertion is
removed or relaxed.

Rust/product source is byte-identical to the reviewed repair; its 1,946 Rust,
Clippy, 1,006 Node (two existing skips), Python and native ABI proofs remain
bound by the immutable repair receipt. The final production module is identical
to the reviewed diagnostic module. This policy increment changes only package
limits/comments, current specifications, inventory metadata and this new
receipt. The inventory has nine digest/provenance/parameter-metadata changes;
symbol declarations and all explicit acceptance/classification gaps remain
unchanged (`inventory-delta.json`). No release freeze is claimed.
