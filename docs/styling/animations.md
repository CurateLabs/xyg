---
title: Animations and Data Transitions
description: Animate entrances, keyed replacements, reorders, exits, and streaming appends with reduced-motion and deterministic-export control.
components:
  - xyg.animation
  - xyg.spring
---

# Animations and Data Transitions

Add `xyg.animation()` as a chart child to give initial render and later live-data
refreshes one declarative motion policy. The browser owns the clock and GPU
interpolation; Python receives only optional start/end lifecycle events.

~~~python demo exec toggle preview-code id=animation-entrance-demo native
# Static snapshot: Python callbacks and data updates require an application host.
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
solar_panels = [2890, 2756, 3322, 3470, 3475, 3129, 3490, 2903, 2643, 2837, 2954, 3239]
inverters = [2338, 2103, 2194, 2108, 1812, 1726, 1982, 2012, 2342, 2473, 3848, 3736]
import xyg

chart = xyg.chart(
    xyg.column(
        months,
        solar_panels,
        key=months,
        name="Solar panels",
        color="#2b7fff",
        corner_radius=0,
        stroke_width=0,
    ),
    xyg.line(
        months, inverters, key=months, name="Inverters", color="#fe9a00", width=2, curve="linear"
    ),
    xyg.animation(
        enabled="auto",
        duration=650,
        easing=xyg.spring(stiffness=150, damping=22),
        match="key",
        enter="auto",
        update="interpolate",
    ),
    xyg.legend(show=False),
    xyg.tooltip(title="{x}", format={"y": ",.0f"}),
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
        plot_background="var(--recipe-surface, #ffffff)",
        grid_color="var(--recipe-grid, #e5e7eb)",
        text_color="var(--recipe-text, #4b5563)",
    ),
    class_name="bg-[#ffffff] [--recipe-surface:#ffffff] [--recipe-grid:#e5e7eb] [--recipe-text:#4b5563] dark:bg-[#000000] dark:[--recipe-surface:#000000] dark:[--recipe-grid:#27272a] dark:[--recipe-text:#d4d4d8]",
    class_names={"tooltip": "rounded-lg bg-zinc-950 px-3 py-2 text-white shadow-xl"},
    width="100%",
    height=280,
    padding=[16, 20, 20, 20],
)
~~~

`enabled="auto"` is the recommended default: it animates normally and renders
the final state immediately when the browser reports reduced motion. Use
`enabled=False` to suppress motion or `enabled=True` only when the application
intentionally overrides that preference.

## Initial render

`enter="auto"` chooses a mark-aware entrance:

- Line, area, and error bands reveal along their path.
- Bars and columns grow from their baseline.
- Scatter points scale from zero; error bars grow from their centers.

Set `enter` explicitly to `none`, `scale`, `grow`, or `reveal` when a shared
chart needs a different visual language.

~~~python demo exec toggle preview-code id=animation-area-reveal-demo native
# Static snapshot: Python callbacks and data updates require an application host.
weeks = list(range(1, 13))
active_teams = [28, 32, 31, 38, 43, 41, 49, 55, 53, 61, 66, 72]
import xyg

chart = xyg.area_chart(
    xyg.area(
        weeks,
        active_teams,
        base=0,
        name="This period",
        color="#8e51ff",
        fill="linear-gradient(#8e51ff4d 5%, #8e51ff00 95%)",
        opacity=1,
        curve="smooth",
        line_width=2,
    ),
    xyg.animation(
        delay=80, duration=900, enter="reveal", easing=xyg.spring(stiffness=120, damping=24)
    ),
    xyg.tooltip(title="Week {x}", format={"y": ",.0f"}),
    xyg.legend(show=False),
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
        domain=(0, 80),
        style={
            "axis_width": 0,
            "axis_color": "#00000000",
            "tick_width": 0,
            "tick_color": "#00000000",
            "tick_label_color": "#00000000",
            "label_color": "#00000000",
        },
    ),
    width="100%",
    height=410,
    padding=(16, 20, 20, 20),
)
~~~

Named easings are `linear`, `ease`, `ease-in`, `ease-out`, and `ease-in-out`.
A four-number tuple supplies a cubic Bézier; `xyg.spring(stiffness=...,
damping=..., mass=...)` supplies a bounded spring policy.

