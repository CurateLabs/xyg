---
title: Advanced Styling Gallery
description: Inspect advanced XYG styling paths for scalar fields, uncertainty, explicit geometry, facets, reduction badges, and custom chrome.
---

# Advanced Styling Gallery

This gallery focuses on advanced renderer and composition paths that do not
belong in the product-ready examples: scalar fields, density reduction,
uncertainty, explicit geometry, facets, and host-owned chrome. Start with
[Examples](/docs/xy/styling/examples/) when you want a polished chart pattern
to copy; use this page when you need to inspect a less common styling boundary.

## Trend and cumulative marks

A compact combo chart gives monthly production the visual weight of blue
columns while an amber line keeps the cumulative signal easy to compare. The
host-owned key distinguishes bar and line marks, and only quiet horizontal guides
remain inside the plot.

~~~python demo exec native
import xyg

months = [
    "Jan 23",
    "Feb 23",
    "Mar 23",
    "Apr 23",
    "May 23",
    "Jun 23",
    "Jul 23",
    "Aug 23",
    "Sep 23",
    "Oct 23",
    "Nov 23",
    "Dec 23",
]
production = [2890, 2756, 3322, 3470, 3475, 3129, 3490, 2903, 2643, 2837, 2954, 3239]
cumulative = [2338, 2103, 2194, 2108, 1812, 1726, 1982, 2012, 2342, 2473, 3848, 3736]
trend_atlas = xyg.chart(
    xyg.column(
        months, production, name="Production", color="#2b7fff", corner_radius=0, stroke_width=0
    ),
    xyg.line(months, cumulative, name="Cumulative", color="#fe9a00", width=2, curve="linear"),
    xyg.x_axis(
        style={
            "axis_width": 0,
            "axis_color": "#00000000",
            "grid_opacity": 0,
            "tick_width": 0,
            "tick_color": "#00000000",
            "tick_label_color": "#00000000",
            "label_color": "#00000000",
        }
    ),
    xyg.y_axis(
        domain=(0, 4200),
        style={
            "axis_width": 0,
            "axis_color": "#00000000",
            "tick_width": 0,
            "tick_color": "#00000000",
            "tick_label_color": "#00000000",
            "label_color": "#00000000",
        },
    ),
    xyg.tooltip(title="{x}", format={"y": ",.0f"}),
    xyg.legend(show=False),
    xyg.theme(
        plot_background="var(--gallery-surface, #ffffff)",
        grid_color="var(--gallery-grid, #e5e7eb)",
        axis_color="var(--gallery-axis, #d1d5db)",
        text_color="var(--gallery-text, #4b5563)",
    ),
    class_name="bg-[#ffffff] [--gallery-surface:#ffffff] [--gallery-grid:#e5e7eb] [--gallery-axis:#d1d5db] [--gallery-text:#4b5563] dark:bg-[#000000] dark:[--gallery-surface:#000000] dark:[--gallery-grid:#27272a] dark:[--gallery-axis:#3f3f46] dark:[--gallery-text:#d4d4d8]",
    width="100%",
    height=330,
    padding=[14, 20, 16, 20],
)
~~~

## What this gallery includes

| Family | Components | Useful styling variations |
| --- | --- | --- |
| Trend | `column`, `line` | layered measures, a custom key, hidden axes, tooltip readout |
| Scalar fields and density | `heatmap`, `hexbin`, `contour`, `scatter` | colormaps, cell alpha, contour strokes, density reduction |
| Uncertainty | `error_band`, `errorbar`, `line` | translucent interval fill, boundary strokes, caps, estimate overlays |
| Explicit geometry | `segments`, `stem`, `triangle_mesh` | per-item color, stroke width, marker paint, mesh borders |
| Chrome | `x_axis`, `y_axis`, `legend`, `tooltip`, `colorbar`, `theme` | hidden axes, built-in and host-owned chrome, tokens, pointer tooltips |
| Composition | `chart`, typed chart factories, `facet_chart` | layered marks, shared panel styles, responsive wrappers, export CSS |

The cursor-tooltip example below uses `area`; choose `ecdf` when
the cumulative signal is a distribution rather than a month-by-month measure.

For every available component and argument, use the API reference.

## Scalar fields and density

`heatmap` supplies the filled scalar field and `contour` supplies its crisp
isolines. The second chart shows screen-bounded `hexbin` geometry. These marks
accept deliberately narrower paint vocabularies than DOM chrome because their
color is data-driven.

~~~python demo exec native
import xyg

