from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from xy import _native, _svg
from xy._figure import Figure

EXPECTED_SCATTER = (
    '<g><circle cx="10" cy="11" r="3" fill="rgb(37,99,235)" '
    'stroke="rgb(0,0,0)" stroke-width="2"/><path d="M 15.5 21 H 24.5 '
    'M 20 16.5 V 25.5" fill="none" stroke="rgb(17,24,39)" '
    'stroke-opacity="0.25" stroke-width="1"/></g>'
)


def test_python_scene_v3_matches_shared_scatter_line_bar_axis_bytes() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "scene_v3.json").read_text())
    encoded = _native.scene_batch_encode(
        viewport=tuple(fixture["viewport"]),
        margins=tuple(fixture["margins"]),
        x_axis=tuple(fixture["x_axis"]),
        y_axis=tuple(fixture["y_axis"]),
        kinds=fixture["kinds"],
        stable_ids=fixture["stable_ids"],
        style_refs=fixture["style_refs"],
        fill_rgba=[channel for style in fixture["styles"] for channel in style["fill_rgba"]],
        stroke_rgba=[channel for style in fixture["styles"] for channel in style["stroke_rgba"]],
        stroke_width=[style["stroke_width"] for style in fixture["styles"]],
        diameter=fixture["diameter"],
        symbols=fixture["symbols"],
        x0=fixture["x0"],
        y0=fixture["y0"],
        x1=fixture["x1"],
        y1=fixture["y1"],
    )
    assert encoded.hex() == fixture["expected_hex"]
    assert encoded[:4] == b"XYGS"
    assert int.from_bytes(encoded[4:8], "little") == 3
    records = 160 + len(fixture["styles"]) * 16
    assert encoded[records + 1] == 1  # center is outside, marker extent overlaps
    assert encoded[records + 2] == 2  # diamond
    assert np.frombuffer(encoded, dtype="<f8", count=1, offset=records + 48)[0] == 16.0
    line0 = records + 56
    line1 = line0 + 56
    rect = line1 + 56
    assert int.from_bytes(encoded[line0 + 8 : line0 + 16], "little") == 201
    assert int.from_bytes(encoded[line1 + 8 : line1 + 16], "little") == 201
    np.testing.assert_array_equal(
        np.frombuffer(encoded, dtype="<f8", count=2, offset=line0 + 32), 0
    )
    np.testing.assert_allclose(
        np.frombuffer(encoded, dtype="<f8", count=4, offset=rect + 16),
        [156.0, 142.0, 272.0, 318.0],
    )


def test_python_scene_v3_rejects_malformed_batches() -> None:
    options = dict(
        viewport=(100.0, 80.0),
        margins=(10.0, 10.0, 10.0, 10.0),
        x_axis=(1, 0, 0.0, 1.0, 1.0, False),
        y_axis=(2, 0, 0.0, 1.0, 1.0, False),
        kinds=[0],
        stable_ids=[1],
        style_refs=[0],
        fill_rgba=[0, 0, 0, 255],
        stroke_rgba=[0, 0, 0, 255],
        stroke_width=[1.0],
        diameter=[8.0],
        symbols=[0],
        x0=[0.5],
        y0=[0.5],
        x1=[0.5],
        y1=[0.5],
    )
    with np.testing.assert_raises_regex(ValueError, "equal length"):
        _native.scene_batch_encode(**(options | {"stable_ids": []}))
    with np.testing.assert_raises_regex(ValueError, "invalid canonical scene batch"):
        _native.scene_batch_encode(**(options | {"kinds": [9]}))
    with np.testing.assert_raises_regex(ValueError, "invalid canonical scene batch"):
        _native.scene_batch_encode(**(options | {"style_refs": [1]}))
    with np.testing.assert_raises_regex(ValueError, "invalid canonical scene batch"):
        _native.scene_batch_encode(**(options | {"margins": (60.0, 40.0, 10.0, 10.0)}))


