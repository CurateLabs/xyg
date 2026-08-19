from __future__ import annotations

import numpy as np

from xy import _native, _svg
from xy._figure import Figure

EXPECTED_SCATTER = (
    '<g><circle cx="10" cy="11" r="3" fill="rgb(37,99,235)" '
    'stroke="rgb(0,0,0)" stroke-width="2"/><path d="M 15.5 21 H 24.5 '
    'M 20 16.5 V 25.5" fill="none" stroke="rgb(17,24,39)" '
    'stroke-opacity="0.25" stroke-width="1"/></g>'
)


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


def test_python_consumes_the_versioned_rust_scatter_scene() -> None:
    assert _native.scene_version() == 1
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
