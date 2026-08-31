"""Wire-spec compiler for `Figure`: `build_payload` plus the per-kind
emitters and the Tier-2 density/sample specs, and the `_PayloadWriter` that
owns the binary blob + column table. Split out of `_figure.py` as a mixin;
`Figure` inherits `PayloadMixin`, so every `self.*` resolves through the
concrete `Figure` via the MRO (§29: data moves as typed binary buffers)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import channels, kernels, lod
from ._payload_density import PayloadDensityMixin
from ._trace import Trace
from .columns import Column
from .config import (
    MAX_ANIMATION_MATCH_ROWS,
    PROTOCOL_VERSION,
)

if TYPE_CHECKING:
    # Type-only host base so the mixin's `self.*` resolves against the Figure
    # surface (a Protocol, so no inheritance cycle); runtime base is `object`.
    from ._hosts import FigureHost as _Host
else:
    _Host = object


class _PayloadWriter:
    """Accumulates the binary blob + column table for `build_payload`.

    The single place that knows the wire encoding, so every chart type ships
    columns the same way (§29): `ship` for offset-encoded geometry (§4), and
    `ship_scalar` for raw f32 channels/grids already in final units, and
    `ship_u8` for byte-precision categorical/density values. Adding a chart
    means calling these, not re-implementing the encoding.
    """

    def __init__(
        self,
        *,
        split: bool = False,
        borrow_heatmaps: bool = False,
        point_overlay: bool = True,
    ) -> None:
        # split=True: every column ships as its own wire buffer — spec entries
        # carry `buf` (the wire-buffer index) with byte_offset 0, and
        # `buffers()` returns per-column views with no join copy. Packed mode
        # keeps the single `blob()` with global byte offsets (standalone
        # export, streaming-refresh reopen state).
        self.columns: list[dict[str, Any]] = []
        self._chunks: list[bytes | np.ndarray] = []
        self._pos = 0
        self._split = split
        self.borrow_heatmaps = borrow_heatmaps
        self.borrowed: list[np.ndarray] = []
        # point_overlay=False: skip the density tier's sampled point overlay.
        # Only the *raster* exporters set this. They draw density traces
        # through `_emit_grid`, which never reads `density["sample"]`, so on
        # that path the overlay is an O(N) SplitMix scan plus two gathers whose
        # result no pixel consumes. The browser client *does* draw it
        # (`50_chartview.ts`), so `build_payload`/`build_payload_split` must
        # keep shipping it.
        self.point_overlay = point_overlay

    def ship(self, values: np.ndarray, col: "Column", *, scale: str | None = None) -> int:
        """Offset-encoded geometry column: `(v - offset) * scale` as f32
        (§4/§16). Scale is 1.0 except for absurd-magnitude domains, where it
        normalizes so finite f64 can't overflow to ±inf in f32 (§19).
        `scale` is the target axis scale: log-family axes pin the offset to
        0.0 (`lod.geometry_offset`) so relative f32 precision survives the
        shader-side transform."""
        # Direct append payloads need a stable encoding so their previous
        # bytes remain a prefix of the new column. Log-family axes retain
        # their required zero origin; linear axes use the column's sticky
        # shipped offset and re-center only when it leaves the safe span.
        offset = (
            lod.geometry_offset(scale, col.min, col.max)
            if lod.pins_offset_to_zero(scale)
            else col.suggest_offset()
        )
        encoded = lod.encode_f32_values(
            values,
            offset,
            col.min,
            col.max,
            kind=col.kind,
        )
        return self._append(encoded.values, encoded.meta)

    def ship_scalar(self, values: np.ndarray) -> int:
        """Raw f32 column already in final units (no offset): channel/grid/heights."""
        enc = np.ascontiguousarray(values, dtype=np.float32)
        return self._append(enc, {})

    def ship_u8(self, values: np.ndarray) -> int:
        """Raw byte column, padded so every later f32 column stays aligned."""
        enc = np.ascontiguousarray(values, dtype=np.uint8).reshape(-1)
        index = len(self.columns)
        if self._split:
            # One buffer per column: fold the alignment padding into the u8
            # buffer itself (spec `len` still counts only real values), so the
            # split layout stays a byte-identical repack of the packed blob.
            padding = (-len(enc)) % 4
            padded = np.concatenate([enc, np.zeros(padding, np.uint8)]) if padding else enc
            self.columns.append(
                {"buf": len(self._chunks), "byte_offset": 0, "len": int(len(enc)), "dtype": "u8"}
            )
            self._chunks.append(padded)
            self._pos += padded.nbytes
            return index
        self.columns.append({"byte_offset": self._pos, "len": int(len(enc)), "dtype": "u8"})
        self._chunks.append(enc)
        self._pos += enc.nbytes
        padding = (-self._pos) % 4
        if padding:
            self._chunks.append(bytes(padding))
            self._pos += padding
        return index

    def ship_u32(self, values: np.ndarray) -> int:
        """Raw uint32 identity words used by keyed transitions.

        Keys remain binary row data, never JSON metadata. Packed and split
        layouts share the ordinary four-byte alignment contract.
        """
        enc = np.ascontiguousarray(values, dtype="<u4").reshape(-1)
        return self._append(enc, {"dtype": "u32"})

    def ship_f64(self, values: np.ndarray) -> int:
        """Ship a canonical f64 column for an explicitly bounded WASM source.

        This is deliberately separate from painter geometry and is valid only
        in the live split transport.  Packed payloads serve export/notebook
        consumers and retain their screen-bounded painter contract; the
        browser host retains this canonical source and transfers only bounded
        replay chunks to the dedicated Worker. It is never decoded from
        offset f32 on the UI thread.
        """
        return self._append(
            np.ascontiguousarray(values, dtype="<f8").reshape(-1),
            {"dtype": "f64"},
        )

    def borrow_f64(self, values: np.ndarray) -> int:
        """Register canonical f64 storage as a synchronous raster-only span.

        Span 0 is the owned payload blob; borrowed arrays start at 1. Nothing
        about the public browser payload uses this representation.
        """
        arr = np.ascontiguousarray(values, dtype="<f8").reshape(-1)
        span = len(self.borrowed) + 1
        self.borrowed.append(arr)
        index = len(self.columns)
        self.columns.append({"span": span, "byte_offset": 0, "len": int(len(arr)), "dtype": "f64"})
        return index

    def ship_values(
        self, values: np.ndarray, *, kind: str = "float", scale: str | None = None
    ) -> int:
        """Offset-encoded temporary geometry not backed by a canonical Column."""
        vals = np.ascontiguousarray(values, dtype=np.float64)
        bounds = kernels.min_max(vals)
        lo, hi = bounds if bounds is not None else (0.0, 0.0)
        offset = lod.geometry_offset(scale, lo, hi) if bounds is not None else 0.0
        encoded = lod.encode_f32_values(vals, offset, lo, hi, kind=kind)
        return self._append(encoded.values, encoded.meta)

    def _append_from_materialized(self, enc: np.ndarray, meta: dict[str, Any]) -> int:
        """Register a Rust-materialized column without host-side re-encoding."""
        enc = np.ascontiguousarray(enc)
        idx = len(self.columns)
        if self._split:
            self.columns.append({"buf": len(self._chunks), "byte_offset": 0, **meta})
            self._chunks.append(enc)
            self._pos += enc.nbytes
            return idx
        self.columns.append({"byte_offset": self._pos, **meta})
        self._chunks.append(enc)
        self._pos += enc.nbytes
        if meta.get("dtype") != "u8" and meta.get("dtype") != "u32":
            padding = (-self._pos) % 4
            if padding:
                self._chunks.append(bytes(padding))
                self._pos += padding
        return idx

    def _append(self, enc: np.ndarray, meta: dict[str, Any]) -> int:
        # Retain the encoded array until blob assembly so each column is copied
        # once into the final bytes object, rather than once in `tobytes()` and
        # again by `join` — and split mode ships these views with no copy at all.
        enc = np.ascontiguousarray(enc)
        idx = len(self.columns)
        if self._split:
            # `buf` indexes the wire buffer list (== `_chunks`), which can
            # drift from the column table (`borrow_f64` columns own no chunk).
            self.columns.append(
                {"buf": len(self._chunks), "byte_offset": 0, "len": int(len(enc)), **meta}
            )
        else:
            self.columns.append({"byte_offset": self._pos, "len": int(len(enc)), **meta})
        self._chunks.append(enc)
        self._pos += enc.nbytes
        return idx

    def blob(self) -> bytes:
        return b"".join(
            chunk if isinstance(chunk, bytes) else chunk.data.cast("B") for chunk in self._chunks
        )

    def buffers(self) -> list[memoryview]:
        """Per-column wire buffers (split mode): zero-copy views over the
        encoded chunks, ready to ship as separate binary comm frames."""
        return [
            memoryview(c).cast("B") if isinstance(c, bytes) else c.data.cast("B")
            for c in self._chunks
        ]


class PayloadMixin(PayloadDensityMixin, _Host):
    def build_payload(self, px_width: Optional[int] = None) -> tuple[dict[str, Any], bytes]:
        """Encode every trace for first paint: (spec, binary buffer blob).

        Per-kind logic lives in `_emit_<kind>` methods dispatched here — adding a
        chart type means adding one emitter, not editing this loop. Direct traces
        ship whole columns offset-encoded (§4); long lines ship M4-decimated
        (§5 Tier 1); dense scatter ships a density grid (§5 Tier 2). Every
        reduction is recorded in the spec — no silent quality changes (§28).
        """
        pw = _PayloadWriter()
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
        pw = _PayloadWriter(split=True)
        spec = self._payload_spec(pw, self._resolve_px_width(px_width))
        spec["buffer_layout"] = "split"
        return spec, pw.buffers()

    def _build_raster_payload(
        self, px_width: Optional[int] = None
    ) -> tuple[dict[str, Any], bytes, tuple[np.ndarray, ...]]:
        """Private static-export payload with borrowed canonical heatmap spans."""
        pw = _PayloadWriter(borrow_heatmaps=True, point_overlay=False)
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

    def _payload_spec(self, pw: "_PayloadWriter", px_width: int) -> dict[str, Any]:
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
        pw: "_PayloadWriter",
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
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
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
        pw: "_PayloadWriter",
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
        pw: "_PayloadWriter",
        column_plan: dict[str, Any],
        arrays: dict[str, np.ndarray],
        *,
        skip_keys: Optional[frozenset[str]] = None,
        nested_keys: Optional[frozenset[str]] = None,
        sel: np.ndarray | None = None,
    ) -> None:
        """Ship gathered geometry arrays into ``entry`` per the column registry."""
        cols = [
            col
            for col in column_plan["columns"]
            if skip_keys is None or col["registry_key"] not in skip_keys
        ]
        if not cols:
            return
        x_scale = self._axis_scale(t.x_axis).encode("utf-8")
        y_scale = self._axis_scale(t.y_axis).encode("utf-8")
        descriptors: list[dict[str, Any]] = []
        values: list[np.ndarray] = []
        kinds: list[bytes] = []
        scales: list[bytes] = []
        for col in cols:
            key = col["registry_key"]
            slot = col["trace_slot"]
            source = getattr(t, slot, None)
            if sel is not None and isinstance(source, Column):
                raw_arr = source.values
            else:
                raw_arr = arrays[key] if key in arrays else arrays[slot]
            column = source if isinstance(source, Column) else getattr(t, slot, None)
            if col["ship_method"] == "offset" and isinstance(column, Column):
                col_min, col_max = float(column.min), float(column.max)
                sticky = float(column.suggest_offset())
                kind_b = str(column.kind).encode("utf-8")
            elif col["ship_method"] == "values":
                bounds = kernels.min_max(raw_arr)
                col_min, col_max = bounds if bounds is not None else (0.0, 0.0)
                sticky = 0.0
                kind_b = str(column.kind if column is not None else "float").encode("utf-8")
            else:
                col_min, col_max = 0.0, 0.0
                sticky = 0.0
                kind_b = b""
            descriptors.append(
                {
                    "registry_key": key,
                    "ship_method": col["ship_method"],
                    "ship_scale": col["ship_scale"],
                    "col_min": col_min,
                    "col_max": col_max,
                    "sticky_offset": sticky,
                }
            )
            values.append(np.ascontiguousarray(raw_arr, dtype=np.float64).reshape(-1))
            kinds.append(kind_b)
            scales.append(x_scale if col["ship_scale"] == "x" else y_scale)
        materialized = kernels.payload_column_gather_materialize(
            sel=sel,
            columns=descriptors,
            values=values,
            kinds=kinds,
            axis_scales=scales,
        )
        for col, mat in zip(cols, materialized, strict=True):
            key = col["registry_key"]
            enc = np.frombuffer(mat["bytes"], dtype="<f4" if mat["dtype_code"] == 0 else "<f8")
            col_idx = pw._append_from_materialized(enc, mat["meta"])
            if nested_keys is not None and key in nested_keys:
                entry[key] = {"col": col_idx, **pw.columns[col_idx]}
            else:
                entry[key] = col_idx

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
