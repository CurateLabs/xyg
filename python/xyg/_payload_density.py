"""Density trace payload helpers extracted from ``_payload.py`` (Push 3C)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import _native, channels, interaction, kernels, lod
from ._payload_helpers import binning_coords, payload_column_ship_plan, ship_trace_channel_attach
from ._payload_ship import ship_registry_columns
from ._trace import Trace
from ._wasm_aggregate_generated import WASM_AGGREGATE_MAX_POINTS
from .config import DENSITY_SAMPLE_SEED, DENSITY_SAMPLE_TARGET

if TYPE_CHECKING:
    from ._payload_writer import PayloadWriter


class PayloadDensityMixin:
    def _ship_density_grid_buffers(
        self,
        density: dict[str, Any],
        pw: "PayloadWriter",
        grid_plan: dict[str, Any],
        *,
        encoded_grid: np.ndarray,
        rgba_grid: Optional[np.ndarray] = None,
    ) -> None:
        """Ship u8 density grid planes per the ABI 315 buffer registry."""
        buffers = {"count": encoded_grid, "rgba": rgba_grid}
        for buf in grid_plan["buffers"]:
            key = buf["registry_key"]
            slot = buf["buffer_slot"]
            values = buffers[slot]
            if values is None:
                continue
            if buf["ship_method"] == "u8":
                density[key] = pw.ship_u8(values)

    def _attach_density_grid_steps(
        self,
        density: dict[str, Any],
        entry: dict[str, Any],
        t: Trace,
        pw: "PayloadWriter",
        grid_plan: dict[str, Any],
        wire: dict[str, Any],
        *,
        sel: np.ndarray,
        visible: int,
        xr: tuple[float, float],
        yr: tuple[float, float],
        sample_sel: Optional[np.ndarray],
        dropped_channels: list[str],
        tiles_meta: Optional[dict[str, Any]],
    ) -> None:
        """Run ordered density nested attach steps from ABI 315."""
        for step in grid_plan["attach"]:
            kind = step["attach_kind"]
            if kind == "wasm_source":
                wasm_source: dict[str, Any] = {
                    "kind": "cartesian-count-f64-stream-v1",
                    "point_count": int(t.n_points),
                    "trace_id": int(t.id),
                    "capacity": WASM_AGGREGATE_MAX_POINTS,
                    "ownership": "retain-host-replay",
                }
                column_plan = payload_column_ship_plan(self, t, kind="density_wasm_source")
                ship_registry_columns(
                    self,
                    wasm_source,
                    t,
                    pw,
                    column_plan,
                    {"x": t.x.values, "y": t.y.values},
                )
                density["wasm_source"] = wasm_source
            elif kind == "tiles":
                if tiles_meta is not None:
                    density["tiles"] = tiles_meta
            elif kind == "rgba":
                density["color_agg"] = "mean"
            elif kind == "channels_dropped":
                filtered = [
                    name
                    for name in dropped_channels
                    if kernels.density_dropped_channel_wire_admit(
                        channel=name,
                        mean_color_aggregates=int(wire["mean_color_aggregates"]),
                    )
                ]
                dropped_channels[:] = filtered
                density["channels_dropped"] = kernels.density_channels_dropped_compat(
                    dropped_count=len(filtered),
                )
            elif kind == "dropped_channels":
                density["dropped_channels"] = dropped_channels
            elif kind == "constant_color":
                assert t.color_ch is not None
                density["color"] = t.color_ch.constant
            elif kind == "overlay_rows_exceed":
                density["overlay_omitted"] = "rows_exceed_u32"
            elif kind == "sample":
                sample = self._density_sample_spec(
                    t, sel, visible, xr, yr, pw, sample_sel=sample_sel
                )
                if sample is not None:
                    density["sample"] = sample
            elif kind == "overlay_static_raster":
                density["overlay_omitted"] = "static_raster"
            elif kind == "entry_color":
                assert t.color_ch is not None
                color_spec = t.color_ch.spec()
                color_spec["palette"] = channels.categorical_palette(
                    t.color_ch.colors, len(t.color_ch.categories or ())
                )
                entry["color"] = color_spec

    def _density_sample_spec(
        self,
        t: Trace,
        sel: np.ndarray,
        visible: int,
        xr: tuple[float, float],
        yr: tuple[float, float],
        pw: "PayloadWriter",
        *,
        sample_sel: Optional[np.ndarray] = None,
    ) -> Optional[dict[str, Any]]:
        if visible <= 0:
            return None
        if sample_sel is None:
            categories = None
            if t.color_ch and t.color_ch.mode == "categorical" and t.color_ch.codes is not None:
                categories = t.color_ch.codes[sel]
            sample_sel = lod.sample_rows_for_target(
                sel,
                DENSITY_SAMPLE_TARGET,
                categories=categories,
                seed=DENSITY_SAMPLE_SEED,
            )
        if len(sample_sel) == 0:
            return None
        x_scale = self._axis_scale(t.x_axis)
        y_scale = self._axis_scale(t.y_axis)
        plan = kernels.payload_nonxy_emit_plan(
            kind="density_sample",
            n_marks=int(len(sample_sel)),
            style_color_is_none=t.style.get("color") is None,
            x_axis_scale=x_scale,
            y_axis_scale=y_scale,
        )
        style = dict(t.style)
        try:
            authored = float(style.get("opacity", 0.8))
        except (TypeError, ValueError):
            authored = float("nan")
        style["opacity"] = kernels.density_overlay_opacity(authored)
        column_plan = payload_column_ship_plan(self, t, kind="density_sample")
        sample = {
            "mode": "sampled",
            "n": int(len(sample_sel)),
            "visible": int(visible),
            "target": DENSITY_SAMPLE_TARGET,
            "level": 0,
            "seed": DENSITY_SAMPLE_SEED,
            "x_range": list(xr),
            "y_range": list(yr),
            "style": style,
        }
        ship_registry_columns(
            self,
            sample,
            t,
            pw,
            column_plan,
            {"x": t.x.values[sample_sel], "y": t.y.values[sample_sel]},
            nested_keys=frozenset({"x", "y"}),
        )
        ship_trace_channel_attach(
            sample,
            t,
            sample_sel,
            pw,
            plan["channel_slot"],
            include_trace_styles=plan["include_trace_styles"],
        )
        return sample

    def _density_trace_emit_plan(
        self,
        t: Trace,
        xr,
        yr,
        w: int,
        h: int,
        pw: "PayloadWriter",
        bx0: float,
        bx1: float,
        by0: float,
        by1: float,
        x_linear: bool,
        y_linear: bool,
        x_memmapped: bool,
        y_memmapped: bool,
        *,
        grid_from_pyramid: bool,
        has_pyramid_resource: bool,
        grid_present: bool,
        has_pyramid_rgba: bool = False,
        has_bin_colors: bool = False,
        dropped_count: int = 0,
    ) -> dict[str, int | bool | float]:
        mode = ""
        codes_present = False
        codes_u8 = False
        has_counts = False
        has_constant = False
        if t.color_ch is not None:
            mode = t.color_ch.mode
            codes = t.color_ch.codes
            codes_present = codes is not None
            codes_u8 = codes is not None and codes.dtype == np.uint8
            has_counts = t.color_ch.counts is not None
            has_constant = t.color_ch.constant is not None
        return kernels.payload_density_trace_emit_plan(
            has_channel=t.color_ch is not None,
            mode=mode,
            codes_present=codes_present,
            codes_u8=codes_u8,
            has_counts=has_counts,
            has_constant=has_constant,
            cartesian=self.coords == "cartesian",
            x_linear=x_linear,
            y_linear=y_linear,
            x_has_nulls=bool(t.x.zone.null_count),
            y_has_nulls=bool(t.y.zone.null_count),
            point_overlay=bool(pw.point_overlay),
            split_payload=bool(pw._split),
            grid_w=int(w),
            grid_h=int(h),
            grid_from_pyramid=grid_from_pyramid,
            has_pyramid_resource=has_pyramid_resource,
            grid_present=grid_present,
            x_memmapped=x_memmapped,
            y_memmapped=y_memmapped,
            x_min=float(t.x.min),
            x_max=float(t.x.max),
            y_min=float(t.y.min),
            y_max=float(t.y.max),
            xr0=float(xr[0]),
            xr1=float(xr[1]),
            yr0=float(yr[0]),
            yr1=float(yr[1]),
            bx0=float(bx0),
            bx1=float(bx1),
            by0=float(by0),
            by1=float(by1),
            n_points=int(t.n_points),
            has_pyramid_rgba=has_pyramid_rgba,
            has_bin_colors=has_bin_colors,
            dropped_count=int(dropped_count),
        )

    def _density_trace_spec(self, t: Trace, xr, yr, w, h, pw: "PayloadWriter") -> dict[str, Any]:  # noqa: ANN001
        """Bin a scatter into a density grid and build its spec entry (§5 Tier 2).
        The grid ships in the client's one-byte log texture precision; exact
        visible counts remain metadata, and the client recomputes the
        normalization domain per view so brightness is stable (§F6)."""
        # Density grids are uniform in axis-scale coordinates (§28): on a
        # nonlinear axis the columns and window are transformed before binning
        # so every cell covers the same strip of *screen*. The wire keeps raw
        # `x_range`/`y_range` endpoints; renderers interpolate between their
        # scale coordinates.
        bx, (bx0, bx1) = binning_coords(self, t.x_axis, t.x.values, xr)
        by, (by0, by1) = binning_coords(self, t.y_axis, t.y.values, yr)
        x_linear = self._axis_scale(t.x_axis) == "linear"
        y_linear = self._axis_scale(t.y_axis) == "linear"
        from . import _ooc as ooc

        x_memmapped = ooc.is_memmapped(t.x.values)
        y_memmapped = ooc.is_memmapped(t.y.values)

        def _emit_plan(
            *, grid_from_pyramid: bool, has_pyramid_resource: bool, grid_present: bool = False
        ) -> dict[str, int | bool | float]:
            return self._density_trace_emit_plan(
                t,
                xr,
                yr,
                w,
                h,
                pw,
                bx0,
                bx1,
                by0,
                by1,
                x_linear,
                y_linear,
                x_memmapped,
                y_memmapped,
                grid_from_pyramid=grid_from_pyramid,
                has_pyramid_resource=has_pyramid_resource,
                grid_present=grid_present,
            )

        plan = _emit_plan(grid_from_pyramid=False, has_pyramid_resource=False)
        pyramid_resource = _native.DENSITY_RESOURCE_NONE
        pyramid_handle = 0
        pyr = None
        store = None
        has_pyramid_resource = False
        if plan["pyramid_eligible"]:
            pyr = interaction._ensure_pyramid(t)
            store = interaction._tile_store_of(t)
            has_pyramid_resource = store is not None or pyr is not None
            plan = _emit_plan(
                grid_from_pyramid=False,
                has_pyramid_resource=has_pyramid_resource,
            )
            if store is not None:
                pyramid_resource = _native.DENSITY_RESOURCE_TILE_STORE
                pyramid_handle = int(store)
            elif pyr is not None:
                pyramid_resource = _native.DENSITY_RESOURCE_PYRAMID
                pyramid_handle = int(pyr)
        bin_colors = interaction.trace_bin_colors(t)
        ship_mean_color = bool(getattr(t, "_pyr_colored", False) or bin_colors is not None)
        color_codes = None
        color_counts = None
        if t.color_ch is not None and t.color_ch.codes is not None:
            color_codes = t.color_ch.codes
            if t.color_ch.counts is not None:
                color_counts = t.color_ch.counts
        materialized = kernels.payload_density_grid_materialize(
            cartesian=self.coords == "cartesian",
            x_linear=x_linear,
            y_linear=y_linear,
            categorical=bool(plan["categorical"]),
            compact_categorical=bool(plan["compact_categorical"]),
            stratified_counts=bool(plan["stratified_counts"]),
            x_has_nulls=bool(t.x.zone.null_count),
            y_has_nulls=bool(t.y.zone.null_count),
            point_overlay=bool(pw.point_overlay),
            grid_from_pyramid=False,
            x_memmapped=x_memmapped,
            y_memmapped=y_memmapped,
            has_pyramid_resource=has_pyramid_resource,
            color_mode=int(plan["color_mode"]),
            x_min=float(t.x.min),
            x_max=float(t.x.max),
            y_min=float(t.y.min),
            y_max=float(t.y.max),
            x_c0=float(plan["x_c0"]),
            x_c1=float(plan["x_c1"]),
            y_c0=float(plan["y_c0"]),
            y_c1=float(plan["y_c1"]),
            n_points=int(t.n_points),
            bx0=float(bx0),
            bx1=float(bx1),
            by0=float(by0),
            by1=float(by1),
            xr0=float(xr[0]),
            xr1=float(xr[1]),
            yr0=float(yr[0]),
            yr1=float(yr[1]),
            w=int(w),
            h=int(h),
            x_raw=t.x.values,
            y_raw=t.y.values,
            bx=bx,
            by=by,
            pyramid_attempt=bool(plan["pyramid_attempt"]),
            pyramid_resource=int(pyramid_resource),
            pyramid_handle=int(pyramid_handle),
            pyr_colored=bool(getattr(t, "_pyr_colored", False)),
            max_upsample=int(plan["pyramid_max_upsample"]),
            tile_upsample=int(plan["pyramid_tile_upsample"]),
            pyramid_no_rescan=bool(plan["pyramid_no_rescan"]),
            needs_pyramid_sample=bool(plan["needs_pyramid_sample"]),
            pyramid_sample_stratified=bool(plan["pyramid_sample_stratified"]),
            ship_mean_color=ship_mean_color,
            color_codes=color_codes,
            color_counts=color_counts,
            bin_colors=bin_colors,
        )
        binning = materialized["binning"]
        encoded_grid = materialized["encoded_grid"]
        gmax = materialized["gmax"]
        visible = int(materialized["visible"])
        sel = materialized["visible_sel"]
        if sel is None:
            sel = np.empty(0, dtype=np.uint32)
        sample_sel = materialized["sample_sel"]
        rgba_grid: Optional[np.ndarray] = materialized["rgba_grid"]
        tiles_meta = (
            interaction._tiles_stats_dict(store)
            if materialized["from_tiles"] and store is not None
            else None
        )
        wire = self._density_trace_emit_plan(
            t,
            xr,
            yr,
            w,
            h,
            pw,
            bx0,
            bx1,
            by0,
            by1,
            x_linear,
            y_linear,
            x_memmapped,
            y_memmapped,
            grid_from_pyramid=bool(materialized["grid_from_pyramid"]),
            has_pyramid_resource=has_pyramid_resource,
            grid_present=True,
            has_pyramid_rgba=bool(materialized["has_pyramid_rgba"]),
            has_bin_colors=bin_colors is not None,
        )
        grid_plan = kernels.payload_density_grid_ship_plan(
            ship_mean_color_rgba=bool(wire["ship_mean_color_rgba"]),
            ship_wasm_source=bool(wire["ship_wasm_source"]),
            attach_sample=bool(wire["attach_sample"]),
            has_tiles=tiles_meta is not None,
            ship_constant_color=bool(wire["ship_constant_color"]),
            overlay_wire_rows_exceed=bool(wire["overlay_wire_rows_exceed"]),
            overlay_wire_static_raster=bool(wire["overlay_wire_static_raster"]),
            ship_categorical_entry_color=bool(wire["ship_categorical_entry_color"]),
        )
        # The density surface wears the data's own colors (LOD doc §2): count
        # is the alpha channel, and per-point color channels aggregate to a
        # per-cell mean shipped as an RGBA plane below. `colormap` stays on
        # the wire only for the client's count-only LUT fallback (hand-built
        # specs); no shipped path colormaps counts.
        cmap = (
            t.color_ch.colormap
            if t.color_ch is not None and wire["use_channel_colormap"]
            else channels.DEFAULT_COLORMAP
        )
        density: dict[str, Any] = {
            "w": w,
            "h": h,
            "max": gmax,
            "enc": "log-u8",
            "colormap": cmap,
            "x_range": list(xr),
            "y_range": list(yr),
            "binning": binning,
            "reduction": (
                "pyramid-count"
                if kernels.density_reduction_kind(binning=binning)
                == kernels.DENSITY_REDUCTION_PYRAMID_COUNT
                else "bin2d"
            ),
        }
        self._ship_density_grid_buffers(
            density,
            pw,
            grid_plan,
            encoded_grid=encoded_grid,
            rgba_grid=rgba_grid,
        )
        dropped_channels = list(t.per_item_channel_names())
        entry = {
            "id": t.id,
            "kind": "scatter",
            "name": t.name,
            "style": dict(t.style),
            "tier": "density",
            "n_points": t.n_points,
            "n_marks": int(wire["n_marks"]),
            "visible": visible,
            "x_axis": t.x_axis,
            "y_axis": t.y_axis,
            "density": density,
        }
        self._attach_density_grid_steps(
            density,
            entry,
            t,
            pw,
            grid_plan,
            wire,
            sel=sel,
            visible=visible,
            xr=xr,
            yr=yr,
            sample_sel=sample_sel,
            dropped_channels=dropped_channels,
            tiles_meta=tiles_meta,
        )
        return entry
