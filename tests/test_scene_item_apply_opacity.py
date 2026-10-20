"""ABI 245 Scene item-apply-opacity — wrapper over xyg_scene_item_apply_opacity."""

from __future__ import annotations

from xyg import kernels


def test_scene_item_apply_opacity_table() -> None:
    packed = bytes([10, 20, 30, 40, 1, 2, 3, 80])
    identity = kernels.scene_item_apply_opacity(packed, 2, None, None)
    assert identity == packed
    artist = kernels.scene_item_apply_opacity(packed, 2, [-1.0, 0.5], None)
    assert artist is not None
    assert artist[:4] == bytes([10, 20, 30, 40])
    assert artist[4:] == bytes([1, 2, 3, 128])
    opacity = kernels.scene_item_apply_opacity(packed, 2, None, [0.5, 0.25])
    assert opacity is not None
    assert opacity[3] == 20
    assert opacity[7] == 20
    assert kernels.scene_item_apply_opacity(packed, 2, [0.5], None) is None
    assert kernels.scene_item_apply_opacity(b"", 0, None, None) == b""


def test_artist_alpha_replaces_an_explicitly_transparent_rgba_paint() -> None:
    """Only the ``none`` keyword is absent paint; ``#rrggbb00`` takes the alpha (#1006)."""
    packed = bytes([9, 8, 7, 0, 1, 2, 3, 80])
    out = kernels.scene_item_apply_opacity(packed, 2, [0.5, 0.5], None)
    assert out == bytes([9, 8, 7, 128, 1, 2, 3, 128])


def test_scene_artist_alpha_css_is_rust_owned_keyword_and_paint_rule() -> None:
    """One native operation applies an artist alpha to an authored CSS paint (ABI 385)."""
    from xyg import _native

    assert _native.scene_artist_alpha_css("none", 0.5) == (0, 0, 0, 0)
    assert _native.scene_artist_alpha_css("transparent", 0.5) == (0, 0, 0, 0)
    assert _native.scene_artist_alpha_css("#ff0000", 0.5) == (255, 0, 0, 128)
    assert _native.scene_artist_alpha_css("#ff000080", 0.5) == (255, 0, 0, 128)
    assert _native.scene_artist_alpha_css("#ff000000", 0.5) == (255, 0, 0, 128)
    assert _native.scene_artist_alpha_css("#ff000080", -1.0) == (255, 0, 0, 128)


def test_scene_artist_alpha_css_bounds_its_input() -> None:
    """The paint is bounded at the Scene text limit: at 4,096 bytes ok, one more rejected."""
    import pytest

    from xyg import _native

    at_limit = "#ff0000".ljust(4096)
    assert _native.scene_artist_alpha_css(at_limit, 0.5) == (255, 0, 0, 128)
    with pytest.raises(ValueError, match="rejected"):
        _native.scene_artist_alpha_css(at_limit + " ", 0.5)
