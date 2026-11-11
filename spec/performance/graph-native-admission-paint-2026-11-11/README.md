# Native graph admission and ordinary notebook paint checkpoint

This checkpoint reduces retained graph publication and paint overhead without
changing the existing arena, force deadline, cadence, LOD, ABI or package caps.
It is **not release qualification**. The reproducible 100k notebook check still
fails the existing 30-second layout deadline, and final browser-foundation
attempts include unexplained early WebGL context losses. Milestones 4–7 and
#35/#36/#1015 remain open.

The source parent is `ad848266a6bde2971ab3d146f6c8f398e7dcc00c`.
Its completed independent replacement review applies to that parent only;
the cancelled original review supplies no approval. This continuation requires
its own final-diff review before delivery.

## Implementation

Rust reserves shaft/wing route capacity from the existing emitted-piece
contract. Straight non-loop shafts need one slot, loops need three, and curved
shafts need eight; explicit wing output adds its existing two slots. The
source-wide maximum remains conservative for mixed loops. The flat certificate
excludes loops and directed sources. Legacy C output capacities remain valid.
Retained paint reserves exactly its final piece count after grouping scratch
retires. Geometry, offsets, clipping, head and dash emission remain unchanged.

Publication admission charges owned packet bytes, the largest simultaneously
live lowering column, and metadata scratch. Focus/ring worlds retain the full
second-packet fallback. Companion labels use the already-validated source
bound `B = min(T,200L)+L`; the existing pre-clone `64B` reservation covers its
`2B` packet capacity and escaping/copy scratch across disjoint phases. No new
cardinality, camera or fixture eligibility is introduced. Shared reference and
lowercase-hex writers preserve byte output and temporary ownership.

The ordinary ChartView acknowledges a native revision after successful
presentation, rather than on an independent RAF. Unchanged computed theme and
backdrop values avoid redundant ancestor-mutation redraws. Rust's explicit
absence of head flags permits omitting an empty head-only pass. One fixed
Cartesian segment shader substitutes proven integer uniforms in the existing
shader bodies; selection remains dynamic. Unknown heads, authored dashes,
other paint modes, CSS widths and nonlinear/polar mappings retain the general
program. No additional geometry or GPU data buffers are introduced.

## Evidence boundaries

`checks.json` binds commands, logs, source inputs, captures and runtime bytes.
`current-bindings.json` preserves the complete predecessor chain. Historical
receipts remain unchanged; archived intermediate trials are not current-source
qualification.

| Check | Disposition |
| --- | --- |
| Engine library | 1,896 tests passed |
| Isolated allocation ledger | Passed, including authored 10k/100k, late refusal, retry and high-degree metadata |
| Native/WASM protocol | 80 complete adversarial replies match, with malformed refusals; both captured 100k replies match completely |
| Native ABI | 673 checks and official declaration checks passed; ABI405 / 551 symbols unchanged |
| WASM package | ABI38, 68 functions, zero imports; 1,884,503 raw / 786,335 Node22 gzip6 bytes |
| Edge rendering | 14 tests passed, including complete RGBA comparisons against the general shader |
| Native graph host framing | 50 tests passed |
| Workspace Clippy | Passed with warnings denied |
| Versioned 1k Jupyter recipe | Passed through CodSpeed; exact UUID mask, live kernel and complete captured-owner cleanup |
| Private 100k strict witness | One pass with exact row-0 mask and live primary/peer before cancellation; not reliability qualification |
| Versioned 100k Jupyter recipe | **Failed**: primary stopped at step 17 and peer at step 225 after the unchanged wall limit; exact selection and cleanup passed |
| Final full foundation | **Failed** attempts at density startup and aggregate first paint; earlier source/intermediate passes do not replace them |

