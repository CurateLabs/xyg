# Repaired P1 parent integration and package decision

Parent `3aea79dd0d58fe1f06f33e1fe3f8436a14dd9c2f` (e91 S5a bind-count repair plus private Python P0) normally merges repaired child `4270f3f6799d5600430e3251c2ade441aacf4a6a`. The sole source conflict preserves the adopted-owner selection count under the destination-world lock and passes the current document into reply serialization. Seven child Rust paths remain byte-identical; the two adapted Rust paths are wire.rs and its existing tests, retaining e91 behavior and regressions. P0 transport bytes remain unchanged.

**Combined production qualification passes.** Current explicit functionality limits are **1,838 KiB raw / 751 KiB gzip6**. Native ABI 398, WASM ABI 35, Scene 34, painter 17, all 65 function signatures, compiler/profile/optimizer/dependencies/exports/guards and 16/384-MiB runtime bounds stay unchanged. No size experiment or automatic future allowance accompanies the decision. This does not establish public host/controller/notebook, scale, issue, M4 or #108 acceptance; publishing remains pending.

## Source and integration review

Completed independent child re-reviews by `m4_notebook_plan` (selection/provenance, including actual native replay) and `s5a_final_review` (progressive/atomicity/admission) approved repaired child 4270. Both verified repair diff SHA-256 `1098cb80f5cf7ba7e4ce71a17dc55b4654a2ebd5c018f7ed5542793e7cb4b500` and cumulative child diff SHA-256 `162c464e016be16d592d21527cdc86f877550fe747034302c58c3254b7966af9`.

The four blocking findings are repaired: shared owners retain foreign derived selection while each composition publishes its complete resolvable subset; IDs and borrowed row planes use one charged descriptor pass; empty retained force states report done with zero actual ticks; first moves honor progressive one-tick seeding while preserving rollback and legacy 300-tick behavior. The child review-repair receipt retains detailed regressions.

Completed independent integrated review by `s5a_final_review` approved the 17-path nonreceipt diff SHA-256 `abaa7e2e9241837600b7b29a801433a05c41b0531ed2cd4b5079f6c36697d947`, including source, explicit package decision, artifact identities and proof. Its requested new-receipt metadata corrections are incorporated here. The same diff is recorded in `evidence.json`. `capture.py` verifies all 3,211 parent and 3,197 child historical receipt files remain unchanged, 299 pre-policy source hashes match except the explicitly changed packager, production/diagnostic module identity, paired assets, foundation PNG hashes and command logs. Only this new receipt evolves during validation.

## Measured old-gate failure and historical proposal

The real producer first failed the unchanged 1,829/747-KiB gates. Its actual optimized module measures **1,881,508 raw / 768,134 gzip6 bytes**, exceeding those old limits by **8,612 / 3,206 bytes**. The producer refused before publishing fresh dist assets; `shipping-package.command.json` and its raw compressed log remain retained. Diagnostic exact-signature/no-import validation and six existing native/WASM replay tests passed, with diagnostic-only labeling. Those results did not qualify shipping.

`package-proposal.json` is retained historical proposal-only evidence from before adoption. Compared with actual e91 production baseline 1,872,568 / 764,079, the addition is **8,940 raw / 4,055 gzip6 bytes**. This includes complete authoritative selection/provenance snapshots and opt-in initialization/continuation using the existing configured ForceState, without host identity policy or a second layout algorithm. Borrowed descriptors and two bounded sparse row passes provide exact allocation.

## Explicit parent package decision

Independent assessor `m4_defaults_audit` verified actual bytes, all 299 recorded source hashes, signatures and diagnostic/failure logs. It recommended the smallest next-KiB functionality limits, with no blocking mechanical duplication. The parent explicitly adopted **1,838 / 751 KiB (1,882,112 / 769,024 bytes)**, leaving **604 / 890 bytes** of headroom. No speculative optimization, validation removal, profile/flag/dependency/export change or runtime-capacity increase was made. The prior failed runs and historical proposal remain unchanged; future growth still fails the gates.

## Fresh production and focused proof

The real production packager subsequently exits 0 under the adopted limits. Production SHA-256 `717440524b63cf87e0127161c128c4f81efdca87e5112f9b05a42e820b456fde` equals the measured diagnostic bytes; gzip6 SHA-256 is `101e1394aff270699602a3945723971243c7bbe11e284372683b9203aa0012ae`. Paired Python/npm raw, inline and manifest assets pass. `module.json` records actual production identity and limits, not a historical artifact substitution.

| Check | Result |
|---|---:|
| Combined GraphForge engine | 219 passed |
| Core / WASM native adapters | 67 / 73 passed |
| Python ABI, private transport and nearby seams | 97 passed |
| Native ABI smoke | 673 passed |
| Workspace Clippy, private Python typecheck, generated declarations | PASS |
| Ownership inventory | 504 files classified |
| Release preparation inventory | PASS; 685 explicit gaps remain |
| Actual production replay and package contract checks | 13 passed, zero skips |
| P1 production selection/progressive/chunk/update replay | PASS |
| Paired package/Python assets | PASS |
| Full strict-CSP source-dist foundation | PASS; six PNGs, no external requests, artifactCommit null |
| Required full-worktree hooks / Ruff / format | PASS; 935 Python files formatted |

The actual native regression uses the rebuilt library SHA-256 `6df9cb7ed06048d08d59ec8c068da0e0be9b5a3eb6b10d1b86f08527a8fd2485` and proves shared-owner local projections, global outcome counts, empty completion and zero/short/exact retries. Production paired replay runs with XYG_SESSION_WASM unset. The browser JS producer source is unchanged from e91, so its bundle/worker bytes are reused; the production packager refreshes all WASM assets. The full foundation runs against these current source-dist files.

Commands, exit codes, timings and raw/gzip log hashes live in `*.command.json` and `*.txt.gz`. `combined-source-hashes.json` records pre-policy source identity and labels the then-stale shipping assets; `module.json` and `evidence.json` identify final actual production files. The environment log records Node 22.23.4, Rust 1.96.0 and Binaryen 132, with unchanged target inline-threshold 100 and no environment flag override.

Two command-input mistakes remain retained: the first Python invocation named a nonexistent transport test (exit 4, no collection); the corrected existing test_graph_session_python_transport.py invocation passed. Inventory validation initially used unsupported --check (exit 2); its corrected default check passed. Neither involved a failed product assertion or weakened validation.

The existing conservative graph resource admission still prevents the required massive-graph ladder. The independent default native-chart presentation comparisons still fail and are not repaired or qualified by this session foundation. No multi-hour full Python suite, comparative speed claim, issue closure or publication is claimed.
