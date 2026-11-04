# Explicit S5b attachment: accepted #1090 main synchronization

Normal merge of accepted main `7c751db1ba216005fe0f3eaf81922d44b4d01157`
into approved controller input `5a5da8d936112467db8e1c676c131fc67edea0c8`.
The initial `git merge --no-commit` exits 1 with conflicts in browser prose,
preparation-inventory provenance/digest/body hash and inventory documentation.
`merge.log` retains the actual output. Approved controller declarations,
contracts, documentation and behavior are retained rather than replaced by
main's property-only snapshot. The official inspector regenerates only
inventory `baseCommit` and the browser-spec body hash; its contract digest,
all APIs/facts, classifications and **685 actual gaps** are unchanged.
Acceptance remains `preparation-only-not-a-freeze`.

Exactly **three nonreceipt paths** differ from 5a5:
`spec/design/browser-wasm.md`, `spec/design/graph-interaction.md` and
`spec/releases/0.6.0-api-inventory.json`. Browser prose adds #1090's actual
main landing; the graph spec updates its current status and S5 roadmap row.
The bounded experimental keyboard/GPU/companion attachment remains implemented
and independently reviewed on this branch; **#1091 main acceptance and broader
S5b/S6/S7 acceptance remain open**. No runtime, test, ABI, budget, arena,
compiler/profile/optimizer/dependency/export, guard or tolerance changes.

No root-worktree change, pointer source/proof import, push, PR action, remote
query/mutation, queue action, history rewrite, issue closure or publication is
performed. The separate pointer PR #1092 and its slot/closed-root review scope
are not part of this keyboard-controller merge.

## Accepted main and independently reviewed input

The parent reports #1090 actually merged at **2026-11-04T03:26:23Z**, commit
`7c751db1ba216005fe0f3eaf81922d44b4d01157`. Its entire accepted main tree is
locally verified byte-exact to reviewed property head
`68ee59f1475068d6782790a410b7da7878e0ff39`. `review-inputs.json` records the
actual tree hash. The landing time is the parent report, not inferred from
Git commit time, and no remote query is performed here.

The parent reports NEW independent `s5a_final_review` approval of actual 5a5,
with all 20 applicable feature-base CI checks green. Its approved whole/source
binary/full-index diff identities against property 68 are locally verified:
`5f00c379a79c1964ac730176b0e175504080030d62d81bd9c9a30a072910d976` /
`2a6229b59f989793e0a64864ae753a394f6e894715c803ceb2d55e4a953b7dba`.
Full R2 at 8445 was independently approved, and all **17 actual packaged
strict-CSP journeys** were independently replayed without an output-file
environment. Those completed reviews and CI results apply to their exact
historical inputs. They do not establish review or main-target CI for this new
merge. **New independent parent final sync review remains required.**

## Complete protected-source and historical identity

`verify-preservation.py` verifies **2,796 unchanged tracked nonreceipt paths**
against approved 5a5, with no new nonreceipt path. It reconstructs exactly the
browser landing paragraph and graph current-status/roadmap updates, and allows
exactly the inventory's two provenance changes. All Rust/TS/Worker/GPU/wire,
engine Clear predicate and named fact, sampler reset across three units,
native/WASM declarations, build/package inputs, tests, fixtures, 17-journey
helpers, helper APIs and behavioral contracts remain byte-exact.
The naming checker, all 117 tests and naming policy remain exact to both inputs.

The prospective Escape contract stays unchanged: synchronous default
cancellation requires local command admission using the latest accepted Rust
applicability fact. A later definitive Rust refusal preserves the preceding
state and reports error although browser default was canceled. This fact is
not an eventual success reservation. Pointer/hover/link/temporal/update/force
scheduling, hover/picked-ref projection and legacy migration remain separate.

`historical-preservation.json` checks every **9,129** historical receipt file
from 5a5 and every **8,883** from accepted main against original Git blobs,
including overlapping history. These are complete `spec/performance/` tree
counts for both inputs. All original attachment/R2/sync receipts, parent
qualification, historical failures, logs and screenshots remain immutable.

