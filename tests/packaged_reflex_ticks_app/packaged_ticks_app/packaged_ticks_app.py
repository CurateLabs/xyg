"""Actual XYChart mounts, using only the installed xyg wheel and Reflex."""

import math

import numpy as np
import reflex as rx

import reflex_xy
import xyg

_density_values = np.linspace(0.0, 1.0, 30_000)
_density_token = reflex_xy.inline(
    xyg.scatter_chart(
        xyg.scatter(_density_values, _density_values, color=_density_values, density=True),
        xyg.x_axis(domain=(0.0, 1.0)),
        xyg.y_axis(domain=(0.0, 1.0)),
        width=560,
        height=440,
    )
)


def page(kind):
    if kind == "polar":
        chart = xyg.polar_chart(
            xyg.line([0.0, math.pi / 2, math.pi], [1.0, 2.0, 3.0]),
            xyg.theta_axis(),
            xyg.r_axis(domain=(0.0, 4.0)),
            width=560,
            height=440,
        )
    else:
        children = [
            xyg.line([0.0, 0.5, 1.0], [0.0, 2.0, 1.0]),
            xyg.x_axis(domain=(0.0, 1.0), format=".1f"),
            xyg.y_axis(domain=(0.0, 4.0), format=".1f"),
        ]
        if kind == "secondary":
            children.extend(
                [
                    xyg.line([0.0, 0.5, 1.0], [100.0, 200.0, 300.0], y_axis="y2"),
                    xyg.y_axis(id="y2", side="right", domain=(0.0, 400.0), format=".1f"),
                ]
            )
        chart = xyg.line_chart(*children, width=560, height=440)
    return rx.box(
        reflex_xy.chart(chart, id=f"packaged-{kind}", height="440px"),
        rx.link("Unmount chart", href="/empty", id="unmount-chart"),
        width="560px",
    )


def primary():
    return page("primary")


def secondary():
    return page("secondary")


def polar():
    return page("polar")


def density():
    return rx.box(
        reflex_xy.chart(_density_token, id="packaged-density", height="440px"),
        rx.link("Unmount chart", href="/empty", id="unmount-chart"),
        width="560px",
    )


app = rx.App()
app.add_page(primary, route="/")
app.add_page(secondary, route="/secondary")
app.add_page(polar, route="/polar")
app.add_page(density, route="/density")
app.add_page(lambda: rx.text("Chart unmounted", id="empty-page"), route="/empty")
reflex_xy.setup(app)
