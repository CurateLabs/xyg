# Source-derived comparison count and grid oracle

This benchmark-only contract implements dossier §§5/12/28–29 and LOD
architecture §7. It preserves the product's approximate pyramid. It changes
no threshold, geometry algorithm, count query, API or ABI. The implementation
is `benchmarks/_ux_comparison_oracle.py`; the stdlib report verifier imports
neither it nor numerical/native libraries.

## Counts and endpoints

For finite canonical source pairs `P` and requested closed rectangle `V`,
`C = |P ∩ V|` is the exact inclusive source/range count. The source creator
also records `H`, using `[x0,x1) × [y0,y1)`, and exclusions `C − H` from the
upper boundaries. Exact native binning has this half-open contract; source
rows on those edges remain disclosed in `C`, never silently removed from it.
Point fallbacks are checked inclusively against actual clipped GPU buffers;
their `visible`/payload count may describe a larger covering drill window.

The pyramid domain is the canonical column extrema, with each upper edge
increased by `1e-9 × axis span`, exactly as the product builds it. All source
maxima therefore enter the finest histogram. The base dimension comes from
the existing product geometry helper; querying geometry/LOD grid shape is
permitted, using a native aggregate answer as an oracle is not.

Let `G0` be an independently constructed integer finest grid. Its cells use
the native half-open binning endpoints. Let `S0(V)` contain whole cells whose
centers are within the viewport. The recorded estimate must equal
`E = Σ G0[c], c ∈ S0(V)` exactly. In integer cell-index coordinates the
center range is clamped to the grid and has indices from
`ceil((lo−origin)/cell−0.5)` through `floor((hi−origin)/cell−0.5)`, inclusive.
This states the implemented upper-center inclusion explicitly; it is distinct
from a half-open **point** predicate.

For a conservative source-mass bound, let `O` include cells touching the
closed viewport and `I` include cells strictly contained by it. Both exact
point membership and center-cell membership lie between these sets. Thus

```
B = Σ G0[O] − Σ G0[I]
|E − C| ≤ B
```

`B` is computed from the independent grid, not native `pyramid_count` or its
reported error. Exact equality to `E` is required even when another value
would also lie within `B`. There is no universal small relative bound: all
rows can concentrate in an intersected boundary cell. Local goldens exercise
an exact count of 1 versus an estimate of 999, with the discrepancy accounted
for by boundary mass.

`count_method`, `count_exact`, exact/half-open source counts, exclusions,
expected and emitted visible counts, boundary mass, base domain/dimension,
upper-edge epsilon and served level remain distinct report fields. The
adapter preserves raw product labels. A density reply advertising direct
tier or no reduction is rejected rather than repaired by instrumentation.

## Independent source-to-grid calculation

Preparation bins source chunks of at most 65,536 rows into a u32 finest
grid and reduces 2×2 cells to build coarser grids. All admitted sources have
at most 1B rows, below u32 capacity, so those integer additions are exact.
No source-row-sized heap array or additional source file is created.

For a pyramid viewport, the oracle independently chooses the coarsest level
with at least the output width/height in center-selected source cells. It
implements the documented separable area-weighted compose: each source
interval contributes to its center output bin and at most one adjacent bin;
off-viewport spills fold into the center bin. Product edge snapping at
fraction `≤1e-6` is part of this resampling definition, **not a numerical
acceptance tolerance**. X taps accumulate in increasing source-cell order,
then source rows accumulate in order with f32 multiply/add rounding, matching
the output contract. Upsampling instead pulls the cell beneath each output
pixel center, including the implementation's integer truncation and domain
checks. Neither upsampled grid mass nor a different served level's rim mass
is treated as `C` or `E`.

For an exact-bin route the oracle bins canonical source chunks directly into
the planned screen grid. It independently converts integer cells to f32.
For either route, with `m = max(grid)`, encoding is zero for empty cells and
otherwise `clamp(round_ties_even(255 log1p(value)/log1p(m)), 1, 255)`.
The expected maximum and every encoded byte must match the actual reply.
The oracle independently decodes those expected bytes with
`f32(expm1(code/255 × log1p(m)))`; their SHA256 must match bytes read from the
actual adopted density object's grid, and its maximum must match too.
These are exact byte/hash comparisons. A platform rounding disagreement
fails closed; it is not hidden behind an epsilon. CPU adoption binding plus
the existing actual-WebGL readbacks does not claim per-pixel cross-library
equivalence or independent GPU texture readback.

## Timing, resource and evidence scope

The existing allocation guard runs before oracle allocation. Source hash and
inclusive/half-open count scans remain in source creation. Each XYG host
prepares independent grids and expectations before `META`, under its existing
process-tree RSS poller and preparation deadline. Preparation wall time,
chunk size and conservative grid-storage accounting are retained. Levels and
temporary grids are grid-bounded; warm validation uses prepared hashes and
does no source scan. LOD threshold/shape queries retain product policy.

Browser instrumentation retains actual binary reply buffers and reads the
adopted grid. It posts these bounded bytes to the benchmark-only oracle via
HTTP; validation time and request-body bytes are recorded separately, while
the full round-trip remains inside observed paint/stability timings. Existing
WebSocket body totals continue to exclude HTTP. The 300s preparation, 15s
step, 20GiB hosted RSS/source-disk and 1M source-chunk ceilings do not change.
An exceeded deadline or cap remains a failure, not a reason to omit proof.

The producer requires a passing current numerical oracle before declaring
paint correct. The independent verifier checks numerical fields, source
identity, raw reply counts/labels, expected/actual/adopted hashes and maxima,
endpoint counts and host-checkpoint bindings. It still enforces full matrix,
all repetitions, axes, revisions, exact fallbacks, cache equivalence, pixels,
empty controls, clocks, resources and artifact provenance. It structurally
checks retained evidence; absent source bytes are not reconstructed.

Only the three already pinned decoded historical archive digests retain the
old contract. The failed hosted receipt `82641839` is immutable rejected
evidence. Neither new fields nor a filename/flag can grant it an exemption.

Bounded regression commands (native core required; no hosted source):

The source/grid and stdlib report checks run in the normal development
environment. Tests importing live browser/HTTP harness modules require the
optional benchmark `websocket-client` and/or Tornado dependencies and skip
individually when those imports are absent. Run the same focused suite in the
constrained benchmark environment to exercise those harness guards; missing
optional packages must not fail the supported Python floor suite.

```bash
uv run pytest tests/test_density_comparison_oracle.py \
  tests/test_density_comparison.py tests/test_density_comparison_report.py -q
```

The 1M forced-pyramid fixture changes build eligibility only, explicitly
passing a 2048 base to its benchmark oracle; default thresholds and product
aggregation remain untouched. It depends on the separately owned product
metadata fix for no-rescan density replies below the direct-count budget.
