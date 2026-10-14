---
title: Colorbars in Python
description: Author, orient, and style built-in continuous-scale colorbars or replace them in a custom adapter.
components:
  - xyg.colorbar
---

# Colorbars in Python

A colorbar explains a continuous color scale. Add `xyg.colorbar()` after a
compatible continuous-color mark and XYG derives the validated domain,
colormap, and a useful title from that mark. The built-in colorbar renders in
the browser, SVG, native PNG, and Chromium PNG.

## Built-in declarative colorbars

The two orientations share the same title and explicit-tick API. Browser DOM
chrome additionally exposes the class and slot styling shown here:

~~~python demo exec native
import xyg

vertical_scale = xyg.heatmap_chart(
    xyg.heatmap([[-2.0, 0.0], [2.0, 4.0]], name="temperature", colormap="coolwarm", domain=(-3, 5)),
    xyg.colorbar(title="Temperature (°C)", ticks=[-3, 0, 5], class_name="rounded-lg bg-white/90"),
    styles={
        "colorbar_bar": {"border_radius": 5},
        "colorbar_tick": {"color": "#475569"},
        "colorbar_title": {"font_weight": 700},
    },
    title="Vertical scale",
)
horizontal_scale = xyg.scatter_chart(
    xyg.scatter(
        [0, 1, 2, 3], [2, 5, 3, 8], color=[0.1, 0.4, 0.7, 1.0], colormap="viridis", size=12
    ),
    xyg.colorbar(title="Confidence", orientation="horizontal", ticks=[0.1, 0.5, 1.0]),
    title="Horizontal scale",
)
~~~

The last compatible continuous mark wins when a chart layers several scales. XYG
derives colorbars for heatmaps, continuous scatter, hexbin, contour,
continuous segments, and triangle meshes. A field or mark name supplies the
default title; `title=` overrides it, `ticks=` supplies finite tick positions,
and `orientation=` accepts `"vertical"` or `"horizontal"`.

XYG deliberately emits no built-in colorbar for constant or categorical color,
RGB(A) heatmaps, or density-tier scatter whose per-row color channel is not
resident in the browser. `colorbar(show=False)` removes an inferred scale.
`xyg.pyplot` has its own Matplotlib-shaped colorbar-authoring API.

### Pinning the scale with a fixed domain

Passing an explicit mark `domain=` pins the colorbar to a known range instead
of the data extent, so the scale stays comparable across refreshes:

~~~python demo exec native
import numpy as np
import xyg

rng_load = np.random.default_rng(7)
cpu_load = (rng_load.random((6, 6)) * 60 + 20).round(1)
pinned_scale = xyg.heatmap_chart(
    xyg.heatmap(cpu_load, name="load", colormap="magma", domain=(0, 100)),
    xyg.colorbar(title="Load (%)", ticks=[0, 25, 50, 75, 100]),
    title="Pinned 0–100 scale",
)


def pinned_domain_colorbar():
    return pinned_scale
~~~

### Derived scales on hexbin and layered marks

A hexbin's aggregated counts feed the colorbar just like any continuous
channel, and when several continuous marks are layered the colorbar derives
from the last compatible one — here the stations scatter (0–50 PPM on
viridis), not the heatmap beneath it:

~~~python demo exec native
import numpy as np
import xyg

rng_bins = np.random.default_rng(21)
hexbin_density = xyg.hexbin_chart(
    xyg.hexbin(
        rng_bins.normal(0.0, 1.0, 400),
        rng_bins.normal(0.0, 1.0, 400),
        gridsize=12,
        colormap="plasma",
    ),
    xyg.colorbar(title="Points per bin", orientation="horizontal"),
    title="Horizontal hexbin scale",
)
rng_layers = np.random.default_rng(3)
layered_scales = xyg.heatmap_chart(
    xyg.heatmap([[4.0, 9.0], [14.0, 22.0]], name="model grid", colormap="cividis", domain=(0, 25)),
    xyg.scatter(
        rng_layers.uniform(0.0, 1.0, 12),
        rng_layers.uniform(0.0, 1.0, 12),
        color=(rng_layers.random(12) * 40 + 10).round(1),
        colormap="viridis",
        color_domain=(0, 50),
        size=12,
        name="stations",
    ),
    xyg.colorbar(title="Station PPM"),
    title="Last compatible mark wins",
)
~~~

## Framework-owned replacement

`render=` (or one positional child) remains an opaque integration hook:

~~~python
import xyg

# An opaque stand-in for a component owned and mounted by your application.
custom_component = object()
chart = xyg.scatter_chart(
    xyg.scatter([1, 2, 3], [3, 5, 4], color=[0.2, 0.8, 1.4]),
    xyg.colorbar(render=custom_component),
)

replacement = chart.chrome_components()["colorbar"]
assert replacement is custom_component
~~~

Core XYG stores that object but does not mount it. A host adapter must read
`chart.chrome_components()` and mount the returned component; standalone HTML, SVG, and PNG ignore the opaque replacement.

## Styling slots

Seven chart slots target every visible part of built-in browser colorbar
chrome: `colorbar`, `colorbar_bar`, `colorbar_tick`, `colorbar_title`,
`colorbar_extension`, `colorbar_line`, and `colorbar_minor_tick`.

The declarative `xyg.colorbar()` API creates the container, gradient bar, major
ticks, and title shown below. The Matplotlib-shaped `xyg.pyplot` colorbar API can
add contour-line and minor-tick nodes. It creates separate
`colorbar_extension` triangles only for an extended, line-only contour
colorbar; filled-contour extensions are painted as part of `colorbar_bar`
instead. These remain stable CSS/Tailwind targets whenever their nodes are
present, but listing their classes on a plain declarative colorbar would not
create them.

~~~python
chart = xyg.scatter_chart(
    xyg.scatter([1, 2, 3], [3, 5, 4], color=[0.2, 0.8, 1.4]),
    xyg.colorbar(title="Intensity"),
    class_names={
        "colorbar_title": "font-semibold",
    },
    styles={
        "colorbar_bar": {"border_radius": 4},
        "colorbar_tick": {"font_size": 10},
    },
)
~~~

See [Marks and components reference](/docs/xy/api-reference/marks-and-components/)
for the complete signature.

## FAQ

### How do I add a color scale to a chart in Python?

Add `xyg.colorbar()` as a chart child after a continuous-color mark such as a
heatmap or a scatter with a numeric `color=` channel. XYG derives the validated
domain, colormap, and a default title from that mark, and the built-in colorbar
renders in the browser, SVG, native PNG, and Chromium PNG.

### How do I set custom ticks and a title on a colorbar?

Pass them to the component: `xyg.colorbar(title="Temperature (°C)", ticks=[-3, 0, 5])`.
`title=` overrides the default title derived from the field or mark name, and
`ticks=` supplies explicit finite tick positions; both work in either
orientation.

### Can I make the colorbar horizontal instead of vertical?

Yes — `xyg.colorbar(orientation="horizontal")`. The `orientation=` option
accepts `"vertical"` (the default) or `"horizontal"`, and both orientations
share the same `title` and `ticks` API.

### Why is no colorbar showing on my chart?

XYG only derives colorbars for continuous-color marks: heatmaps, continuous
scatter, hexbin, contour, continuous segments, and triangle meshes. Constant or
categorical color, RGB(A) heatmaps, and density-tier scatter whose per-row
color channel is not resident in the browser deliberately get no built-in
colorbar. When several continuous scales are layered, the last compatible mark
wins, and `xyg.colorbar(show=False)` removes an inferred scale you don't want.
