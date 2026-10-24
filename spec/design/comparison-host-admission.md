# Comparison host entry and cold output admission

This benchmark-only contract supplements dossier §§5, 12, 17, 28–29,
[the count/grid oracle](comparison-count-oracle.md), and
[the independent report contract](density-comparison-report-contract.md).
It changes no product API, LOD policy, numerical oracle, competitor aggregation,
source generator, resource allowance, verifier or hosted authority.

The actual-main `959e1004924774711a35df7ab1317cca30b18d68` Actions run
`40075049750` remains rejected evidence. Its six XYG hosts exited before META;
four 100M/1B Bokeh cold checkpoints paired a 400×400 browser image with a
512×512 backend grid. These repairs do not retroactively admit that receipt.

## File entry is a supported boundary

The comparison runner executes `_ux_live_host.py` by absolute filename.
Python places the script directory on `sys.path`, not its checkout parent.
A package-qualified import inside sibling-loaded `_ux_comparison_host.py`
therefore failed while preparing `SourceOracle`. Adding a fallback only to
that import would leave the oracle's own package import and the HTTP POST's
`decode_attachment` import exposed to the same failure.

At direct file entry, `_ux_live_host.py` establishes its checkout root from
`__file__` and sets the `benchmarks` package context before benchmark imports.
Its shared instrumentation import is relative to that package. Preparation,
source helpers and deferred HTTP validation consequently resolve within the
same checkout, independently of the caller's working directory or PYTHONPATH.
Installed XYG and its native library remain ordinary runtime prerequisites.
No workflow environment change supplies the missing import context.

The regression starts the real file in an unrelated temporary directory,
removes PYTHONPATH/PYTHONHOME, and checks that the checkout root was absent
from the interpreter's starting path. It requires META, reads oracle preparation
metrics, and POSTs an actual native cold payload and decoded grid through the
real handler, requiring a passing source-bound proof. An import-only or mocked
handler test does not satisfy this contract.

## Bokeh cold output must be causally admitted

HoloViews initially evaluates a default 400×400 raster before the browser's
512×512 plot-size stream produces its second raster. The backend can already
have completed that second grid while its response remains in transit or
unadopted. Equal extents, correct total mass and ten unchanged canvas frames do
not prove adoption of that response. Previously the producer's `cold || ...`
conditions bypassed both adoption and competitor oracle checks, and its data
change observer could still report revision zero for the bootstrap image.

Instrumentation around the actual `Canvas.points` records each grid's domain,
shape, SHA256, count, mass and monotonic backend revision. A bounded metadata
registry retains these records by domain/shape for the fixed comparison
windows; it retains no extra source or grid arrays. HoloViews' real
`RGBPlot.get_data` result receives the matching record and the SHA256 of its
actual shaded image bytes **before** the existing ColumnDataSource update.
The same update therefore carries the image and its backend binding. Metadata
is never assigned from an unrelated latest backend output. This adds no extra
aggregation, image replacement, range kick, image transfer or raster generation.
The binding hashes existing shaded bytes; it does not change shading.

Browser admission requires:

- The actual image's binding has the requested domain, a 512×512 grid and a
  passing source-count/mass check.
- Its actual typed-array bytes hash to the bound shaded-image SHA256.
- The current host metrics match the bound backend revision, grid SHA256,
  domain, dimensions, count and mass.
- The image and binding remain the same objects across asynchronous hash and
  metrics reads. Replacement invalidates the result.
- A warm request receives a later observed data-source revision. Initial
  admission instead requires a valid bound backend revision; it need not
  observe an event that occurred before the browser observer connected.

The browser records request revision, observed data revision and bound backend
revision separately. The producer rechecks the complete binding against host
metrics at cold, all 32 warm, and empty-control screenshot checkpoints. A
backend that advances beyond the adopted image fails admission.

Cold uses the same adoption/domain/oracle predicates as warm. Ten stable
readbacks begin only after those predicates pass, and their output identity
must stay fixed as well as their pixel hash. Exceptions reset stability.
Waiting for ten frames of a bootstrap image cannot admit it.

The existing full matrix, repetitions, 32 windows, empty control, count/grid
hashes, source bindings, WebSocket byte accounting, RSS sampling and deadlines
remain required. Hashing and the bounded HTTP metrics read occur inside the
observed adoption/paint clock. HTTP remains excluded from the existing
WebSocket-body totals. Source preparation and grids remain under the original
host watchdog, RSS cap and source-chunk ceiling. No delayed-response exception
or tolerance is added to the independent verifier.

## Bounded proof and limits

Run the focused suite in the normal dev environment and in the optional
comparison environment with installed XYG/native support:

```bash
TMPDIR="$PWD/target/task-tmp" uv run pytest \
  tests/test_density_comparison.py tests/test_density_comparison_oracle.py \
  tests/test_density_comparison_report.py -q
```

Numerical and stdlib tests stay active in minimal development. Individual
tests importing optional live-harness dependencies skip only when those
imports are unavailable. The deterministic Node regression holds the old
400×400 image for 35 animation frames while backend revision 2 is already
available. It requires admission of the later bound 512×512 image, and rejects
wrong image hashes, backend revisions, grid hashes and extents. The original
producer admits the bootstrap before frame 35 and fails this regression.

A real bounded browser proof uses 1,000 actual mapped rows, every arm and both
fresh-process repetitions, all 32 windows, and the separate empty control:

```bash
TMPDIR="$PWD/target/task-tmp" NUMBA_NUM_THREADS=2 OMP_NUM_THREADS=2 \
  OPENBLAS_NUM_THREADS=1 python benchmarks/bench_density_comparison.py \
  --sizes 1000 --profile f64-memmap --repetitions 2 \
  --arms xy-density,plotly-aggregate,datashader-aggregate \
  --timeout 180 --step-timeout 15 --chrome "$CHROME" --out "$REPORT"
python scripts/verify_density_comparison_report.py "$REPORT" \
  --artifact-root "$PWD" --sizes 1000 \
  --arms xy-density,plotly-aggregate,datashader-aggregate
```

Keep raw reports, environment, exact commands and actual producer source
hashes with the parent-owned receipt. Local dirty measurements are exploratory.
These proofs establish bounded harness correctness, not massive-scale capacity,
real-gesture latency, a performance winner or competitive acceptance. A future
hosted attempt requires parent review and the existing authority process.
