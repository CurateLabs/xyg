"""ABI 266 density_overlay_omitted_wire parity."""

from __future__ import annotations

from xyg import kernels


def test_density_overlay_omitted_wire_rows_exceed() -> None:
    assert (
        kernels.density_overlay_omitted_wire(
            overlay_omitted=kernels.DENSITY_OVERLAY_ROWS_EXCEED_U32,
            point_overlay=True,
        )
        == "rows_exceed_u32"
    )


def test_density_overlay_omitted_wire_static_raster() -> None:
    assert (
        kernels.density_overlay_omitted_wire(
            overlay_omitted=kernels.DENSITY_OVERLAY_STATIC_RASTER,
            point_overlay=False,
        )
        == "static_raster"
    )


def test_density_overlay_omitted_wire_static_with_overlay() -> None:
    assert (
        kernels.density_overlay_omitted_wire(
            overlay_omitted=kernels.DENSITY_OVERLAY_STATIC_RASTER,
            point_overlay=True,
        )
        is None
    )


def test_density_overlay_omitted_wire_none() -> None:
    assert (
        kernels.density_overlay_omitted_wire(
            overlay_omitted=kernels.DENSITY_OVERLAY_NONE,
            point_overlay=False,
        )
        is None
    )
