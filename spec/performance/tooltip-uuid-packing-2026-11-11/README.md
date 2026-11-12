# Bounded UUID tooltip packing

Source parent: `7100be60ab0b0218c9ad70515ef2dfc4a693be60`.

The failed public 100k notebook profile identifies semantic tooltip encoding as
a repeated Python compilation cost. Canonical UUID strings previously incurred
one hex decode, NumPy view and slice assignment each. Columns longer than 4,096
rows now decode at most 4,096 UUIDs together and assign their slots in one copy.
Mixed text remains dictionary encoded in encounter order; absent/null flags,
zero padding, signed-zero numeric bytes and the wire schema remain identical.
Short columns retain the predecessor scalar writer. The output plane still
owns the full column; this bounds packing scratch, not total process memory.

## Measured encoder scope

The committed `benchmarks/test_codspeed_tooltip_columns.py` constructs fixtures
outside measurement and uses the real split-buffer PayloadWriter. Its independent
UUID/f64 oracle checks complete metadata and column bytes after each measured
call. Existing CI's `benchmarks/test_codspeed_*.py` glob discovers these cases.
No dependency or workflow change is needed.

CodSpeed walltime, two rounds, zero warmup, same benchmark/dependencies:

| Workload | Predecessor | Final encoder |
| --- | ---: | ---: |
| 1k nodes | 2.80 ms | 2.94 ms |
| 2k edges, three UUID columns | 13.29 ms | 13.26 ms |
| 10k nodes | 26.80 ms | 18.62 ms |
| 20k edges, three UUID columns | 131.08 ms | 82.67 ms |
| 100k nodes | 272.32 ms | 187.67 ms |
| 200k edges, three UUID columns | 1.34 s | 835.96 ms |

[Final comparison](https://app.codspeed.io/CurateLabs/xyg/runs/compare/6af41a4d35e17fef3bacdcb3..6af4254f876d96fb757b859a).
CodSpeed classified the four large cases as improvements and both small cases
as unchanged. These short measurements do not establish a confidence interval,
notebook latency, frame rate, competitor lead or full-scale acceptance.

The first implementation also batched short columns. A separate sparse UUID
control (one UUID followed by dictionary strings) detected a 10-row regression,
59.10 to 66.95 microseconds. That implementation and its failed comparison remain
archived. Restoring the scalar writer for a single block yields 59.53 microseconds;
the 1k/100k sparse controls measured 2.57/264.76 ms versus 2.51/262.06 ms and were
classified unchanged. [Sparse final comparison](https://app.codspeed.io/CurateLabs/xyg/runs/compare/6af4237782059738cb64953c..6af42532f4422ded788c10f5).
All slower samples remain visible; no blanket no-regression or speed claim is made.

## Correctness and actual-host boundary

The focused Python contracts cover lists, tuples and deques across 4,096-row
boundaries, all presence states, dictionary sharing/order and an empty UUID
block. A separate unchanged Node encoder compares complete metadata and every
logical raw column byte on six large/sparse fixtures; one-bit mutations fail.
The original checked-in cross-host fixture is unchanged.

The final actual JupyterLab 4.6.5 1k+1k control passes with exact UUID selection,
GPU-mask and peer-isolation assertions and complete native/thread cleanup. It
is one functional round, without a whole-notebook speed comparison.
CodSpeed run: `6af42598f4422ded788c10fa`.

The first optimized encoder's public 100k notebook run still fails the unchanged
30-second peer deadline (peer step 153; primary alive/building at step 9).
Selection and cleanup pass. The final scalar-fallback run also fails: its peer
reaches the deadline at step 145 while the primary is alive/building at step 9;
selection and cleanup again pass. These state samples are not a throughput
comparison. Both failed runs are preserved separately in `checks.json`.
No deadline, iteration count, chunking, renderer, selection,
resource cap, Rust policy, ABI or package setting is relaxed.

## Reproduction and provenance

Use Node 22.23.4, CPython 3.12.15, explicit `PYTHONPATH` and `XYG_NATIVE_LIB`,
`TMPDIR=/var/tmp`, and the existing CodSpeed pytest integration. Create the
profile folder first. Run the committed benchmark through `codspeed run -m
walltime --base <run> --profile-folder <folder> -- uv run --no-sync pytest
--codspeed --codspeed-mode=walltime --codspeed-warmup-time=0
--codspeed-max-rounds=2 -q benchmarks/test_codspeed_tooltip_columns.py`.

Actual-host checks use the unchanged `benchmarks/bench_graph_native_notebook.mjs`
through `codspeed exec`, with the explicit installed Jupyter and Chromium paths.
Exact commands, environment, raw logs, profiles, source snapshots, public capture
files and failed results are bound by `checks.json`. Raw JIT files are preserved
locally with hashes and terminal-process checks; they are not Git artifacts.

The successor retains the 45-parent Core provenance chain, all previous receipts,
324 unchanged compiled inputs, nine runtime artifacts and six static copies.
No native/WASM/client rebuild or broad Rust/Node execution is claimed. The module
remains ABI38, 1,884,503 raw /786,337 Node22 gzip6 bytes, 95 gzip bytes below the
unchanged cap; native ABI405 has 551 declarations. This Python transport change
does not alter any of those artifacts.

Independent final-diff review, current-head hosted checks and the required merge
queue remain delivery gates. Public 100k notebook acceptance, global memory,
broader host/scale/accessibility/export/competitor proof and milestones 4–7 remain
open.