def test_python_scene_v3_rejects_unsigned_values_before_coercion() -> None:
    options = dict(
        viewport=(100.0, 80.0),
        margins=(10.0, 10.0, 10.0, 10.0),
        x_axis=(1, 0, 0.0, 1.0, 1.0, False),
        y_axis=(2, 0, 0.0, 1.0, 1.0, False),
        kinds=[0],
        stable_ids=[1],
        style_refs=[0],
        fill_rgba=[0, 0, 0, 255],
        stroke_rgba=[0, 0, 0, 255],
        stroke_width=[0.0],
        diameter=[8.0],
        symbols=[0],
        x0=[0.5],
        y0=[0.5],
        x1=[0.0],
        y1=[0.0],
    )
    assert _native.scene_batch_encode(
        **(options | {"stable_ids": [2**64 - 1], "fill_rgba": [0, 255, 0, 255]})
    )
    for field, values in (
        ("kinds", [-1]),
        ("kinds", [256]),
        ("kinds", [1.5]),
        ("symbols", [-1]),
        ("symbols", [256]),
        ("style_refs", [-1]),
        ("style_refs", [2**32]),
        ("stable_ids", [-1]),
        ("stable_ids", [2**64]),
        ("fill_rgba", [-1, 0, 0, 255]),
        ("stroke_rgba", [0, 0, 0, 256]),
    ):
        with np.testing.assert_raises_regex(ValueError, "unsigned"):
            _native.scene_batch_encode(**(options | {field: values}))


