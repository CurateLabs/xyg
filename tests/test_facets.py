from __future__ import annotations

import html as _html
import io
import re
import struct

import numpy as np
import pytest

import xyg
from xyg._figure import Figure
from xyg.facets import FacetGrid, _facet_values, _subset_data


def _table() -> dict[str, list]:
    return {
        "x": [1.0, 2.0, 3.0, 1.0, 2.0, 3.0],
        "y": [1.0, 2.0, 3.0, 3.0, 2.0, 1.0],
        "g": ["a", "a", "a", "b", "b", "b"],
    }


def _png_size(png: bytes) -> tuple[int, int]:
    assert png[12:16] == b"IHDR"
    w, h = struct.unpack(">II", png[16:24])
    return int(w), int(h)


# -- shared domains preserve axis options (set_axis wipe regression) --------


def test_shared_domain_preserves_axis_options() -> None:
    grid = xyg.facet_chart(
        xyg.line(x="x", y="y"),
        xyg.y_axis(type_="log", label="volts", format=".2f", tick_count=4),
        by="g",
        data=_table(),
    ).figure()
    domains = set()
    for fig in grid.figures:
        spec, _ = fig.build_payload()
        ya = spec["y_axis"]
        assert ya.get("scale") == "log"
        assert ya["label"] == "volts"
        assert ya.get("format") == ".2f"
        assert ya.get("tick_count") == 4
        domains.add(tuple(ya["domain"]))
    assert len(domains) == 1


def test_reversed_shared_axis_builds_and_stays_reversed() -> None:
    grid = xyg.facet_chart(
        xyg.line(x="x", y="y"),
        xyg.x_axis(reverse=True),
        by="g",
        data=_table(),
    ).figure()
    ranges = set()
    for fig in grid.figures:
        spec, _ = fig.build_payload()
        assert spec["x_axis"].get("reverse") is True
        lo, hi = spec["x_axis"]["domain"]
        assert lo < hi  # stored domain is increasing; reverse is a render flag
        ranges.add(fig.x_range())
    assert len(ranges) == 1
    hi, lo = grid.figures[0].x_range()  # reversed axes report descending pairs
    assert hi > lo


# -- mark-level data subsetting ---------------------------------------------


