# API Examples

These examples cover the currently implemented 2D chart families. They are
short on purpose: each one should be copyable into a notebook or script after
`pip install xyg`. The Python snippets in this file are executed by
`tests/test_docs_examples.py`, so docs changes should fail fast if the public
API drifts.

The library is optimized for large data, but ordinary charts should stay boring
to build. The first section below is intentionally small business-style data;
the later per-chart examples show the same APIs scaling up.

## API Stability Notes

xy has one public chart-building API: the declarative composition API.
Charts are Reflex-shaped, declarative chart children — marks, axes,
annotations, legend/tooltip chrome — composed inside a family container
(`xyg.line_chart(...)`, `xyg.bar_chart(...)`, ...) or the neutral layering
container `xyg.chart(...)`. Marks accept arrays directly or column-name
resolution through `data=`, and charts take `on_hover` / `on_select` callbacks.
The core composition contract is now stabilizing around lightweight Python
children, layered marks, axes, annotations, built-in or custom legend/tooltip
chrome, and CSS/Tailwind-friendly DOM hooks. Callback payload details and
future adapter packages may still evolve before 1.0.

Composed `Chart` objects handle standalone HTML export, static image export
(PNG/JPEG/WebP/SVG/PDF), notebook display, and memory reporting directly. The
internal engine object a chart compiles to is reachable via `chart.figure()` as
an advanced escape hatch, but it is not part of the public chart-building
surface.

Charts accept `width="100%"` and/or `height="100%"` for responsive layouts.
Standalone `to_html(...)` needs no browser dependency. Every static image
format — PNG, JPEG, WebP, SVG, PDF — is produced natively, without a browser.

`Engine` has three members — `auto`, `default`, `chromium` — and the entry
points split on their default. `to_png(...)` defaults to `Engine.default`, the
browser-free native rasterizer; `to_svg(...)` takes no `engine` argument at all
and is always native. The unified `to_image(...)` / `write_image(...)` entry
points default to `Engine.auto`, which resolves deterministically per request:
native for every format, chromium only when `custom_css=` is passed, since
author CSS needs a real CSS engine. `to_png(..., engine=Engine.chromium)` uses
an installed Chrome, Chromium, Edge, or `chrome-headless-shell` executable
because it screenshots
the same standalone HTML document for browser CSS/WebGL fidelity. Automatic
discovery can be overridden with `XYG_BROWSER`. Native raster export
intentionally rejects browser-only stylesheets, and SVG is native-only:
resolving to a browser engine for SVG — by `engine=Engine.chromium` or by
`custom_css=` — raises, because a screenshot cannot emit vector SVG.

## Chart Family Quick Reference

| Chart family | Composition API |
|---|---|
| Line | `xyg.line_chart(xyg.line(...))` |
| Scatter | `xyg.scatter_chart(xyg.scatter(...))` |
| Area | `xyg.area_chart(xyg.area(...))` |
| Histogram | `xyg.histogram_chart(xyg.histogram(...))` or `xyg.hist(...)` |
| Bar | `xyg.bar_chart(xyg.bar(...))` |
| Column | `xyg.column_chart(xyg.column(...))` |
| Grouped bars | `xyg.bar_chart(xyg.bar(..., mode="grouped"))` |
| Stacked bars | `xyg.bar_chart(xyg.bar(..., mode="stacked"))` |
| Normalized bars | `xyg.bar_chart(xyg.bar(..., mode="normalized"))` |
| Horizontal bars | `xyg.bar_chart(xyg.bar(..., orientation="horizontal"))` |
| Heatmap | `xyg.heatmap_chart(xyg.heatmap(...))` |
| Error bars/bands | `xyg.errorbar_chart(xyg.errorbar(...))` and `xyg.error_band_chart(xyg.error_band(...))` |
| Box | `xyg.box_chart(xyg.box(...))` |
| Violin | `xyg.violin_chart(xyg.violin(...))` |
| ECDF | `xyg.ecdf_chart(xyg.ecdf(...))` |
| Hexbin | `xyg.hexbin_chart(xyg.hexbin(...))` |
| Contour | `xyg.contour_chart(xyg.contour(...))` |
| Step/stairs/stem | `xyg.step_chart(xyg.step(...))`, `xyg.stairs_chart(xyg.stairs(...))`, `xyg.stem_chart(xyg.stem(...))` |
| Independent segments | `xyg.segments_chart(xyg.segments(x0=..., y0=..., x1=..., y1=...))` |
| Triangle mesh | `xyg.triangle_mesh_chart(xyg.triangle_mesh(...))` |
| Facets | `xyg.facet_chart(xyg.scatter(...), by="group", data=data)` |

