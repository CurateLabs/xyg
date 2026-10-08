"""Offline seven-family geographic catalog; uv run python examples/geographic_catalog.py."""

from pathlib import Path

import numpy as np

import xyg


def column(kind, xy, *, offsets0=None, offsets1=None):
    source = dict(
        geometry=kind,
        crs=4326,
        xy=np.asarray(xy, dtype="<f8"),
        validity=np.ones(1 if kind != 1 else len(xy) // 2, dtype="u1"),
    )
    source["feature_ids"] = np.arange(len(source["validity"]), dtype="<u8") + 2**63
    if offsets0 is not None:
        source["offsets0"] = np.asarray(offsets0, dtype="<u4")
    if offsets1 is not None:
        source["offsets1"] = np.asarray(offsets1, dtype="<u4")
    return source


def label(text, coordinate):
    return [
        dict(
            feature_index=0,
            anchor=1,
            font_size=13.0,
            coordinate=coordinate,
            rgba=bytes([30, 45, 60, 255]),
            text=text,
        )
    ]


def geographic_catalog():
    points = column(1, [-110, 40, -90, 30, -100, 20])
    bubbles = column(1, [80, 40, 100, 30, 120, 20])
    routes = column(2, [-125, -20, -95, -35, -60, -20], offsets0=[0, 3])
    arcs = column(2, [55, -25, 115, -25], offsets0=[0, 2])
    polygon = column(
        3,
        [-50, 5, -10, 5, -10, 40, -50, 40, -50, 5, -40, 15, -20, 15, -20, 30, -40, 30, -40, 15],
        offsets0=[0, 2],
        offsets1=[0, 5, 10],
    )
    choropleth = column(3, [10, 5, 45, 5, 45, 40, 10, 40, 10, 5], offsets0=[0, 1], offsets1=[0, 5])
    density = column(
        1, np.array([(x, y) for x in range(-12, 13, 2) for y in range(-45, -24, 2)]).ravel()
    )
    return xyg.geo_chart(
        xyg.geo_layer(
            "density",
            source=density,
            layer_id=7,
            density=dict(columns=80, rows=60),
            legend_label="Density",
            labels=label("Density", [0, -50]),
        ),
        xyg.geo_layer(
            "points",
            source=points,
            layer_id=1,
            style=dict(fill=bytes([18, 110, 135, 255]), diameter=12.0),
            legend_label="Points",
            labels=label("Points", [-100, 52]),
        ),
        xyg.geo_layer(
            "bubbles",
            source=bubbles,
            layer_id=2,
            values=np.array([1.0, 3.0, 6.0]),
            value_domain=[0.0, 6.0],
            bubble_diameters=[8.0, 28.0],
            style=dict(fill=bytes([227, 124, 46, 230])),
            legend_label="Bubbles",
            labels=label("Bubbles", [100, 52]),
        ),
        xyg.geo_layer(
            "routes",
            source=routes,
            layer_id=3,
            style=dict(stroke=bytes([18, 110, 135, 255]), stroke_width=3.0),
            legend_label="Routes",
            labels=label("Routes", [-95, -45]),
        ),
        xyg.geo_layer(
            "arcs",
            source=arcs,
            layer_id=4,
            style=dict(stroke=bytes([181, 80, 66, 255]), stroke_width=3.0),
            arc=dict(bend=0.3, steps=32),
            legend_label="Arcs",
            labels=label("Arcs", [85, -48]),
        ),
        xyg.geo_layer(
            "polygons",
            source=polygon,
            layer_id=5,
            style=dict(
                fill=bytes([18, 110, 135, 160]), stroke=bytes([18, 110, 135, 255]), stroke_width=2.0
            ),
            legend_label="Polygon with hole",
            labels=label("Hole", [-30, 22]),
        ),
        xyg.geo_layer(
            "choropleth",
            source=choropleth,
            layer_id=6,
            values=np.array([0.7]),
            value_domain=[0.0, 1.0],
            color_stops=np.array([35, 55, 85, 65, 160, 145, 225, 190, 90], dtype="u1"),
            legend_label="Choropleth",
            labels=label("Choropleth", [27, 48]),
        ),
        camera=dict(crs=4326, center_x=0.0, center_y=0.0, zoom=1.0, width=1000.0, height=700.0),
        legend=dict(title="Geographic layers", location=0, font_size=12.0),
    )


if __name__ == "__main__":
    chart = geographic_catalog()
    destination = Path("spec/assets/geographic-catalog.svg")
    chart.write_image(destination)
    chart.write_image(destination.with_suffix(".png"))
    print(destination)
