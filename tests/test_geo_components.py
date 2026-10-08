"""Public geographic composition shares the catalog compiler and static Scene."""

import numpy as np
import pytest

import xyg


def source():
    return dict(
        geometry=1,
        crs=4326,
        xy=np.array([0.0, 0.0], dtype="<f8"),
        validity=np.array([1, 0], dtype="u1"),
        feature_ids=np.array([2**64 - 1, 2**63], dtype="<u8"),
    )


def test_public_composition_preserves_sources_and_exports_labels(tmp_path):
    data = source()
    camera = dict(crs=4326, center_x=0.0, center_y=0.0, zoom=0.0, width=800.0, height=600.0)
    chart = xyg.geo_chart(
        xyg.geo_layer(
            "points",
            source=data,
            layer_id=2**64 - 1,
            style=dict(fill=bytes([255, 0, 0, 255]), diameter=10.0),
            legend_label="Locations",
            labels=[
                dict(
                    feature_index=0,
                    anchor=0,
                    font_size=12.0,
                    coordinate=[0.0, 0.0],
                    rgba=bytes([0, 0, 0, 255]),
                    text="Origin",
                )
            ],
        ),
        camera=camera,
        legend=dict(title="Geography", location=0, font_size=12.0),
    )
    before = data["xy"].tobytes()
    out = chart.compile()
    np.testing.assert_array_equal(out["layers"][0]["feature_ids"], data["feature_ids"])
    assert data["xy"].tobytes() == before
    svg = chart.to_svg()
    assert "Origin" in svg and "Locations" in svg and "Geography" in svg
    png = chart.to_image()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    destination = tmp_path / "geography.svg"
    chart.write_image(destination)
    assert destination.read_text() == svg


def test_geographic_composition_rejects_unknown_children_and_family():
    with pytest.raises(TypeError):
        xyg.geo_chart(object(), camera={})
    with pytest.raises(ValueError):
        xyg.geo_layer("unknown", source=source(), layer_id=1)