field = [[0.0, 0.2, 0.4, 0.1], [0.2, 0.8, 1.1, 0.5], [0.1, 0.6, 0.9, 0.4], [0.0, 0.2, 0.3, 0.1]]
field_chart = xyg.chart(
    xyg.heatmap(field, colormap="purples", opacity=0.86),
    xyg.contour(field, levels=7, color="#312e81", colormap="purples", width=1.4, opacity=0.9),
    xyg.x_axis(
        tick_label_strategy="none", style={"axis_width": 0, "grid_opacity": 0, "tick_width": 0}
    ),
    xyg.y_axis(tick_label_strategy="none", style={"axis_width": 0, "tick_width": 0}),
    xyg.colorbar(
        title="Intensity",
        orientation="vertical",
        ticks=[0.0, 0.5, 1.1],
        style={
            "background": "var(--chart-bg)",
            "border": "1px solid var(--chart-axis)",
            "color": "var(--chart-text)",
            "border-radius": 8,
        },
    ),
    styles={
        "colorbar_bar": {"border_radius": 4},
        "colorbar_tick": {"color": "var(--chart-text)"},
        "colorbar_title": {"font_weight": 700},
    },
)
hex_x = (
    [
        -1.8,
        -1.5,
        -1.3,
        -1.1,
        -0.9,
        -0.7,
        -0.5,
        -0.3,
        -0.1,
        0.1,
        0.3,
        0.5,
        0.7,
        0.9,
        1.1,
        1.3,
        1.5,
        1.8,
    ]
    + [-0.3] * 4
    + [0.9] * 6
)
hex_y = (
    [-0.9, -0.5, -0.7, -0.2, -0.4, 0.1, -0.1, 0.4, 0.2, 0.7, 0.4, 0.9, 0.6, 1.2, 0.8, 1.4, 1.1, 1.6]
    + [0.4] * 4
    + [1.2] * 6
)
hexbin_chart = xyg.hexbin_chart(
    xyg.hexbin(
        hex_x,
        hex_y,
        gridsize=9,
        mincnt=1,
        colormap="viridis",
        opacity=0.9,
        style={"fill-opacity": 0.9},
    ),
    xyg.colorbar(title="Points per hexagon", orientation="horizontal", ticks=[1, 3, 6]),
    xyg.x_axis(
        tick_label_strategy="none", style={"axis_width": 0, "grid_opacity": 0, "tick_width": 0}
    ),
    xyg.y_axis(tick_label_strategy="none", style={"axis_width": 0, "tick_width": 0}),
)
~~~

## Uncertainty and explicit geometry

This pair shows advanced geometry from `error_band`, `errorbar`, `segments`,
`stem`, and `triangle_mesh`. A restrained dashboard
palette separates each geometry without adding decorative chart chrome.

~~~python demo exec native
import xyg

x = [0, 1, 2, 3, 4, 5]
estimate = [3, 4, 4.5, 6, 6.5, 8]
uncertainty_chart = xyg.chart(
    xyg.error_band(
        x,
        [value - 0.8 for value in estimate],
        [value + 0.8 for value in estimate],
        name="90% interval",
        color="#8e51ff",
        fill="linear-gradient(#8e51ff4d 5%, #8e51ff00 95%)",
        opacity=1,
        line_width=2,
        line_opacity=1,
    ),
    xyg.errorbar(
        x,
        estimate,
        yerr=[0.4, 0.7, 0.5, 0.8, 0.6, 0.5],
        name="Observed error",
        color="#00b8db",
        width=1.7,
        cap_size=5,
    ),
    xyg.line(x, estimate, name="Estimate", color="#2b7fff", width=2),
    xyg.x_axis(
        tick_label_strategy="none", style={"axis_width": 0, "grid_opacity": 0, "tick_width": 0}
    ),
    xyg.y_axis(tick_label_strategy="none", style={"axis_width": 0, "tick_width": 0}),
    xyg.legend(loc="upper left"),
    xyg.theme(
        plot_background="var(--atlas-surface, #ffffff)",
        grid_color="var(--atlas-grid, #e5e7eb)",
        axis_color="var(--atlas-axis, #d1d5db)",
        text_color="var(--atlas-text, #4b5563)",
    ),
    class_name="bg-[#ffffff] [--atlas-surface:#ffffff] [--atlas-grid:#e5e7eb] [--atlas-axis:#d1d5db] [--atlas-text:#4b5563] dark:bg-[#000000] dark:[--atlas-surface:#000000] dark:[--atlas-grid:#27272a] dark:[--atlas-axis:#3f3f46] dark:[--atlas-text:#d4d4d8]",
)
geometry_chart = xyg.chart(
    xyg.triangle_mesh(
        [0, 1, 1],
        [0, 0, 1],
        [1, 2, 2],
        [0, 0, 1],
        [0.5, 1.5, 1.5],
        [1.2, 1.3, 2.1],
        color=[0.2, 0.65, 1.0],
        colormap="purples",
        domain=(0, 1),
        opacity=0.52,
        stroke="#8e51ff",
        stroke_width=1,
        name="Mesh",
    ),
    xyg.segments(
        [0.1, 0.6, 1.1],
        [0.3, 0.7, 1.1],
        [0.8, 1.3, 1.9],
        [0.8, 1.2, 1.7],
        color=[0.1, 0.55, 1.0],
        colormap="blues",
        domain=(0, 1),
        width=4,
        name="Segments",
    ),
    xyg.stem(
        [0.25, 0.9, 1.55],
        [0.7, 1.45, 1.9],
        base=0,
        color="#fe9a00",
        width=1.8,
        marker_size=7,
        name="Stems",
    ),
    xyg.x_axis(
        tick_label_strategy="none", style={"axis_width": 0, "grid_opacity": 0, "tick_width": 0}
    ),
    xyg.y_axis(tick_label_strategy="none", style={"axis_width": 0, "tick_width": 0}),
    xyg.legend(loc="upper left"),
    xyg.theme(
        plot_background="var(--atlas-surface, #ffffff)",
        grid_color="var(--atlas-grid, #e5e7eb)",
        axis_color="var(--atlas-axis, #d1d5db)",
        text_color="var(--atlas-text, #4b5563)",
    ),
    class_name="bg-[#ffffff] [--atlas-surface:#ffffff] [--atlas-grid:#e5e7eb] [--atlas-axis:#d1d5db] [--atlas-text:#4b5563] dark:bg-[#000000] dark:[--atlas-surface:#000000] dark:[--atlas-grid:#27272a] dark:[--atlas-axis:#3f3f46] dark:[--atlas-text:#d4d4d8]",
)
~~~