The allocator's 100k requested-allocation peak is **379,244,334 bytes** under
the unchanged **402,653,184-byte** arena. That generated styled/labelled ledger
fixture emits an 84,812,232-byte reply. The separately captured notebook
replies are 84,401,072 and 84,401,016 bytes. These are distinct fixtures.
An isolated shipping-WASM replay reached **416,612,352 linear-memory bytes**;
linear memory is not the logical owner ledger or total process/RSS/GPU memory.
Global resource acceptance remains open.

The module has only **97 gzip bytes** below the unchanged 786,432-byte cap
(raw cap 1,927,168). Failed larger size trials, including rejected escaping
refactors, remain evidence of failure. No package allowance, compiler/profile,
optimizer, export or dependency change supplies the fit.

CodSpeed measured the ordinary notebook command with three identical redraws:
the earlier baseline had one 62.76-second round; the compiled dynamic-selection
client had three rounds averaging 37.81 seconds. This workload includes
Jupyter/bootstrap/layout/readback and teardown, not isolated GPU latency.
Within-run pixel comparisons passed. The baseline's single round, changing
live-layout timing and disclosed failed host runs prohibit a general latency,
reliability, massive-scale or competitor-win claim. The earlier single-redraw
comparison reported **No Change** and remains recorded.

## Reproduction

Build matching artifacts with the repository's normal native/client/WASM
producer commands. Use explicit `XYG_NATIVE_LIB`, `PYTHONPATH`, a disk-backed
`TMPDIR`, Node22 and the recorded Chromium. Do not synchronize a borrowed
environment. The relevant bounded checks are:

```bash
cargo test -p xyg-engine --lib
cargo test -p xyg-engine --test graph_session_memory -- --nocapture
cargo clippy --workspace --all-targets -- -D warnings
uv run --no-sync pytest -q tests/test_graph_edge_ends.py
node --test js/test/graph-host-transport.test.mjs
python3 scripts/abi_smoke.py
node scripts/wasm_foundation_smoke.mjs
```

The versioned native-host fixture derives force defaults from the actual
controller signature, binds the loaded native/client hashes, waits for accepted
selection state before reading a mask, and checks the kernel again afterward.
It cancels before convergence and closes captured native owners and threads.
It supports the bounded 1k/10k/100k inputs; it establishes no 1M notebook result.
Run timing through the existing CodSpeed CLI:

```bash
XYG_NOTEBOOK_SCALE=1000 codspeed exec -m walltime --warmup-time 0s --max-rounds 1 \
  --name native-notebook-scale-1k-contract -- node benchmarks/bench_graph_native_notebook.mjs
XYG_NOTEBOOK_SCALE=100000 codspeed exec -m walltime --warmup-time 0s --max-rounds 1 \
  --name native-notebook-scale-100k -- node benchmarks/bench_graph_native_notebook.mjs
```

The second command remains an acceptance gap, not an expected green gate.
Its actual application proof is JupyterLab4.6.5; larger Notebook7 and VS Code
cohorts, convergence, pointer/region and full accessibility ladders, exports,
global memory and reproducible competitor qualification remain outstanding.

## Unresolved context-loss investigation

One Python frozen-browser batch had 47 passes and one graph-GPU-unavailable
failure. An observation-only seven-freeze run then passed, observing context
loss only after explicit disposal. Later unchanged foundation attempts failed
at density startup and aggregate first paint. Isolated current and preserved
pre-shader clients both passed; no GPU-process crash was recorded. There is no
identified origin or reliability repair.

An independent read-only lifecycle audit confirms that a graph's first-paint
failure rejects initialization and disposes its session/host, cancelling host
recovery when the last client leaves. The graph contract explicitly specifies
initialization-failure cleanup and does not unambiguously guarantee recovery
before the first accepted picture. This is a recovery coverage gap, not proof
that the new segment shader caused the context loss. Density's eight attempts
can end before the existing 250ms recovery timer; neither attempts nor timer
were changed. The audit is research and supplies no final-diff approval.

All failed size, host, browser and diagnostic-setup attempts retain their
dispositions. Source-checkpoint review, current-main integration, a green
combined qualification, hosted CI and the required merge queue remain pending.
