---
title: Interactions and Selections
description: Configure hover, click, selection, brushing, crosshairs, callbacks, and linked views.
---

# Interactions and Selections

Interactive HTML and notebook charts support pan, zoom, hover, click,
selection, brushing, crosshairs, and view changes. Interaction settings control
browser behavior; callbacks decide whether a live Python process also receives
an event.

## Configure browser behavior

Set flags directly on a chart or compose an `interaction_config()` child:

~~~python demo exec native
import xyg

x = [0, 1, 2, 3]
y = [1, 3, 2, 5]
chart = xyg.area_chart(
    xyg.area(x, y, color="#6e56cf"),
    xyg.scatter(x, y, color="#6e56cf", size=6),
    xyg.interaction_config(hover=True, click=True, select=True, brush=True, crosshair=True),
)


def browser_behavior_demo():
    return chart
~~~

Standalone HTML keeps these local browser behaviors. It cannot invoke Python
because no kernel or server is attached.

Viewport DOM events are always available. Add ``on_view_change`` to a live
notebook when Python needs the semantic range events; there
is no separate transport configuration flag.

### Polar interaction boundary

Polar charts keep hover. Zoom is the one default that differs from Cartesian
charts: `zoom` resolves to `False` under `coords="polar"`. The center of a disc is
a fixed point of the polar transform and radial zoom pins the minimum, so zooming
in crops the outer ring rather than magnifying the chart around the cursor. That
is the wrong default for a composition read against an authored frame — a pie or
donut, whose value is the angle and whose radius is a constant rim, but also a
radial bar, gauge, or radar, where the radial extent *is* the value yet is read
against a fixed rim or shared domain that zoom would clip away.
`xyg.wind_rose()` is the exception and ships with zoom on, since its radius is a
frequency count and pulling the ring in magnifies the short sectors.

Opt back in per chart with `xyg.interaction_config(zoom=True)` (or `zoom=True` on
the chart) — an ordinary `polar_chart()` whose radius is measured data is the
expected case for this. Radial zoom then changes the maximum radius while holding
the minimum fixed, so zooming a disc does not unexpectedly create a hole and an
authored `hole` or `origin` remains stable.

While zoom is off, no gesture can move the view, so the *derived* reset-axis
policy is empty and reset is not part of the default polar contract either: with
no `reset_axes` authored, the modebar shows no zoom or reset controls and
double-click has nothing to restore. Zoom brings both back. An authored
`reset_axes` is honored regardless of the zoom switch, and grants reset — controls
and double-click alike — on its own; that is the right choice for a chart whose
view moves through linked axes or application state rather than a gesture. The
chart also leaves wheel events uncancelled while zoom is off, so the surrounding
page keeps scrolling under the cursor.

`default_drag_action` accepts only `"auto"` or `"none"` on a polar chart. The
other values name drag tools a disc does not have, so they raise at construction
instead of resolving to no tool at all.

Authored sectors are supported, but theta rotation/panning, interactive sector
zoom, box zoom, selection, brushing, and crosshairs are disabled until those
gestures have polar-native geometry. Polar charts do not expose the Pan button,
and interaction flags cannot opt one into an unsupported gesture.

See the [polar chart guide](/docs/xy/charts/polar-chart/#hover-and-zoom) for the
complete coordinate-system boundary.

## Handle chart events in Python

Core callbacks are ordinary Python functions called by a live notebook widget.
A generated documentation preview or standalone HTML file has no Python
callback connection.

```python
import xyg


def picked(row):
    print(row["trace"], row["index"], row["x"], row["y"])


def selected(selection: xyg.Selection):
    print(len(selection), selection.per_trace)


chart = xyg.scatter_chart(
    xyg.scatter([0, 1, 2, 3], [2, 4, 3, 5], size=7),
    on_click=picked,
    on_select=selected,
)
chart  # Display in a live notebook to receive callbacks.
```

`on_hover` and `on_click` receive resolved row dictionaries; `on_select`
receives an `xyg.Selection` grouped by trace. `on_brush` receives bounds or a
polygon; `on_view_change` receives the changed viewport ranges. See
[Events and callbacks](/docs/xy/api-reference/events-and-callbacks/).

## Exact readout and selection

A renderer may display a decimated line, density grid, or retained sample,
while a live native host retains canonical source rows. A notebook callback
can resolve the selected rows with `selection.xy(trace_id=0)`; use
`selection.per_trace` when trace identity matters. `chart.select_range()`
returns a `Selection` without requiring a browser gesture.

GraphForge selections use canonical graph UUIDs and contributing result rows.
Native webviews relay `xy:click` trace/index hits to `graphforgePick()`;
direct WASM GraphForge views dispatch `xy:graphforge-select`. Aggregate graph
edges expose membership rather than inventing one exact relationship. See
[Use with GraphForge](/docs/xy/integrations/graphforge/) for identity and host
routing, and the [limitations](/docs/xy/api-reference/limitations-and-alpha-status/)
for representation-specific interaction coverage.

## Linked views

Give related charts the same `link_group` and choose which axes participate:

~~~python demo exec native
import xyg

x = list(range(16))
overview_y = [2, 4, 3, 5, 4, 6, 5, 7, 6, 8, 7, 9, 8, 10, 9, 11]
detail_y = [20, 38, 31, 47, 42, 58, 51, 69, 63, 77, 72, 88, 81, 96, 91, 108]
overview = xyg.line_chart(
    xyg.line(x, overview_y, color="#6e56cf"), link_group="revenue", link_axes=("x",)
)
detail = xyg.scatter_chart(
    xyg.scatter(x, detail_y, color="#6e56cf", size=7), link_group="revenue", link_axes=("x",)
)
~~~

Pan or zoom changes propagate between mounted charts in that group. Linking
coordinates the view window; cross-filtering application data still belongs in
a widget callback or host-framework state. For complete dashboard patterns,
read [Dashboards and linked views](/docs/xy/guides/dashboards-and-linked-views/).