## A real reduction badge

Badges exist only when the representation reports a real quality tradeoff.
Enabling density while supplying per-point color produces an “aggregated
channels” badge. This example styles the badge generated from that real data
reduction.

~~~python demo exec native
import numpy as np
import xyg

rng = np.random.default_rng(17)
x = rng.normal(size=12000)
y = 0.65 * x + rng.normal(scale=0.7, size=x.size)
reduction_chart = xyg.scatter_chart(
    xyg.scatter(x, y, color=np.hypot(x, y), density=True, colormap="viridis", opacity=0.9),
    xyg.x_axis(
        tick_label_strategy="none", style={"axis_width": 0, "grid_opacity": 0, "tick_width": 0}
    ),
    xyg.y_axis(tick_label_strategy="none", style={"axis_width": 0, "tick_width": 0}),
    class_names={"badge": "gap-1", "badge_item": "rounded-full font-mono text-[10px] shadow-sm"},
    styles={
        "badge_item": {
            "background": "rgb(24 24 27 / 88%)",
            "border": "1px solid rgb(148 163 184 / 40%)",
            "color": "#f8fafc",
            "padding": "3px 7px",
        }
    },
)


def reduction_badge_preview():
    return reduction_chart
~~~

## Styled facets

`facet_chart` applies the same mark, axis, annotation, theme, and chart-slot
styles to every panel. XYG's standalone wrapper owns the grid, so wrapper
layout selectors belong in export CSS.

~~~python demo exec native
import xyg

facet_data = {
    "x": [0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3],
    "y": [1, 3, 2, 4, 4, 2, 3, 1, 2, 4, 3, 5],
    "region": ["West"] * 4 + ["East"] * 4 + ["Central"] * 4,
}
styled_facets = xyg.facet_chart(
    xyg.area(
        x="x",
        y="y",
        color="#d97706",
        fill="linear-gradient(#d977064d 5%, #d9770600 95%)",
        line_color="#d97706",
        line_width=2,
    ),
    xyg.x_axis(
        tick_label_strategy="none", style={"axis_width": 0, "grid_opacity": 0, "tick_width": 0}
    ),
    xyg.y_axis(tick_label_strategy="none", style={"axis_width": 0, "tick_width": 0}),
    xyg.theme(
        plot_background="var(--facet-bg, #ffffff)",
        grid_color="var(--facet-grid, #e5e7eb)",
        axis_color="var(--facet-axis, #d1d5db)",
        text_color="var(--facet-text, #4b5563)",
    ),
    xyg.modebar(show=False),
    by="region",
    data=facet_data,
    cols=3,
    gap=16,
    width=900,
    height=230,
    padding=[24, 18, 18, 18],
)
~~~

For standalone HTML, style the grid itself at export time:

~~~python
html = styled_facets.to_html(
    custom_css="""
.xy-facet-grid { gap: 1rem; padding: 1rem; background: #ffffff; }
.xy-facet-panel { overflow: hidden; border: 1px solid #e2e8f0; border-radius: 12px; }
.xy-facet-title { color: #4b5563; letter-spacing: .02em; }
"""
)
~~~

