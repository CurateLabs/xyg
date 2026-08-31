"""Wire-spec compiler for `Figure`: `build_payload` plus the per-kind
emitters and the Tier-2 density/sample specs, and the `_PayloadWriter` that
owns the binary blob + column table. Split out of `_figure.py` as a mixin;
`Figure` inherits `PayloadMixin`, so every `self.*` resolves through the
concrete `Figure` via the MRO (§29: data moves as typed binary buffers)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import _native, channels, interaction, kernels, lod
from ._trace import Trace
from ._wasm_aggregate_generated import WASM_AGGREGATE_MAX_POINTS
from .columns import Column
from .config import (
    DENSITY_GRID,
    DENSITY_SAMPLE_SEED,
    DENSITY_SAMPLE_TARGET,
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


class PayloadMixin(_Host):
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
        emitter = getattr(self, f"_emit_{t.kind}", None)
        if emitter is None:
            raise ValueError(f"no payload emitter for trace kind {t.kind!r}")
        return emitter(t, pw, xr, yr, px_width)

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

    def _visible_sel(
        self,
        t: Trace,
        xv: np.ndarray,
        yv: np.ndarray,
        *,
        base: Optional[np.ndarray] = None,
        prefiltered: bool = False,
        base_column: Optional[Column] = None,
    ) -> np.ndarray | None:
        """Keep-all (`None`) vs original-row keep indices (ABI 205)."""
        keep_all, idx = kernels.payload_visible_indices(
            xv,
            yv,
            x_log=self._axis_scale(t.x_axis) == "log",
            y_log=self._axis_scale(t.y_axis) == "log",
            base=base,
            prefiltered=prefiltered,
            x_has_nulls=bool(t.x.zone.null_count),
            y_has_nulls=bool(t.y.zone.null_count),
            has_base=base is not None or base_column is not None,
            base_has_nulls=(
                bool(base_column.zone.null_count) if base_column is not None else False
            ),
        )
        if keep_all:
            return None
        return idx

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

    def _default_styled(self, t: Trace) -> dict[str, Any]:
        """Trace style dict with the per-trace palette default when no color
        was given — the one place this rule lives (was copy-pasted per kind).
        Cycles the figure's palette (`xyg.theme(palette=...)`), which defaults
        to config.DEFAULT_PALETTE."""
        style = dict(t.style)
        plan = kernels.payload_base_entry_plan(
            has_trace_animation=False,
            n_xv=0,
            style_color_is_none=style.get("color") is None,
            x_axis_scale="linear",
            y_axis_scale="linear",
        )
        if plan["apply_palette_default"]:
            style["color"] = self.palette_color(t.id)
        return style

    def _base_entry(
        self, t: Trace, pw: "_PayloadWriter", xv: np.ndarray, yv: np.ndarray, tier: str, style: dict
    ) -> dict[str, Any]:
        """The shared spec skeleton for any xy trace that ships x/y geometry."""
        x_scale = self._axis_scale(t.x_axis)
        y_scale = self._axis_scale(t.y_axis)
        plan = kernels.payload_base_entry_plan(
            has_trace_animation=t.animation is not None,
            n_xv=len(xv),
            style_color_is_none=False,
            x_axis_scale=x_scale,
            y_axis_scale=y_scale,
        )
        entry = {
            "id": t.id,
            "kind": t.kind,
            "name": t.name,
            "style": style,
            "tier": tier,
            "n_points": t.n_points,
            "n_marks": plan["n_marks"],
            "x": pw.ship(xv, t.x, scale=plan["x_ship_scale"]),
            "y": pw.ship(yv, t.y, scale=plan["y_ship_scale"]),
            "x_axis": t.x_axis,
            "y_axis": t.y_axis,
        }
        if plan["attach_animation"]:
            entry["animation"] = dict(t.animation)
        return entry

    def _m4_decimate(
        self, t: Trace, xr: tuple, px_width: int, *arrays: np.ndarray
    ) -> tuple[str, tuple[np.ndarray, ...]]:
        """M4-decimate the parallel `arrays` (x first) when the trace is over
        the threshold; M4 already excludes non-finite within the window (§19).
        Returns `(tier, arrays)` — shared by the line and area emitters.

        On a nonlinear x axis the buckets are laid out in scale coordinates so
        each bucket covers a uniform strip of *screen*, not of raw data (§28);
        monotone transforms keep per-bucket min/max rows identical, so y stays
        raw and the gathered rows ship untransformed."""
        mx, (m0, m1) = self._binning_coords(t.x_axis, arrays[0], xr)
        use_bin = mx is not arrays[0]
        tier_code, idx = kernels.payload_m4_indices(
            t.n_points,
            arrays[0],
            arrays[1],
            float(xr[0]),
            float(xr[1]),
            int(px_width),
            polar=self.coords == "polar",
            bin_x=mx if use_bin else None,
            bin_x0=m0 if use_bin else 0.0,
            bin_x1=m1 if use_bin else 0.0,
        )
        if tier_code == 0:
            return "direct", arrays
        if len(idx):
            return "decimated", tuple(a[idx] for a in arrays)
        return "decimated", tuple(a[:0] for a in arrays)

    def _emit_line(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        tier, (xv, yv) = self._m4_decimate(t, xr, px_width, t.x.values, t.y.values)
        sel = self._visible_sel(t, xv, yv, prefiltered=tier != "direct")
        if sel is not None:
            xv, yv = xv[sel], yv[sel]
        entry = self._base_entry(t, pw, xv, yv, tier, self._default_styled(t))
        if tier == "decimated":
            # Record the px width this M4 pass was computed for (§28): the
            # client uses it to skip an at-home re-request that would only
            # recompute the same windows after a streaming append.
            entry["decimation_px"] = int(px_width)
        # Attach direct keys in the same finite/log-filtered row order.
        if t.transition_keys is not None:
            self._transition_entry(entry, t, pw, sel)
        return entry

    def _emit_area(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        if t.base is None:
            raise ValueError("area trace missing baseline column")
        tier, (xv, yv, bv) = self._m4_decimate(
            t, xr, px_width, t.x.values, t.y.values, t.base.values
        )
        sel = self._visible_sel(t, xv, yv, base=bv, base_column=t.base)
        if sel is not None:
            xv, yv, bv = xv[sel], yv[sel], bv[sel]
        entry = self._base_entry(t, pw, xv, yv, tier, self._default_styled(t))
        if tier == "decimated":
            entry["decimation_px"] = int(px_width)
        if t.transition_keys is not None:
            self._transition_entry(entry, t, pw, sel)
        entry["base"] = pw.ship(bv, t.base, scale=self._axis_scale(t.y_axis))
        return entry

    def _emit_error_band(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        return self._emit_area(t, pw, xr, yr, px_width)

    def _emit_scatter(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        del px_width
        pre_plan = kernels.payload_scatter_emit_plan(
            n_points=t.n_points,
            polar=self.coords == "polar",
            force_density=t.payload_force_density(),
            force_direct=False,
            per_item=t.has_per_item_channels(),
            n_marks=int(t.n_points),
            has_trace_animation=t.animation is not None,
            x_axis_scale=self._axis_scale(t.x_axis),
            y_axis_scale=self._axis_scale(t.y_axis),
            has_transition_keys=t.transition_keys is not None,
            has_tooltip_rows=t.tooltip_rows is not None,
            n_tooltip_rows=len(t.tooltip_rows) if t.tooltip_rows is not None else 0,
        )
        if pre_plan["emit_density"]:
            if pre_plan["clear_shipped_sel"]:
                t.shipped_sel = None
            if pre_plan["drill_mode_false"]:
                t.drill_mode = False
            entry = self._density_trace_spec(t, xr, yr, *DENSITY_GRID, pw)
            if pre_plan["attach_transition"]:
                return self._transition_entry(entry, t, pw)
            return entry
        xv, yv = t.x.values, t.y.values
        sel = self._visible_sel(t, xv, yv)
        if sel is not None:
            xv, yv = xv[sel], yv[sel]
        plan = kernels.payload_scatter_emit_plan(
            n_points=t.n_points,
            polar=self.coords == "polar",
            force_density=t.payload_force_density(),
            force_direct=False,
            per_item=t.has_per_item_channels(),
            n_marks=int(len(xv)),
            has_trace_animation=t.animation is not None,
            x_axis_scale=self._axis_scale(t.x_axis),
            y_axis_scale=self._axis_scale(t.y_axis),
            has_transition_keys=t.transition_keys is not None,
            has_tooltip_rows=t.tooltip_rows is not None,
            n_tooltip_rows=len(t.tooltip_rows) if t.tooltip_rows is not None else 0,
        )
        entry = self._base_entry(t, pw, xv, yv, "direct", dict(t.style))
        if plan["attach_transition"]:
            self._transition_entry(entry, t, pw, sel)
        self._ship_trace_channel_attach(
            entry,
            t,
            sel,
            pw,
            plan["channel_slot"],
            include_trace_styles=plan["include_trace_styles"],
        )
        if plan["attach_tooltip"]:
            self._attach_tooltip_rows(entry, t, sel)
        elif t.tooltip_rows is not None and not plan["tooltip_length_ok"]:
            raise ValueError(
                f"{t.kind} tooltip rows must match geometry ({len(t.tooltip_rows)} != {t.n_points})"
            )
        if plan["set_shipped_sel"]:
            t.shipped_sel = sel
        return entry

    def _emit_hexbin(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        del xr, yr, px_width
        xv, yv = t.x.values, t.y.values
        sel = self._visible_sel(t, xv, yv)
        if sel is not None:
            xv, yv = xv[sel], yv[sel]
        x_scale = self._axis_scale(t.x_axis)
        y_scale = self._axis_scale(t.y_axis)
        plan = kernels.payload_nonxy_emit_plan(
            kind="hexbin",
            n_marks=int(len(xv)),
            style_color_is_none=t.style.get("color") is None,
            x_axis_scale=x_scale,
            y_axis_scale=y_scale,
        )
        entry = {
            "id": t.id,
            "kind": t.kind,
            "name": t.name,
            "style": self._default_styled(t),
            "tier": "direct",
            "n_points": t.n_points,
            "n_marks": plan["n_marks"],
            "x_axis": t.x_axis,
            "y_axis": t.y_axis,
            "x": pw.ship_values(xv, scale=plan["x_ship_scale"]),
            "y": pw.ship_values(yv, scale=plan["y_ship_scale"]),
        }
        self._ship_trace_channel_attach(
            entry,
            t,
            sel,
            pw,
            plan["channel_slot"],
            include_trace_styles=plan["include_trace_styles"],
        )
        return entry

    def _emit_histogram(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        return self._emit_rect(t, pw, xr, yr, px_width)

    def _emit_bar(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        return self._emit_bar_compact(t, pw, xr, yr, px_width)

    def _emit_column(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        return self._emit_bar_compact(t, pw, xr, yr, px_width)

    def _emit_heatmap(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        del xr, yr, px_width
        if t.grid is None or t.grid_shape is None:
            raise ValueError("heatmap trace missing grid column")
        rows, cols = t.grid_shape
        plan = kernels.payload_heatmap_emit_plan(
            has_rgba_grid=t.rgba_grid is not None,
            grid_rows=int(rows),
            grid_cols=int(cols),
            style_colormap_is_none=t.style.get("colormap") is None,
            borrow_heatmaps=pw.borrow_heatmaps,
        )
        if plan["path"] == "rgba":
            return {
                "id": t.id,
                "kind": "heatmap",
                "name": t.name,
                "style": dict(t.style),
                "tier": "direct",
                "n_points": t.n_points,
                "n_marks": plan["n_marks"],
                "x_axis": t.x_axis,
                "y_axis": t.y_axis,
                "heatmap": {
                    "rgba_bufs": [pw.ship_scalar(column.values) for column in t.rgba_grid],
                    "w": int(cols),
                    "h": int(rows),
                    "x_range": list(t.style["x_range"]),
                    "y_range": list(t.style["y_range"]),
                },
            }
        domain = tuple(t.style["domain"])
        if plan["borrow_canonical"]:
            buffer_index = pw.borrow_f64(t.grid.values)
            encoding = "canonical-f64"
        else:
            norm = kernels.normalize_f32(t.grid.values, domain, nonfinite="nan")
            buffer_index = pw.ship_scalar(norm)
            encoding = None
        cmap = t.style.get("colormap")
        if plan["use_constant_colormap_fallback"]:
            # Constant-style Scene path: every renderer must paint the literal
            # color, not a default viridis ramp, so exports stay aligned.
            from ._raster import _parse_color

            red, green, blue, _alpha = _parse_color(str(t.style.get("color", "#3987e5")), 1.0)
            cmap = [[red, green, blue], [red, green, blue]]
        entry: dict[str, Any] = {
            "id": t.id,
            "kind": "heatmap",
            "name": t.name,
            "style": dict(t.style),
            "tier": "direct",
            "n_points": t.n_points,
            "n_marks": plan["n_marks"],
            "x_axis": t.x_axis,
            "y_axis": t.y_axis,
            "heatmap": {
                "buf": buffer_index,
                "w": int(cols),
                "h": int(rows),
                "x_range": list(t.style["x_range"]),
                "y_range": list(t.style["y_range"]),
                "colormap": cmap,
                "domain": list(domain),
                **({"enc": encoding} if plan["attach_encoding"] and encoding is not None else {}),
            },
        }
        if plan["attach_color"]:
            entry["color"] = {"mode": "continuous", "colormap": cmap, "domain": list(domain)}
        return entry

    def _emit_box(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        return self._emit_rect(t, pw, xr, yr, px_width)

    def _emit_violin(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        return self._emit_rect(t, pw, xr, yr, px_width)

    def _emit_segments(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        del xr, yr
        if t.x0 is None or t.x1 is None or t.y0 is None or t.y1 is None:
            raise ValueError(f"{t.kind} trace missing segment columns")
        x0v, x1v, y0v, y1v = t.x0.values, t.x1.values, t.y0.values, t.y1.values
        pre_plan = kernels.payload_segments_emit_plan(
            kind=t.kind,
            n_marks=int(len(x0v)),
            style_color_is_none=t.style.get("color") is None,
            x_axis_scale=self._axis_scale(t.x_axis),
            y_axis_scale=self._axis_scale(t.y_axis),
            has_transition_keys=t.transition_keys is not None,
        )
        gather: Optional[dict[str, object]] = None
        if pre_plan["attempt_gather"]:
            gather = kernels.payload_segments_emit_gather(
                t.kind,
                len(x0v),
                int(t.count or 0),
                px_width,
            )
        tier = "direct"
        source_sel: Optional[np.ndarray] = None
        segment_sources: Optional[np.ndarray] = None
        segment_roles: Optional[np.ndarray] = None
        if gather is not None:
            tier = "decimated" if gather["tier"] == 1 else "direct"
            if not gather["keep_all"]:
                chosen64 = np.asarray(gather["indices"], dtype=np.int64)
                x0v, x1v, y0v, y1v = (
                    x0v[chosen64],
                    x1v[chosen64],
                    y0v[chosen64],
                    y1v[chosen64],
                )
                source_sel = chosen64
            if gather["role_maps"]:
                segment_sources = np.asarray(gather["sources"], dtype=np.int64)
                segment_roles = np.asarray(gather["roles"], dtype=np.int64)
        finite_sel = self._rect_finite_sel(t, x0v, x1v, y0v, y1v)
        if finite_sel is not None:
            x0v, x1v, y0v, y1v = (
                x0v[finite_sel],
                x1v[finite_sel],
                y0v[finite_sel],
                y1v[finite_sel],
            )
            source_sel = finite_sel if source_sel is None else source_sel[finite_sel]
            if segment_sources is not None and segment_roles is not None:
                segment_sources = segment_sources[finite_sel]
                segment_roles = segment_roles[finite_sel]
        plan = kernels.payload_segments_emit_plan(
            kind=t.kind,
            n_marks=int(len(x0v)),
            style_color_is_none=t.style.get("color") is None,
            x_axis_scale=self._axis_scale(t.x_axis),
            y_axis_scale=self._axis_scale(t.y_axis),
            has_transition_keys=t.transition_keys is not None,
        )
        entry = {
            "id": t.id,
            "kind": t.kind,
            "name": t.name,
            "style": self._default_styled(t),
            "tier": tier,
            "n_points": t.n_points,
            "n_marks": plan["n_marks"],
            "x_axis": t.x_axis,
            "y_axis": t.y_axis,
            "x0": pw.ship(x0v, t.x0, scale=plan["x_ship_scale"]),
            "x1": pw.ship(x1v, t.x1, scale=plan["x_ship_scale"]),
            "y0": pw.ship(y0v, t.y0, scale=plan["y_ship_scale"]),
            "y1": pw.ship(y1v, t.y1, scale=plan["y_ship_scale"]),
        }
        self._ship_trace_channel_attach(
            entry,
            t,
            source_sel,
            pw,
            plan["channel_slot"],
            include_trace_styles=plan["include_trace_styles"],
        )
        self._attach_tooltip_rows(entry, t, source_sel)
        key_values = None
        if (
            plan["attempt_role_keys"]
            and tier == "direct"
            and t.transition_keys is not None
            and segment_sources is not None
            and segment_roles is not None
        ):
            # An errorbar point expands into independently rendered main/cap
            # segments. Derive a stable role-qualified key so the browser can
            # key-match those segments without duplicate identities.
            key_values = kernels.payload_errorbar_role_keys(
                t.transition_keys[:, 0],
                t.transition_keys[:, 1],
                segment_sources.astype(np.uint32, copy=False),
                segment_roles.astype(np.uint32, copy=False),
            )
        if plan["attach_transition"]:
            return self._transition_entry(entry, t, pw, source_sel, key_values)
        return entry

    def _emit_ribbon(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        """Ship a flow band: two faces on x, four span edges on y, two paints.

        The six geometry slots are saturated (ribbon geometry contract), so the
        target span's y values ride in the `x`/`y` slots and must be shipped on
        the **y** scale, not the x one — the single easiest thing to get wrong
        here, and it would place every ribbon's far end at the wrong height.
        """
        del xr, yr, px_width
        if t.x0 is None or t.x1 is None or t.y0 is None or t.y1 is None:
            raise ValueError("ribbon trace missing geometry columns")
        columns = (t.x0, t.x1, t.y0, t.y1, t.x, t.y)
        arrays = [column.values for column in columns]
        any_geometry_nulls = any(column.zone.null_count for column in columns)
        pre_plan = kernels.payload_ribbon_emit_plan(
            n_marks=int(len(arrays[0])),
            style_color_is_none=t.style.get("color") is None,
            x_axis_scale=self._axis_scale(t.x_axis),
            y_axis_scale=self._axis_scale(t.y_axis),
            any_geometry_nulls=any_geometry_nulls,
            has_color2_ch=t.color2_ch is not None,
        )
        sel_arg: Optional[np.ndarray] = None
        if pre_plan["attempt_gather"]:
            candidates = [
                array
                for column, array in zip(columns, arrays, strict=True)
                if column.zone.null_count
            ]
            sel_arg = kernels.valid_indices_f64(tuple(candidates))
        if sel_arg is not None:
            arrays = [array[sel_arg] for array in arrays]
        x0v, x1v, slo, shi, tlo, thi = arrays
        plan = kernels.payload_ribbon_emit_plan(
            n_marks=int(len(x0v)),
            style_color_is_none=t.style.get("color") is None,
            x_axis_scale=self._axis_scale(t.x_axis),
            y_axis_scale=self._axis_scale(t.y_axis),
            any_geometry_nulls=any_geometry_nulls,
            has_color2_ch=t.color2_ch is not None,
        )
        entry = {
            "id": t.id,
            "kind": t.kind,
            "name": t.name,
            "style": self._default_styled(t),
            # Always direct: a flow diagram is small-N by nature, and neither
            # decimation nor a density tier means anything for a band (§28).
            "tier": "direct",
            "n_points": t.n_points,
            "n_marks": plan["n_marks"],
            "x_axis": t.x_axis,
            "y_axis": t.y_axis,
            "x0": pw.ship(x0v, t.x0, scale=plan["x_ship_scale"]),
            "x1": pw.ship(x1v, t.x1, scale=plan["x_ship_scale"]),
            "y0": pw.ship(slo, t.y0, scale=plan["y_ship_scale"]),
            "y1": pw.ship(shi, t.y1, scale=plan["y_ship_scale"]),
            "target_y0": pw.ship(tlo, t.x, scale=plan["y_ship_scale"]),
            "target_y1": pw.ship(thi, t.y, scale=plan["y_ship_scale"]),
        }
        if plan["attach_color2"]:
            entry["color_target"] = channels.ship_color_channel(
                t.color2_ch, sel_arg, pw.ship_scalar, pw.ship_u8
            )
        self._attach_tooltip_rows(entry, t, sel_arg)
        self._ship_trace_channel_attach(
            entry,
            t,
            sel_arg,
            pw,
            plan["channel_slot"],
            include_trace_styles=plan["include_trace_styles"],
        )
        if plan["attach_transition"]:
            return self._transition_entry(entry, t, pw, sel_arg)
        return entry

    def _emit_triangle_mesh(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        del xr, yr, px_width
        if t.x0 is None or t.x1 is None or t.y0 is None or t.y1 is None:
            raise ValueError("triangle_mesh trace missing geometry columns")
        x0v, x1v, x2v = t.x0.values, t.x1.values, t.x.values
        y0v, y1v, y2v = t.y0.values, t.y1.values, t.y.values
        geometry = (t.x0, t.x1, t.x, t.y0, t.y1, t.y)
        values = (x0v, x1v, x2v, y0v, y1v, y2v)
        any_geometry_nulls = any(column.zone.null_count for column in geometry)
        has_continuous_color = t.color_ch is not None and t.color_ch.mode == "continuous"
        continuous_color_values_missing = (
            has_continuous_color and t.color_ch is not None and t.color_ch.values is None
        )
        pre_plan = kernels.payload_mesh_emit_plan(
            n_marks=int(len(x0v)),
            style_color_is_none=t.style.get("color") is None,
            x_axis_scale=self._axis_scale(t.x_axis),
            y_axis_scale=self._axis_scale(t.y_axis),
            any_geometry_nulls=any_geometry_nulls,
            has_continuous_color=has_continuous_color,
            continuous_color_values_missing=continuous_color_values_missing,
        )
        sel_arg: Optional[np.ndarray] = None
        if pre_plan["attempt_gather"]:
            candidates = [
                array
                for column, array in zip(geometry, values, strict=True)
                if column.zone.null_count
            ]
            if pre_plan["gather_include_color"]:
                if t.color_ch is None or t.color_ch.values is None:
                    raise ValueError("triangle_mesh continuous color channel missing values")
                candidates.append(t.color_ch.values)
            sel_arg = kernels.valid_indices_f64(tuple(candidates))
        if sel_arg is not None:
            x0v, x1v, x2v = x0v[sel_arg], x1v[sel_arg], x2v[sel_arg]
            y0v, y1v, y2v = y0v[sel_arg], y1v[sel_arg], y2v[sel_arg]
        plan = kernels.payload_mesh_emit_plan(
            n_marks=int(len(x0v)),
            style_color_is_none=t.style.get("color") is None,
            x_axis_scale=self._axis_scale(t.x_axis),
            y_axis_scale=self._axis_scale(t.y_axis),
            any_geometry_nulls=any_geometry_nulls,
            has_continuous_color=has_continuous_color,
            continuous_color_values_missing=continuous_color_values_missing,
        )
        entry = {
            "id": t.id,
            "kind": t.kind,
            "name": t.name,
            "style": self._default_styled(t),
            "tier": "direct",
            "n_points": t.n_points,
            "n_marks": plan["n_marks"],
            "x_axis": t.x_axis,
            "y_axis": t.y_axis,
            "x0": pw.ship(x0v, t.x0, scale=plan["x_ship_scale"]),
            "x1": pw.ship(x1v, t.x1, scale=plan["x_ship_scale"]),
            "x2": pw.ship(x2v, t.x, scale=plan["x_ship_scale"]),
            "y0": pw.ship(y0v, t.y0, scale=plan["y_ship_scale"]),
            "y1": pw.ship(y1v, t.y1, scale=plan["y_ship_scale"]),
            "y2": pw.ship(y2v, t.y, scale=plan["y_ship_scale"]),
        }
        self._ship_trace_channel_attach(
            entry,
            t,
            sel_arg,
            pw,
            plan["channel_slot"],
            include_trace_styles=plan["include_trace_styles"],
        )
        if plan["attach_transition"]:
            return self._transition_entry(entry, t, pw, sel_arg)
        return entry

    def _emit_errorbar(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        return self._emit_segments(t, pw, xr, yr, px_width)

    def _emit_stem(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        return self._emit_segments(t, pw, xr, yr, px_width)

    def _emit_box_whisker(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        return self._emit_segments(t, pw, xr, yr, px_width)

    def _emit_box_median(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        return self._emit_segments(t, pw, xr, yr, px_width)

    def _emit_contour(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        return self._emit_segments(t, pw, xr, yr, px_width)

    def _emit_rect(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        del xr, yr, px_width
        if t.x0 is None or t.x1 is None or t.y0 is None or t.y1 is None:
            raise ValueError(f"{t.kind} trace missing rectangle columns")
        x0v, x1v, y0v, y1v = t.x0.values, t.x1.values, t.y0.values, t.y1.values
        sel_arg = self._rect_finite_sel(t, x0v, x1v, y0v, y1v)
        if sel_arg is not None:
            x0v, x1v, y0v, y1v = x0v[sel_arg], x1v[sel_arg], y0v[sel_arg], y1v[sel_arg]
        x_scale = self._axis_scale(t.x_axis)
        y_scale = self._axis_scale(t.y_axis)
        if t.kind == "histogram":
            plan = kernels.payload_bar_hist_emit_plan(
                kind="histogram",
                n_marks=int(len(x0v)),
                style_color_is_none=t.style.get("color") is None,
                x_axis_scale=x_scale,
                y_axis_scale=y_scale,
            )
        else:
            plan = kernels.payload_nonxy_emit_plan(
                kind="rect",
                n_marks=int(len(x0v)),
                style_color_is_none=t.style.get("color") is None,
                x_axis_scale=x_scale,
                y_axis_scale=y_scale,
            )
        style = self._default_styled(t)
        entry = {
            "id": t.id,
            "kind": t.kind,
            "name": t.name,
            "style": style,
            "tier": "direct",
            "n_points": t.n_points,
            "n_marks": plan["n_marks"],
            "x_axis": t.x_axis,
            "y_axis": t.y_axis,
            "x0": pw.ship(x0v, t.x0, scale=plan["x_ship_scale"]),
            "x1": pw.ship(x1v, t.x1, scale=plan["x_ship_scale"]),
            "y0": pw.ship(y0v, t.y0, scale=plan["y_ship_scale"]),
            "y1": pw.ship(y1v, t.y1, scale=plan["y_ship_scale"]),
        }
        self._ship_trace_channel_attach(
            entry,
            t,
            sel_arg,
            pw,
            plan["channel_slot"],
            include_trace_styles=plan["include_trace_styles"],
        )
        if plan["attach_transition"]:
            return self._transition_entry(entry, t, pw, sel_arg)
        return entry

    def _emit_bar_compact(
        self, t: Trace, pw: "_PayloadWriter", xr: tuple, yr: tuple, px_width: int
    ) -> dict[str, Any]:
        del xr, yr, px_width
        if t.x0 is None or t.x1 is None or t.y0 is None or t.y1 is None:
            raise ValueError(f"{t.kind} trace missing bar columns")

        x0v, x1v, y0v, y1v = t.x0.values, t.x1.values, t.y0.values, t.y1.values
        sel_arg = self._rect_finite_sel(t, x0v, x1v, y0v, y1v)
        if sel_arg is not None:
            x0v, x1v, y0v, y1v = x0v[sel_arg], x1v[sel_arg], y0v[sel_arg], y1v[sel_arg]

        orientation = str(t.style.get("orientation", "vertical"))
        if orientation == "vertical":
            widths = x1v - x0v
            pos = t.x.values if sel_arg is None else t.x.values[sel_arg]
            value0 = y0v
            value1 = t.y.values if sel_arg is None else t.y.values[sel_arg]
            value0_col = t.y0
        elif orientation == "horizontal":
            widths = y1v - y0v
            pos = (y0v + y1v) / 2.0
            value0 = x0v
            value1 = x1v
            value0_col = t.x0
        else:
            raise ValueError(f"unknown bar orientation {orientation!r}")

        compact, width, has_value0_const, value0_const = kernels.payload_bar_compact_admit(
            np.ascontiguousarray(widths, dtype=np.float64),
            np.ascontiguousarray(value0, dtype=np.float64),
        )
        x_scale = self._axis_scale(t.x_axis)
        y_scale = self._axis_scale(t.y_axis)
        plan = kernels.payload_bar_hist_emit_plan(
            kind="bar_compact",
            compact=compact,
            n_marks=int(len(pos)),
            style_color_is_none=t.style.get("color") is None,
            x_axis_scale=x_scale,
            y_axis_scale=y_scale,
            orientation=orientation,
        )
        if not plan["emit_bar"]:
            return self._emit_rect(t, pw, (), (), 0)

        if orientation == "vertical":
            pos_ref = pw.ship(pos, t.x, scale=plan["pos_ship_scale"])
            value1_ref = pw.ship(value1, t.y, scale=plan["value_ship_scale"])
        else:
            pos_ref = pw.ship_values(pos, scale=plan["pos_ship_scale"])
            value1_ref = pw.ship(value1, t.x1, scale=plan["value_ship_scale"])

        style = self._default_styled(t)
        bar_spec: dict[str, Any] = {
            "orientation": orientation,
            "value_axis": plan["value_axis"],
            "pos": pos_ref,
            "value1": value1_ref,
            "width": width,
        }
        if has_value0_const:
            bar_spec["value0_const"] = value0_const
        else:
            bar_spec["value0"] = pw.ship(
                value0,
                value0_col,
                scale=plan["value_ship_scale"],
            )

        entry = {
            "id": t.id,
            "kind": t.kind,
            "name": t.name,
            "style": style,
            "tier": "direct",
            "n_points": t.n_points,
            "n_marks": plan["n_marks"],
            "x_axis": t.x_axis,
            "y_axis": t.y_axis,
            "bar": bar_spec,
        }
        self._ship_trace_channel_attach(
            entry,
            t,
            sel_arg,
            pw,
            plan["channel_slot"],
            include_trace_styles=plan["include_trace_styles"],
        )
        if plan["attach_transition"]:
            return self._transition_entry(entry, t, pw, sel_arg)
        return entry

    def _ship_trace_channel_attach(
        self,
        entry: dict[str, Any],
        t: Trace,
        sel,
        pw: "_PayloadWriter",
        slot: int,
        *,
        include_trace_styles: bool,
    ) -> None:  # noqa: ANN001
        """Attach color/size/stroke/style channels per Rust-owned emit policy."""
        attach = kernels.payload_trace_channels_ship_attach(
            slot,
            include_trace_styles=include_trace_styles,
            has_color_ch=t.color_ch is not None,
            has_stroke_ch=t.stroke_ch is not None,
            has_style_channels=bool(t.style_channels),
        )
        if attach["ship_color"]:
            entry["color"], entry["size"] = self._ship_channels(t, sel, pw.ship_scalar, pw.ship_u8)
        if attach["ship_stroke"]:
            entry["stroke"] = channels.ship_color_channel(
                t.stroke_ch, sel, pw.ship_scalar, pw.ship_u8
            )
        if attach["ship_style_channels"]:
            entry["channels"] = channels.ship_style_channels(
                t.style_channels, sel, pw.ship_scalar, pw.ship_u8
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

    def _density_sample_spec(
        self,
        t: Trace,
        sel: np.ndarray,
        visible: int,
        xr: tuple[float, float],
        yr: tuple[float, float],
        pw: "_PayloadWriter",
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
        x_col = pw.ship_values(t.x.values[sample_sel], kind=t.x.kind, scale=plan["x_ship_scale"])
        y_col = pw.ship_values(t.y.values[sample_sel], kind=t.y.kind, scale=plan["y_ship_scale"])
        sample = {
            "mode": "sampled",
            "n": int(len(sample_sel)),
            "visible": int(visible),
            "target": DENSITY_SAMPLE_TARGET,
            "level": 0,
            "seed": DENSITY_SAMPLE_SEED,
            "x": {"col": x_col, **pw.columns[x_col]},
            "y": {"col": y_col, **pw.columns[y_col]},
            "x_range": list(xr),
            "y_range": list(yr),
            "style": style,
        }
        self._ship_trace_channel_attach(
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
        pw: "_PayloadWriter",
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

    def _density_trace_spec(self, t: Trace, xr, yr, w, h, pw: "_PayloadWriter") -> dict[str, Any]:  # noqa: ANN001
        """Bin a scatter into a density grid and build its spec entry (§5 Tier 2).
        The grid ships in the client's one-byte log texture precision; exact
        visible counts remain metadata, and the client recomputes the
        normalization domain per view so brightness is stable (§F6)."""
        # Density grids are uniform in axis-scale coordinates (§28): on a
        # nonlinear axis the columns and window are transformed before binning
        # so every cell covers the same strip of *screen*. The wire keeps raw
        # `x_range`/`y_range` endpoints; renderers interpolate between their
        # scale coordinates.
        bx, (bx0, bx1) = self._binning_coords(t.x_axis, t.x.values, xr)
        by, (by0, by1) = self._binning_coords(t.y_axis, t.y.values, yr)
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
        sample_sel = None
        grid = None
        visible = int(t.n_points)
        sel = np.empty(0, dtype=np.uint32)
        binning = _native.density_format_binning(exact=True)
        rgba_from_pyramid = None
        tiles_meta = None
        has_pyramid_resource = False
        # Tier-3 first paint: when the interactive path would already build a
        # pyramid, compose the opening density surface from it instead of an
        # O(N) `bin_2d` that the next pan throws away (§28 `pyramid-L*`).
        if plan["pyramid_eligible"]:
            pyr = interaction._ensure_pyramid(t)
            store = interaction._tile_store_of(t)
            has_pyramid_resource = store is not None or pyr is not None
            plan = _emit_plan(
                grid_from_pyramid=False,
                has_pyramid_resource=has_pyramid_resource,
            )
            if plan["pyramid_attempt"]:
                no_rescan = bool(plan["pyramid_no_rescan"])
                max_upsample = int(plan["pyramid_max_upsample"])
                tile_upsample = int(plan["pyramid_tile_upsample"])
                if store is not None:
                    if getattr(t, "_pyr_colored", False):
                        res_color = kernels.tile_store_compose_color(
                            store, bx0, bx1, by0, by1, w, h, tile_upsample
                        )
                        if res_color is not None:
                            grid, rgba_from_pyramid, level = res_color
                            binning = _native.density_format_binning(
                                exact=False,
                                level=int(level),
                                tiles=True,
                                upsampled=no_rescan and level == 0,
                            )
                            tiles_meta = interaction._tiles_stats_dict(store)
                    else:
                        res = kernels.tile_store_compose(
                            store, bx0, bx1, by0, by1, w, h, tile_upsample
                        )
                        if res is not None:
                            grid, level = res
                            binning = _native.density_format_binning(
                                exact=False,
                                level=int(level),
                                tiles=True,
                                upsampled=no_rescan and level == 0,
                            )
                            tiles_meta = interaction._tiles_stats_dict(store)
                elif pyr is not None and getattr(t, "_pyr_colored", False):
                    res_color = kernels.pyramid_compose_color(
                        pyr, bx0, bx1, by0, by1, w, h, max_upsample
                    )
                    if res_color is not None:
                        grid, rgba_from_pyramid, level = res_color
                        binning = _native.density_format_binning(
                            exact=False,
                            level=int(level),
                            upsampled=no_rescan and level == 0,
                        )
                elif pyr is not None:
                    res = kernels.pyramid_compose(pyr, bx0, bx1, by0, by1, w, h, max_upsample)
                    if res is not None:
                        grid, level = res
                        binning = _native.density_format_binning(
                            exact=False,
                            level=int(level),
                            upsampled=no_rescan and level == 0,
                        )
        plan = _emit_plan(
            grid_from_pyramid=grid is not None,
            has_pyramid_resource=has_pyramid_resource,
        )
        # Pyramid compose yields the grid without a fused overlay sample.
        # Fill the public sample without re-binning so first paint still
        # ships `density["sample"]` (raster `point_overlay=False` stays empty).
        if plan["needs_pyramid_sample"] and sample_sel is None:
            if plan["pyramid_sample_stratified"]:
                assert t.color_ch is not None and t.color_ch.codes is not None
                sample_sel = lod.stratified_sample_row_range_for_target(
                    t.color_ch.codes,
                    len(t.color_ch.categories or ()),
                    DENSITY_SAMPLE_TARGET,
                    counts=t.color_ch.counts,
                    seed=DENSITY_SAMPLE_SEED,
                )
            else:
                sample_sel = lod.sample_row_range_for_target(
                    t.n_points,
                    DENSITY_SAMPLE_TARGET,
                    seed=DENSITY_SAMPLE_SEED,
                )
        if grid is None:
            path = int(plan["grid_path"])
            if plan["visible_init_n_points"]:
                visible = int(t.n_points)
                sel = np.empty(0, dtype=np.uint32)
            if plan["use_raw_range_bin2d"]:
                sample_sel = None
                grid = kernels.bin_2d(t.x.values, t.y.values, xr[0], xr[1], yr[0], yr[1], w, h)
                binning = _native.density_format_binning(exact=True)
            elif path == _native.DENSITY_GRID_PATH_IDENTITY_GRID_ONLY:
                grid = kernels.bin_2d(bx, by, bx0, bx1, by0, by1, w, h)
                binning = _native.density_format_binning(exact=True)
            elif path == _native.DENSITY_GRID_PATH_IDENTITY_STRATIFIED_FUSED:
                assert t.color_ch is not None and t.color_ch.codes is not None
                grid, sample_sel = lod.bin_2d_stratified_sample_row_range_for_target(
                    bx,
                    by,
                    t.color_ch.codes,
                    len(t.color_ch.categories or ()),
                    bx0,
                    bx1,
                    by0,
                    by1,
                    w,
                    h,
                    DENSITY_SAMPLE_TARGET,
                    counts=t.color_ch.counts,
                    seed=DENSITY_SAMPLE_SEED,
                )
                binning = _native.density_format_binning(exact=True)
            elif path == _native.DENSITY_GRID_PATH_IDENTITY_STRATIFIED_SPLIT:
                assert t.color_ch is not None and t.color_ch.codes is not None
                grid = kernels.bin_2d(bx, by, bx0, bx1, by0, by1, w, h)
                sample_sel = lod.stratified_sample_row_range_for_target(
                    t.color_ch.codes,
                    len(t.color_ch.categories or ()),
                    DENSITY_SAMPLE_TARGET,
                    seed=DENSITY_SAMPLE_SEED,
                )
                binning = _native.density_format_binning(exact=True)
            elif path == _native.DENSITY_GRID_PATH_IDENTITY_SAMPLE_FUSED:
                grid, sample_sel = lod.bin_2d_sample_row_range_for_target(
                    bx,
                    by,
                    bx0,
                    bx1,
                    by0,
                    by1,
                    w,
                    h,
                    DENSITY_SAMPLE_TARGET,
                    seed=DENSITY_SAMPLE_SEED,
                )
                binning = _native.density_format_binning(exact=True)
            elif path == _native.DENSITY_GRID_PATH_RANGE_INDICES:
                grid, sel = kernels.bin_2d_indices(bx, by, bx0, bx1, by0, by1, w, h)
                visible = int(len(sel))
                binning = _native.density_format_binning(exact=True)
            else:
                raise RuntimeError(f"unexpected density grid path {path}")
        elif plan["visible_is_n_points"]:
            visible = int(t.n_points)
            sel = np.empty(0, dtype=np.uint32)
        encoded_grid, gmax = kernels.density_log_u8(grid)
        bin_colors = interaction.trace_bin_colors(t)
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
            grid_from_pyramid=grid is not None,
            has_pyramid_resource=has_pyramid_resource,
            grid_present=True,
            has_pyramid_rgba=rgba_from_pyramid is not None,
            has_bin_colors=bin_colors is not None,
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
        dropped_channels = list(t.per_item_channel_names())
        density = {
            "buf": pw.ship_u8(encoded_grid),
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
        # `XYAS` v1 retains the canonical split f64 columns in the host for
        # replay on every pan.  The worker only receives one ABI-generated
        # 32,768-point raw chunk at a time; this source capacity is the
        # generated aggregate ABI's declared point limit.
        wasm_capacity = WASM_AGGREGATE_MAX_POINTS
        if wire["ship_wasm_source"]:
            density["wasm_source"] = {
                "kind": "cartesian-count-f64-stream-v1",
                "x": pw.ship_f64(t.x.values),
                "y": pw.ship_f64(t.y.values),
                "point_count": int(t.n_points),
                "trace_id": int(t.id),
                "capacity": wasm_capacity,
                "ownership": "retain-host-replay",
            }
        if tiles_meta is not None:
            density["tiles"] = tiles_meta
        ship_mean_color_rgba = bool(wire["ship_mean_color_rgba"])
        if ship_mean_color_rgba:
            if rgba_from_pyramid is not None:
                density["rgba"] = pw.ship_u8(rgba_from_pyramid.reshape(-1))
            elif bin_colors is not None:
                # Mean point color per cell, straight-alpha RGBA8: the color the
                # points themselves would downsample to (averaged in linear
                # light). The channel is aggregated, recorded via `color_agg`,
                # and therefore leaves the dropped list.
                rgba_grid = kernels.bin_2d_mean_color(
                    bx, by, bx0, bx1, by0, by1, w, h, **bin_colors
                )
                density["rgba"] = pw.ship_u8(rgba_grid.reshape(-1))
            density["color_agg"] = "mean"
        dropped_channels = [
            name
            for name in dropped_channels
            if kernels.density_dropped_channel_wire_admit(
                channel=name,
                mean_color_aggregates=int(wire["mean_color_aggregates"]),
            )
        ]
        density["channels_dropped"] = kernels.density_channels_dropped_compat(
            dropped_count=len(dropped_channels),
        )
        density["dropped_channels"] = dropped_channels  # complete, actionable list (§28)
        if wire["ship_constant_color"]:
            assert t.color_ch is not None
            density["color"] = t.color_ch.constant
        if wire["overlay_wire_rows_exceed"]:
            # §28: exact grid, but the deterministic point overlay is dropped
            # because row ids exceed u32. Recorded so the client/legend can say so.
            density["overlay_omitted"] = "rows_exceed_u32"
        if wire["attach_sample"]:
            sample = self._density_sample_spec(t, sel, visible, xr, yr, pw, sample_sel=sample_sel)
            if sample is not None:
                density["sample"] = sample
        elif wire["overlay_wire_static_raster"]:
            # §28: no representation is dropped silently. `oversized` above may
            # have already recorded the more fundamental u32 reason; that one
            # wins, so only claim the field when nothing else has.
            density["overlay_omitted"] = "static_raster"
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
        if wire["ship_categorical_entry_color"]:
            assert t.color_ch is not None
            # Legend chrome needs the encoding even though the per-point codes
            # aggregate into the mean-color plane: ship the channel spec slim
            # (categories + palette, no per-point `buf`) so category rows
            # exist for density-tier traces — the §10 category-toggle path is
            # unreachable without them, and every client consumer of a color
            # buffer already guards on `buf`. Continuous channels stay
            # deliberately unshipped here: a gradient row would claim
            # color == density.
            color_spec = t.color_ch.spec()
            color_spec["palette"] = channels.categorical_palette(
                t.color_ch.colors, len(t.color_ch.categories or ())
            )
            entry["color"] = color_spec
        return entry