`metadata.diff.gz` losslessly retains the complete current metadata-only
binary/full-index diff. `metadata-diff.json` records exact argv, raw/compressed
sizes and SHA-256 hashes. Compression preserves raw diff context whitespace;
no raw evidence is normalized to satisfy a whitespace probe.

## Exact reuse of actual R2 production and browser qualification

`source-artifact-preservation.json` checks all **301 protected R2 producer
inputs** and **15 actual qualified R2 artifacts** on disk. Source-input digest
remains `55c5937f90634796d4d125a0f7531b3ca328b910d2f470e4896812c9f9f35934`.
Both paired asset sets, manifests, inline assets, module/classic Workers,
native release library and unoptimized WASM release target are exact.
Node 22.23.4 gzip6 recompression reproduces the immutable R2 compressed module.

| Qualified actual R2 artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Native core | 6,108,424 | `3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6` |
| Raw WASM release target | 2,120,259 | `3f53a4747010f6cfc9e7f308c73d35a81d68cd2f6ffecaafb1860aa3cf9053b0` |
| Optimized shipping WASM | 1,922,723 | `6ebbdb7f7e6859ad9a08bd2c0237c62aaa6147df8c683b080959b42e7d2fb273` |
| Shipping gzip6 | 783,181 | `5ed44e4d8802ddcdfb48dbe0aded7206d8228e9f9970a868b2bb8aaec35e5d4a` |

Unchanged **1,878/765-KiB** shipping limits are **1,923,072 / 783,360 bytes**,
leaving **349 / 179 bytes**. The raw gate applies to the optimized shipping
module. ABI399/538 symbols, WASM35/GPUv1/Scene34/painter17 and named
`clear.action.u32` version1 remain exact. No additional budget is authorized.

This is **exact reuse of fresh actual R2 shipping/browser qualification**,
not a fresh native/WASM build, package run or browser rerun on this merge.
`reused-qualification.json` verifies all **28 original logs/exits**, with their
original pass/failure status, and the 24 unchanged proof inputs among the R2
manifest's 27. The three metadata exceptions (browser prose, roadmap and
inventory) are independently checked above. Preserved passing proof includes
actual release producers, normal shipping packager, paired assets, 1,970 Rust
tests, **13 shipping tests / zero skips**, 11 wire/GPU tests, **17 packaged
strict-CSP journeys**, trusted dialog Escape/refusal/old-fact/old-module guards,
exact dirty-neighbor pixels and context restore, full unfiltered strict-CSP
foundation, 78 contracts and canonical/geo journeys. The historical initial
contract and optional repository-wide rustfmt failures remain failures; no
old failure is retroactively qualified or replaced. No mask/tolerance changes.

## Fresh validation and reproduction

- Full naming suite: **117 passed**; standalone whole-repository audit: PASS.
- Affected inventory/ownership/WASM-generator tests: **61 passed**.
- Ownership: **508** tracked production files classified, PASS.
- Native generated declarations: **538 symbols, ABI399**, PASS; WASM: PASS.
- Full Python source typing (`uv run ty check python`): PASS.
- Official inventory regeneration/default comparison: PASS; **685 gaps**.
- Full all-files pre-commit, Ruff check and Ruff format check: PASS before the
  normal merge commit.

`checks.json` binds fresh records, exact argv, selected environment, cwd,
timestamps, exits and combined raw log hashes. The expected initial merge
conflict remains exit 1; recorded validation gates are zero. `run.py` refuses
existing labels. Reproduce from the repository root using project UV, recorded
Node 22 PATH, new labels and `XYG_ATTACHMENT_RECEIPT=<fresh-directory>`.
Copy the preservation script to a fresh receipt directory before reproducing;
its outputs are append-only. It checks hashes and recompresses existing bytes
only. Final committed whole/nonreceipt binary/full-index hashes are returned
separately to avoid a self-referential receipt digest.

Parent new final sync review, pre-push hooks, push #1091, dedicated main-target
PR body, fresh main CI and any queue action remain parent-owned. No #1091
main acceptance, broader S5b/S6/S7, #36/M4/#108 closure, release freeze,
performance or publication acceptance is claimed. Those scopes remain open.