## Custom legend and styled cursor tooltip

XYG's built-in tooltip already follows the pointer and can be fully restyled.
This example keeps that client-owned positioning while rendering an interactive
host-owned legend below the chart. Python hover callbacks expose resolved
rows rather than pointer coordinates; a custom application tooltip needs its
own positioning data. Documentation previews show the compiled chart rather
than running application state or custom legend callbacks.

~~~python demo exec native
# Static snapshot: Python callbacks and data updates require an application host.
import xyg


class StyledChromeState:
    show_plan: bool = True

    def figure(self):
        data = {
            "period": [
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            ],
            "actual": [2900, 2780, 3330, 3490, 3500, 3120, 3510, 2910, 2650, 2840, 2960, 3240],
            "plan": [2340, 2100, 2190, 2110, 1820, 1730, 1980, 2010, 2340, 2470, 3850, 3740],
        }
        marks = [
            xyg.area(
                x="period",
                y="actual",
                data=data,
                name="Actual",
                color="#2b7fff",
                fill="linear-gradient(#2b7fff66 5%, #2b7fff00 95%)",
                line_width=2.25,
                opacity=1,
                curve="linear",
            )
        ]
        if self.show_plan:
            marks.append(
                xyg.area(
                    x="period",
                    y="plan",
                    data=data,
                    name="Plan",
                    color="#00bc7d",
                    fill="linear-gradient(#00bc7d66 5%, #00bc7d00 95%)",
                    line_width=2.25,
                    opacity=1,
                    curve="linear",
                )
            )
        return xyg.area_chart(
            *marks,
            xyg.legend(show=False),
            xyg.tooltip(
                fields=["actual", "plan"],
                title="{period}",
                format={"actual": "$,.0f", "plan": "$,.0f"},
                style={
                    "background": "var(--tooltip-surface, #ffffff)",
                    "color": "var(--tooltip-text, #1d293d)",
                    "border": "1px solid var(--tooltip-border, #e5e7eb)",
                    "border-radius": 8,
                    "box-shadow": "0 8px 24px #1118271f",
                    "padding": "8px 10px",
                },
            ),
            xyg.x_axis(
                style={
                    "axis_width": 0,
                    "axis_color": "#00000000",
                    "grid_opacity": 0,
                    "tick_width": 0,
                    "tick_color": "#00000000",
                    "tick_label_color": "#00000000",
                    "label_color": "#00000000",
                }
            ),
            xyg.y_axis(
                domain=(0, 4200),
                style={
                    "axis_width": 0,
                    "axis_color": "#00000000",
                    "tick_width": 0,
                    "tick_color": "#00000000",
                    "tick_label_color": "#00000000",
                    "label_color": "#00000000",
                },
            ),
            xyg.theme(
                plot_background="var(--chrome-surface, #ffffff)",
                grid_color="var(--chrome-grid, #e5e7eb)",
                axis_color="var(--chrome-axis, #d1d5db)",
                text_color="var(--chrome-text, #4b5563)",
            ),
            class_name="bg-[#ffffff] [--chrome-surface:#ffffff] [--chrome-grid:#e5e7eb] [--chrome-axis:#d1d5db] [--chrome-text:#4b5563] [--tooltip-surface:#ffffff] [--tooltip-text:#1d293d] [--tooltip-border:#e5e7eb] dark:bg-[#000000] dark:[--chrome-surface:#000000] dark:[--chrome-grid:#27272a] dark:[--chrome-axis:#3f3f46] dark:[--chrome-text:#d4d4d8] dark:[--tooltip-surface:#18181f] dark:[--tooltip-text:#f3f4f6] dark:[--tooltip-border:#3f3f46]",
            width="100%",
            height=340,
            padding=[12, 20, 18, 20],
        )


initial_chart = StyledChromeState().figure()
~~~

That pattern keeps the legend interactive while the styled built-in tooltip
tracks the pointer and remains available to standalone chart exports.
For a fixed chart, a simpler host-owned key can sit next to its chart
container, as described in
[Customize Each Part](/docs/xy/styling/customize/#legend).

## Export parity checklist

- Keep mark paint in typed props or mark `style`; WebGL, SVG, and native raster
  can all consume that contract.
- Keep essential colors in chart tokens when the export must be self-contained.
- Pass ordinary compiled CSS with `to_html(custom_css=...)` for standalone DOM
  chrome, facets, media queries, or a portable design system.
- Tailwind class names remain in the exported markup, but Tailwind's compiled
  rules are not bundled automatically.
- Host-owned components and interaction state are application UI, not
  serializable XYG chart content.
- Compare live HTML with `to_svg()` and both native and Chromium `to_png()`
  when exact renderer parity matters.
