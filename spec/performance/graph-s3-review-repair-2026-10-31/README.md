# Graph S3 geometry review repair and bounded size experiments

Scope: one P2 geometry blocker from the independent `m4_s2_final_review`,
followed by the two codegen-boundary experiments permitted by the independent
coordination/update execution-plan review. This is typed Rust S3 work only.
The independent review of the final integrated S3 remains the parent's gate;
this receipt is implementation evidence, not that review. #36 and M4 remain open.

The isolated branch `t3/repair-graph-interaction-geometry` fast-forward merged
`4ff7871846a5a3634dcc53ef7a3341d96d156429` from its ancestor
`1440bec94202129eea25751c3d51ee7cd1620130`. The original full binary/full-index
S3 diff against reviewed S2 `d47968e1eb66f269ffe7c610fb282ac5da371c7b` hashes to
`4e9d48a22da7a865a2174e39aec0cbe6781da6aa4ef655434600a0c57676ca28`.
The final handoff reports the new whole-diff hashes; these cannot be embedded
in their own committed diff. There are no remote, release, PR, issue, dependency,
profile, compiler-flag, export, ABI, host, controller, browser, or gate changes.

## Geometry finding and disposition

Before repair, the unchanged parent-provided `/tmp/xyg-s3-pick-review.rs`
program, compiled against this checkout's actual engine rlib, publishes revision
2 with zero edge pieces after revision 1 had one piece. The endpoints remain
finite and membership still contains the persisted edge. Its direct
`[0, 1e155]` load likewise publishes an unpainted edge. The exact supplied
program is retained as `reviewer-repro.rs`; `reviewer-repro-before.txt.gz`
retains its output.

`regression-before-compiled.txt.gz` proves three failing new negative cases and
18 passing controls before production edits. The earlier `regression-before`
log records a test-authoring compile error (selection returns refs, not a set),
corrected before collecting the failing behavioral evidence.

The narrow owner is `graphforge/interaction/paint.rs`. It validates each
published edge's data-space delta and the same `hypot` length used by routing
before calling the shared router. That router can silently discard non-finite
arithmetic before the piece loop, so checking emitted pieces alone is
insufficient. The piece loop now returns `Invalid` for non-finite mapped
endpoints, delta, or computed length. Publication already commits its output,
camera and revision only after successful construction; that path is unchanged.
The shared routing kernel and coordination/update contracts are unchanged.

New negative controls in `interaction/tests/pick.rs`:

- A persisted edge from `(0,0)` to `(100,0)` first publishes under an identity
  camera. `scale_x=1e154`, width `1e156` then returns `Invalid`. The complete
  old publication (paint, index and membership), revision, published revision,
  camera, old-stamp usability and persisted edge pick/selection identity remain.
- A direct loaded edge `[0,1e155]` refuses squared-length overflow without
  publishing or advancing revision. Opposite finite `f64::MAX` endpoints also
  refuse routing subtraction overflow, retaining the loaded positions.
- Opposite `f64::MAX` endpoints under a `1e-308` camera make the mapped chord
  representable but overflow the router's data-space delta: `Invalid`, no
  publication and no revision advance.

Positive controls retain one edge's provenance with zero pieces for coincident
nodes, an edge fully inside markers (`[0,1]`), and a tiny occluded chord
(`[0,1e-200]`). A fully culled graph still publishes no nodes/edges/pieces.
The existing overflowed mapped-node case and all S1/S2/S3 interaction tests
remain included. No fallback chords, clamps, or admission changes were added.

The initial geometry draft also refused finite nonzero deltas whose squared
length underflowed. That extra refusal was removed to preserve the existing
valid occlusion behavior, with a positive regression before final validation.
`geometry-baseline.patch.gz` / `regression-baseline.patch.gz` and the baseline
and candidate source manifests preserve the exact earlier experimental inputs;
`geometry-fix.patch.gz`, `regression.patch.gz`, and `final-source.json` identify
the final source. This unexported typed session code is absent from the WASM
product path; the final module is rebuilt rather than assumed unchanged.

## Exactly two size candidates, neither retained

