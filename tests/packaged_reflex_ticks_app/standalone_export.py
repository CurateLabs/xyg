"""Produce the public standalone document with the selected installed wheel."""

import sys

import numpy as np

import xyg

values = np.linspace(0.0, 1.0, 30_000)
chart = xyg.scatter_chart(
    xyg.scatter(values, values, density=True),
    xyg.x_axis(domain=(0.0, 1.0)),
    xyg.y_axis(domain=(0.0, 1.0)),
    width=480,
    height=360,
)
chart.to_html(sys.argv[1])
