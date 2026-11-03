# S5a explicit functionality budget and production qualification

The parent explicitly retains the required Rust-owned GPU/result addition
and adopts the smallest next-KiB hard package limits after independent source
and measurement review. This is a package-functionality decision, not issue,
scale, milestone, #108 or publication acceptance.

## Source and independent review

Accepted main is `030c79062138bb8287df2dc93ab6fdc0ecc8747b`. The normal integration
retains reviewed S5a child `629101e0e750dadb68bab2750d4c5e87191789cd`, accepted
S4 compatibility/ABI398 repairs and Node scheduling/cache work. Independent
`s5a_final_review` approved the source/tests diff
`c418c895a45c965ccacbb0a9315842ed7caa2e240aaa8d4981e3bb6f6a77bcd0`.
The five Rust deltas equal the reviewed child; the Node replay adds only the
unchanged accepted-main standalone-temporal regression to that child.

Independent `m4_defaults_audit` inspected the implementation, fresh failed
producer, exact production-optimizer measurement, hashes and arithmetic, and
recommended these concrete limits. GPU lowering reuses published geometry and
existing offset-f32 kernels; operation/focus facts reuse authoritative state and
reducers. No duplicate layout, router, LOD or semantic resolver was found.
The duplicate mechanical 60-byte style serializer remains unchanged; no
unmeasured binary saving is assumed. Its future sharing is separate cleanup.
The GPU validator currently has inspection/test callers, not shipping upload
callers; S5b still must validate the host boundary.

## Measured decision

| Measurement | Raw bytes | Node gzip6 bytes |
|---|---:|---:|
| Accepted S4 artifact | 1,860,254 | 759,013 |
| Integrated S5a artifact | 1,872,541 | 764,063 |
| Added functionality | 12,287 | 5,050 |
| Previous hard limit | 1,860,608 | 759,808 |
| Actual old-gate excess | 11,933 | 4,255 |
| Adopted smallest next-KiB limit | 1,872,896 (1,829 KiB) | 764,928 (747 KiB) |
| Headroom | 355 | 865 |

Optimized module SHA-256:
`355a31bc7f949070251e73dbeebdd7f466d55e9a242a14f7c85bf29fdec59c50`.
Gzip6 SHA-256:
`83bc6c780620b8df57d0c5dd3ab6a3e382eaff64c3ca709252e71945f5244038`.
The [integration receipt](../graph-s5a-integration-2026-11-03/README.md) retains
the real old-gate failure and separately labelled diagnostic measurement/replay;
all old receipts remain unchanged. This decision changes only the two package
constants, their explanation and current specifications/inventory metadata.
No size experiment, compiler/profile/toolchain/optimizer/dependency/export or
validation change is included. Browser default 16 MiB and maximum 384 MiB,
native ABI398, WASM35, Scene34 and painter17 remain unchanged. Later package
growth still fails; these limits provide no automatic allowance.

## Production proof

Real `npm run build:wasm` passes under the explicit limits and emits the exact
reviewed optimized bytes into both production locations. Paired-asset
verification passes bytes, hashes, ABI/Scene/painter versions and inline copy.
Thirteen package-contract and real native/production-WASM replay tests pass,
zero skips, with `diagnosticModule: false`. Wrong ABI, Scene, u64 signature,
start function, missing producer input and forbidden classic-worker API still
reject before publication.

The original full strict-CSP local-only foundation passes against production
source-dist assets, with all six ESM/IIFE no-refinement screenshot cases and
Worker lifecycle/failure/recovery controls. `foundation.json` records
`scope: full-foundation`, `artifactCommit: null`, zero external requests and
actual source/asset hashes; no subset or diagnostic staging substitutes for it.
Final source/policy/evidence review and full-worktree checks pass; committed CI remains pending.
Diagnostic proof alone is not shipping qualification. `run.py` retains actual argv, status, timing and
raw/gzip log hashes with append-only names. Uncommitted-source artifacts must
record `artifactCommit: null`. Final integrated review must cover the actual
policy/spec/evidence diff before a PR is opened.

S5b controller/worker/retained painter/DOM/ARIA, S6 notebook attachment and S7
rendered scale/responsiveness remain outstanding. No speed, capacity, competitor
win, release freeze, registry publication or completed acceptance is claimed.

## Nearby regression and readiness evidence

Seventy-six Node graph-host/CoSE/native-WASM parity tests pass, zero skips.
The existing GraphForge browser smoke paints nine identities and 264 derived
rows, resolves an actual node pick and 16 table rows, and rejects stale source
generation. Forty-nine Python package/asset/inline contract tests pass. The
preparation API inventory changes only its base provenance and browser-spec
source hash; declarations and all 685 explicit acceptance/classification gaps
are unchanged. No release freeze is implied.

For #36, this slice supplies complete GPU paint attributes, simultaneous state
bits and authoritative operation/focused-action facts. It does not establish
public callbacks, full selection/result-row projection, notebook/VS Code
round-trips, browser keyboard/ARIA, linked-view UI, latency ladder or selected
export parity. All remain open under the original issue and M4 acceptance.
The separate #934/#935 bounded audit reports presentation parity failures;
this package proof does not waive or claim to fix those failures.

The first provenance capture incorrectly expected the classic inline-worker source
as a separate Python static file; packaging embeds it inside the inline artifact.
The corrected capture checks the dist worker source and all actual paired files.
Both capture results are retained; no production code or assertion was changed.
Full-worktree hooks, Ruff lint and Ruff format checks pass (928 Python files).
`final-checks.json` binds these checks to the nonreceipt diff.

## Final independent review

`s5a_final_review` approved the final 13-path source/spec/package/inventory diff
`d6e2af16666be21a94fa2d5acb93c9845f4a6834f33c1e41cde5ac81e242f68b`,
including real production proof, source/asset/log hashes, six screenshots,
2,831 accepted-main and 110 child historical files unchanged. No blocker remains
for this bounded slice. Subsequent status wording records approval/CI pending;
product/package implementation remains identical. `review.json` binds that
metadata finalization to its final diff. Original proof keeps artifactCommit null.