All sizes use actual Node **22.23.4**, pinned Binaryen via the unchanged
`optimizeWasm`, release fat LTO/codegen-units 1, and actual Node `gzipSync`
default level 6. Limits stay **1,548,288 raw / 641,024 gzip bytes** (1512/626 KiB).

| Input | Raw bytes | Gzip bytes | Change from baseline | Disposition |
|---|---:|---:|---|---|
| Repaired baseline | 1,548,509 | 640,755 | — | raw fails by 221; gzip headroom 269 |
| Candidate 1: `#[inline]` on `CoordinationGate::validate` | 1,548,390 | 640,709 | −119 raw / −46 gzip | rejected: still 102 raw bytes over |
| Candidate 2: reset baseline, `#[inline(never)]` on that function | 1,548,509 | 640,755 | 0 / 0 | rejected: no improvement, raw still fails |

Candidate patches alter only the annotation; every guard, guard order, and
public semantic remains. Both were reverted. `candidate1.patch.gz` and
`candidate2.patch.gz`, their source manifests, build/measurement logs and
artifact reports retain exact patches and hashes. There is no third candidate,
validation removal, speculative algorithm rewrite, gate waiver, or runtime
speed claim.

Baseline/final optimized SHA-256:
`1ba9fcc8c8bef3b2acc9b87f6b740e5c57bd4f7b8f94335da8f7f3c674f52019`.
Candidate 1 SHA-256:
`db698663bb9db02e50001af58e45c538cbdd9644c778d52ae82aebd6a3baa61a`.
Candidate 2 matches baseline. Each artifact JSON also records gzip hashes,
0 imports, the exact 60-function export set, WASM ABI 34 and Scene 34.

## Package and validation contract

Real packaging remains a failure under unchanged limits. Diagnostic optimized
modules are retained under checkout-local `target/task-tmp/*-optimized.wasm`;
they are not packaged assets. The real asset verifier fails because no paired
WASM/inline/manifest set was produced. The original strict-CSP foundation is
therefore blocked and is not claimed. Existing actual native/WASM parity runs
against a SHA-bound, explicitly diagnostic temporary copy for the test harness,
which `diagnostic_parity.py` removes in `finally`; parity does not waive packaging.
A later size/functionality decision belongs to the parent and is not approved
here. There is no new 1513-KiB limit in this change.

`results.json` indexes exact commands, exits, timings, raw-log and compressed-log
hashes, source and artifact bindings, candidate dispositions, and final proof
counts. All command output is retained, including expected failures and setup
corrections. The initial Node native run omitted the required explicit native
library path and failed; the configured rerun passes. `run.py` records the
reproduction environment: actual Node 22 binary, `$HOME/.cargo/bin`, Python 3.12
through uv, local TMPDIR, explicit `XYG_NATIVE_LIB`, offline uv, and cached
Chromium 156 at
`/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
These browser smokes are software-rendered regressions, not performance or S7
hardware evidence. Dependency setup uses existing offline caches.

The final full workspace passes 1,776 engine, 58 core, 65 WASM, and five
integration tests, including 95 graph-interaction and 13 temporal-controller
cases. Final validation covers full Rust workspace and Clippy, graph interaction and
temporal controller tests, native/WASM rebuilds, actual Node 22 packaging and
native/WASM parity, Python/Node native graph/temporal seams, semantic/cross-host
goldens, 529-symbol ABI v396 generation/parity and the ABI/render/append smokes.
Full-worktree hooks and Ruff checks run before the commit. The multi-hour Python
suite, unrelated geographic diagnostic runs, and blanket Rust formatting backlog
are outside this bounded change. Only touched production/test Rust files are
formatted. No competitive performance or new chart capability is claimed.

`history-before.json` and the final history check bind every prior receipt,
fixture and ABI manifest, including the entire original
`spec/performance/graph-s3-local-2026-10-31` directory, byte for byte unchanged.
The final source manifest binds all pre-existing S3 build inputs. Reproduce with
the argv vectors in `*.command.json` via
`uv run python spec/performance/graph-s3-review-repair-2026-10-31/run.py NAME COMMAND ...`;
use fresh names to preserve the original evidence. `measure-artifact.mjs LABEL`
writes only this new receipt and local target output, never the original receipt.
