---
title: Pie and Donut Charts in Python
description: Create pie charts and donut charts in Python with xyg. Build pie plots, progress rings, and gauge blocks with values, percentages, and custom colors.
components:
  - xyg.pie_chart
---

# Pie and Donut Charts in Python

A **pie chart** (also called a pie plot or pie graph) maps each share to an
angular span. A donut uses the same sectors
with a positive inner radius, leaving room for a total, status, or supporting
label. In XYG, both are compositions of unequal-width bars inside
`polar_bar_chart()`. For the standard composition, use
`xyg.pie_chart(labels, values, hole=...)`; the examples below use the lower-level
bars directly to demonstrate custom sector geometry and dashboard layouts.

Jump to [a basic pie chart](#basic-pie-chart),
[progress rings](#progress-rings), or
[build your own pie block](#build-your-own-pie-block).

The first example keeps the chart intentionally small. The examples after it
combine XYG's exportable sector geometry with ordinary application layout for center
labels, legends, captions, and summary rows. That separation keeps the data
visualization reusable while the surrounding block remains easy to adapt to a
dashboard.





## Basic Pie Chart

A filled pie starts with simple label-and-value data. The chart converts each
value to an angular width, and `base=0` makes every sector reach the center:

~~~python demo exec native
import xyg

PIE_DATA = [("Direct", 40), ("Partner", 30), ("Organic", 20), ("Other", 10)]
PURPLE_SHADES = ["#6e56cf", "#806bd5", "#9888dd", "#b5aae8"]
total = sum((value for _label, value in PIE_DATA))
widths = [value / total * 360 for _label, value in PIE_DATA]
angles = [sum(widths[:index]) + width / 2 for index, width in enumerate(widths)]
pie = xyg.polar_bar_chart(
    *(
        xyg.bar(
            [angle],
            [1],
            base=0,
            width=width,
            color=color,
            name=f"{label} · {value / total:.0%}",
            opacity=1,
        )
        for (label, value), angle, width, color in zip(
            PIE_DATA, angles, widths, PURPLE_SHADES, strict=True
        )
    ),
    xyg.theta_axis(unit="degrees", zero="N", show=False, tick_label_strategy="none"),
    xyg.r_axis(show=False, tick_label_strategy="none"),
    xyg.legend(loc="left"),
    xyg.modebar(show=False),
)


def basic_pie_demo():
    return pie
~~~

`PIE_DATA` stays independent of the chart geometry, so changing a value updates
both its slice and legend percentage. The separate palette uses the same
`#6e56cf` primary purple used throughout these docs.

## Market Share

Use a high-contrast donut when the whole is meaningful and every slice needs a
compact percentage label. The two-column legend preserves the names and raw
values without crowding the ring:

~~~python demo exec native
import xyg

MARKET_SERIES = [
    ("Skyline", 27, "#0a0a0a"),
    ("Datawell", 21, "#262626"),
    ("Cloudpeak", 13, "#3d3d3d"),
    ("Taskbridge", 21, "#545454"),
    ("Insightloop", 6, "#6b6b6b"),
    ("Streamforge", 12, "#7d7d7d"),
]


def sector_layout(values):
    spans = [value / sum(values) * 360.0 for value in values]
    centers, cursor = ([], 0.0)
    for span in spans:
        centers.append(cursor + span / 2.0)
        cursor += span
    return (centers, spans)


market_angles, market_widths = sector_layout(
    [value for _label, value, _color in reversed(MARKET_SERIES)]
)
market_share = xyg.polar_bar_chart(
    *(
        xyg.bar(
            [angle],
            [0.42],
            base=0.52,
            width=width,
            name=label,
            color=color,
            opacity=1,
            stroke="#ffffff",
            stroke_width=3,
        )
        for (label, _value, color), angle, width in zip(
            reversed(MARKET_SERIES), market_angles, market_widths, strict=True
        )
    ),
    *(
        xyg.text(
            angle,
            0.73,
            f"{value}%",
            dx=0,
            dy=4,
            anchor="middle",
            color="#ffffff",
            class_name="text-xs font-medium",
        )
        for (_label, value, _color), angle in zip(
            reversed(MARKET_SERIES), market_angles, strict=True
        )
    ),
    xyg.theta_axis(
        unit="degrees",
        zero="N",
        direction="counterclockwise",
        show=False,
        tick_label_strategy="none",
    ),
    xyg.r_axis(domain=(0.0, 1.0), show=False, tick_label_strategy="none"),
    xyg.legend(show=False),
    xyg.modebar(show=False),
    xyg.theme(plot_background="#ffffff", text_color="#171717"),
    width="100%",
    height=243,
    padding=(0, 0, 0, 0),
)
~~~

The slot width remains proportional to the value. A three-pixel
background-colored stroke creates a constant screen-space separator; unlike an
angular gap, it stays visually even at the inner and outer rim. Text annotations
use `(theta, radius)` coordinates, so their anchors remain attached to the
slices in browser and static output.

## Progress Rings

A thin annulus can behave like a circular progress bar. Splitting it into 40
rounded dashes gives the display a lighter rhythm than one continuous arc:

~~~python demo exec native
import xyg

PROGRESS_STATS = [
    (48, "Additional support requests from users."),
    (67, "Inaccurate forecasts disrupt planning."),
]


def progress_ring(value):
    dots = 40
    filled = round(dots * value / 100)
    active = [228 / 255, 56 / 255, 97 / 255]
    track = [212 / 255, 212 / 255, 212 / 255]
    return xyg.polar_bar_chart(
        xyg.bar(
            [index * 9.0 for index in range(dots)],
            [0.07] * dots,
            base=0.85,
            width=4.5,
            color=[active if index < filled else track for index in range(dots)],
            opacity=1,
            corner_radius=6,
        ),
        xyg.theta_axis(
            unit="degrees",
            zero="N",
            direction="counterclockwise",
            show=False,
            tick_label_strategy="none",
        ),
        xyg.r_axis(domain=(0.0, 1.0), show=False, tick_label_strategy="none"),
        xyg.legend(show=False),
        xyg.modebar(show=False),
        xyg.theme(plot_background="#ffffff"),
        width="100%",
        height=265,
        padding=(0, 0, 0, 0),
    )


progress_ring_charts = [progress_ring(value) for value, _caption in PROGRESS_STATS]
~~~

Each visible dash occupies half of a nine-degree slot. The remaining half is
the gap, so the track stays evenly spaced without creating transparent data
rows.

## Revenue Mix

For a smaller category set, pair a rounded donut with a value list. The center
answers the primary question while the aligned legend supports exact lookup:

~~~python demo exec native
import xyg

REVENUE_SERIES = [
    ("Direct", 52400, "#7c3aed", "#a855f7"),
    ("Marketplace", 38900, "#4f46e5", "#6366f1"),
    ("Wholesale", 24150, "#0284c7", "#0ea5e9"),
    ("Affiliate", 16300, "#059669", "#10b981"),
]


def sector_layout(values):
    spans = [value / sum(values) * 360.0 for value in values]
    centers, cursor = ([], 0.0)
    for span in spans:
        centers.append(cursor + span / 2.0)
        cursor += span
    return (centers, spans)


revenue_angles, revenue_widths = sector_layout(
    [value for _label, value, _start, _end in REVENUE_SERIES]
)
revenue_mix = xyg.polar_bar_chart(
    *(
        xyg.bar(
            [angle],
            [0.3],
            base=0.62,
            width=width,
            name=label,
            fill={"gradient": f"linear-gradient(to right, {start}, {end})", "space": "plot"},
            opacity=1,
            corner_radius=12,
            stroke="#ffffff",
            stroke_width=6,
        )
        for (label, _value, start, end), angle, width in zip(
            REVENUE_SERIES, revenue_angles, revenue_widths, strict=True
        )
    ),
    xyg.theta_axis(
        unit="degrees",
        zero="N",
        direction="counterclockwise",
        show=False,
        tick_label_strategy="none",
    ),
    xyg.r_axis(domain=(0.0, 1.0), show=False, tick_label_strategy="none"),
    xyg.legend(show=False),
    xyg.modebar(show=False),
    xyg.theme(plot_background="#ffffff"),
    width="100%",
    height=280,
    padding=(0, 0, 0, 0),
)
~~~

Rounded corners are available when `base` is positive. A CSS linear gradient
paints each one-slice mark independently, so every segment can keep its own
two-color ramp.

## Reliability Score

A partial donut becomes a gauge when its angular span represents an ordered
scale. Keep the qualitative bands in the ring and repeat them as a linear key
for exact threshold lookup:

~~~python demo exec native
import xyg

RELIABILITY_BANDS = [
    ("At risk", 450, "#e11d48"),
    ("Fair", 200, "#f59e0b"),
    ("Good", 170, "#84cc16"),
    ("Excellent", 180, "#059669"),
]
SCORE = 842
GAUGE_SPAN = 240.0
GAUGE_START = -120.0


def gauge_layout(values):
    spans = [value / sum(values) * GAUGE_SPAN for value in values]
    centers, cursor = ([], GAUGE_START)
    for span in spans:
        centers.append(cursor + span / 2.0)
        cursor += span
    return (centers, spans)


gauge_angles, gauge_widths = gauge_layout(
    [value for _label, value, _color in reversed(RELIABILITY_BANDS)]
)
reliability_gauge = xyg.polar_bar_chart(
    *(
        xyg.bar(
            [angle],
            [0.2],
            base=0.74,
            width=width,
            name=label,
            color=color,
            opacity=1,
            corner_radius=10,
            stroke="#ffffff",
            stroke_width=6,
        )
        for (label, _value, color), angle, width in zip(
            reversed(RELIABILITY_BANDS), gauge_angles, gauge_widths, strict=True
        )
    ),
    xyg.theta_axis(
        unit="degrees",
        zero="N",
        direction="counterclockwise",
        show=False,
        tick_label_strategy="none",
    ),
    xyg.r_axis(domain=(0.0, 1.0), show=False, tick_label_strategy="none"),
    xyg.legend(show=False),
    xyg.modebar(show=False),
    xyg.theme(plot_background="#ffffff"),
    width="100%",
    height=200,
    padding=(0, 0, 0, 0),
)


def reliability_scale():
    starts = [0, 450, 650, 820]
~~~

This example keeps a full circular layout and authors only 240 degrees of
colored bars, matching a conventional dashboard gauge. Use
`theta_axis(sector=(start, end))` instead when the visible arc should expand to
fill the plot box.

## Build Your Own Pie Block

1. Normalize values to a full turn (360 degrees or `2π` radians).
2. Use the cumulative midpoint of each slot as the bar angle.
3. Add a background-colored stroke for a constant-pixel separator, or subtract
   a small angle from each slot when the gap should scale with the ring.
4. Give every slice the same `base` and height.
5. Hide the axes and compose labels or legends around the chart in your application.

Set `base=0` for a filled pie. For donuts, a positive base enables rounded
sector corners. Per-slice gradients are easiest to express as one single-slice
bar mark per category.

## Interaction and Export

Pie blocks use the shared polar renderer. These examples set
`xyg.modebar(show=False)` to keep the presentation clean. The underlying
interactions and APIs remain intact: sector hover works, and
browser/static exports remain available. A hovered slice reads its own label and
value; the layout angle and the constant rim radius stay out of the readout.

Zoom is off by default here, as on every polar chart except the wind rose. A pie
carries its value in the *angle* and uses the radius as a constant rim, so
zooming would crop that rim around a fixed center rather than reveal anything —
and leaving the wheel free means a page scrolls normally over the chart. With
nothing to move the view, there is nothing to restore either: unless `reset_axes`
is authored, double-click reset does nothing and the reset controls drop out of the
modebar. An authored `reset_axes` grants both back on its own, whatever the zoom
switch says. Add `xyg.interaction_config(zoom=True)` to restore the wheel and
double-click reset; these examples also hide the modebar with
`xyg.modebar(show=False)`, so drop that child too if you want the visible zoom and
reset buttons. See
[why zoom is off by default](/docs/xy/charts/polar-chart/#why-zoom-is-off-by-default).
Center labels and legends composed by an application are browser UI; annotations placed
with `xyg.text()` are part of the chart and are preserved in SVG and native
raster exports.

See [Radial bar charts](/docs/xy/charts/radial-bar-chart/) for width, base,
corner-radius, clipping, and partial-sector details.

## Related Polar Charts

- [Polar overview](/docs/xy/charts/polar-chart/) — shared axes, interaction,
  annotations, pyplot, and renderer limits.
- [Radial bar charts](/docs/xy/charts/radial-bar-chart/) — equal-angle and
  variable-height annular sectors.
- [Radar charts](/docs/xy/charts/radar-chart/) — categorical profile
  comparisons.
- [Wind rose charts](/docs/xy/charts/wind-rose/) — direction and speed
  distributions.

## FAQ

### Does XYG have a dedicated pie mark?

No. Every pie plot and donut plot on this page is composed from `xyg.bar()`
marks inside `xyg.polar_bar_chart()`. This keeps sector styling and export
behavior on the same renderer as radial bars.

### How do I add space between slices?

For an even screen-space separator, keep the proportional `width` and add a
background-colored `stroke` with `stroke_width=`. For an angular gap, pass a
slightly smaller per-item `width` while keeping each slot midpoint unchanged.

### How do I round donut slices?

Pass `corner_radius=` on bars whose `base` is positive. A filled pie reaches
the center and therefore keeps a sharp center vertex.
