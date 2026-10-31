# Graph interaction S3 — local typed Rust evidence

Scope: #36 S3 only, on reviewed S2 `d47968e1eb66f269ffe7c610fb282ac5da371c7b`.
The isolated branch `t3/graph-rust-s3-interaction` advanced to S2 by an ordinary
fast-forward merge; no history rewrite, push, PR, issue, registry or release
operation was performed. Final parent review is still required. This receipt
claims neither #36 nor milestone 4 completion.

The implementation adds publication-bound picking/admission/degradation,
`CoordinationGate` shared with the temporal controller, exact-identity graph
snapshots, and atomic full document/load replacement. New engine owners are
`coordination.rs` and `graphforge/interaction/{paint,pick,coordination,update}.rs`.
The existing render/state/identity and temporal authorities remain shared.
There are no C ABI, C header, WASM export, generated manifest, host/controller,
dependency, compiler profile, package-gate or worker lifecycle changes.

## Behavior decisions

- Pick geometry resolves semantic styles/layers through `graph_style`, routes
  and clips through `edge_route`, and retains node markers, clipped shafts,
  filled heads and compound bands in the publication. Index construction reads
  only that value, including after style-only republication at the same
  revision. The composed marker's outer diameter/inset stroke is authoritative.
  Aggregate paint omits source semantic summaries and resolves a neutral
  aggregate style. Non-finite screen geometry cannot replace a valid render.
- A 200,000-node publication may exceed 131,072 indexed primitives. The 64×64
  index checks duplication before allocation, retains at most 1,048,576 grid
  entries/65,536 candidates, and records degraded mode. Nodes that cannot all
  be indexed use a bounded scan of the same publication. Degraded point picks
  admit only canonical single-piece edges; clipped remnants of loops cannot
  masquerade as single-piece routes. Degraded region edges use induced edges.
  Query work includes grid/dedup, node/polygon, membership and induced work;
  refusal never commits a truncated selection.
- Regions include node centers, boundary inclusive, with even-odd concave
  lasso fill. Exact edge regions intersect dash-aware butt-ended stroke bands
  and filled heads, including triangle-edge crossings. Point overlap order is
  nodes, heads, shafts, frame bands; later canonical draw order wins per pass.
- Graph snapshots use their own sequence. Each successful distinct local
  selection request queues a complete snapshot even when membership is
  identical; same-op retries do not queue again. Temporal no-op behavior stays
  unchanged. Full remote shape validation precedes group filtering, exact
  string identities resolve before state writes, and watermark commit follows
  successful selection. Remote apply never increments local sequences or echoes.
- Update replaces omitted collapse/budgets with create defaults and omitted
  x/y with lazy deterministic seeding. Surviving UUID pins persist unless an
  explicit pinned plane replaces them; without positions they anchor at the
  new seeded coordinates. UUID state reconciles exactly, generation changes
  drop derived keys, and same-generation keys require exact result/layer/path/
  order. Bound UUID order and persisted endpoints must match the temporal
  owner. Validation, current-state reconciliation and commit share one lock;
  the owner is never copied/unbound. Success bumps once and clears transient
  publication/layout state while preserving coordination history/delivery.

## Proof map

New source-bound cases live in `interaction/tests/pick.rs`, the admission tests
inside `interaction/pick.rs`, and the appended S3 cases in `tests/session.rs`.
They cover all six semantic marker shapes, outlines, same-revision style
refresh, parallel lanes, trim/head/loop geometry, head-pass ordering, compound
band/interior/collapse, LOD membership, all selection policies and modes,
concave lasso, exact primitive/grid/candidate/work boundaries, node-only
index overflow, dashed region gaps/thickness/triangle crossings, atomic
10,001-ref refusal and 10,000-ref success, remote malformed/group/self/stale/
unknown/exact-result/shared-UUID/generation/no-echo behavior, and update
reorder/remove/result/generation/persistence/pins/load/forest/bound-endpoint/
disposal/frame-race/revision-exhaustion/idempotency behavior. The original S1
forced-hash-collision resolver tests run unchanged; S3 remote tests additionally
prove exact-result mismatches through ApplyRemote. A bound update race test
counts the single registry access and injects a frame immediately before it.
The S1/S2 session and temporal regressions and #1078 real-worker teardown tests
remain in the validation set.

`results.json` indexes every raw gzip log, exact command, exit status and raw
SHA-256. `source.json` hashes build inputs; `artifact.json` identifies optimized
WASM bytes. Setup uses Python 3.12 through uv, Rust 1.96, actual Node 22.23.4 at
`/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin/node`,
and a checkout-local `target/task-tmp` TMPDIR. Browser smokes use the explicitly
permitted cached Chromium 156 executable at
`/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`;
these are software-rendered regression proofs, not S7 hardware/latency evidence.
Full multi-hour pytest, unrelated geo diagnostic programs, and the blanket
pre-existing Rust formatting backlog were not invoked.

The final workspace passes 1,772 engine + 58 core + 65 WASM tests and five
integration tests (91 graph-session tests total). Clippy, native/WASM build, ABI generator/parity/673
smoke, focused Python/Node, goldens, browser render/append smokes, ownership,
new-file rustfmt, hooks/Ruff and type-check logs are retained individually.
Earlier failed proof attempts are also retained: an expired-node test first
used the wrong time, then incorrectly expected no hit where a live derived
edge crossed; the corrected test verifies both omitted source membership and
the live edge's identity. The finite-coordinate test initially used a camera
that culled the point, then used an overflowing visible transform. Clippy's
unnecessary test allocation and ownership ledger setup failures were corrected.
These logs are not package or feature acceptance claims.

## Packaging blocker (unchanged limits)

The real `node js/package-wasm.mjs` fails the raw gate. The diagnostic optimized
module is 1,548,509 raw / 640,755 gzip6 bytes, SHA-256
`1ba9fcc8c8bef3b2acc9b87f6b740e5c57bd4f7b8f94335da8f7f3c674f52019`.
The unchanged gates are 1,548,288 raw / 641,024 gzip: **221 raw bytes over**,
269 gzip bytes of headroom. Relative to reviewed S2 this is +730 raw / +228 gzip.
No gate, profile, dependency or runtime validation was weakened.

`measure-artifact.mjs` reproduces the diagnostic artifact and checks its zero
imports, exact 60-function export set, WASM ABI 34 and Scene 34. The diagnostic
copy used for native/WASM parity is explicitly separate from successful
packaging and is removed afterwards. The 33 Node native/WASM parity tests do
not waive the real package failure. No published/generated artifact is committed.
A parent-owned functionality/size decision or a separately reviewed size repair
is required before packaging can pass.

Reproduce using the environment above and the exact commands in `results.json`.
For package diagnostics run `node js/build.mjs`, the recorded wasm32 release
build, `node js/package-wasm.mjs` (expected failure), then
`node spec/performance/graph-s3-local-2026-10-31/measure-artifact.mjs`.
The real asset verifier also fails because packaging stopped before producing the
WASM asset/inline/manifest set. All earlier receipts and committed fixtures remain byte unchanged.
S4 capacity/wire tests, S5 painter/controller/accessibility, S6 host delivery,
S7 massive/hardware/latency acceptance, final parent review and remote
integration remain outstanding.