## Axes And Scales

```python
import numpy as np
import xyg

x = np.logspace(0, 6, 240)
rank = 96 - np.log10(x) * 11.5
conversion = 0.08 + np.log10(x) * 0.035

chart = xyg.chart(
    xyg.line(x=x, y=rank, name="rank", color="#2563eb"),
    xyg.line(x=x, y=conversion, y_axis="y2", name="conversion", color="#dc2626"),
    xyg.x_axis(label="request volume", type_="log", domain=(1, 1_000_000), format=",.0f"),
    xyg.y_axis(label="rank (reversed)", domain=(0, 100), reverse=True, format=".0f"),
    xyg.y_axis(id="y2", label="conversion", side="right", domain=(0, 0.35), format=".0%"),
    title="Axes and scales",
)
chart
```

## Small Business Chart

```python
import xyg

month_number = [1, 2, 3, 4, 5, 6]
revenue = [42, 45, 48, 51, 55, 59]
pipeline = [35, 38, 42, 40, 46, 50]

chart = xyg.line_chart(
    xyg.line(month_number, revenue, name="revenue", color="#2563eb", width=2.0),
    xyg.line(month_number, pipeline, name="pipeline", color="#16a34a", width=2.0),
    xyg.x_axis(label="month number"),
    xyg.y_axis(label="USD thousands"),
    title="Revenue vs pipeline",
)
chart
```

## Line

```python
import numpy as np
import xyg

rng = np.random.default_rng(0)
x = np.arange(1_000_000, dtype=np.float64)
y = np.cumsum(rng.normal(size=len(x)))

chart = xyg.line_chart(
    xyg.line(x, y, name="walk"),
    xyg.x_axis(label="sample"),
    xyg.y_axis(label="value"),
    title="Random walk",
)
chart
```

## Scatter

```python
import numpy as np
import xyg

rng = np.random.default_rng(1)
x = rng.normal(size=500_000)
y = 0.5 * x + rng.normal(scale=0.6, size=len(x))

xyg.scatter_chart(
    xyg.scatter(
        x,
        y,
        color=y,
        size=np.abs(y),
        colormap="viridis",
        size_range=(2, 14),
    ),
    title="Correlated scatter",
)
```

## Area

```python
import numpy as np
import xyg

x = np.linspace(0, 10, 100_000)
y = np.sin(x) + 0.15 * x

xyg.area_chart(
    xyg.area(x, y, base=0.0, name="signal", opacity=0.35),
    title="Area",
)
```

## Histogram

```python
import numpy as np
import xyg

rng = np.random.default_rng(2)
values = np.concatenate(
    [rng.normal(-1.2, 0.45, 300_000), rng.normal(1.4, 0.6, 200_000)]
)

xyg.histogram_chart(
    xyg.histogram(values, bins=240, name="samples"),
    title="Distribution",
)
```

Pass `cumulative=True` to accumulate bins left-to-right. Combined with
`density=True` this is the empirical CDF, whose last bin is ~1.0:

```python
import numpy as np
import xyg

rng = np.random.default_rng(3)
latency_ms = rng.gamma(shape=2.0, scale=40.0, size=100_000)

xyg.histogram_chart(
    xyg.hist(latency_ms, bins=200, density=True, cumulative=True, name="p(x)"),
    xyg.x_axis(label="ms"),
    xyg.y_axis(label="fraction"),
    title="Latency CDF",
)
```

