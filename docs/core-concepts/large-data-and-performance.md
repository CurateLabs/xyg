---
title: Large Data and Performance
description: Understand direct rendering, M4 decimation, density aggregation, drilldown, and memory.
---

# Large Data and Performance

XYG keeps exact canonical columns in the native engine and chooses a rendered
representation for each trace. The goal is to keep transport and draw work
bounded by what the viewport can distinguish while retaining exact rows for
readout and refinement.

## The representation ladder

| Representation | Used for | What reaches the renderer |
| --- | --- | --- |
| Direct | Small visible traces | One rendered point or segment per retained row |
| M4-decimated | Long ordered lines and areas | A bounded sequence preserving per-bucket extrema |
| Density | Dense scatter overviews | A count grid wearing the data's own mean point colors. It stands across pans and zooms — softening as you go deeper — rather than re-aggregating per viewport; in standalone (kernel-less) charts a deterministic point sample overlays it once the view's estimated count would fit the direct budget |
| Refined view | A window near or below the direct budget | Exact visible points for a padded aligned window — nearby pans and zooms then render from the cached window with no further requests |

The current defaults begin M4 line decimation above 10,000 rows and automatic
scatter density above 200,000 points. Density grids default to 512×384 cells,
and very large density traces can build a lazy multiresolution pyramid for
viewport queries. These are pre-1.0 policy thresholds, not API guarantees;
write code against the behavior and recorded `tier`, not a hard-coded count.

Native SVG, PNG, and PDF export make the same first-paint choice the browser
does: a line above the decimation threshold exports the same M4 rows at the
export width, a plain scatter on the direct tier exports every point, and a
density-tier scatter exports its density surface. Two static limits are
stricter than the browser:

- a scatter with per-point color, size, or stroke channels exports directly
  only up to about 174,000 points (its per-point paint must fit one 4 MiB
  attach record); the browser draws it directly up to 2,000,000;
- the whole figure may pack at most 2,000,000 marks, counting every point of
  every direct trace and up to 16,384 rows per decimated line.

Large triangle meshes keep every face. PNG, JPEG, and WebP paint all of them
at the requested scale. SVG and PDF write one vector shape per face up to
50,000 faces in the figure; above that, each mesh becomes **one raster image**
of its faces inside the SVG or PDF (painted at twice the figure's pixel size,
so it is no longer resolution-independent vector art). Above 1,024 faces, a
mesh is also refused when the bounding boxes of its faces add up to more than
about 64 plot areas. This is a cost estimate from each face's bounding box, not
a measure of overlap, so a mesh whose faces do not overlap can trip it too:
for example a radial fan of long, thin wedges around a centre point. The check
applies to every format, including SVG and PDF that would not paint the
faces.

Anything outside those tiers raises `XYG_SCENE_UNSUPPORTED_PUBLIC_LOD` instead
of drawing a reduced chart.

Polar traces are an explicit exception to this ladder. They always use the
direct tier because Cartesian M4 and density reductions do not preserve cyclic
polar geometry. Polar `line`, `scatter`, and `area` traces have a hard
200,000-point ceiling; building a larger point trace raises `ValueError`
instead of silently drawing an unbounded payload or applying an unsuitable
reduction. Heatmap and contour grids are not rejected merely because their
cell count exceeds that point ceiling. Polar heatmaps inverse-sample at the
requested browser/export surface, so output work is pixel-bounded even though
source ingest and validation still depend on the source grid.

## Automatic versus explicit density

~~~python demo exec native
import numpy as np
import xyg

rng = np.random.default_rng(9)
x = rng.normal(size=1000000)
y = 0.4 * x + rng.normal(size=x.size)
chart = xyg.scatter_chart(xyg.scatter(x, y, density=None), width=1000, height=500)


def automatic_density_demo():
    return chart
~~~

- `density=None` chooses automatically and is the normal large-data setting.
- `density=True` requests a density overview explicitly.
- `density=False` forces direct points. Above the soft ceiling XYG warns about
  fill-rate and allocation risk, but honors the explicit opt-out.

Density aggregation is computed by the native core and rendered as a compact
WebGL texture. Calling it “GPU density” would blur those two stages: the GPU
draws the result, while the source-row binning happens before that draw.

## Exactness under reduction

Reduction changes visible geometry, not the canonical source store. Hover,
selection, `pick()`, and drilldown resolve source rows when the active tier has
an exact mapping. When a dense view cannot support exact per-marker semantics,
XYG exposes its aggregate/sample representation rather than pretending that a
bin is an individual row.

Line decimation preserves extrema for the visible buckets, but it does not
claim that every intermediate vertex is drawn. A narrow view is re-decimated
against its own window.

## The performance model

There are two different scaling regimes:

1. Ingest, validation, range scans, binning, and decimation inspect source data
   and therefore retain row-dependent work.
2. The resulting wire payload, WebGL geometry, and static SVG/native-PNG scene
   are bounded by the chosen viewport representation.

The output side after reduction scales with pixels; the complete data-to-pixels
pipeline still includes row-dependent ingest and reduction work.

## Inspect memory and tier decisions

~~~python demo exec native
report = chart.memory_report()
print(report["canonical_bytes"])
for column in report["columns"]:
    print(column["len"], column["bytes"], column["ingest_copies"])


def memory_report_demo():
    return chart
~~~

Tier decisions are also recorded in the built payload rather than being
silent. Use the memory report for many-chart dashboards and long-running append
workloads, and use the committed benchmark harness before publishing a
performance comparison.

See the [benchmark snapshot](/docs/xy/overview/benchmarks/) for a measured
example, or [Interactions and selections](/docs/xy/core-concepts/interactions/)
for exact readout behavior.
