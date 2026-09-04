# M2 Stage 0 recovery contract

**Tracker:** [#862](https://github.com/CurateLabs/xyg/issues/862). Stage 0 is
the stop-the-line prerequisite for the 0.6.0 train. Its children are
[#863](https://github.com/CurateLabs/xyg/issues/863) through
[#867](https://github.com/CurateLabs/xyg/issues/867), plus the later safety
findings [#876](https://github.com/CurateLabs/xyg/issues/876) and
[#877](https://github.com/CurateLabs/xyg/issues/877). The tracker closes only
after those children close and the same product state completes the required
matrix three consecutive times.

## Recovery matrix

| Issue | Release surface | Required product contract |
| --- | --- | --- |
| #863 | wheel, sdist, no-Rust installation | `verify_wheel.py` checks the current split Figure/export modules structurally, then a freshly installed native wheel must execute public `Chart` and internal `Figure` HTML/SVG/PNG exports from an isolated interpreter whose installed distribution version matches the wheel filename. Missing methods and stale installations remain negative failures. |
| #864 | density first paint | Ordinary packed and split Python/Node payloads contain only a screen-bounded u8 grid and offset-f32 sample geometry. Canonical f64 remains host-side. The separately measured replay journey must opt in with `wasm_source=True` / `wasmSource: true`. CodSpeed reports named grid, sample, canonical-f64, other, and total byte classes. The live cross-host differential compares the complete Rust emission plan at 1M and 100M rows, and the strict-CSP direct-browser foundation queries the same plan through WASM ABI 24: fixed grid/sample ceilings, tier/pyramid/WASM decisions, and zero canonical-f64 shipment must agree without allocating a data-sized fixture. |
| #865 | Node authored Scene | Node mirrors Python's bounded ABI 323 density observation marshal. The four-tier 100/10k/100k/1M authored workload explicitly selects the direct tier with the shared density tri-state, produces byte-identical Scenes, and is consumed by Rust SVG, raster-command, and browser-painter paths before merge. |
| #866 | CodSpeed and dependency audit | Benchmarks construct and assert their routing boundary without importing movable private constants. A structural test rejects private module-constant references. Root npm dependencies are build/test-only: the production audit (`npm audit --omit=dev`) is zero, the prior high report therefore has no shipped-runtime exposure, and the generated browser client remains runtime-dependency-free. Full development audit endpoint availability does not weaken correctness, tier, payload, or buffer-shape assertions. |
| #867 | merge protection and governance | One required **Release surfaces** aggregate accepts baseline test/WASM/Python-floor jobs and, for classifier-positive changes, wheel, sdist, no-Rust, host-parity, Node authored-Scene, and browser evidence only when each succeeds. An applicable skip fails. Independent approving-review/CODEOWNER capacity is deferred to backlog #871 rather than blocking M2. Milestone mutations require recorded human approval and have no autonomous repository workflow. |
| #876 | measured 100M density journey | PR checks validate only the small-scale harness and versioned report contract. The authoritative scheduled/manual main run ingests 100M canonical f64 rows from bounded chunks or a memory map and records source admission, Rust aggregation, first-paint buffer classes, peak RSS, browser upload/first-render/refine latency, cancellation, and teardown without hosted PR CodSpeed. |
| #877 | capacity-aware raster framebuffer ABI | ABI 359 removes every capacity-blind 2-D RGB/RGBA output signature: framebuffer RGB/RGBA/data/span, mean-color, colormap/canonical, heatmap, density/linear, and in-memory/tile-store colored compose. Each receives actual capacities, computes `w*h*channels` with checked arithmetic, rejects totals above `isize::MAX`, and rejects null, zero-sized, overflowing, or short outputs before constructing any mutable slice. The already-capacity-aware fused PNG/data/span destinations also reject capacities above `isize::MAX`. Generated C, Python, and Node contracts record each byte/element unit. |

## Release-surface classifier

`scripts/classify_release_surface.py` is deliberately conservative. For pull
requests, CI feeds the base/head path diff to the classifier loaded from the
trusted base revision; if that revision predates the classifier, the complete
matrix is required. Rust,
Python, Node, browser, scripts, tests, benchmarks/CodSpeed configuration,
native and WASM ABI declarations, build hooks, package manifests, and workflow
changes require the complete release matrix.
The workflow verifier parses the classifier step's exact active Bash command
sequence and binds its unique `classify` step ID to the job output. That job
contains only the pinned checkout and classifier steps, permits no inherited
workflow, job, or step environment override, runs the trusted-base classifier
with isolated Python, and fails safe to the complete matrix when Git quotes any
unusual changed path. A comment
decoy, extra step, detached output, or PR-head copy cannot substitute for the
trusted-base `git show` before execution.
Prose-only `docs/` and non-ABI `spec/` changes may skip the expensive artifact
jobs, but the aggregate itself still runs and rejects failures. Classifier and
aggregate behavior are executable contracts in
`tests/test_release_surface_gate.py` and workflow structure is protected by
`scripts/verify_ci_workflow.py`.

## Human control boundary

Creating, renaming, closing, or deleting a milestone, or moving an issue into
or out of a milestone, requires explicit human approval recorded in an issue
or pull request. Agents and automation may draft the exact mutation but may not
execute it before that approval. The retired one-shot M2 assignment and Wave C
closure workflows are not exceptions; neither an issue-assignment nor a
milestone-closing Actions path remains. Branch protection requires only the
lean **Release surfaces** aggregate. Independent approving-review/CODEOWNER
capacity is deferred to unmilestoned backlog #871 under the scope decision
recorded in #855; it is not an M2 close requirement.

## Evidence and close

Local or feature-branch success is necessary but does not satisfy #862's close
bar. Record three consecutive complete workflow runs for the identical commit,
including SHA-keyed authored/browser artifacts, then link those runs from the
children and tracker. A skipped applicable job, changed commit, rerun with
weakened assertions, or incomplete applicable evidence resets the sequence.