## Replacement, reorder, insert, and delete

Live host refreshes and notebook append updates change the mounted
chart in place. This static preview shows the initial accounts. In a live
application, update the data to reorder retained accounts, insert or remove
accounts, and change their values. Stable keys let XYG distinguish each case:

~~~python demo exec toggle preview-code id=animation-keyed-update-demo native
# Static snapshot: Python callbacks and data updates require an application host.
import xyg


class KeyedAnimationDemo:
    updated: bool = False

    def sales(self):
        before = {
            "account_id": ["atlas", "boreal", "cinder", "dune", "ember"],
            "region": ["North", "South", "West", "East", "Central"],
            "sales": [18, 42, 27, 50, 33],
        }
        after = {
            "account_id": ["cinder", "foxtrot", "atlas", "ember", "gale"],
            "region": ["West", "Coastal", "North", "Central", "International"],
            "sales": [54, 16, 46, 22, 60],
        }
        rows = after if self.updated else before
        return xyg.column_chart(
            xyg.column(
                x="region",
                y="sales",
                key="account_id",
                data=rows,
                color="#2b7fff",
                corner_radius=0,
                stroke_width=0,
            ),
            xyg.animation(
                match="key",
                duration=750,
                easing=xyg.spring(stiffness=150, damping=22),
                enter="auto",
                update="interpolate",
            ),
            xyg.legend(show=False),
            xyg.tooltip(title="{x}", format={"y": ",.0f"}),
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
                domain=(0, 65),
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
                plot_background="var(--keyed-surface, #ffffff)",
                grid_color="var(--keyed-grid, #e5e7eb)",
                text_color="var(--keyed-text, #4b5563)",
            ),
            class_name="bg-[#ffffff] [--keyed-surface:#ffffff] [--keyed-grid:#e5e7eb] [--keyed-text:#4b5563] dark:bg-[#000000] dark:[--keyed-surface:#000000] dark:[--keyed-grid:#27272a] dark:[--keyed-text:#d4d4d8]",
            class_names={"tooltip": "rounded-lg bg-zinc-950 px-3 py-2 text-white shadow-xl"},
            width="100%",
            height=320,
            padding=[16, 20, 20, 20],
        )


initial_chart = KeyedAnimationDemo().sales()
~~~

`key=` accepts an array or a `data=` column name on line, area, scatter, bar,
column, error-band, and errorbar marks. Values must be present, supported,
unique, and the same length as the logical rows. XYG validates these conditions
before rendering. For a replacement without stable identity, choose
`match="index"` explicitly.

| Mode | Use when |
| --- | --- |
| `key` | Rows can reorder, appear, or disappear and have a stable business ID |
| `append` | An ordered time series retains old x values and adds a tail |
| `index` | Row order itself is the identity |

Each mark may override the chart policy or opt out. The override cascades field
by field, so a mark only changes what it names — `xyg.animation(duration=90)` on
a mark keeps the chart's `match`, `easing`, and everything else:

~~~python demo exec toggle preview-code id=animation-mark-override-demo native
# Static snapshot: Python callbacks and data updates require an application host.
rows = {
    "x": [0, 1, 2, 3, 4, 5],
    "low": [8, 10, 9, 13, 12, 15],
    "high": [16, 18, 17, 21, 20, 24],
    "mean": [12, 14, 13, 17, 16, 20],
}
import xyg

chart = xyg.chart(
    xyg.area(
        "x",
        "high",
        base="low",
        data=rows,
        color="#2b7fff",
        fill="linear-gradient(#2b7fff4d 5%, #2b7fff00 95%)",
        opacity=1,
        curve="smooth",
        animation=False,
    ),
    xyg.line(
        "x",
        "mean",
        data=rows,
        color="#2b7fff",
        width=2,
        curve="smooth",
        animation=xyg.animation(duration=850, enter="reveal"),
    ),
    xyg.animation(duration=500, enter="auto"),
    xyg.legend(show=False),
    xyg.tooltip(title="Sample {x}", format={"y": ",.0f"}),
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
        domain=(0, 26),
        style={
            "axis_width": 0,
            "axis_color": "#00000000",
            "tick_width": 0,
            "tick_color": "#00000000",
            "tick_label_color": "#00000000",
            "label_color": "#00000000",
        },
    ),
    width="100%",
    height=320,
    padding=[16, 20, 20, 20],
)
~~~