## Bar

```python
import xyg

channels = ["Search", "Ads", "Email", "Direct", "Partner", "Social"]
conversions = [120, 94, 72, 66, 43, 31]

xyg.bar_chart(
    xyg.bar(channels, conversions, name="Desktop"),
    xyg.x_axis(label="channel"),
    xyg.y_axis(label="count"),
    title="Conversions",
)
```

## Column

```python
import xyg

quarters = ["Q1", "Q2", "Q3", "Q4"]
revenue = [42, 47, 51, 58]

xyg.column_chart(
    xyg.column(quarters, revenue, name="Revenue"),
    xyg.x_axis(label="quarter"),
    xyg.y_axis(label="revenue"),
    title="Quarterly revenue",
)
```

## Grouped Bars

```python
import numpy as np
import xyg

channels = ["Search", "Ads", "Email", "Direct", "Partner", "Social"]
values = np.array(
    [
        [120, 88, 42],
        [94, 76, 39],
        [72, 55, 26],
        [66, 48, 31],
        [43, 29, 19],
        [31, 22, 14],
    ],
    dtype=float,
)

xyg.bar_chart(
    xyg.bar(
        channels,
        values,
        mode="grouped",
        series=["Desktop", "Mobile", "Tablet"],
    ),
    title="Grouped channels",
)
```

## Stacked Bars

```python
import numpy as np
import xyg

quarters = ["Q1", "Q2", "Q3", "Q4"]
values = np.array(
    [
        [42, 21, 13],
        [47, 25, 16],
        [51, 29, 18],
        [58, 31, 22],
    ],
    dtype=float,
)

xyg.bar_chart(
    xyg.bar(
        quarters,
        values,
        mode="stacked",
        series=["Product", "Services", "Partners"],
    ),
    title="Stacked revenue",
)
```

## Normalized Stacked Bars

`mode="normalized"` divides every stack by its per-category total, so each
category renders the series' share of the whole (segments sum to 1):

```python
import numpy as np
import xyg

quarters = ["Q1", "Q2", "Q3", "Q4"]
values = np.array(
    [
        [42, 21, 13],
        [47, 25, 16],
        [51, 29, 18],
        [58, 31, 22],
    ],
    dtype=float,
).T

xyg.bar_chart(
    xyg.bar(
        quarters,
        values,
        mode="normalized",
        series=["Product", "Services", "Partners"],
    ),
    xyg.y_axis(label="share"),
    title="Revenue mix",
)
```

## Horizontal Bars

```python
import xyg

teams = ["Platform", "Growth", "Data", "Support"]
latency_ms = [42, 56, 31, 73]

xyg.bar_chart(
    xyg.bar(
        teams,
        latency_ms,
        orientation="horizontal",
        name="latency",
    ),
    title="Median latency",
)
```

## Heatmap

```python
import numpy as np
import xyg

x = np.linspace(-3, 3, 160)
y = np.linspace(-2, 2, 120)
xx, yy = np.meshgrid(x, y)
z = np.exp(-(xx**2 + yy**2)) + 0.3 * np.exp(-((xx - 1.5) ** 2 + (yy + 0.8) ** 2))

xyg.heatmap_chart(
    xyg.heatmap(z, x=x, y=y),
    xyg.x_axis(label="x"),
    xyg.y_axis(label="y"),
    title="Heatmap",
)
```

## Statistical, Density, And Facet Charts

The statistical marks keep their source arrays in the canonical column store,
then ship compact segment, rectangle, or occupied-bin geometry:

