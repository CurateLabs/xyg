"""Wire-spec compiler for `Figure`: `build_payload` plus the per-kind
emitters and the Tier-2 density/sample specs. Split out of `_figure.py` as a
mixin; `Figure` inherits `PayloadMixin`, so every `self.*` resolves through the
concrete `Figure` via the MRO (§29: data moves as typed binary buffers)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import channels, kernels, lod
from ._payload_density import PayloadDensityMixin
from ._payload_helpers import (
    attach_tooltip_rows,
    binning_coords,
    log_visible_mask,
    payload_column_ship_plan,
    ship_trace_channel_attach,
    transition_entry,
    visible_mask_needed,
)
from ._payload_spec_attach import attach_build_plan_fields
from ._payload_writer import PayloadWriter
from ._trace import Trace
from .columns import Column
from .config import PROTOCOL_VERSION

if TYPE_CHECKING:
    from ._hosts import FigureHost as _Host
else:
    _Host = object


class PayloadMixin(PayloadDensityMixin, _Host):
    def build_payload(self, px_width: Optional[int] = None) -> tuple[dict[str, Any], bytes]:
        """Encode every trace for first paint: (spec, binary buffer blob)."""
        pw = PayloadWriter()
        spec = self._payload_spec(pw, self._resolve_px_width(px_width))
        return spec, pw.blob()

    def build_payload_split(
        self, px_width: Optional[int] = None, *, wasm_source: bool = False
    ) -> tuple[dict[str, Any], list[memoryview]]:
        """`build_payload` with per-column wire buffers instead of one blob.

        ``wasm_source=True`` explicitly adds bounded canonical f64 replay
        columns for the Worker/WASM density adapter. The ordinary first-paint
        path stays screen-bounded and never implies replay from ``split``.
        """
        pw = PayloadWriter(split=True, wasm_source=wasm_source)
        spec = self._payload_spec(pw, self._resolve_px_width(px_width))
        spec["buffer_layout"] = "split"
        return spec, pw.buffers()

    def _build_raster_payload(
        self, px_width: Optional[int] = None
    ) -> tuple[dict[str, Any], bytes, tuple[np.ndarray, ...]]:
        """Private static-export payload with borrowed canonical heatmap spans."""
        pw = PayloadWriter(borrow_heatmaps=True, point_overlay=False)
        spec = self._payload_spec(pw, self._resolve_px_width(px_width))
        return spec, pw.blob(), tuple(pw.borrowed)

    def _resolve_px_width(self, px_width: Optional[int]) -> int:
        if px_width is None:
            width = self.width
            px_width = (
                int(width)
                if isinstance(width, (int, float)) and not isinstance(width, bool)
                else 2048
            )
        px_width, _ = lod.screen_shape(px_width, 16)
        return px_width

    def _payload_spec(self, pw: PayloadWriter, px_width: int) -> dict[str, Any]:
        ranges: dict[str, tuple[float, float]] = {}

        def axis_range(axis_id: str) -> tuple[float, float]:
            r = ranges.get(axis_id)
            if r is None:
                ranges[axis_id] = r = self._range(axis_id)
            return r

        self._validate_coords()
        spec_traces = []
        for t in self.traces:
            xr = axis_range(t.x_axis)
            yr = axis_range(t.y_axis)
            spec_traces.append(
                self._emit_trace(t, pw, (min(xr), max(xr)), (min(yr), max(yr)), px_width)
            )
        axis_specs = {
            axis_id: self._axis_spec(axis_id, axis_range(axis_id)) for axis_id in self.axis_options
        }

        wasm_sources = [entry.get("density", {}).get("wasm_source") for entry in spec_traces]
        wasm_sources = [source for source in wasm_sources if source is not None]
        has_density_tier = any(entry.get("tier") == "density" for entry in spec_traces)
        dom = self._dom_spec()
        legend_opts = self.legend_options
        mark_style = self._mark_style_spec()
        interaction_spec = self._interaction_spec()
        annotations = self._annotation_specs()
        build_plan = kernels.payload_build_plan(
            split_payload=bool(pw._split),
            wasm_source_count=len(wasm_sources),
            has_density_tier=has_density_tier,
            coords_cartesian=self.coords == "cartesian",
            has_title_options=bool(self.title_options),
            has_palette=self.palette is not None,
            has_legend_options=bool(legend_opts),
            legend_loc_best=bool(legend_opts and legend_opts.get("loc") == "best"),
            has_extra_legends=bool(getattr(self, "extra_legends", None)),
            has_frame_sides=self.frame_sides is not None,
            has_colorbar_options=bool(self.colorbar_options),
            show_modebar_is_false=self.show_modebar is False,
            has_export_options=bool(getattr(self, "export_options", None)),
            show_tooltip_is_false=self.show_tooltip is False,
            has_padding=self.padding is not None,
            has_dom=bool(dom),
            has_tooltip=self.tooltip is not None,
            has_mark_style=bool(mark_style),
            has_interaction=bool(interaction_spec),
            has_annotations=bool(annotations),
            has_animation_options=self.animation_options is not None,
            has_graph_meta=bool(getattr(self, "_graph_meta", None)),
        )

        spec = {
            "protocol": PROTOCOL_VERSION,
            "width": self.width,
            "height": self.height,
            "title": self._optional_text(self.title, "title"),
            "x_axis": axis_specs["x"],
            "y_axis": axis_specs["y"],
            "axes": axis_specs,
            "traces": spec_traces,
            "columns": pw.columns,
            "backend": kernels.BACKEND,
            "show_legend": self.show_legend,
            "view": {
                "ranges": {axis_id: list(axis["range"]) for axis_id, axis in axis_specs.items()}
            },
        }
        attach_build_plan_fields(
            spec,
            self,
            pw,
            build_plan,
            spec_traces=spec_traces,
            wasm_sources=wasm_sources,
            dom=dom,
            legend_opts=legend_opts,
            mark_style=mark_style,
            interaction_spec=interaction_spec,
            annotations=annotations,
        )
        return spec

    _transition_entry = staticmethod(transition_entry)
    _attach_tooltip_rows = staticmethod(attach_tooltip_rows)

    def _emit_trace(
        self, t: Trace, pw: PayloadWriter, xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        from ._payload_trace_materialize import emit_trace_materialized

        return emit_trace_materialized(self, t, pw, xr, yr, px_width)

    def _visible_mask_needed(
        self,
        t: Trace,
        *,
        prefiltered: bool,
        base_column: Optional[Column] = None,
    ) -> bool:
        return visible_mask_needed(self, t, prefiltered=prefiltered, base_column=base_column)

    def _log_visible_mask(
        self,
        t: Trace,
        xv: np.ndarray,
        yv: np.ndarray,
        base: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        return log_visible_mask(self, t, xv, yv, base=base)

    def _binning_coords(
        self, axis_id: str, values: np.ndarray, bounds: tuple[float, float]
    ) -> tuple[np.ndarray, tuple[float, float]]:
        return binning_coords(self, axis_id, values, bounds)

    def _ship_trace_channel_attach(
        self,
        entry: dict[str, Any],
        t: Trace,
        sel,
        pw: PayloadWriter,
        slot: int,
        *,
        include_trace_styles: bool,
        has_color2_ch: bool = False,
    ) -> None:  # noqa: ANN001
        ship_trace_channel_attach(
            entry,
            t,
            sel,
            pw,
            slot,
            include_trace_styles=include_trace_styles,
            has_color2_ch=has_color2_ch,
        )

    def _payload_column_ship_plan(
        self, t: Trace, *, kind: Optional[str] = None, orientation: Optional[str] = None
    ) -> dict:
        return payload_column_ship_plan(self, t, kind=kind, orientation=orientation)

    def _ship_channels(
        self, t: Trace, sel, ship_scalar, ship_u8, *, quantize_continuous: bool = False
    ) -> tuple[Any, Any]:  # noqa: ANN001
        return channels.ship_channels(
            t, sel, ship_scalar, ship_u8, quantize_continuous=quantize_continuous
        )
