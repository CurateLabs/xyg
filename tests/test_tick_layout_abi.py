"""ABI 123 tick-label collision: Python host wrappers match the Rust goldens."""

from __future__ import annotations

from xyg import _native
from xyg._svg import _axis_tick_label_layout, _Scale


def _category_positions(n: int = 9) -> list[float]:
    return [100.0 + i * 90.0 for i in range(n)]


def _category_labels(n: int = 9) -> list[str]:
    return [f"Category_Name_{i:02d}" for i in range(n)]


def test_none_and_off_drop_every_label() -> None:
    pos = [0.0, 10.0]
    labels = ["a", "b"]
    assert _native.scene_tick_label_layout(pos, labels, kind="none") == []
    assert _native.scene_tick_label_layout(pos, labels, kind="off") == []


def test_preserve_keeps_colliding_labels() -> None:
    kept = _native.scene_tick_label_layout(
        _category_positions(),
        _category_labels(),
        kind="preserve",
        is_x=True,
        category=True,
        explicit_angle=-30.0,
    )
    assert [item["index"] for item in kept] == list(range(9))


def test_end_anchor_rotate_keeps_wide_categorical_labels() -> None:
    kept = _native.scene_tick_label_layout(
        _category_positions(),
        _category_labels(),
        kind="rotate",
        side="bottom",
        anchor="end",
        is_x=True,
        category=True,
        font_size=11.0,
        min_gap=8.0,
        explicit_angle=-30.0,
    )
    assert len(kept) == 9
    assert kept[0]["angle"] == -30.0
    assert all(item["row"] == 0 for item in kept)


def test_centered_rotate_downsamples_the_same_geometry() -> None:
    kept = _native.scene_tick_label_layout(
        _category_positions(),
        _category_labels(),
        kind="rotate",
        side="bottom",
        anchor="center",
        is_x=True,
        category=True,
        font_size=11.0,
        min_gap=8.0,
        explicit_angle=-30.0,
    )
    assert 0 < len(kept) < 9


def test_svg_packer_matches_native_end_anchor_rotate() -> None:
    n = 9
    categories = _category_labels(n)
    axis: dict = {
        "kind": "category",
        "categories": categories,
        "range": [0.0, float(n - 1)],
        "tick_label_angle": -30,
        "tick_label_anchor": "end",
        "tick_label_strategy": "rotate",
    }
    scale = _Scale(axis, px0=100.0, px1=820.0)
    values = [float(i) for i in range(n)]
    packed = _axis_tick_label_layout(axis, values, 1.0, scale, is_x=True)
    native = _native.scene_tick_label_layout(
        [float(scale(v)) for v in values],
        categories,
        kind="rotate",
        side="bottom",
        anchor="end",
        is_x=True,
        category=True,
        explicit_angle=-30.0,
    )
    assert [item["text"] for item in packed] == categories
    assert [item["index"] for item in native] == list(range(n))
    assert len(packed) == n