```python
import xyg

x = [0, 1, 2, 3]
lower = [0.8, 1.1, 1.4, 1.9]
upper = [1.2, 1.8, 2.1, 2.8]
y = [1.0, 1.4, 1.7, 2.3]
stderr = [0.1, 0.15, 0.12, 0.2]
control = [0.8, 1.0, 1.1, 1.3]
treatment = [1.1, 1.4, 1.6, 1.9]

chart = xyg.chart(
    xyg.error_band(x, lower, upper, name="confidence"),
    xyg.errorbar(x, y, yerr=stderr, name="estimate"),
    xyg.box(values=[control, treatment], x=["control", "treatment"]),
    xyg.violin(values=[control, treatment], x=["control", "treatment"]),
    xyg.ecdf(values=control, bins=256),
    xyg.x_axis(label="group"),
    xyg.y_axis(label="value"),
)
chart
```

For dense point data, `hexbin` uses the native 2-D bin kernel and `contour`
uses bounded regular-grid marching squares. `step`, `stairs`, and `stem`
provide the common discrete-series variants without changing the line/segment
transport model.

Small multiples repeat a composition over a table column and share domains by
default:

```python
import xyg

data = {
    "x": [0, 1, 2, 0, 1, 2],
    "y": [1, 2, 3, 3, 2, 1],
    "region": ["west", "west", "west", "east", "east", "east"],
}

grid = xyg.facet_chart(
    xyg.scatter(x="x", y="y", density=None),
    by="region",
    data=data,
    cols=3,
    share_x=True,
    share_y=True,
)
grid
```

Each panel retains the normal screen-bounded payload and can also be exported
as SVG or a browser-free native PNG grid.

## Composition API

Marks resolve column names through `data=`, so charts can bind straight to a
dict, DataFrame, or any mapping of columns:

```python
import xyg

data = {
    "channel": ["Search", "Ads", "Email", "Direct"],
    "desktop": [120, 94, 72, 66],
}

chart = xyg.bar_chart(
    xyg.bar(x="channel", y="desktop", data=data, name="Desktop"),
    xyg.x_axis(label="channel"),
    xyg.y_axis(label="conversions"),
    xyg.legend(),
    title="Composed bar chart",
)
chart
```

Composed `Chart` objects expose `to_html(...)`, `html(...)`, `_repr_html_()`,
`to_png(...)`, `to_svg(...)`, `to_image(...)`, `write_image(...)`, `widget()`,
`show()`, and `memory_report()` readout methods directly. `show(display=...)`
picks the notebook host — `"widget"`, `"html"`, or auto, which falls back to
the standalone-HTML iframe only on WASM kernels (JupyterLite/Pyodide), where a
prebuilt frontend cannot load the anywidget extension; Marimo's WASM build
bundles its own anywidget frontend and keeps the widget host
(design/reflex-shaped-api.md §3.3).
`to_image(format="png", ...)` returns bytes and `write_image(path, ...)` writes
one file atomically with the format inferred from its extension; together they
are the unified export surface across PNG/JPEG/WebP/SVG/PDF (and standalone
HTML for `write_image`). `xyg.write_images(figs, paths)` is the batch form: it
accepts composed charts directly and shares one persistent Chromium session
across every browser-resolved file instead of paying browser startup per
figure.

Export defaults travel with the chart. `xyg.export_config(...)` is a chart child
taking `formats`, `filename`, `width`, `height`, `scale`, `background`, and
`quality`; it sets the browser modebar's download menu (the client-safe subset
png/jpeg/webp/svg/csv, in the given order — an empty list hides the menu) and
supplies the `width`/`height`/`scale`/`background`/`quality` defaults for any
of those arguments omitted from `to_image`, `write_image`, or that chart's
files in `write_images`. Explicit arguments override them.

## Live Data On A Composed Chart

The data plane of a `Chart` is live — stream new points and read exact rows
or selections from Python. Structure stays declarative: adding marks, axes,
or annotations means composing a new chart.

