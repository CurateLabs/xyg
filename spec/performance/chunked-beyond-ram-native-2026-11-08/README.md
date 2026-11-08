# Native chunked navigation beyond physical RAM

This bounded #110 continuation integrates reviewed root `a0a5087e` with candidate
`87ad5d73`, repairs its independent review's authored-style finding, and records
an actual materialized larger-than-RAM native Node journey. It does not complete
#110 or milestones 4–7. Independent review of this complete integration, hosted
CI and the mandatory merge queue remain outstanding.

## Product and integration

Python widget and Node live-host controls use the existing renderer, Rust paging,
canonical f64 columns and u64 source identities. Final native publication requires
the current intent and real browser paint acknowledgment. The two normal merge
conflicts preserve both attribute pin sets and advance Core source binding
discovery to the combined successor. No Rust, ABI, WASM, cap, default, timeout,
LOD or renderer policy changed here.

Refinement now retains authored constant color/size channels, symbol, opacity,
stroke, name and axes while replacing only the geometry. Private authoring
values are copied so later mutation cannot rewrite a staged frame. The prior
implementation visibly reset a red size-13 square at opacity 0.35 to defaults.
The final Python and Node assertions fail against the original implementation.
XYGC carries only x/y: unresolved per-item paint channels explicitly refuse
refinement and retain the accepted frame. They are not silently reinterpreted
against a different row population. Broader per-item channel support remains
open.

The styled public Node HTTP journey and installed wheel → JupyterLab → kernel
journey compare all decoded presentation RGBA bytes with authored full-scan
oracles. Existing data, u64 identity, pointer/keyboard/box/lasso, failure-retention,
remount and lifetime controls remain. Browser harness readiness now waits for
the final committed ranges to reach the host, the matching generation and its
actual paint ACK. Previously it could compare an earlier accepted data frame
with the final camera. Pixel and data assertions and deadlines are unchanged.

## Actual source and complete oracle

The manual fixture contains **4,500,000,000** canonical rows, x=i and
 y=(17*i)%65521. It is **72,003,345,112 bytes**, with **72,003,354,624 allocated
disk bytes**, on a machine with **33,319,313,408 physical RAM bytes**. It is fully
materialized, not sparse or compressed. Chunks contain 65,536 rows (1 MiB).
The v2 overview has 2,047 canonical first/min/max/last points. Bounded generation
and an independent scan process avoid retaining the complete source in memory.
A small fixture also matches the public Rust writer's complete bytes.

The scan verified **every detail row**, chunk extrema, metadata and overview,
and computed source SHA-256:

`d97c734e31fc8fa31d5bd543c83f52bd9dbd7b5ca6e96244c82feb1b931894a9`

All four actual browser predicates match the scan's complete u64/x/y planes,
6,606 rows per viewport. These identities exceed u32. Each actual plot image
matches its independently composed oracle over every decoded RGBA byte. The
four captures cover trusted x-axis wheel zoom, 18 trusted pans into a new chunk,
18 return pans and a resident working-set pan. The second independent native
owner remains at its original overview. There are no page errors or external
network requests. Initial overview paint reads no detail rows.

This is a functional native Node qualification. The large fixture does not
establish exact picking/selection at billion-row scale, installed Python
beyond-RAM operation, ordinary gradual overview refinement, remote sources,
browser/WASM paging, linked-filter spill, all-host export/accessibility or
latency/competitor acceptance.

## Resource and I/O scopes

The two owners explicitly request 4 MiB canonical output and 2 MiB page/cache
budgets. These preserve Rust's existing admission and 8 MiB page ceiling; example
defaults are unchanged. The retained 1 MiB-cache attempt could not keep both
chunks of a 2 MiB viewport and reread on return. It is not counted as successful
warm reuse.

