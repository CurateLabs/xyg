# Explicit S5b attachment: reviewed parent synchronization

Normal merge of parent `cc60fd8ca93a4afca3f7d634cba55e0086a7c06f`
into controller branch input `8445c238c7115c5f20e8d3541cf9b81023c47ee5`.
The initial `git merge --no-commit` exits 1 with two metadata conflicts,
retained in `merge.log`: the S5 roadmap row and inventory provenance.
The resolution combines the actual #1088 landing at 3c665807 with the
controller's explicit bounded S5b status, and regenerates the preparation
inventory. Only its generation-time `baseCommit` changes; all declarations,
source hashes, classifications, controller APIs/facts and **685 actual gaps**
are exact to approved 8445. Acceptance remains `preparation-only-not-a-freeze`.

Exactly five nonreceipt paths differ from 8445. Three are exact reviewed parent
imports: `scripts/check_stale_names.py`, `tests/test_stale_names.py`, and
`spec/design/xyg-naming.md`. The other two are the single roadmap row and
inventory provenance described above. There is no runtime, ABI, compiler,
optimizer, profile, dependency, export, guard, arena, budget, test threshold or
product-policy change. The controller remains separate from parent #1090.
The parent worktree is untouched; no remote action, push, PR, issue closure,
history rewrite or release publication is performed.

## Independent input review

Parent `/root/s5a_final_review` approved exact 8445 with no blockers after
independently rerunning all **17 actual packaged strict-CSP journeys**, without
an output-file environment. The trusted Escape/refusal/old-fact guards,
old-module fail-closed behavior, dirty sampler and context restoration passed.
Both earlier P1 findings are resolved by that approved R2 source. Parent also
reports `/root/m4_defaults_audit` approval of cc60 and final independent
`s5a_final_review` approval of its corrected naming input 46c2573c. The rejected
initial naming repair and all historical CI failures remain historical failures.

`review-inputs.json` independently verifies the supplied local commit diff
identities, including approved 8445 whole/source hashes
`cfb873e08dab9e2d5fee82d7bf402729f6140139675ce11662f7571e0e426868` /
`f257b30564957c482616850fca4a47839d0e1821cb65c1b5519398334e243df8`
against 7e99, and R2 source increment
`9e961d19c2ebba9003b63ef5267241eb40048cfdb70a6630e147e57d92b7143a`.
These are completed input reviews, not review of this new merge. Parent **new
independent final sync review** remains required before any integration or
separate stacked controller PR on #1090. No broader acceptance is inferred.

## Exact preservation and qualified reuse

`verify-preservation.py` checks **2,794** unchanged tracked nonreceipt paths
against approved 8445, the three exact parent naming imports, the exact additive
roadmap resolution, and the inventory's sole provenance change. Thus all Rust,
browser/Worker, GPU/controller/wire, fixtures/tests, native/WASM declarations,
build/package inputs, helper APIs and behavioral specifications remain intact.
The reviewed prospective Escape contract is unchanged: browser default is
canceled synchronously only after local admission using the latest accepted
Rust applicability fact. A later definitive Rust refusal preserves state and
reports error, although browser default was already canceled; no eventual
success reservation is claimed.

`historical-preservation.json` verifies **8,750** receipt files from 8445 and
**8,832** from cc60 against their original Git blobs, including overlapping
history. These are actual complete `spec/performance/` tree counts for the two
inputs, not counts of a selected historical subset. All original attachment,
R2, parent, naming-repair and failed-run evidence is unchanged.

`source-artifact-preservation.json` verifies every one of the **301 exact R2
production build inputs** and **15 actual qualified R2 artifacts** on disk.
These include native and unoptimized WASM release outputs, both shipping asset
sets, module/classic Workers, manifests and inline assets. The source-input
digest remains `55c5937f90634796d4d125a0f7531b3ca328b910d2f470e4896812c9f9f35934`.
Node 22.23.4 gzip6 recompression reproduces the immutable R2 compressed module.

| Actual qualified R2 artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Optimized WASM | 1,922,723 | `6ebbdb7f7e6859ad9a08bd2c0237c62aaa6147df8c683b080959b42e7d2fb273` |
| Shipping gzip6 | 783,181 | `5ed44e4d8802ddcdfb48dbe0aded7206d8228e9f9970a868b2bb8aaec35e5d4a` |
| Native core | 6,108,424 | `3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6` |

Unchanged raw/gzip6 limits **1,923,072 / 783,360 bytes** (1,878/765 KiB) leave
**349 / 179 bytes**. ABI399/WASM35/GPUv1/Scene34/painter17 and version1 of the
named `clear.action.u32` fact remain exact. No extra budget is authorized.

This is **exact reuse of fresh actual R2 production and browser qualification**,
not a fresh build, package run or browser rerun on this metadata-only merge.
`reused-qualification.json` verifies all **28 original recorded logs/exits**
and 25 unchanged proof inputs; only the two specified metadata files differ
among the 27 proof inputs. Preserved passing evidence includes fresh native /
WASM production compilation, the normal shipping packager and paired assets,
1,970 Rust tests, **13 shipping tests with zero skips**, 11 wire/GPU tests,
**17 actual packaged strict-CSP journeys**, exact dirty-neighbor pixel proof,
full unfiltered strict-CSP foundation, 78 contracts, canonical graph and geo
controller journeys. No masks or tolerances change. Historical failed
`contracts` and optional repository-wide `rust-fmt` probes remain failures;
their corrected/required checks are distinguished in the immutable R2 receipt.
No unrelated formatting or expensive rebuild is justified by this sync.

## Fresh integrated validation

- Full imported naming suite: **117 passed**, including the 63 punctuation
  negatives, complete-token positives and whole-repository audit.
- Standalone whole-repository naming audit, including this receipt and all
  imported historical receipts: PASS.
- Affected inventory, ownership and WASM declaration tests: **61 passed**.
- Ownership: **508** tracked production files classified, PASS.
- Native declarations: **538 symbols, ABI399**, PASS; WASM declarations: PASS.
- Python source typing (`uv run ty check python`): PASS.
- Preparation inventory regeneration and default comparison: PASS, **685 gaps**.
- Mandatory all-files pre-commit, Ruff check and Ruff format check: PASS before
  the normal merge commit.

`checks.json` binds the fresh command records, argv, selected environment,
working directory, timestamps, exits and combined raw log hashes. `run.py`
refuses overwriting existing evidence; reproduce with new labels and
`XYG_ATTACHMENT_RECEIPT=<fresh-directory>`. Copy the preservation script to a
fresh directory before reproducing because its proof files are append-only.
Run from the repository root with project UV and recorded Node 22.23.4 PATH.
The preservation script performs hash checks and recompression only. It does
not rebuild or alter qualified artifacts. Final committed binary/full-index
whole and nonreceipt hashes are returned separately to avoid self-reference.

This sync does not qualify remote CI, #1089/#1090 main landing, broader S5b,
S6/S7, hover/picked-ref projection, legacy attachment/removal, #36/M4/#108,
release freeze, performance/competitor acceptance or publication. Those scopes
remain open. The implementer stops at a clean local normal merge candidate.