## Streaming append

Use append matching for a live ordered series. Existing x values retain their
identity while the new tail enters, and append's normal viewport policy still
applies: home follows the domain, a live-edge view slides, and a user looking
at history stays put. This static preview shows the initial series; append
new batches from a notebook kernel or application host. The example's source
uses bounded random jitter when generating additional samples.

~~~python demo exec toggle preview-code id=animation-streaming-demo native
# Static snapshot: Python callbacks and data updates require an application host.
import math
import random
import xyg


class StreamingAnimationDemo:
    next_x: int = 2

    def sensor(self):
        return xyg.line_chart(
            xyg.line(
                [0.0, 1.0], [10.0, 12.0], name="Sensor", color="#8e51ff", width=2, curve="smooth"
            ),
            xyg.animation(match="append", duration=350, easing="linear"),
            xyg.legend(show=False),
            xyg.tooltip(title="Sample {x}", format={"y": ".2f"}),
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
                domain=(7, 15),
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
                plot_background="var(--stream-surface, #ffffff)",
                grid_color="var(--stream-grid, #e5e7eb)",
                text_color="var(--stream-text, #4b5563)",
            ),
            class_name="bg-[#ffffff] [--stream-surface:#ffffff] [--stream-grid:#e5e7eb] [--stream-text:#4b5563] dark:bg-[#000000] dark:[--stream-surface:#000000] dark:[--stream-grid:#27272a] dark:[--stream-text:#d4d4d8]",
            class_names={"tooltip": "rounded-lg bg-zinc-950 px-3 py-2 text-white shadow-xl"},
            width="100%",
            height=320,
            padding=[16, 20, 20, 20],
        )


initial_chart = StreamingAnimationDemo().sensor()
~~~

In a live notebook, use `chart.append(...)`; an application routes native
updates through its host transport. A full dataset replacement uses keyed or
index matching through the same browser controller.
Rapid updates are latest-wins: a new refresh begins at the currently displayed
position, closes the interrupted lifecycle as cancelled, and never queues an
unbounded chain of old scenes.

## Lifecycle callbacks

Live notebook hosts expose start/end events. Documentation previews show
compiled chart motion and do not run Python state or callback controls. Python callbacks are
configuration, not serialized chart data:

~~~python demo exec toggle preview-code id=animation-lifecycle-demo native
# Static snapshot: Python callbacks and data updates require an application host.
import xyg


class AnimationLifecycleDemo:
    shifted: bool = False
    status: str = "Ready"

    def points(self):
        x = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        y = [4, 8, 5, 10, 7, 3, 9, 6, 11] if self.shifted else [3, 5, 9, 6, 11, 8, 4, 10, 7]
        return xyg.scatter_chart(
            xyg.scatter(
                x, y, key=["a", "b", "c", "d", "e", "f", "g", "h", "i"], color="#8e51ff", size=14
            ),
            xyg.animation(match="key", duration=700, enter="scale"),
            xyg.legend(show=False),
            xyg.tooltip(title="Point {x}", format={"y": ",.0f"}),
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
                domain=(0, 12),
                style={
                    "axis_width": 0,
                    "axis_color": "#00000000",
                    "tick_width": 0,
                    "tick_color": "#00000000",
                    "tick_label_color": "#00000000",
                    "label_color": "#00000000",
                },
            ),
            width="100%",
            height=320,
            padding=[16, 20, 20, 20],
        )


initial_chart = AnimationLifecycleDemo().points()
~~~

Standalone HTML dispatches local `xy:animation_start` and
`xy:animation_end` DOM events. It has no Python process to invoke.

## Large data stays bounded

Key matching is intentionally limited to direct representations. Above the
matching limit, and for decimated lines or density grids, XYG snaps to the new
screen-bounded representation instead of constructing a browser map for every
canonical row. Density and level-of-detail (LOD) tier handoffs retain their separate
stale-while-refine blending and never flash blank.

Direct keyed payloads add two binary 32-bit key words per mark. Position
interpolation adds temporary start buffers only while the animation is active;
the previous scene and scratch buffers are freed at completion.
