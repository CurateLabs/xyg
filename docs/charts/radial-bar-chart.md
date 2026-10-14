---
title: Radial Bar Charts in Python
description: Create radial bar charts in Python with xyg. Build radial bar plots, progress rings, gauge charts, and semicircular capacity blocks.
components:
  - xyg.polar_bar_chart
---

# Radial Bar Charts in Python

A **radial bar chart** (also called a radial bar plot or radial bar graph)
encodes each value as an annular sector. The bar's first
channel is its center angle, its second is its radial height, `width` controls
the angular span, and `base` controls the inner radius.

Jump to [a basic radial bar chart](#basic-radial-bar-chart),
[inner radius and sector geometry](#inner-radius-and-sector-geometry), or
[partial gauges](#partial-gauges).

The first example keeps that geometry intentionally small. The blocks after it
combine XYG's exportable sectors with ordinary application layout for center values,
legends, rails, and summary statistics. This keeps the visualization reusable
without forcing dashboard UI into the chart itself.





## Basic Radial Bar Chart

Start with six named values at evenly spaced angles. Each row also carries one
shade from the purple palette used throughout these docs:

~~~python demo exec native
import xyg

RADIAL_DATA = [
    ("Direct", 0, 6, "#5b3cc4"),
    ("Search", 60, 9, "#6e56cf"),
    ("Email", 120, 7, "#806bd5"),
    ("Partner", 180, 11, "#927edc"),
    ("Social", 240, 8, "#a596e4"),
    ("Other", 300, 5, "#b8afea"),
]
radial_bars = xyg.polar_bar_chart(
    *(
        xyg.bar([angle], [value], width=48, color=color, name=label)
        for label, angle, value, color in RADIAL_DATA
    ),
    xyg.theta_axis(
        unit="degrees", zero="N", direction="clockwise", tick_values=[0, 60, 120, 180, 240, 300]
    ),
    xyg.r_axis(label="value", domain=(0, 12), tick_values=[0, 4, 8, 12]),
    xyg.legend(loc="right"),
    xyg.modebar(show=False),
)


def radial_bar_demo():
    return radial_bars
~~~

`RADIAL_DATA` stays independent of the chart construction, so labels, values,
and colors are easy to replace. The named one-bar marks populate the legend,
while the authored ticks keep the angular and radial axes easy to read. Pass
one scalar `width` for equal angular spans or a same-length sequence for
per-bar spans. Widths must be finite and positive.

## Allocation Overview

Small progress rings work well when several categories share one maximum. Each
ring below is an explicit muted track plus a colored foreground sector; the
table repeats the values for exact lookup:

~~~python demo exec native
import xyg

ALLOCATION_DATA = [
    ("Platform", 44, 880000, "#6e56cf"),
    ("Product", 24, 480000, "#806bd5"),
    ("Growth", 15, 300000, "#9888dd"),
    ("Operations", 10, 200000, "#b5aae8"),
    ("Support", 7, 140000, "#d2cbf1"),
]


def allocation_ring_chart(label, percent, color):
    span = percent / 100 * 360.0
    return xyg.polar_bar_chart(
        xyg.bar([180.0], [0.12], base=0.72, width=360.0, color="#eeecf6", opacity=1),
        xyg.bar(
            [span / 2.0],
            [0.12],
            base=0.72,
            width=span,
            color=color,
            opacity=1,
            corner_radius=8,
            name=f"{label} · {percent}%",
        ),
        xyg.theta_axis(
            unit="degrees", zero="N", direction="clockwise", show=False, tick_label_strategy="none"
        ),
        xyg.r_axis(domain=(0.0, 1.0), show=False, tick_label_strategy="none"),
        xyg.legend(show=False),
        xyg.modebar(show=False),
        xyg.theme(plot_background="#ffffff"),
        width="100%",
        height=92,
        padding=(0, 0, 0, 0),
    )


allocation_ring_chart_charts = [
    allocation_ring_chart(label, percent, color)
    for label, percent, _amount, color in ALLOCATION_DATA
]
~~~

The rings use a common radial domain and thickness. The percentage controls
only the foreground `width`, while the track remains a complete annulus. The
labels and exact dollar values stay in the host application so the ring geometry can be
exported or reused independently.

## Training Summary

A hero metric can share a card with compact radial KPIs. Here the primary
distance and goal rail lead, while three rings summarize the supporting
measurements and the narrow side column preserves quick operational context:

~~~python demo exec native
import xyg

TRAINING_METRICS = [
    ("Elevation", 312, "m", 68, "#6e56cf"),
    ("Work", 684, "kJ", 82, "#f59e0b"),
    ("Cadence", 82, "rpm", 74, "#e11d48"),
]
TRAINING_STATS = [("Intervals", "7"), ("Recovery", "46 min"), ("Avg speed", "28.4 km/h")]


def training_ring_chart(label, percent, color):
    span = percent / 100 * 360.0
    return xyg.polar_bar_chart(
        xyg.bar([180.0], [0.13], base=0.7, width=360.0, color="#f0eef7", opacity=1),
        xyg.bar(
            [span / 2.0],
            [0.13],
            base=0.7,
            width=span,
            color=color,
            opacity=1,
            corner_radius=9,
            name=f"{label} · {percent}%",
        ),
        xyg.theta_axis(
            unit="degrees", zero="N", direction="clockwise", show=False, tick_label_strategy="none"
        ),
        xyg.r_axis(domain=(0.0, 1.0), show=False, tick_label_strategy="none"),
        xyg.legend(show=False),
        xyg.modebar(show=False),
        xyg.theme(plot_background="#ffffff"),
        width="100%",
        height=118,
        padding=(0, 0, 0, 0),
    )


training_ring_chart_charts = [
    training_ring_chart(label, percent, color)
    for label, _value, _unit, percent, color in TRAINING_METRICS
]
~~~

The chart helper owns only a track and foreground arc. The headline, horizontal
goal rail, center values, and side statistics are ordinary layout, so they
remain easy to restyle without changing the chart payload.

## Cache Tiers

Nested semicircular bars can compare several capacities without repeating four
separate plots. Every tier starts at the same angle; its foreground width is the
used fraction of the shared 180-degree track:

~~~python demo exec native
import xyg

CACHE_TIERS = [
    ("Memory", 610, 1000, "#6e56cf", "#9d8df1"),
    ("Regional", 240, 1000, "#f59e0b", "#fcd34d"),
    ("Edge", 100, 1000, "#2563eb", "#60a5fa"),
    ("Origin", 50, 1000, "#e11d48", "#fb7185"),
]
CACHE_BASES = [0.24, 0.4, 0.56, 0.72]
CACHE_STATS = [
    ("Served warm", "8,420"),
    ("Revalidated", "1,140"),
    ("Evictions", "386"),
    ("Purges", "72"),
]
cache_tiers = xyg.polar_bar_chart(
    *(
        xyg.bar([0.0], [0.09], base=base, width=180.0, color="#eeecf6", opacity=1, corner_radius=8)
        for base in CACHE_BASES
    ),
    *(
        xyg.bar(
            [-90.0 + used / capacity * 180.0 / 2.0],
            [0.09],
            base=base,
            width=used / capacity * 180.0,
            name=label,
            fill=f"linear-gradient(to top, {start}, {end})",
            opacity=1,
            corner_radius=8,
            stroke="#ffffff",
            stroke_width=1,
        )
        for (label, used, capacity, start, end), base in zip(CACHE_TIERS, CACHE_BASES, strict=True)
    ),
    xyg.theta_axis(
        unit="degrees",
        sector=(-90.0, 90.0),
        zero="N",
        direction="clockwise",
        show=False,
        tick_label_strategy="none",
    ),
    xyg.r_axis(domain=(0.0, 1.0), show=False, tick_label_strategy="none"),
    xyg.legend(show=False),
    xyg.modebar(show=False),
    xyg.theme(plot_background="#ffffff"),
    width="100%",
    height=210,
    padding=(4, 4, 0, 4),
)


def cache_legend_item(label, used, capacity, color):
    percent = used / capacity
~~~

Separate one-bar marks make it straightforward to give every tier a name,
gradient, and rounded edge. The `sector=(-90.0, 90.0)` axis fits the visible
semicircle to the available plot box instead of reserving space for the missing
half.

## Build Your Own Radial Block

1. Decide whether values control radial height, angular progress, or both.
2. Author a muted track when every category shares a known maximum.
3. Keep the track and foreground on the same `base` and radial height.
4. Convert a percentage to `percentage / 100 × 360` for a full ring, or multiply
   by the declared partial-sector span.
5. Hide axes and the native legend when the host supplies the surrounding labels.
6. Keep raw data and derived spans outside the chart construction.

XYG does not add a background track or infer a maximum automatically. Explicit
track marks make the maximum, thickness, color, and export behavior unambiguous.

## Inner Radius and Sector Geometry

`base` is the inner radial edge, and the bar value is the height above it. A
scalar base opens the same hole beneath every bar; a sequence can give each bar
its own starting radius:

~~~python
rings = xyg.polar_bar_chart(
    xyg.bar(
        [0, 90, 180, 270],
        [0.30, 0.42, 0.24, 0.36],
        base=0.40,
        width=72,
    ),
    xyg.theta_axis(unit="degrees"),
    xyg.r_axis(domain=(0.0, 1.0)),
)
~~~

Filled sectors that cross the visible radial range are clipped at the inner or
outer ring. A sector wholly outside the range disappears instead of reflecting
through the center.

`base=` belongs to the mark and may differ per bar. For one chart-wide opening,
use `r_axis(hole=...)` to reserve a display-space inner fraction or
`r_axis(origin=...)` to set a data-space radial origin. `hole` and `origin` are
mutually exclusive.

A single sector with `width=360` on a degree axis (or a full `2π` width on a
radian axis) and a positive `base` draws a complete annulus. That is the track
used by the progress-ring blocks above.

## Partial Gauges

Use `sector=(start, end)` for a gauge chart whose visible arc should expand to
fill the plot box. Rounded sectors, background-colored strokes, gradients, and
explicit padding work the same way on a partial layout:

~~~python
partial_gauge = xyg.polar_bar_chart(
    xyg.bar(
        [0.0],
        [0.18],
        base=0.70,
        width=240.0,
        color="#e5e7eb",
        corner_radius=10,
    ),
    xyg.bar(
        [-30.0],
        [0.18],
        base=0.70,
        width=180.0,
        fill="linear-gradient(to top, #7c3aed, #34d399)",
        corner_radius=10,
        stroke="#ffffff",
        stroke_width=1.5,
    ),
    xyg.theta_axis(
        unit="degrees",
        sector=(-120.0, 120.0),
        zero="N",
        direction="clockwise",
        show=False,
    ),
    xyg.r_axis(domain=(0.0, 1.0), show=False),
    padding=(18, 18, 36, 18),
)
~~~

Use a scalar `corner_radius` for symmetric rounding. A gradient applies to the
whole mark and takes priority over a solid color. Use `stroke_width` to control
the separator or outline in screen pixels. Explicit
`padding=(top, right, bottom, left)` is preserved by the polar layout, so a
stable caption or legend band can be reserved without shifting the arc.

## Angular Convention

Use `xyg.theta_axis(unit="degrees")` when positions and widths are expressed in
degrees. Add `zero="N", direction="clockwise"` for compass bearings. With the
default radian axis, both the center angles and widths must be radians.

On `theta_axis()`, `domain=` is a compatibility alias for `sector=`; pass only
one. XYG clips marks and ticks to that interval and fits the visible arc to its
own bounding box.

## Interaction and Export

All live blocks on this page set `xyg.modebar(show=False)` to keep the
presentation quiet. Sector hover and browser/static exports remain available
through the shared polar renderer.

Zoom is off by default, as on every polar chart except the wind rose: these
compositions are laid out against a fixed center and a fixed outer ring, so
zooming crops the sectors rather than revealing detail. With no gesture able to
move the view, reset has nothing to restore either: unless `reset_axes` is
authored, double-click is inert and the reset controls drop out of the modebar. An
authored `reset_axes` grants both back on its own, whatever the zoom switch says.
Add `xyg.interaction_config(zoom=True)` to turn radial zoom (and reset) on when the
sector lengths are worth magnifying — see
[why zoom is off by default](/docs/xy/charts/polar-chart/#why-zoom-is-off-by-default).

Application-composed center values, rails, statistics, and custom legends are browser
UI. The radial sectors themselves remain part of the XYG chart and are preserved
in SVG and native raster exports.

See the [polar overview](/docs/xy/charts/polar-chart/) for shared axes,
interaction, pyplot, large-data, and annotation limits.

## Related Polar Charts

- [Radar charts](/docs/xy/charts/radar-chart/) — compare values across named
  dimensions.
- [Pie and donut charts](/docs/xy/charts/pie-chart/) — polished share,
  progress-ring, and gauge blocks.
- [Wind rose charts](/docs/xy/charts/wind-rose/) — bin raw direction/speed
  observations into stacked radial bars.
- [Bar charts](/docs/xy/charts/bar-chart/) — rectangular bars on Cartesian
  axes.

## FAQ

### How do I add gaps between radial bars?

Place bar centers at the full bin spacing and choose a slightly smaller
`width`. For centers 30° apart, `width=26` leaves a 4° gap.

### How do I create a donut hole?

Set a positive `base` and choose a bar height that reaches the desired outer
radius. Hide both axes for a conventional ring presentation.

### Can each sector have a different angular width?

Yes. Pass a width sequence with one finite, positive value per bar.
