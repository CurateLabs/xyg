"""Wire-spec compiler for `Figure`: `build_payload` plus the per-kind
emitters and the Tier-2 density/sample specs. Split out of `_figure.py` as a
mixin; `Figure` inherits `PayloadMixin`, so every `self.*` resolves through the
concrete `Figure` via the MRO (§29: data moves as typed binary buffers)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import channels, kernels, lod
from ._payload_density import PayloadDensityMixin
from ._payload_ship import ship_registry_columns
from ._payload_writer import PayloadWriter
from ._trace import Trace
from .columns import Column
from .config import (
    MAX_ANIMATION_MATCH_ROWS,
    PROTOCOL_VERSION,
)

if TYPE_CHECKING:
    from ._hosts import FigureHost as _Host
else:
    _Host = object


class PayloadMixin(PayloadDensityMixin, _Host):
    def build_payload(self, px_width: Optional[int] = None) -> tuple[dict[str, Any], bytes]:
        """Encode every trace for first paint: (spec, binary buffer blob).

        Per-kind logic lives in `_emit_<kind>` methods dispatched here — adding a
        chart type means adding one emitter, not editing this loop. Direct traces
        ship whole columns offset-encoded (§4); long lines ship M4-decimated
        (§5 Tier 1); dense scatter ships a density grid (§5 Tier 2). Every
        reduction is recorded in the spec — no silent quality changes (§28).
        """
        pw = PayloadWriter()
        spec = self._payload_spec(pw, self._resolve_px_width(px_width))
        return spec, pw.blob()

    def build_payload_split(
        self, px_width: Optional[int] = None
    ) -> tuple[dict[str, Any], list[memoryview]]:
        """`build_payload` with per-column wire buffers instead of one blob.

        Same emitters, same encoded bytes — but the columns ship as a list of
        borrowed buffer views, skipping the join copy (the single largest
        allocation of a direct-tier build). The spec says so explicitly:
        `buffer_layout: "split"`, and each column entry carries `buf`, its
        index into the buffer list (§29 — the comm protocol already carries
        multi-buffer messages on the update path; this extends it to first
        paint).
        """
        pw = PayloadWriter(split=True)
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
            # A concrete chart should pay for the pixels it can display, not
            # the historical 2048px fluid-layout fallback. Responsive charts
            # keep that headroom until the browser reports a real width; live
            # resize/view requests then refine the decimation for the new size.
            width = self.width
            px_width = (
                int(width)
                if isinstance(width, (int, float)) and not isinstance(width, bool)
                else 2048
            )
        px_width, _ = lod.screen_shape(px_width, 16)
        return px_width

    def _payload_spec(self, pw: PayloadWriter, px_width: int) -> dict[str, Any]:
        # `_range` is an O(traces x chunks) autorange scan and is invariant
        # while this build runs (emitters only touch shipped_sel/drill state),
        # so each axis pays for it once even when many traces share an axis.
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
        if build_plan["attach_wasm_density"]:
            wasm_density_kind = build_plan["wasm_density_kind"]
            if wasm_density_kind == kernels.DENSITY_WASM_DENSITY_AUTOMATIC:
                spec["wasm_density"] = {"automatic": True, "source": wasm_sources[0]}
            elif wasm_density_kind == kernels.DENSITY_WASM_DENSITY_UNSUPPORTED:
                spec["wasm_density"] = {
                    "automatic": False,
                    "unsupported": {
                        "code": "XYG_WASM_SOURCE_UNSUPPORTED",
                        "message": "direct WASM density requires one bounded Cartesian count-only f64 source",
                        "trace_ids": [
                            entry["id"] for entry in spec_traces if entry.get("tier") == "density"
                        ],
                    },
                }
        if build_plan["attach_title_options"]:
            spec["title_options"] = [
                {
                    **{key: value for key, value in entry.items() if key not in {"y", "pad"}},
                    "geometry": pw.ship_scalar(
                        np.asarray(
                            (entry.get("y", 1.0), entry.get("pad", 8.0)),
                            dtype=np.float64,
                        )
                    ),
                }
                for entry in self.title_options
            ]
        if build_plan["attach_coords"]:
            spec["coords"] = self.coords
        if build_plan["attach_palette"]:
            # Chart-level categorical cycle (`xyg.theme(palette=...)`). Every
            # trace already bakes its own color and every categorical channel
            # ships its own resolved `palette`, so this is only the indexed
            # fallback the STATIC exporters use for a trace that carries no
            # style color. The browser client never reads it — it works from
            # `trace.color.palette` — which is why omitting it (no chart
            # palette set) leaves existing specs byte-identical.
            # `palette_cycle`, not `list(self.palette)`: a `{category: color}`
            # palette would otherwise ship its category NAMES as colors.
            spec["palette"] = self.palette_cycle
        if build_plan["attach_legend"]:
            legend = legend_opts
            if build_plan["resolve_legend_best"]:
                # Settle `best` here, once, so the client and the two static
                # writers all receive a concrete location and cannot disagree
                # about it (§28: the decision ships, it is not re-made
                # downstream three times).
                from ._legendfit import resolve_for_figure

                legend = {**legend, "loc": resolve_for_figure(self)}
            spec["legend"] = legend
        if build_plan["attach_extra_legends"]:
            spec["extra_legends"] = getattr(self, "extra_legends", None)
        if build_plan["attach_frame_sides"]:
            spec["frame_sides"] = list(self.frame_sides)
        if build_plan["attach_colorbar"]:
            spec["colorbar"] = self.colorbar_options
        if build_plan["attach_show_modebar"]:
            spec["show_modebar"] = False
        if build_plan["attach_export"]:
            spec["export"] = getattr(self, "export_options", None)
        if build_plan["attach_show_tooltip"]:
            spec["show_tooltip"] = False
        if build_plan["attach_padding"]:
            spec["padding"] = list(self.padding)
        if build_plan["attach_dom"]:
            spec["dom"] = dom
        if build_plan["attach_tooltip"]:
            spec["tooltip"] = self.tooltip
        if build_plan["attach_mark_style"]:
            spec["mark_style"] = mark_style
        if build_plan["attach_interaction"]:
            spec["interaction"] = interaction_spec
        if build_plan["attach_annotations"]:
            spec["annotations"] = annotations
        if build_plan["attach_animation"]:
            spec["animation"] = dict(self.animation_options)
        if build_plan["attach_graph"]:
            # JSON-safe graph meta for neighborhood highlight / LOD (§28).
            # CSR offsets/neighbors stay u64 lists; geometry remains segments+scatter.
            spec["graph"] = list(getattr(self, "_graph_meta", None))
        return spec

    @staticmethod
    def _transition_entry(
        entry: dict[str, Any],
        t: Trace,
        pw: PayloadWriter,
        sel: Optional[np.ndarray] = None,
        key_values: Optional[np.ndarray] = None,
    ) -> dict[str, Any]:
        """Attach bounded declarative transition metadata to one trace spec."""
        plan = kernels.payload_transition_entry_attach(
            has_trace_animation=t.animation is not None,
            entry_has_animation="animation" in entry,
            has_trace_keys=t.transition_keys is not None,
            has_key_values=key_values is not None,
            has_sel=sel is not None,
            tier_direct=entry.get("tier") == "direct",
            n_marks=int(entry.get("n_marks", 0)),
            n_trace_key_rows=len(t.transition_keys) if t.transition_keys is not None else 0,
            n_key_value_rows=len(key_values) if key_values is not None else 0,
            n_sel_rows=len(sel) if sel is not None else 0,
            max_rows=MAX_ANIMATION_MATCH_ROWS,
            has_tooltip_rows=False,
            n_tooltip_rows=0,
            n_points=t.n_points,
        )
        if plan["attach_animation"]:
            entry["animation"] = dict(t.animation)
        if not plan["attempt_keys"]:
            return entry
        keys = t.transition_keys if key_values is None else key_values
        keys = np.asarray(keys, dtype=np.uint32)
        values = keys[sel] if plan["filter_keys_by_sel"] else keys
        if not plan["ship_keys"]:
            entry["animation_fallback"] = plan["animation_fallback"]
            return entry
        entry["keys"] = {
            "lo": pw.ship_u32(values[:, 0]),
            "hi": pw.ship_u32(values[:, 1]),
        }
        return entry

    def _emit_trace(
        self, t: Trace, pw: PayloadWriter, xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        from ._payload_trace_materialize import emit_trace_materialized

        return emit_trace_materialized(self, t, pw, xr, yr, px_width)

    @staticmethod
    def _attach_tooltip_rows(entry: dict[str, Any], t: Trace, sel: Optional[np.ndarray]) -> None:
        """Ship optional semantic hover rows (Sankey / graph props), filtered with geometry."""
        plan = kernels.payload_transition_entry_attach(
            has_trace_animation=False,
            entry_has_animation=False,
            has_trace_keys=False,
            has_key_values=False,
            has_sel=sel is not None,
            tier_direct=False,
            n_marks=0,
            n_trace_key_rows=0,
            n_key_value_rows=0,
            n_sel_rows=len(sel) if sel is not None else 0,
            max_rows=MAX_ANIMATION_MATCH_ROWS,
            has_tooltip_rows=t.tooltip_rows is not None,
            n_tooltip_rows=len(t.tooltip_rows) if t.tooltip_rows is not None else 0,
            n_points=t.n_points,
        )
        if not plan["attach_tooltip"]:
            if t.tooltip_rows is not None and not plan["tooltip_length_ok"]:
                raise ValueError(
                    f"{t.kind} tooltip rows must match geometry "
                    f"({len(t.tooltip_rows)} != {t.n_points})"
                )
            return
        indices = (
            range(len(t.tooltip_rows))
            if not plan["filter_tooltip_by_sel"]
            else (int(i) for i in sel)
        )
        entry["tooltip_rows"] = [dict(t.tooltip_rows[i]) for i in indices]

    @staticmethod
    def _finite_sel(t: Trace, xv: np.ndarray, yv: np.ndarray) -> np.ndarray | None:
        """Indices where both x and y are finite, or None if nothing to drop.

        Non-finite (NaN or ±inf) never reaches a vertex buffer — it silently
        corrupts primitives, driver-dependently (§19). Zone maps count both as
        null, so we only scan when a null is present. Canonical keeps every row;
        real gap semantics (segment index list) arrive with validity bitmaps.
        """
        if not (t.x.zone.null_count or t.y.zone.null_count):
            return None
        return np.flatnonzero(np.isfinite(xv) & np.isfinite(yv))

    def _visible_mask_needed(
        self,
        t: Trace,
        *,
        prefiltered: bool,
        base_column: Optional[Column] = None,
    ) -> bool:
        """Whether `_log_visible_mask` can drop any row for this trace.

        The mask is three O(N) passes plus two N-byte temporaries, and on the
        common shape (linear axes, no nulls) it is provably all-True: zone maps
        count NaN *and* ±inf as null (§22/§19), so a null-free column has no
        row for `isfinite` to reject, and `prefiltered` rows already went
        through `_finite_sel`. Only a log axis (which additionally rejects
        non-positive values) or a baseline column outside the x/y zone maps can
        actually remove something.
        """
        return kernels.payload_visible_needed(
            x_log=self._axis_scale(t.x_axis) == "log",
            y_log=self._axis_scale(t.y_axis) == "log",
            prefiltered=prefiltered,
            x_has_nulls=bool(t.x.zone.null_count),
            y_has_nulls=bool(t.y.zone.null_count),
            has_base=base_column is not None,
            base_has_nulls=bool(base_column.zone.null_count) if base_column is not None else False,
        )

    def _log_visible_mask(
        self,
        t: Trace,
        xv: np.ndarray,
        yv: np.ndarray,
        base: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Rows this trace may actually ship.

        Paired with `_visible_mask_needed`, which decides whether calling this
        can drop anything at all: **a new rejection rule here needs a matching
        condition there**, or the emitters will skip the mask on data it would
        now reject. (`tests/test_figure.py` pins one case per rule; the
        predicate going stale is otherwise silent.)
        """
        return kernels.payload_visible_mask(
            xv,
            yv,
            x_log=self._axis_scale(t.x_axis) == "log",
            y_log=self._axis_scale(t.y_axis) == "log",
            base=base,
        )

    def _binning_coords(
        self, axis_id: str, values: np.ndarray, bounds: tuple[float, float]
    ) -> tuple[np.ndarray, tuple[float, float]]:
        """Column values and window bounds in the axis's binning space.

        Nonlinear axes aggregate in scale coordinates (§28) so grid cells are
        uniform on screen; linear axes pass through untouched. Falls back to
        raw values when the transformed window degenerates (e.g. a log axis
        asked to bin a window that touches zero) — a uniform-in-data grid is
        better than no grid."""
        if self._axis_scale(axis_id) == "linear":
            return values, (float(bounds[0]), float(bounds[1]))
        c0, c1 = (float(v) for v in self._axis_coord(axis_id, bounds))
        if not (np.isfinite(c0) and np.isfinite(c1) and c1 > c0):
            return values, (float(bounds[0]), float(bounds[1]))
        return self._axis_coord(axis_id, values), (c0, c1)

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
        """Attach paint/style channels per Rust-owned channel ship registry (ABI 311)."""
        plan = kernels.payload_channel_ship_plan(
            slot,
            include_trace_styles=include_trace_styles,
            has_color2_ch=has_color2_ch,
            has_color_ch=t.color_ch is not None,
            has_stroke_ch=t.stroke_ch is not None,
            has_style_channels=bool(t.style_channels),
        )
        channels.ship_registry_attach(entry, t, sel, pw.ship_scalar, pw.ship_u8, plan)

    def _payload_column_ship_plan(
        self, t: Trace, *, kind: Optional[str] = None, orientation: Optional[str] = None
    ) -> dict:
        """Rust-owned geometry column registry and gather policy (ABI 310/314)."""
        return kernels.payload_column_ship_plan(
            kind=kind or t.kind,
            x_axis_scale=self._axis_scale(t.x_axis),
            y_axis_scale=self._axis_scale(t.y_axis),
            orientation=orientation,
        )

    def _ship_registry_columns(
        self,
        entry: dict[str, Any],
        t: Trace,
        pw: PayloadWriter,
        column_plan: dict[str, Any],
        arrays: dict[str, np.ndarray],
        *,
        skip_keys: Optional[frozenset[str]] = None,
        nested_keys: Optional[frozenset[str]] = None,
        sel: np.ndarray | None = None,
    ) -> None:
        ship_registry_columns(
            self,
            entry,
            t,
            pw,
            column_plan,
            arrays,
            skip_keys=skip_keys,
            nested_keys=nested_keys,
            sel=sel,
        )

    def _ship_channels(
        self, t: Trace, sel, ship_scalar, ship_u8, *, quantize_continuous: bool = False
    ) -> tuple[Any, Any]:  # noqa: ANN001
        """Ship a trace's color/size channels (delegates to channels.py — the
        same wire shape serves the build path and drill-in view updates).
        `quantize_continuous` is for live-interaction callers only; the build
        path keeps unit f32 because tooltips denormalize the shipped columns
        (see channels.ship_channels)."""
        return channels.ship_channels(
            t, sel, ship_scalar, ship_u8, quantize_continuous=quantize_continuous
        )