def test_mark_level_data_is_subset_per_panel() -> None:
    mark_data = {
        "mx": [0.0, 1.0, 2.0, 0.0, 1.0, 2.0],
        "my": [5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
    }
    grid = xyg.facet_chart(
        xyg.line(x="mx", y="my", data=mark_data),
        by="g",
        data={"g": _table()["g"]},
    ).figure()
    assert [fig.traces[0].n_points for fig in grid.figures] == [3, 3]
    assert grid.figures[0].traces[0].y.values.tolist() == [5.0, 6.0, 7.0]
    assert grid.figures[1].traces[0].y.values.tolist() == [8.0, 9.0, 10.0]


def test_raw_array_channels_raise_instead_of_duplicating() -> None:
    with pytest.raises(ValueError, match="pass column names"):
        xyg.facet_chart(
            xyg.line(x=np.arange(6.0), y=np.arange(6.0)),
            by="g",
            data={"g": _table()["g"]},
        ).figure()
    with pytest.raises(ValueError, match="pass column names"):
        xyg.facet_chart(
            xyg.scatter(x="x", y="y", color=np.arange(6.0)),
            by="g",
            data=_table(),
        ).figure()


def test_short_config_arrays_pass_through() -> None:
    # A 2-element dash pattern must not be confused with row data (n != 2).
    grid = xyg.facet_chart(
        xyg.line(x="x", y="y", dash=[4, 2]),
        by="g",
        data=_table(),
    ).figure()
    assert len(grid.figures) == 2


# -- facet split semantics ---------------------------------------------------


def test_facet_values_first_seen_order_and_codes() -> None:
    codes, labels = _facet_values({"g": ["b", "a", "b", "c", "a"]}, "g")
    assert labels == ["b", "a", "c"]
    assert codes.tolist() == [0, 1, 0, 2, 1]


def test_facet_values_object_column_fallback() -> None:
    codes, labels = _facet_values({"g": np.array(["b", None, 1, "b"], dtype=object)}, "g")
    assert labels == ["b", "(missing)", "1"]
    assert codes.tolist() == [0, 1, 2, 0]


def test_facet_values_numeric_column_merges_nans() -> None:
    codes, labels = _facet_values({"g": np.array([1.0, np.nan, 2.0, np.nan])}, "g")
    assert labels == ["1.0", "(missing)", "2.0"]
    assert codes.tolist() == [0, 1, 2, 1]


def test_facet_split_matches_row_membership() -> None:
    grid = xyg.facet_chart(xyg.line(x="x", y="y"), by="g", data=_table()).figure()
    assert grid.labels == ("a", "b")
    assert grid.figures[0].traces[0].y.values.tolist() == [1.0, 2.0, 3.0]
    assert grid.figures[1].traces[0].y.values.tolist() == [3.0, 2.0, 1.0]


# -- _subset_data contract ----------------------------------------------------


def test_subset_data_masks_only_row_aligned_columns() -> None:
    mask = np.array([True, False, True])
    out = _subset_data(
        {"a": [1.0, 2.0, 3.0], "scalar": 5, "config": [1, 2], "text": "hi"},
        mask,
        3,
    )
    assert out["a"].tolist() == [1.0, 3.0]
    assert out["scalar"] == 5
    assert out["config"] == [1, 2]
    assert out["text"] == "hi"


def test_subset_data_rejects_row_aligned_matrices() -> None:
    mask = np.array([True, False, True])
    z = np.zeros((3, 4))
    with pytest.raises(ValueError, match="multi-dimensional"):
        _subset_data({"z": z}, mask, 3)
    # A matrix whose first axis is not row-aligned passes through whole.
    out = _subset_data({"z": np.zeros((2, 4))}, mask, 3)
    assert out["z"].shape == (2, 4)


def test_subset_data_rejects_ragged_columns() -> None:
    mask = np.array([True, False, True])
    with pytest.raises(ValueError, match="ragged"):
        _subset_data({"a": [[1, 2], [3], [4, 5]]}, mask, 3)


# -- composed SVG -------------------------------------------------------------


def test_facet_svg_ids_are_unique_and_refs_resolve() -> None:
    grid = xyg.facet_chart(
        xyg.area(x="x", y="y", fill="linear-gradient(#fff, #000)"),
        by="g",
        data=_table(),
    ).figure()
    svg = grid.to_svg()
    ids = re.findall(r'id="([^"]+)"', svg)
    assert len(ids) == len(set(ids))
    refs = re.findall(r"url\(#([^)]+)\)", svg)
    assert refs and set(refs) <= set(ids)


def test_supported_facet_svg_routes_each_panel_through_the_canonical_scene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grid placement must not bypass an otherwise supported public export."""
    from xyg import _native, _scene_v3

    figures = [
        Figure(width=240, height=160).scatter([1, 2], [2, 3], color="#3987e5"),
        Figure(width=240, height=160).scatter([1, 2], [3, 2], color="#ef4444"),
    ]
    grid = FacetGrid(figures, labels=("left", "right"), cols=2, width=480, height=160)
    static_export = _native.static_document_export
    calls = 0

    def observed_static_export(*args: object, **kwargs: object) -> bytes:
        nonlocal calls
        calls += 1
        return static_export(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_native, "static_document_export", observed_static_export)
    real_scene = _scene_v3.figure_scene
    compile_calls = {"n": 0}

    def counted_scene(*args: object, **kwargs: object) -> bytes:
        compile_calls["n"] += 1
        return real_scene(*args, **kwargs)

    monkeypatch.setattr(_scene_v3, "figure_scene", counted_scene)
    svg = grid.to_svg()

    assert calls == 1
    assert compile_calls["n"] == 2
    assert 'id="xy-doc-0-xy-scene-plot"' in svg
    assert 'id="xy-doc-1-xy-scene-plot"' in svg
    assert "url(#xy-doc-0-xy-scene-plot)" in svg
    assert "url(#xy-doc-1-xy-scene-plot)" in svg
    assert _native.static_document_export is observed_static_export
    assert grid.to_image("pdf").startswith(b"%PDF-")


@pytest.mark.xfail(
    reason="XYST static route admission gap; tracked in #889.",
    strict=False,
)
def test_supported_facet_scene_failure_never_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from xyg import _native, _svg

    figure = Figure(width=240, height=160).scatter([1, 2], [2, 3], color="#3987e5")
    grid = FacetGrid([figure], labels=("only",), cols=1, width=240, height=160)

    def broken_document(*_args: object, **_kwargs: object) -> bytes:
        raise ValueError("broken StaticDocument consumer")

    def unexpected_compatibility(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("supported facet must not fall back")

    monkeypatch.setattr(_native, "static_document_export", broken_document)
    monkeypatch.setattr(_svg, "to_svg", unexpected_compatibility)
    with pytest.raises(ValueError, match="broken StaticDocument consumer"):
        grid.to_svg()


@pytest.mark.xfail(
    reason="XYST static route admission gap; tracked in #889.",
    strict=False,
)
def test_supported_facet_png_routes_each_panel_through_the_canonical_scene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grid placement must not bypass an otherwise supported public raster export."""
    from xyg import _native, _raster, _scene_v3

    figures = [
        Figure(width=240, height=160).scatter([1, 2], [2, 3], color="#3987e5"),
        Figure(width=240, height=160).scatter([1, 2], [3, 2], color="#ef4444"),
    ]
    grid = FacetGrid(figures, labels=("left", "right"), cols=2, width=480, height=160)
    static_export = _native.static_document_export
    calls = 0

    def observed_static_export(*args: object, **kwargs: object) -> bytes:
        nonlocal calls
        calls += 1
        return static_export(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_native, "static_document_export", observed_static_export)

    def unexpected_compatibility(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("supported facet must not fall back")

    monkeypatch.setattr(_raster, "_export_payload", unexpected_compatibility)
    real_scene = _scene_v3.figure_scene
    compile_calls = {"n": 0}

    def counted_scene(*args: object, **kwargs: object) -> bytes:
        compile_calls["n"] += 1
        return real_scene(*args, **kwargs)

    monkeypatch.setattr(_scene_v3, "figure_scene", counted_scene)
    png = grid.to_png(scale=1.0)

    assert calls == 1
    assert compile_calls["n"] == 2
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert _png_size(png) == (480, grid.grid_height)
    assert grid.to_image("jpeg")[:3] == b"\xff\xd8\xff"
    assert grid.to_image("webp")[:4] == b"RIFF"


@pytest.mark.xfail(
    reason="XYST static route admission gap; tracked in #889.",
    strict=False,
)
def test_supported_facet_scene_raster_failure_never_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from xyg import _native, _raster

    figure = Figure(width=240, height=160).scatter([1, 2], [2, 3], color="#3987e5")
    grid = FacetGrid([figure], labels=("only",), cols=1, width=240, height=160)

    def broken_document(*_args: object, **_kwargs: object) -> bytes:
        raise ValueError("broken StaticDocument raster consumer")

    def unexpected_compatibility(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("supported facet must not fall back")

    monkeypatch.setattr(_native, "static_document_export", broken_document)
    monkeypatch.setattr(_raster, "_export_payload", unexpected_compatibility)
    with pytest.raises(ValueError, match="broken StaticDocument raster consumer"):
        grid.to_png(scale=1.0)


def test_facet_raster_background_override_uses_static_document() -> None:
    figure = Figure(width=240, height=160).scatter([1, 2], [2, 3], color="#3987e5")
    grid = FacetGrid([figure], labels=("only",), cols=1, width=240, height=160)

    data = grid.to_png(scale=1.0)
    canvas = np.asarray(pytest.importorskip("PIL.Image").open(io.BytesIO(data)).convert("RGBA"))
    assert canvas.shape == (grid.grid_height, grid.width, 4)
    assert canvas.dtype == np.uint8


def test_facet_labels_and_grid_title_render_once() -> None:
    grid = xyg.facet_chart(xyg.line(x="x", y="y"), by="g", data=_table(), title="My grid").figure()
    svg = grid.to_svg()
    assert svg.count(">My grid<") == 1
    assert svg.count(">a<") == 1
    assert svg.count(">b<") == 1
    html = grid.to_html()
    # rendered once as the grid heading (the head <title> is document metadata)
    assert html.count('xy-facet-title">My grid<') == 1
    assert html.count("My grid") == 2
    # panel titles are the facet labels, not "grid · label" composites
    assert [fig.title for fig in grid.figures] == ["a", "b"]


def test_facet_notebook_repr_isolates_standalone_document() -> None:
    chart = xyg.facet_chart(
        xyg.line(x="x", y="y"),
        by="g",
        data=_table(),
        cols=1,
        width=600,
        height=200,
        gap=10,
        title="Notebook facets",
    )

    repr_html = chart._repr_html_()
    document = _html.unescape(repr_html)

    assert repr_html.startswith('<iframe class="xy-notebook-frame"')
    assert 'sandbox="allow-scripts"' in repr_html
    assert 'width="600" height="434"' in repr_html
    assert "<!doctype html>" in document
    assert '<body class="xy-facet-document">' in document
    assert "html,body{" not in document
    assert ".xy-facet-document .xy-facet-grid{" in document


def test_facet_ipython_display_uses_isolated_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    import IPython.display

    displayed: list[tuple[object, bool]] = []

    def record(value: object, *, raw: bool = False) -> None:
        displayed.append((value, raw))

    monkeypatch.setattr(IPython.display, "display", record)
    chart = xyg.facet_chart(xyg.line(x="x", y="y"), by="g", data=_table())

    chart._ipython_display_()

    assert len(displayed) == 1
    payload, raw = displayed[0]
    assert raw is True
    assert isinstance(payload, dict)
    assert payload["text/html"].startswith('<iframe class="xy-notebook-frame"')


# -- PNG geometry -------------------------------------------------------------


def test_facet_png_dimensions_and_default_scale() -> None:
    chart = xyg.facet_chart(
        xyg.line(x="x", y="y"),
        by="g",
        data=_table(),
        cols=2,
        width=600,
        height=200,
        gap=10,
    )
    grid = chart.figure()
    png = grid.to_png()  # default scale must match Figure.to_png (2.0)
    assert _png_size(png) == (1200, 2 * grid.grid_height)
    png1 = grid.to_png(scale=1.0)
    assert _png_size(png1) == (600, grid.grid_height)
    assert grid.grid_height == 200  # one row: no gaps, no title strip


def test_facet_chart_png_forwards_current_export_options() -> None:
    chart = xyg.facet_chart(
        xyg.line(x="x", y="y"),
        by="g",
        data=_table(),
        width=320,
        height=180,
    )

    assert chart.to_png(scale=1.0, gl="software").startswith(b"\x89PNG")


# -- shared categorical axes --------------------------------------------------


def test_shared_categorical_axis_uses_union_category_order() -> None:
    data = {
        "x": ["a", "b", "a", "c"],
        "y": [1.0, 2.0, 3.0, 4.0],
        "g": ["g1", "g1", "g2", "g2"],
    }
    grid = xyg.facet_chart(xyg.bar(x="x", y="y"), by="g", data=data).figure()
    specs = [fig.build_payload()[0] for fig in grid.figures]
    assert [spec["x_axis"]["categories"] for spec in specs] == [
        ["a", "b", "c"],
        ["a", "b", "c"],
    ]
    assert specs[0]["x_axis"]["domain"] == specs[1]["x_axis"]["domain"]


def test_shared_named_categorical_axis_uses_its_own_union_category_order() -> None:
    data = {
        "x": [1.0, 2.0, 3.0, 4.0],
        "category": ["a", "b", "a", "c"],
        "y": [1.0, 2.0, 3.0, 4.0],
        "g": ["g1", "g1", "g2", "g2"],
    }
    grid = xyg.facet_chart(
        xyg.line(x="x", y="y"),
        xyg.line(x="category", y="y", x_axis="x2"),
        xyg.x_axis(id="x2", side="top"),
        by="g",
        data=data,
    ).figure()
    specs = [fig.build_payload()[0] for fig in grid.figures]

    assert all("categories" not in spec["axes"]["x"] for spec in specs)
    assert [spec["axes"]["x2"]["categories"] for spec in specs] == [
        ["a", "b", "c"],
        ["a", "b", "c"],
    ]
    assert specs[0]["axes"]["x2"]["domain"] == specs[1]["axes"]["x2"]["domain"]


# -- interaction linking ------------------------------------------------------


def test_shared_axes_stay_independent_by_default() -> None:
    grid = xyg.facet_chart(xyg.line(x="x", y="y"), by="g", data=_table()).figure()
    assert all("link_group" not in fig.interaction for fig in grid.figures)


@pytest.mark.parametrize(
    ("link", "axes"),
    [("x", ["x"]), ("y", ["y"]), ("both", ["x", "y"]), (True, ["x", "y"])],
)
def test_link_is_explicit_and_selectable(link: str | bool, axes: list[str]) -> None:
    grid = xyg.facet_chart(
        xyg.line(x="x", y="y"), by="g", data=_table(), link=link, link_select=True
    ).figure()
    assert len({fig.interaction["link_group"] for fig in grid.figures}) == 1
    assert all(fig.interaction["link_axes"] == axes for fig in grid.figures)
    assert all(fig.interaction["link_select"] is True for fig in grid.figures)


def test_link_false_disables_runtime_axis_linking() -> None:
    grid = xyg.facet_chart(xyg.line(x="x", y="y"), by="g", data=_table(), link=False).figure()
    assert all("link_group" not in fig.interaction for fig in grid.figures)


def test_link_implies_initial_domain_sharing() -> None:
    grid = xyg.facet_chart(
        xyg.line(x="x", y="y"), by="g", data=_table(), share_x=False, link="x"
    ).figure()
    assert len({fig.x_range() for fig in grid.figures}) == 1


def test_invalid_link_rejected() -> None:
    with pytest.raises(ValueError, match="link must"):
        xyg.facet_chart(xyg.line(x="x", y="y"), by="g", data=_table(), link="z")


def test_user_link_group_is_not_overridden() -> None:
    grid = xyg.facet_chart(
        xyg.line(x="x", y="y"), by="g", data=_table(), link_group="mine"
    ).figure()
    assert all(fig.interaction["link_group"] == "mine" for fig in grid.figures)


# -- misc ---------------------------------------------------------------------


def test_facet_chart_requires_by_eagerly() -> None:
    with pytest.raises(TypeError, match="by="):
        xyg.facet_chart(xyg.line(x="x", y="y"), data=_table())


def test_stairs_tooltip_channels_are_not_mislabeled() -> None:
    chart = xyg.stairs_chart(
        xyg.stairs(values="v", edges="e", data={"v": [1.0, 2.0], "e": [0.0, 1.0, 2.0]}),
        xyg.tooltip(),
    )
    tooltip = chart.figure().tooltip
    assert tooltip is not None
    # values are heights (y) sampled at edge positions (x), not the reverse
    assert tooltip["aliases"] == {"v": "y", "e": "x"}
    assert tooltip["sources"]["v"] == [{"trace": 0, "channel": "y"}]
    assert tooltip["sources"]["e"] == [{"trace": 0, "channel": "x"}]