A source-path-filtered `pread64` trace includes superseded reads. The successful
run issued four 1 MiB positioned detail reads in chunks 66981, 66982, 66983 and
66981: **4,194,304 bytes** in total. The warm request issued zero positioned
detail reads. Header/metadata/overview reads are additional, 3,345,112 bytes per
open. There are three opens (caller plus two independently owned hosts), and
the caller closes after construction. Zero warm detail I/O is not zero total
I/O. A successful frame's own counters cannot account for reads cached by a
superseded operation; the raw syscall trace supplies that evidence.

The fixture file had zero resident pages under Linux mincore before the traced
run, using a hint scoped to this owned file. No global cache purge occurred.
Generation peak RSS is 47,161,344 bytes; full-scan peak RSS is 48,062,464 bytes.
Node RSS snapshots reach 228,986,880 bytes. Those are different scopes: snapshots
are not a process peak, and neither includes complete browser, GPU, OS cache or
global CPU/WASM memory accounting. Diagnostic timings include instrumentation
and shared-machine effects and establish no latency SLA or performance win.

## Reproduction

Use the receipt's Node 22.23.4, native ABI405, Chromium, Playwright/Pillow/NumPy
dev dependencies and a disk-backed `TMPDIR`. The source requires at least 73 GB
free disk and is deliberately outside Git and ordinary CI. On a machine with
more RAM, choose a larger source and matching journey rather than claiming this
fixture is still larger than physical RAM.

```sh
uv run --no-sync python scripts/chunked_massive_fixture.py generate \
  --path target/source-4p5b.xygc --rows 4500000000 --chunk-rows 65536
TMPDIR=/var/tmp XYG_NATIVE_LIB=/absolute/native405.so XYG_CHROMIUM=/absolute/chrome \
  strace -f -ttt -e trace=pread64 -P "$PWD/target/source-4p5b.xygc" -s 0 -yy \
  -o target/source-reads.strace node scripts/chunked_massive_navigation.mjs \
  target/source-4p5b.xygc target/massive-browser
uv run --no-sync python scripts/chunked_massive_fixture.py verify \
  --path target/source-4p5b.xygc --requests target/massive-browser/requests.json
uv run --no-sync python scripts/verify_chunked_massive.py \
  --source target/source-4p5b.xygc --oracle target/source-4p5b.xygc.oracle.json \
  --browser target/massive-browser --trace target/source-reads.strace \
  --output target/full-validation.json
```

`verify_chunked_massive.py` checks archived scan/data/pixel/trace consistency; it
does not independently rehash the 72 GB file. The preceding full scan does that.
The promoted manual harnesses preserve the qualified draft bodies except import
paths, bounded utility metadata admission, non-overwriting fixture installation
and type/format cleanup. Original executed drafts are archived. Small generator
controls run in normal pytest; the huge workload is manual.

## Evidence and failures

`checks.json` binds fresh commands, logs, reports, native planes, PNGs, source
identity, environment and artifacts. `current-bindings.json` preserves both
parent histories. Unchanged native/WASM producers and historical qualification
remain inherited after source/digest verification, not fresh builds here.
The 72 GB source stays at the handoff's ignored local path for inspection; raw
reports and reproduction contracts are retained in this receipt.

Failed attempts remain failed: initial Python browser setup lacked Playwright;
a normalized-style revalidation rejected an already accepted style; a test
variable shadowed its paint helper; installed-server startups (including a final-candidate invocation) failed
with an empty server log before navigation; an incorrect per-frame I/O assertion ignored superseded
reads; and an early-frame readiness race failed exact data comparison. Setup
corrections and passing reruns do not establish a general reliability repair.
A separate import-profiled server control reached readiness within the unchanged
100 polling attempts in 5.36 seconds; it does not explain or erase the startup
failures.
The first final real-CRLF check exposed three newly bound Python files without
LF pins; explicit pins repair that source-evidence preservation defect.
The original candidate's full suites and older root qualification remain
receipt evidence, not current executions. Existing unrelated typing diagnostics
and earlier broad CI failures are not credited as green.

Global source/CPU/WASM/GPU budgets, defaults, gradual coarse-to-detail tiles,
paged linked filtering, massive pressure and all-host/competitor qualification
remain open. No issue, milestone, shipping or merge-queue completion follows.