```python
import xyg

chart = xyg.scatter_chart(
    xyg.scatter(x=[0.0, 1.0, 2.0, 3.0], y=[0.0, 2.0, 4.0, 6.0], name="stream"),
    xyg.x_axis(label="t"),
    xyg.y_axis(label="value"),
)

# Streaming append: extends the trace in place. With a live widget the
# client refreshes; headless, the next widget()/to_html() ships the
# streamed state (already-exported HTML files are snapshots).
chart.append(0, [4.0], [8.0])

# Exact source-row readout from the canonical f64 store.
row = chart.pick(0, 4)
assert row["x"] == 4.0 and row["y"] == 8.0

# Python-side box select: the same Selection object on_select receives.
selection = chart.select_range(0.5, 3.5, 0.0, 10.0)
assert len(selection) == 3
xs, ys = selection.xy(0)
chart
```

## Layered Composition And Annotations

Use the neutral `xyg.chart(...)` container when marks need to share a panel.
Children are painted in order, and rules, bands, and text annotations live in
the chart chrome instead of becoming data traces.

```python
import xyg

data = {
    "month": ["Jan", "Feb", "Mar", "Apr"],
    "actual": [12, 18, 16, 22],
    "target": [14, 15, 17, 20],
    "sample": [13, 19, 15, 23],
}

chart = xyg.chart(
    xyg.bar(x="month", y="actual", data=data, name="actual", color="#f59e0b"),
    xyg.scatter(x="month", y="sample", data=data, name="samples", color="#2563eb", size=8),
    xyg.line(x="month", y="target", data=data, name="target", color="#dc2626", width=2),
    xyg.x_band("Feb", "Apr", text="campaign", color="#7c3aed", opacity=0.12),
    xyg.vline("Mar", text="release", color="#7c3aed"),
    xyg.x_axis(label="month"),
    xyg.y_axis(label="pipeline"),
    xyg.tooltip(
        fields=["month", "actual", "sample", "target"],
        title="{month}",
        format={"actual": ".1f", "sample": ".1f", "target": ".1f"},
    ),
    xyg.legend(),
    title="Layered pipeline",
)
chart
```

```python
import xyg

z = [
    [0.2, 0.4, 0.5],
    [0.5, 0.7, 0.9],
]

chart = xyg.chart(
    xyg.heatmap(z=z, x=["Mon", "Tue", "Wed"], y=["AM", "PM"], name="load"),
    xyg.hline("PM", text="busy threshold", color="#dc2626", width=2),
    xyg.text("Wed", "PM", "peak", dx=8, dy=-8, color="#111827"),
    xyg.arrow("Mon", "AM", "Tue", "PM", text="ramp", color="#7c3aed"),
    xyg.callout("Wed", "PM", "ops review", dx=-72, dy=-26, color="#0f172a"),
    xyg.x_axis(label="day"),
    xyg.y_axis(label="shift"),
    title="Annotated heatmap",
)
chart
```

## Framework Chrome Hooks

Legend and tooltip nodes can carry opaque framework components for adapters
without making `xy` depend on that framework. The objects are kept on
the Python `Chart` and never serialized into standalone HTML.

```python
import xyg

# In a Reflex app these could be rx.box(...), rx.vstack(...), etc.
class FrameworkComponent:
    pass


data = {"x": [1.0, 2.0], "y": [2.0, 3.0], "segment": ["enterprise", "growth"]}
custom_legend = FrameworkComponent()
custom_tooltip = FrameworkComponent()

chart = xyg.chart(
    xyg.scatter(x="x", y="y", color="segment", data=data),
    xyg.legend(custom_legend, show=False),
    xyg.tooltip(custom_tooltip, show=False, fields=["x", "y", "segment"]),
)

chrome = chart.chrome_components()
# {"legend": custom_legend, "tooltip": custom_tooltip}
chart
```

`show=False` disables the built-in DOM legend/tooltip for adapter replacement.
Leaving it at the default keeps the safe built-in fallback for notebooks and
standalone `.html` export.
The returned chrome object is a keyed slot map; framework adapters should mount
`chrome["legend"]` and `chrome["tooltip"]` by name beside the chart container.