def test_python_scene_v3_log_mask_ignores_reserved_coordinates_and_breaks_lines() -> None:
    encoded = _native.scene_batch_encode(
        viewport=(100.0, 100.0),
        margins=(10.0, 10.0, 10.0, 10.0),
        x_axis=(1, 1, 1.0, 10.0, 1.0, True),
        y_axis=(2, 1, 1.0, 10.0, 1.0, True),
        kinds=[0, 1, 1, 1, 2, 2],
        stable_ids=[1, 20, 20, 20, 30, 31],
        style_refs=[0] * 6,
        fill_rgba=[0, 0, 0, 255],
        stroke_rgba=[0, 0, 0, 255],
        stroke_width=[0.0],
        diameter=[6.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        symbols=[0] * 6,
        x0=[2.0, 2.0, 0.0, 4.0, 2.0, 2.0],
        y0=[2.0] * 6,
        x1=[0.0, 0.0, 0.0, 0.0, 8.0, 0.0],
        y1=[0.0, 0.0, 0.0, 0.0, 8.0, 8.0],
    )
    records = 176
    assert [encoded[records + index * 56 + 1] for index in range(6)] == [1, 1, 0, 1, 1, 0]
    assert encoded[records + 32 : records + 48] == bytes(16)
    assert encoded[records + 88 : records + 104] == bytes(16)


def test_linear_and_log_ticks_are_consumed_from_the_rust_scene(monkeypatch) -> None:
    calls: list[tuple[int, float, float, int]] = []
    original = _native.scene_axis_ticks

    def recording(kind: int, lo: float, hi: float, target: int):
        calls.append((kind, lo, hi, target))
        return original(kind, lo, hi, target)

    monkeypatch.setattr(_native, "scene_axis_ticks", recording)
    assert _svg._linear_ticks(-0.9, 5.1, 6) == ([0.0, 1.0, 2.0, 3.0, 4.0, 5.0], 1.0)
    assert _svg._log_ticks(0.1, 100.0, 6)[1] == [0.1, 1.0, 10.0, 100.0]
    assert calls == [(0, -0.9, 5.1, 6), (1, 0.1, 100.0, 6)]


def test_static_scale_consumes_rust_scene_policy_for_all_numeric_kinds(monkeypatch) -> None:
    calls: list[tuple[int, int]] = []
    original = _native.scene_scale_map

    def recording(values, kind, operation, *args, **kwargs):
        calls.append((kind, operation))
        return original(values, kind, operation, *args, **kwargs)

    monkeypatch.setattr(_native, "scene_scale_map", recording)
    linear = _svg._Scale({"kind": "linear", "range": [0.0, 10.0]}, 20.0, 120.0)
    np.testing.assert_allclose(linear([0.0, 5.0, 10.0]), [20.0, 70.0, 120.0])
    log = _svg._Scale({"kind": "linear", "scale": "log", "range": [0.1, 100.0]}, 0.0, 300.0)
    np.testing.assert_allclose(log([0.1, 1.0, 100.0]), [0.0, 100.0, 300.0])
    symlog = _svg._Scale(
        {"kind": "linear", "scale": "symlog", "constant": 2.0, "range": [-10.0, 10.0]}, 0.0, 100.0
    )
    coordinates = symlog.coord([-4.0, 0.0, 4.0])
    np.testing.assert_allclose(symlog.value(coordinates), [-4.0, 0.0, 4.0])
    assert {(0, 1), (1, 1), (2, 0), (2, 2)} <= set(calls)


def test_static_log_scale_preserves_clip_mask_and_nan_behavior() -> None:
    clipped = _svg._Scale({"range": [0.1, 10.0], "scale": "log"}, 0.0, 100.0)
    masked = _svg._Scale({"range": [0.1, 10.0], "scale": "log", "nonpositive": "mask"}, 0.0, 100.0)
    clipped_values = np.asarray(clipped.coord([-1.0, 0.0, np.nan]))
    assert clipped_values[:2].tolist() == [-300.0, -300.0]
    assert np.isnan(clipped_values[2])
    assert np.isnan(masked.coord(0.0))


def test_static_scale_reuses_rust_scalar_results_across_export_consumers(monkeypatch) -> None:
    calls = 0
    original = _native.scene_scale_map

    def recording(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(_native, "scene_scale_map", recording)
    scale = _svg._Scale({"range": [0.0, 10.0]}, 20.0, 120.0)
    assert scale(5.0) == scale(5.0) == 70.0
    assert scale.coord(5.0) == scale.coord(5.0) == 5.0
    assert scale.value(5.0) == scale.value(5.0) == 5.0
    # One Rust call per distinct scalar operation; repeated consumers are
    # cache hits. Rust owns transformed-domain preparation inside each batch.
    assert calls == 3


def test_static_scale_batches_vectors_and_seeds_followup_scalar_consumers(monkeypatch) -> None:
    shapes: list[tuple[int, ...]] = []
    original = _native.scene_scale_map

    def recording(values, *args, **kwargs):
        shapes.append(np.shape(values))
        return original(values, *args, **kwargs)

    monkeypatch.setattr(_native, "scene_scale_map", recording)
    scale = _svg._Scale({"range": [0.0, 10.0]}, 20.0, 120.0)
    np.testing.assert_allclose(scale([2.0, 4.0, 6.0]), [40.0, 60.0, 80.0])
    # Tick/grid/label consumers revisit these positions individually. The
    # vector's Rust results seed the bounded cache, so none adds an ABI call.
    assert [scale(value) for value in (2.0, 4.0, 6.0)] == [40.0, 60.0, 80.0]
    assert shapes == [(3,)]


def test_static_scale_vector_cache_never_exceeds_its_per_operation_bound() -> None:
    scale = _svg._Scale({"range": [0.0, 1000.0]}, 0.0, 1000.0)
    scale(np.arange(250.0))
    scale(np.concatenate((np.arange(240.0, 250.0), np.arange(250.0, 496.0))))
    assert len(scale._scalar_cache[1]) == scale._SCALAR_CACHE_LIMIT

    # A disjoint vector at the per-call limit cannot grow a full cache. Other
    # operations retain independent hard bounds rather than sharing capacity.
    scale(np.arange(1000.0, 1256.0))
    scale.coord(np.arange(512.0))
    scale.value(np.arange(512.0, 768.0))
    assert all(len(cache) <= scale._SCALAR_CACHE_LIMIT for cache in scale._scalar_cache)


def test_python_consumes_the_versioned_rust_scatter_scene() -> None:
    assert _native.scene_version() == 3
    assert (
        _native.scene_scatter_svg(
            [10.0, 20.0],
            [11.0, 21.0],
            [8.0, 10.0],
            np.array([[37, 99, 235, 255], [239, 68, 68, 128]], dtype=np.uint8),
            np.array([[0, 0, 0, 255], [17, 24, 39, 64]], dtype=np.uint8),
            [2.0, 0.0],
            [0, 14],
        )
        == EXPECTED_SCATTER
    )


def test_public_svg_scatter_routes_builtin_symbols_through_rust(monkeypatch) -> None:
    original = _native.scene_scatter_svg
    calls: list[int] = []

    def record(*args, **kwargs):
        calls.append(len(args[0]))
        return original(*args, **kwargs)

    monkeypatch.setattr(_native, "scene_scatter_svg", record)
    svg = Figure().scatter([0.0, 1.0], [1.0, 0.0], symbol="diamond").to_svg()

    assert calls == [2]
    assert '<path d="M ' in svg
    assert 'fill="#3987e5"' in svg


def test_scene_rejects_malformed_host_arrays() -> None:
    with np.testing.assert_raises_regex(ValueError, "one record per mark"):
        _native.scene_scatter_svg(
            [1.0],
            [],
            [4.0],
            [0, 0, 0, 255],
            [0, 0, 0, 0],
            [0.0],
            [0],
        )
    with np.testing.assert_raises_regex(ValueError, "invalid canonical scatter scene"):
        _native.scene_scatter_svg(
            [np.nan],
            [1.0],
            [4.0],
            [0, 0, 0, 255],
            [0, 0, 0, 0],
            [0.0],
            [0],
        )
