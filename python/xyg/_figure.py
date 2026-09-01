"""The Figure: a data-less spec + column handles (§9).

The spec is tiny JSON — trace kinds, styles, axis config, and *references* into
the column store. Data never rides in the spec: encoded f32 columns travel as
one binary blob beside it (§29: no JSON numbers, no re-encoding, parse-shaped
work is forbidden on the client).
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Mapping
from os import PathLike
from typing import Any, Optional, TypeAlias, Union

import numpy as np

from . import (
    _annotations,
    _validate,
    export,
    interaction,
    kernels,
)
from . import _figure_autorange as _autorange
from . import _figure_axis as _axis
from . import _figure_ingest as _ingest
from . import _figure_traces as _traces
from . import marks as _marks
from ._annotations import AnnotationsMixin
from ._payload import PayloadMixin
from ._trace import Trace
from .columns import ColumnStore, ColumnStoreCheckpoint

# Tier/tuning constants live in config.py (shared with interaction/export/
# _payload); several are re-exported here — this module is their historic
# import path and tests import them from `xyg._figure` (F401 kept for
# the re-exports; DIRECT_SOFT_CEILING/DEFAULT_PALETTE are also used below).
from .config import (  # noqa: E402, F401
    DECIMATION_THRESHOLD,
    DEFAULT_PALETTE,
    DENSITY_GRID,
    DENSITY_SAMPLE_SEED,
    DENSITY_SAMPLE_TARGET,
    DIRECT_SOFT_CEILING,
    POLAR_DIRECT_CEILING,
    POLAR_MARK_KINDS,
    PROTOCOL_VERSION,
    SCATTER_DENSITY_THRESHOLD,
    default_palette_color,
)
from .dom import validate_dom_slots

_FigureCheckpoint: TypeAlias = tuple[ColumnStoreCheckpoint, int, dict[str, list[str]], int]

# "selection not passed" sentinel for state_patch_message: None is meaningful
# there (clear the selection), so absence needs its own marker.
_STATE_UNSET: Any = object()


class Selection:
    """The payload handed to an `on_select` callback. Holds the selected
    row indices per trace and lends convenient access to the underlying data —
    callbacks receive real arrays, never JSON."""

    def __init__(self, figure: "Figure", per_trace: dict[int, np.ndarray]) -> None:
        self._figure = figure
        self.per_trace = per_trace  # {trace_id: np.ndarray[uint32]}

    @property
    def index(self) -> np.ndarray:
        """Concatenated selected indices across all traces (single-trace charts
        are the common case, where this is just that trace's indices)."""
        arrs = list(self.per_trace.values())
        return np.concatenate(arrs) if arrs else np.empty(0, dtype="uint32")

    def __len__(self) -> int:
        return int(sum(len(v) for v in self.per_trace.values()))

    def xy(self, trace_id: int = 0) -> tuple[np.ndarray, np.ndarray]:
        """(x, y) f64 arrays for the selected points of a trace (from canonical)."""
        t = interaction._trace(self._figure, trace_id)
        idx = self.per_trace.get(t.id)
        if idx is None:
            return np.empty(0), np.empty(0)
        return t.x.values[idx], t.y.values[idx]

    def rows(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Return deterministic JSON rows based on canonical indices.

        Traces and their indices are ordered ascending. ``limit`` bounds the
        projection without changing the complete selection held by this object.
        """
        rows, _ = interaction.selection_rows(self._figure, self.per_trace, limit)
        return rows


class Figure(AnnotationsMixin, PayloadMixin):
    """Build with `line()` / `scatter()`, display with `show()` (notebook) or
    `to_html()` (standalone file, no kernel round-trips)."""

    def __init__(
        self,
        *,
        width: "int | str" = 900,
        height: "int | str" = 420,
        title: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        padding: Any = None,
        coords: str = "cartesian",
    ) -> None:
        # width/height: pixels, or "100%" to fill the parent container — the
        # client measures the container and re-renders on resize
        # (ResizeObserver), re-requesting decimation/density at the new pixel
        # size (§28). height="100%" needs a parent with a defined height (the
        # usual CSS contract); otherwise the chart falls back to its 120px
        # min-height.
        self.width = self._pixel_dimension(width, "width")
        self.height = self._pixel_dimension(height, "height")
        # padding: override the auto plot margins (top, right, bottom, left) in
        # px — a scalar sets all four. None keeps the label-aware defaults. Zero
        # padding + hidden axes gives an edge-to-edge sparkline for dashboards.
        self.padding = self._padding(padding, "padding")
        self.title = self._optional_text(title, "title")
        # Optional renderer-owned title slots. Declarative charts keep using
        # ``title``; the pyplot shim fills this with Matplotlib's independent
        # left/center/right title artists.
        self.title_options: list[dict[str, Any]] = []
        self.x_label = self._optional_text(x_label, "x_label")
        self.y_label = self._optional_text(y_label, "y_label")
        # "cartesian" (two separable axes) or "polar" (the x axis carries theta,
        # the y axis carries r). Polar reinterprets the same two axes rather
        # than declaring new ids: axis ids are required to start with 'x'/'y' in
        # four separate places, and the interaction axis policies are built on
        # that grammar. See spec/design/polar-axes.md.
        self.coords = _validate.coords(coords, "coords")
        self.axis_options: dict[str, dict[str, Any]] = {
            "x": {"label": self.x_label, "side": "bottom"},
            "y": {"label": self.y_label, "side": "left"},
        }
        self.store = ColumnStore()
        self.traces: list[Trace] = []
        # Graph mark meta (CSR / LOD / layout decision) — shipped on the wire
        # spec when present (graph-mark.md). Not a Trace; one entry per graph.
        self._graph_meta: list[dict[str, Any]] | None = None
        self.show_legend = True
        self.legend_options: dict[str, Any] = {}
        # Additional legend boxes (each with its own explicit items + loc),
        # e.g. the pyplot shim's manually added Legend artists. Empty for the
        # ordinary single-legend case.
        self.extra_legends: list[dict[str, Any]] = []
        # None keeps the declarative engine's two-axis baseline convention;
        # pyplot sets an explicit Matplotlib-style spine list.
        self.frame_sides: Optional[list[str]] = None
        self.colorbar_options: Optional[dict[str, Any]] = None
        # Declarative export defaults (xyg.export_config): governs the client
        # modebar's format menu + filename and the Python export defaults.
        self.export_options: Optional[dict[str, Any]] = None
        self.show_modebar = True
        self.show_tooltip = True
        self.class_name: Optional[str] = None
        self.class_names: dict[str, str] = {}
        self.style: dict[str, str | int | float] = {}
        self.chrome_styles: dict[str, dict[str, str | int | float]] = {}
        self.tooltip: Optional[dict[str, Any]] = None
        self.interaction: dict[str, Any] = {}
        # Browser-only motion policy. Static/native exporters intentionally
        # ignore this and always render the deterministic final scene.
        self.animation_options: Optional[dict[str, Any]] = None
        self.mark_style: dict[str, dict[str, str | int | float]] = {}
        # Categorical color cycle for this chart: unnamed series colors AND
        # categorical color channels. `xyg.theme(palette=[...])` replaces it;
        # None means the built-in CVD-safe default (config.DEFAULT_PALETTE).
        # Set before any mark is applied — a trace bakes its color at build.
        # A list is a positional cycle; a `{category: color}` mapping pins
        # colors to category labels (`palette_cycle` flattens it for the
        # series cycle, `channels.resolve_color` looks categories up in it).
        self.palette: Union[list[str], dict[str, str], None] = None
        # How many logical series have already taken a palette slot. The cycle
        # advances per *series*, never per trace: a box is four traces and a
        # stem is two, and indexing by `len(self.traces)` made those marks skip
        # (or collide on) palette entries — four brand colors and four boxes
        # painted every box `palette[0]`.
        self._series_cursor = 0
        self.annotations: list[dict[str, Any]] = []
        self._axis_categories: dict[str, list[str]] = {}
        # Declarative marks still call the shared fluent mark bodies with the
        # channel dimensions ("x"/"y").  Chart temporarily points those
        # dimensions at the mark's bound axis ids while it applies each mark,
        # so category registries stay independent for x, x2, y, y2, ... .
        self._active_axis_ids: dict[str, str] = {"x": "x", "y": "y"}
        self._widget: Any = None
        # Kernel-side durable view-state cache (spec/design/view-state.md
        # §5.1): the browser client owns the live state; this mirror is fed
        # by the view/selection events the transports already deliver, so
        # `view_state()` never round-trips. Reads are eventually consistent.
        self._view_state_ranges: Optional[dict[str, list[float]]] = None
        self._view_state_selection: Optional[dict[str, Any]] = None
        # Monotonic streaming-append counter; rides the spec as
        # `append.seq` so trait-transported hosts can detect the refresh
        # (wire-protocol §4).
        self._append_seq = 0

    # -- palette ------------------------------------------------------------

    @property
    def palette_cycle(self) -> Optional[list[str]]:
        """The chart palette as a positional cycle, or None when unset.

        A `{category: color}` palette pins colors by label; series that are not
        categories still need an order, and the mapping's own is the only one
        the author expressed."""
        if self.palette is None:
            return None
        if isinstance(self.palette, dict):
            return list(self.palette.values())
        return list(self.palette)

    @property
    def colors(self) -> list[str]:
        """This chart's categorical cycle — its own palette, else the default."""
        return self.palette_cycle or list(DEFAULT_PALETTE)

    def palette_color(self, index: int, *, stacklevel: int = 3) -> str:
        """Color for the `index`-th series (0-based): the chart palette, cycled.

        Wrapping is allowed but never silent (§28) — see
        `config.default_palette_color`, which owns the built-in-palette warning
        and its CVD-order rationale."""
        cycle = self.palette_cycle
        if cycle is None:
            return default_palette_color(index, stacklevel=stacklevel + 1)
        if index >= len(cycle):
            warnings.warn(
                f"more than {len(cycle)} series use default colors; the chart "
                f"palette repeats every {len(cycle)} (series "
                f"{len(cycle) + 1} wears series 1's color). Pass a longer "
                "xyg.theme(palette=...), or an explicit color= per series.",
                RuntimeWarning,
                stacklevel=stacklevel,
            )
        return cycle[index % len(cycle)]

    def next_series_color(self, *, stacklevel: int = 4) -> str:
        """Take the next categorical slot for one logical series.

        Marks call this only when the caller gave no `color=`, so a mark that
        builds several traces (box, stem) — or that delegates to another mark
        body with the color already resolved — consumes exactly one slot."""
        index = self._series_cursor
        self._series_cursor += 1
        return self.palette_color(index, stacklevel=stacklevel)

    def set_interaction(
        self,
        *,
        hover: Optional[bool] = None,
        click: Optional[bool] = None,
        select: Optional[bool] = None,
        brush: Optional[bool] = None,
        crosshair: Optional[bool] = None,
        navigation: Optional[bool] = None,
        pan: Optional[bool] = None,
        pan_axes: Optional[tuple[str, ...]] = None,
        zoom: Optional[bool] = None,
        default_drag_action: Optional[str] = None,
        zoom_axes: Optional[tuple[str, ...]] = None,
        zoom_limits: Any = None,
        wheel_zoom: Optional[bool] = None,
        box_zoom: Optional[bool] = None,
        zoom_buttons: Optional[bool] = None,
        double_click_reset: Optional[bool] = None,
        reset_axes: Optional[tuple[str, ...]] = None,
        link_group: Optional[str] = None,
        link_axes: Optional[tuple[str, ...]] = None,
        link_select: Optional[bool] = None,
        history: Optional[bool] = None,
    ) -> "Figure":
        updates: dict[str, Any] = {}
        for name, value in (
            ("hover", hover),
            ("click", click),
            ("select", select),
            ("brush", brush),
            ("crosshair", crosshair),
            ("navigation", navigation),
            ("pan", pan),
            ("zoom", zoom),
            ("wheel_zoom", wheel_zoom),
            ("box_zoom", box_zoom),
            ("zoom_buttons", zoom_buttons),
            ("double_click_reset", double_click_reset),
            ("link_select", link_select),
            ("history", history),
        ):
            normalized = self._optional_bool(value, f"interaction {name}")
            if normalized is not None:
                updates[name] = normalized
        for name, axes in (
            ("pan_axes", pan_axes),
            ("zoom_axes", zoom_axes),
            ("reset_axes", reset_axes),
        ):
            if axes is not None:
                updates[name] = self._axis_policy(axes, name)
        if zoom_limits is not None:
            updates["zoom_limits"] = zoom_limits
        if default_drag_action is not None:
            updates["default_drag_action"] = self._default_drag_action(default_drag_action)
        if link_group is not None:
            group = self._optional_text(link_group, "interaction link_group")
            if not group:
                raise ValueError("interaction link_group must be a non-empty string or None")
            updates["link_group"] = group
        if link_axes is not None:
            updates["link_axes"] = self._axis_policy(link_axes, "link_axes")
        self.interaction.update(updates)
        return self

    def set_mark_style(
        self,
        *,
        hover: Optional[dict[str, Any]] = None,
        selected: Optional[dict[str, Any]] = None,
        unselected: Optional[dict[str, Any]] = None,
    ) -> "Figure":
        """Configure legacy standalone hover/selection styling.

        This low-level compatibility hook is intentionally not exposed by the
        declarative component API. Reflex integrations should derive ordinary
        mark props/styles from Reflex state instead of maintaining XYG state.
        """
        for state, value in (
            ("hover", hover),
            ("selected", selected),
            ("unselected", unselected),
        ):
            style = self._optional_state_style(value, f"mark_style {state}")
            if style:
                self.mark_style[state] = {**self.mark_style.get(state, {}), **style}
        return self

    set_axis = _axis.set_axis
    _set_axis_domain = _axis._set_axis_domain
    _axis_dim = staticmethod(_axis._axis_dim)
    _axis_policy = _axis._axis_policy
    _axis_scale = _axis._axis_scale
    _axis_coord = _axis._axis_coord
    _axis_kind = _axis._axis_kind
    _axis_spec = _axis._axis_spec
    _range_columns = _axis._range_columns

    # -- trace builders -----------------------------------------------------

    _ingest_xy = _ingest.ingest_xy

    def _checkpoint(self) -> _FigureCheckpoint:
        return (
            self.store.checkpoint(),
            len(self.traces),
            {axis: list(labels) for axis, labels in self._axis_categories.items()},
            len(self.annotations),
        )

    def _rollback(self, checkpoint: _FigureCheckpoint) -> None:
        store_checkpoint, trace_len, axis_categories, annotation_len = checkpoint
        self.store.rollback(store_checkpoint)
        del self.traces[trace_len:]
        del self.annotations[annotation_len:]
        self._axis_categories = axis_categories

    # The mark implementations live in the declarative core (marks.py); they
    # are bound here as the fluent methods, so `Figure.scatter is marks.scatter`
    # — one body, one signature, one set of defaults for both dialects.
    line = _marks.line
    area = _marks.area
    scatter = _marks.scatter
    histogram = _marks.histogram
    hist = _marks.hist
    error_band = _marks.error_band
    errorbar = _marks.errorbar
    box = _marks.box
    violin = _marks.violin
    ecdf = _marks.ecdf
    hexbin = _marks.hexbin
    contour = _marks.contour
    step = _marks.step
    stairs = _marks.stairs
    stem = _marks.stem
    segments = _marks.segments
    ribbon = _marks.ribbon
    sankey = _marks.sankey
    graph = _marks.graph
    triangle_mesh = _marks.triangle_mesh
    bar = _marks.bar
    column = _marks.column
    heatmap = _marks.heatmap

    def _append_segment_trace(self, *args: Any, **kwargs: Any) -> None:
        _marks._append_segment_trace(self, *args, **kwargs)

    _rect_mark_style = _traces.rect_mark_style
    _append_bar_rect = _traces.append_bar_rect
    _append_rect_trace = _traces.append_rect_trace
    _rect_finite_sel = _traces.rect_finite_sel

    _as_1d_float = staticmethod(_ingest.as_1d_float)

    # Shared argument validators (bodies live in `_validate`); these thin
    # staticmethod aliases keep `self._foo(...)` call sites — and the two
    # helpers `components` reaches through `Figure` — unchanged.
    _finite_scalar = staticmethod(_validate.finite_scalar)
    _finite_increasing_pair = staticmethod(_validate.finite_increasing_pair)
    _positive_scalar = staticmethod(_validate.positive_scalar)
    _optional_finite_scalar = staticmethod(_validate.optional_finite_scalar)
    _optional_positive_int = staticmethod(_validate.optional_positive_int)
    _axis_tick_label_strategy = staticmethod(_validate.axis_tick_label_strategy)
    _axis_tick_label_anchor = staticmethod(_validate.axis_tick_label_anchor)
    _nonnegative_scalar = staticmethod(_validate.nonnegative_scalar)
    _opacity = staticmethod(_validate.opacity)
    _padding = staticmethod(_validate.plot_padding)
    _optional_bool = staticmethod(_validate.optional_bool)
    _bool_param = staticmethod(_validate.bool_param)
    _axis_id = staticmethod(_validate.axis_id)
    _optional_text = staticmethod(_validate.optional_text)
    _optional_css_color = staticmethod(_validate.optional_css_color)
    _string_mapping = staticmethod(_validate.string_mapping)
    _style_mapping = staticmethod(_validate.style_mapping)

    @staticmethod
    def _default_drag_action(value: Any) -> str:
        allowed = {
            "auto",
            "none",
            "pan",
            "zoom",
            "select",
            "select-x",
            "select-y",
            "select-lasso",
        }
        if not isinstance(value, str) or value not in allowed:
            choices = ", ".join(repr(mode) for mode in sorted(allowed))
            raise ValueError(f"interaction default_drag_action must be one of {choices}")
        return value

    @staticmethod
    def _zoom_limit_pair(value: Any, label: str) -> list[Optional[float]]:
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise ValueError(f"{label} must be a two-item tuple/list")
        normalized: list[Optional[float]] = []
        for endpoint in value:
            if endpoint is None:
                normalized.append(None)
                continue
            if isinstance(endpoint, (bool, np.bool_)):
                raise ValueError(f"{label} endpoints must be positive finite numbers or None")
            try:
                number = float(endpoint)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{label} endpoints must be positive finite numbers or None"
                ) from exc
            if not np.isfinite(number) or number <= 0:
                raise ValueError(f"{label} endpoints must be positive finite numbers or None")
            normalized.append(number)
        lower, upper = normalized
        if lower is not None and upper is not None and lower > upper:
            raise ValueError(f"{label} lower endpoint must not exceed its upper endpoint")
        if (lower is not None and lower > 1.0) or (upper is not None and upper < 1.0):
            raise ValueError(f"{label} must contain home magnification 1.0")
        return normalized

    def _zoom_limits(self, value: Any) -> dict[str, list[Optional[float]]]:
        selected = self._interaction_axes("zoom_axes")
        default = [1.0, None]
        if isinstance(value, Mapping):
            unknown = [axis for axis in value if axis not in self.axis_options]
            if unknown:
                raise ValueError(f"interaction zoom_limits contains unknown axis IDs {unknown!r}")
            normalized = {axis: list(default) for axis in selected}
            for axis in self.axis_options:
                if axis in value:
                    normalized[axis] = self._zoom_limit_pair(
                        value[axis], f"interaction zoom_limits[{axis!r}]"
                    )
            return normalized
        pair = self._zoom_limit_pair(value, "interaction zoom_limits")
        return {axis: list(pair) for axis in selected}

    def _interaction_axes(self, name: str) -> list[str]:
        value = self.interaction.get(name)
        return list(self.axis_options) if value is None else self._axis_policy(value, name)

    def _validate_coords(self) -> None:
        """Refuse mark kinds the polar transform does not yet render correctly.

        A whole-scene check rather than a per-mark one: marks can be appended
        at any time, so only payload-build time sees the finished figure.

        The refusal is deliberate. Every unsupported kind here *would* draw
        something — a bar would come out as a chord-edged rectangle rather than
        an annular sector, an area would fill the wrong region — and a
        plausible wrong picture is worse than an error. §28 requires the
        decision to ship rather than be silently approximated.
        """
        if self.coords != "polar":
            return
        unsupported = sorted({t.kind for t in self.traces} - POLAR_MARK_KINDS)
        if unsupported:
            raise ValueError(
                f"coords='polar' does not support {unsupported} yet; "
                f"supported kinds are {sorted(POLAR_MARK_KINDS)}. "
                "See spec/design/polar-axes.md."
            )
        unsupported_annotations = sorted(
            {str(annotation.get("kind")) for annotation in self.annotations} & {"rule", "band"}
        )
        if unsupported_annotations:
            raise ValueError(
                "coords='polar' does not support rule/band annotations yet; "
                f"found {unsupported_annotations}. Point-anchored text, label, marker, "
                "arrow, and callout annotations remain supported."
            )
        # One angular and one radial axis, no more. A secondary axis binds and
        # validates exactly like a Cartesian one, but the polar transform reads
        # only the primary pair, so the result is the failure this method exists
        # to prevent: an overlapping secondary range draws *pixel-identical* to
        # the primary, inviting the reader to decode it against a tick ladder it
        # does not belong to, while a disjoint one culls the series away
        # entirely — and either way the axis still gets its Cartesian spine and
        # title drawn in the gutter of a disc. Refuse instead.
        extra_axes = sorted(
            (
                set(self.axis_options)
                | {t.x_axis for t in self.traces}
                | {t.y_axis for t in self.traces}
            )
            - {"x", "y"}
        )
        if extra_axes:
            raise ValueError(
                "coords='polar' supports a single angular ('x') and radial ('y') "
                f"axis; found {extra_axes}. See spec/design/polar-axes.md."
            )
        theta = self.axis_options.get("x", {})
        # A non-linear *angle* has no coherent projection, and the two renderers
        # never agreed on one: the client scales theta before projecting it
        # while the static exporters ignore the scale outright (their SVG is
        # byte-identical across linear/log/symlog), so the same figure points a
        # datum at opposite sides of the disc depending on where it is drawn.
        # The spec offers a scale row for r only; a log radial axis stays valid.
        # Inspecting only the *declared* spelling let an inferred time column
        # through: datetime theta shipped with kind="time" pinned to a fixed
        # 0..2pi range, so twelve consecutive days wrapped the disc billions of
        # times and the spokes were labelled as radians. `theta_axis(domain=)`
        # is aliased to `sector`, so there was no escape hatch either. Refuse on
        # the resolved kind, and say what a time angle would have to mean.
        if self._axis_kind("x") == "time":
            raise ValueError(
                "coords='polar' does not support a time angular axis; an "
                "instant has no angle. Map time onto the turn yourself — e.g. "
                "theta = 2*pi * ((t - t0) / period) — and pass the result as a "
                "number. A time *radial* axis (r_axis) is supported."
            )
        theta_scale = theta.get("type")
        if theta_scale is not None and theta_scale != "linear":
            raise ValueError(
                f"coords='polar' does not support a {theta_scale!r} angular axis; "
                "the angle must be linear. A log or symlog *radial* axis "
                "(r_axis) is supported. See spec/design/polar-axes.md."
            )
        # `reverse` is the Cartesian "flip this axis" switch; on a disc the
        # equivalent is a direction of travel, which the angular axis already
        # spells as `direction`. It rode the wire as `"reverse": true` and every
        # renderer ignored it, so the axis silently drew unreversed — the same
        # accepted-but-inert trap as a secondary axis. Point at the switch that
        # works instead. (`r_axis(reverse=True)` is honoured and unaffected.)
        if theta.get("reverse"):
            raise ValueError(
                "coords='polar' does not support reverse=True on the angular "
                "axis; use theta_axis(direction='clockwise') to reverse the "
                "direction of travel. See spec/design/polar-axes.md."
            )
        sector = theta.get("sector")
        if sector is not None:
            unit = theta.get("theta_unit") or "radians"
            turn = 360.0 if unit == "degrees" else 2.0 * math.pi
            if sector[1] - sector[0] > turn:
                raise ValueError(
                    f"x axis sector sweep must not exceed one full turn ({turn:g} {unit})"
                )
        radial = self.axis_options.get("y", {})
        r_origin = radial.get("r_origin")
        if r_origin is not None:
            # The first resolved limit is the centre-side ring and the second
            # is the outer ring.  On an ordinary radial axis that means the
            # origin lies at/below r_lo; reversing the axis reverses that
            # inequality too.  Sorting here accepted an origin on the wrong
            # side of a reversed view, which then normalized every visible
            # radius beyond 1 and culled the entire plot.
            r_inner, r_outer = self._range("y")
            if radial.get("type") == "log" and r_origin <= 0:
                raise ValueError("y log axis r_origin must be positive")
            if r_inner < r_outer:
                if not r_origin < r_outer:
                    raise ValueError(
                        "y axis r_origin must be less than the resolved radial maximum"
                    )
                if r_origin > r_inner:
                    raise ValueError("y axis r_origin must not exceed the resolved radial minimum")
            else:
                if not r_origin > r_outer:
                    raise ValueError(
                        "y axis r_origin must be greater than the resolved radial minimum"
                    )
                if r_origin < r_inner:
                    raise ValueError(
                        "y axis r_origin must not be less than the resolved radial maximum"
                    )
        for t in self.traces:
            # heatmap/contour are exempt because a cell grid legitimately
            # carries more cells than the *point* ceiling. Narrowing the gate
            # to that end un-capped bar/column/errorbar as collateral, and a
            # polar bar is the most expensive mark there is — 2*(96+1) verts
            # per wedge against a cartesian quad's 4 — so a million of them
            # built without a word. Name every capped kind explicitly.
            if (
                t.kind in {"line", "scatter", "area", "bar", "column", "errorbar"}
                and t.n_points > POLAR_DIRECT_CEILING
            ):
                # Polar has no decimation or density tier to fall back to
                # (polar-axes.md §7), so past the cap the only honest options
                # are refusing or an unbounded direct draw. Refuse, and say
                # which trace and why.
                raise ValueError(
                    f"polar {t.kind} trace has {t.n_points:,} points, over the "
                    f"{POLAR_DIRECT_CEILING:,}-point polar ceiling: polar traces "
                    "always draw every point (no decimation/density tier yet — "
                    "spec/design/polar-axes.md §7). Reduce the data or bin it "
                    "before charting."
                )

    def _zoom_enabled(self) -> bool:
        """The resolved `zoom` capability.

        `zoom` is the one interaction switch whose default depends on the
        coordinate system: polar resolves it to False (polar-axes.md §8 — the
        centre is a fixed point, so zooming a constant-rim composition crops it
        instead of navigating it), Cartesian to True. Every consumer of the
        resolved value goes through here, so validation and the payload cannot
        disagree about it — they did, and `default_drag_action='zoom'` on a
        polar chart passed construction only to ship the self-contradicting
        `{"zoom": false, "default_drag_action": "zoom"}`.
        """
        value = self.interaction.get("zoom")
        if value is None:
            return self.coords != "polar"
        return value is not False

    def _validate_interaction(self) -> None:
        for name in ("pan_axes", "zoom_axes", "reset_axes", "link_axes"):
            if name in self.interaction:
                self._axis_policy(self.interaction[name], name)
        if "zoom_limits" in self.interaction:
            self._zoom_limits(self.interaction["zoom_limits"])
        action = self.interaction.get("default_drag_action")
        if action is None:
            return
        action = self._default_drag_action(action)
        if action in {"auto", "none"}:
            return
        if self.coords == "polar":
            # A disc has no drag tools at all (polar-axes.md §8), which is why
            # polar's resolved drag mode is `none`: the client returns [] for
            # `pan_axes` and forces `box_zoom`/`select`/`brush` off under polar,
            # whatever the flags say. So every action but `auto`/`none` is
            # accepted-and-inert — the plausible-but-wrong outcome §28 refuses
            # everywhere else in this validator. Radial zoom is unaffected: it is
            # a wheel/button gesture, not a drag.
            raise ValueError(
                f"coords='polar' does not support default_drag_action={action!r}; a "
                "disc has no drag tools (theta pan, box zoom, and rectangular/lasso "
                "selection all lack polar geometry), so only 'auto' and 'none' are "
                "meaningful. Radial zoom is a separate wheel/button capability, "
                "controlled by the `zoom` switch rather than by a drag action. See "
                "spec/design/polar-axes.md."
            )

        def enabled(name: str) -> bool:
            # `zoom` reads through the resolved predicate rather than the raw
            # dict so this can never disagree with what `_interaction_spec`
            # ships. The polar guard above means the two currently agree for
            # every action that reaches here; keeping the indirection is what
            # stops that from silently ceasing to be true.
            if name == "zoom":
                return self._zoom_enabled()
            return self.interaction.get(name, True) is not False

        if action == "pan" and not (enabled("navigation") and enabled("pan")):
            raise ValueError("interaction default_drag_action='pan' requires navigation and pan")
        if action == "zoom" and not (
            enabled("navigation") and enabled("zoom") and enabled("box_zoom")
        ):
            raise ValueError(
                "interaction default_drag_action='zoom' requires navigation, zoom, and box_zoom"
            )
        if action.startswith("select") and not (
            enabled("select") and enabled("brush") and any(t.kind == "scatter" for t in self.traces)
        ):
            raise ValueError(
                f"interaction default_drag_action={action!r} requires select, brush, and pickable data"
            )

    _axis_label_position = staticmethod(_validate.axis_label_position)

    @staticmethod
    def _required_text(value: Any, label: str) -> str:
        if isinstance(value, str):
            return value
        raise ValueError(f"{label} must be a string")

    @staticmethod
    def _pixel_dimension(value: Any, label: str) -> Any:
        if isinstance(value, str):
            if value == "100%":
                return value
            raise ValueError(f'{label} must be a positive integer pixel count or "100%"')
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise ValueError(f'{label} must be a positive integer pixel count or "100%"')
        out = int(value)
        if out <= 0:
            raise ValueError(f'{label} must be a positive integer pixel count or "100%"')
        return out

    _as_float_array = staticmethod(_ingest.as_float_array)
    _real_float_array = staticmethod(_ingest.real_float_array)
    _bar_value_matrix = staticmethod(_ingest.bar_value_matrix)
    _series_names = staticmethod(_ingest.series_names)
    _series_colors = staticmethod(_ingest.series_colors)
    _is_category_like = staticmethod(_ingest.is_category_like)
    _category_axis_labels = staticmethod(_ingest.category_axis_labels)
    _materialize_sequence = staticmethod(_ingest.materialize_sequence)
    _category_positions = staticmethod(_ingest.category_positions)
    _broadcast_base = staticmethod(_ingest.broadcast_base)
    _cell_edges = staticmethod(_ingest.cell_edges)
    _category_axis_id = _ingest.category_axis_id
    _axis_positions = _ingest.axis_positions
    _axis_positions_with_labels = _ingest.axis_positions_with_labels
    _commit_category_labels = _ingest.commit_category_labels
    _commit_axis_positions = _ingest.commit_axis_positions
    _heatmap_axis_positions = _ingest.heatmap_axis_positions

    _auto_domain = staticmethod(_autorange.auto_domain)
    x_range = _autorange.x_range
    y_range = _autorange.y_range
    _range = _autorange.range_
    _pack_autorange = _autorange.pack_autorange
    _zero_baseline_anchor = _autorange.zero_baseline_anchor

    # -- payload --------------------------------------------------------------

    def _interaction_spec(self) -> dict[str, Any]:
        self._validate_interaction()
        spec: dict[str, Any] = {}
        for name in (
            "hover",
            "click",
            "select",
            "brush",
            "crosshair",
            "navigation",
            "pan",
            "zoom",
            "wheel_zoom",
            "box_zoom",
            "zoom_buttons",
            "double_click_reset",
            "link_select",
            "history",
        ):
            if name in self.interaction:
                spec[name] = self._bool_param(self.interaction[name], f"interaction {name}")
        if "zoom" not in self.interaction and not self._zoom_enabled():
            # Polar zoom is OFF by default (polar-axes.md §8). The centre is a
            # fixed point of the transform and r_lo is pinned, so zooming in
            # only crops the rim while the geometry stays welded to the middle
            # of the disc — on a pie, radial bar, or radar, whose radius is a
            # constant rim or a fixed frame, that reads as broken rather than as
            # navigation. A composition whose RADIUS is a measured quantity
            # (`wind_rose`, where it is a frequency count) opts back in by
            # shipping `zoom=True`, as does any author via
            # `xyg.interaction_config(zoom=True)`; an ordinary `polar_chart` whose
            # radius IS data is expected to do the same.
            #
            # Resolved HERE and shipped explicitly, against §5.2's "unspecified
            # keys stay absent" rule, for two reasons: the client cannot make
            # this decision (`Chart.kind` never reaches the wire — every polar
            # figure looks identical to it), and §28 requires the choice to be
            # on the wire rather than re-derived per renderer. The predicate is
            # `_zoom_enabled` so validation resolves the same default this ships.
            spec["zoom"] = False
        for name in ("pan_axes", "zoom_axes", "reset_axes", "link_axes"):
            if name in self.interaction:
                spec[name] = self._axis_policy(self.interaction[name], name)
        if "zoom_limits" in self.interaction:
            spec["zoom_limits"] = self._zoom_limits(self.interaction["zoom_limits"])
        if "default_drag_action" in self.interaction:
            spec["default_drag_action"] = self._default_drag_action(
                self.interaction["default_drag_action"]
            )
        link_group = self.interaction.get("link_group")
        if link_group is not None:
            group = self._optional_text(link_group, "interaction link_group")
            if not group:
                raise ValueError("interaction link_group must be a non-empty string or None")
            spec["link_group"] = group
        return spec

    def _mark_style_spec(self) -> dict[str, Any]:
        spec: dict[str, Any] = {}
        for state in ("hover", "selected", "unselected"):
            style = self._optional_state_style(self.mark_style.get(state), f"mark_style {state}")
            if style:
                spec[state] = style
        return spec

    def dom_class_strings(self) -> list[str]:
        """Every DOM class string this figure emits, deduped in insertion order.

        Contract: this is the *complete* set of class strings that can reach
        the DOM — the chart root (``class_name``), the chrome slots
        (``class_names`` values, including component-local classes merged into
        those slots), and annotation labels (``annotation["class_name"]`` when
        the annotation has text).
        Per-trace mark ``class_name`` values are adapter-only metadata for
        canvas geometry and do not create DOM nodes. The Reflex adapter joins
        this inventory into the Tailwind scan manifest for static charts (XYBF
        payloads are opaque to Tailwind's source scan), so this method must be
        extended whenever a new DOM class-carrying surface is added.
        """
        class_strings: list[str] = []
        seen: set[str] = set()

        def add(value: Any) -> None:
            if isinstance(value, str) and value.strip() and value not in seen:
                seen.add(value)
                class_strings.append(value)

        add(self.class_name)
        for value in self.class_names.values():
            add(value)
        for annotation in self.annotations:
            if annotation.get("text"):
                add(annotation.get("class_name"))
        return class_strings

    def _dom_spec(self) -> dict[str, Any]:
        dom: dict[str, Any] = {}
        class_name = self._optional_text(self.class_name, "class_name")
        if class_name:
            dom["class_name"] = class_name
        class_names = self._string_mapping(self.class_names, "class_names")
        validate_dom_slots(class_names, "class_names")
        if class_names:
            dom["class_names"] = class_names
        validate_dom_slots(self.chrome_styles, "chrome_styles")
        style = self._style_mapping(self.style, "style")
        if style:
            dom["style"] = style
        chrome_slot_styles = {
            slot: self._style_mapping(slot_style, f"chrome_styles[{slot!r}]")
            for slot, slot_style in self.chrome_styles.items()
        }
        chrome_slot_styles = {
            slot: slot_style for slot, slot_style in chrome_slot_styles.items() if slot_style
        }
        if chrome_slot_styles:
            dom["styles"] = chrome_slot_styles
        return dom

    # -- per-kind payload emitters (extend here for new chart types) ---------

    # -- channel & density helpers -------------------------------------------

    # Interaction handlers live in interaction.py (§17/§34); these delegates are
    # the public API the widget and users call.

    def density_view(
        self, trace_id: int, x0: float, x1: float, y0: float, y1: float, w: int, h: int
    ) -> tuple[dict[str, Any], list[bytes]]:
        """Re-bin a density-mode scatter's aggregation grid for a new viewport."""
        return interaction.density_view(self, trace_id, x0, x1, y0, y1, w, h)

    def pick(
        self, trace_id: int, index: int, drill_seq: Optional[int] = None
    ) -> Optional[dict[str, Any]]:
        """Exact source-row readout for a hover/pick; `index` is a shipped
        vertex index, translated to a canonical row when NaN rows were dropped
        at ship time. Pass the client's `drill_seq` to reject a pick that
        raced a drill update (wrong index space → None, never a wrong row)."""
        return interaction.pick(self, trace_id, index, drill_seq)

    def select_range(
        self, x0: float, x1: float, y0: float, y1: float, trace_id: Optional[int] = None
    ) -> dict[int, np.ndarray]:
        """Box-select: the canonical row indices inside the box, per scatter trace."""
        return interaction.select_range(self, x0, x1, y0, y1, trace_id)

    def select_polygon(self, points: Any, trace_id: Optional[int] = None) -> dict[int, np.ndarray]:
        """Lasso-select → canonical indices per scatter trace."""
        return interaction.select_polygon(self, points, trace_id)

    def to_shipped_indices(self, trace_id: int, canonical: np.ndarray) -> np.ndarray:
        """Canonical rows → shipped vertex positions (the client's mask space)."""
        return interaction.to_shipped_indices(self, trace_id, canonical)

    def decimate_view(
        self, x0: float, x1: float, px_width: int
    ) -> tuple[dict[str, Any], list[bytes]]:
        """Re-decimate the visible line windows on zoom, re-centering the
        f32 upload offsets so precision holds at deep zoom."""
        return interaction.decimate_view(self, x0, x1, px_width)

    def legend_toggle(self, trace_id: int, hidden: bool, category: Optional[int] = None) -> None:
        """Record a legend visibility toggle: whole trace, or one categorical
        code. Selections, decimation, and density re-bins honor it (§34)."""
        interaction.legend_toggle(self, trace_id, hidden, category)

    def append(
        self,
        trace_id: int,
        x: Any,
        y: Any,
        *,
        color: Any = None,
        size: Any = None,
        stroke: Any = None,
        opacity: Any = None,
        alpha: Any = None,
        stroke_width: Any = None,
        symbol: Any = None,
    ) -> tuple[dict[str, Any], list[memoryview]]:
        """Streaming append: extend a scatter/line trace's canonical columns
        and get the client refresh message back. The widget's `append` sends
        it; headless callers can inspect or discard it. Payloads stay
        screen-bounded, so this is O(pixels) on the wire regardless of how
        much data has accumulated."""
        return interaction.append_data(
            self,
            trace_id,
            x,
            y,
            color,
            size,
            stroke,
            opacity,
            alpha,
            stroke_width,
            symbol,
        )

    # -- unified view state (spec/design/view-state.md) ---------------------

    def _validated_state_ranges(self, ranges: Any) -> dict[str, list[float]]:
        """Validate a partial ranges mapping against the declared axes.

        Boundary rules match the §2 state document: exact axis IDs only,
        finite ``[lo, hi]`` pairs, no coercion of NaN/infinity.
        """
        if not isinstance(ranges, dict) or not ranges:
            raise ValueError("ranges must be a non-empty mapping of axis id to (lo, hi)")
        out: dict[str, list[float]] = {}
        for axis_id, pair in ranges.items():
            if axis_id not in self.axis_options:
                raise ValueError(f"unknown axis id {axis_id!r}")
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError(f"range for axis {axis_id!r} must be a (lo, hi) pair")
            lo, hi = float(pair[0]), float(pair[1])
            if not math.isfinite(lo) or not math.isfinite(hi) or lo == hi:
                raise ValueError(f"range for axis {axis_id!r} must be finite and non-empty")
            out[axis_id] = [lo, hi]
        return out

    @staticmethod
    def _validated_state_selection(
        range: Any = None, polygon: Any = None
    ) -> Optional[dict[str, Any]]:
        """Normalize a geometric selection to its §2 wire shape (or None)."""
        if range is not None and polygon is not None:
            raise ValueError("pass range= or polygon=, not both")
        if range is not None:
            if isinstance(range, dict):
                try:
                    values = [float(range[key]) for key in ("x0", "x1", "y0", "y1")]
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("selection range must supply finite x0, x1, y0, y1") from exc
            else:
                try:
                    values = [float(v) for v in range]
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "selection range must be a (x0, x1, y0, y1) tuple or dict"
                    ) from exc
                if len(values) != 4:
                    raise ValueError("selection range must have exactly x0, x1, y0, y1")
            if not all(math.isfinite(v) for v in values):
                raise ValueError("selection range must be finite")
            x0, x1, y0, y1 = values
            return {"range": {"x0": x0, "x1": x1, "y0": y0, "y1": y1}}
        if polygon is not None:
            try:
                points = [[float(p[0]), float(p[1])] for p in polygon]
            except (TypeError, ValueError, IndexError) as exc:
                raise ValueError("selection polygon must be a sequence of (x, y)") from exc
            if len(points) < 3:
                raise ValueError("selection polygon needs at least 3 points")
            if not all(math.isfinite(v) for point in points for v in point):
                raise ValueError("selection polygon must be finite")
            return {"polygon": points}
        return None

    def state_patch_message(
        self,
        *,
        ranges: Any = None,
        selection: Any = _STATE_UNSET,
        animate: bool = True,
        history: bool = True,
    ) -> dict[str, Any]:
        """Build one §8 ``state_patch`` message (merge-patch semantics: absent
        keys leave that facet of the client state alone)."""
        state: dict[str, Any] = {"v": 1}
        if ranges is not None:
            state["ranges"] = self._validated_state_ranges(ranges)
        if selection is not _STATE_UNSET:
            state["selection"] = selection
        if "ranges" not in state and "selection" not in state:
            raise ValueError("state patch must change ranges or selection")
        return {
            "type": "state_patch",
            "state": state,
            "animate": bool(animate),
            "history": bool(history),
        }

    def view_nav_message(self, axes: Any = None) -> dict[str, Any]:
        """Build the §8 ``view_nav`` reset message (axes=None → the client's
        configured reset_axes)."""
        message: dict[str, Any] = {"type": "view_nav", "op": "reset"}
        if axes is not None:
            message["axes"] = self._axis_policy(tuple(axes), "reset axes")
        return message

    def selection_rows_message(self, rows: Any) -> tuple[dict[str, Any], list[bytes]]:
        """Kernel-resolve a per-trace row-index selection into the same binary
        mask buffers the gesture selection path ships (§5.1). Rows-selections
        are non-durable by design; the client applies them outside history."""
        if rows is None:
            raise ValueError("rows selection requires per-trace row indices")
        if not isinstance(rows, dict):
            rows = {0: rows}
        traces: list[dict[str, Any]] = []
        out: list[bytes] = []
        total = 0
        for trace_id, indices in rows.items():
            tid = int(trace_id)
            if not 0 <= tid < len(self.traces):
                raise ValueError(f"unknown trace id {trace_id!r}")
            raw = np.asarray(indices)
            # Canonical row indices are validated here, before the uint32
            # wire encoding: a negative or oversized value would otherwise
            # wrap/ship silently (-1 -> 4294967295) and inflate `total`
            # while the browser highlights nothing (staff-review finding).
            integral = raw.size == 0 or (
                raw.dtype != np.bool_
                and (
                    np.issubdtype(raw.dtype, np.integer)
                    or (
                        np.issubdtype(raw.dtype, np.floating)
                        and bool(np.all(np.isfinite(raw)))
                        and bool(np.all(np.equal(np.mod(raw, 1), 0)))
                    )
                )
            )
            if not integral:
                raise ValueError(
                    f"row indices for trace {tid} must be integers, got dtype {raw.dtype}"
                )
            idx = np.unique(np.asarray(raw, dtype=np.int64).ravel())
            n_rows = len(self.traces[tid].x)
            if idx.size and (int(idx[0]) < 0 or int(idx[-1]) >= n_rows):
                raise ValueError(
                    f"row indices for trace {tid} must be in [0, {n_rows}), "
                    f"got {int(idx[0])}..{int(idx[-1])}"
                )
            wire_idx = self.to_shipped_indices(tid, idx)
            traces.append(
                {
                    "id": tid,
                    "count": int(len(wire_idx)),
                    "buf": len(out),
                    "drill_seq": self.traces[tid].drill_seq,
                }
            )
            out.append(wire_idx.tobytes())
            # Deduplicated, validated canonical rows — not the raw request
            # length and not only the currently-shipped subset.
            total += int(idx.size)
        return {"type": "selection_rows", "traces": traces, "total": total}, out

    def view_state(self) -> dict[str, Any]:
        """The last committed durable state (§5.1). Served from the kernel's
        event-fed cache — no client round-trip; reads are eventually
        consistent and start at the home ranges before any event arrives."""
        if self._view_state_ranges is not None:
            ranges = {axis_id: list(pair) for axis_id, pair in self._view_state_ranges.items()}
        else:
            ranges = {axis_id: list(self._range(axis_id)) for axis_id in self.axis_options}
        selection = self._view_state_selection
        if isinstance(selection, dict):
            selection = dict(selection)
        return {"v": 1, "ranges": ranges, "selection": selection}

    def _record_view_ranges(self, ranges: dict[str, list[float]]) -> None:
        """Fold a committed view event's ranges into the state cache."""
        if self._view_state_ranges is None:
            self._view_state_ranges = {
                axis_id: list(self._range(axis_id)) for axis_id in self.axis_options
            }
        for axis_id, pair in ranges.items():
            if axis_id in self.axis_options:
                self._view_state_ranges[axis_id] = [float(pair[0]), float(pair[1])]

    def _record_selection(self, selection: Optional[dict[str, Any]]) -> None:
        """Fold a committed selection into the state cache; rows-selections
        are recorded only as the opaque ``{"rows": true}`` marker (§2)."""
        self._view_state_selection = selection

    # -- output -----------------------------------------------------------

    def widget(self, *, wasm_ticks: Optional[Mapping[str, str]] = None) -> Any:
        if self._widget is None:
            from .widget import FigureWidget

            self._widget = FigureWidget(self, wasm_ticks=wasm_ticks)
        return self._widget

    def show(self, display: Optional[str] = None) -> Any:
        """The live widget, or a standalone-HTML view when the html display
        host is selected (reflex-shaped-api.md §3.3: "auto" falls back to
        html only on WASM kernels, whose prebuilt frontends cannot load the
        anywidget extension)."""
        if export.notebook_display_mode(display) == "widget":
            return self.widget()
        return export.HtmlView(self._repr_html_())

    def _ipython_display_(self) -> None:
        from IPython.display import display  # type: ignore[import-not-found]

        if export.notebook_display_mode() == "widget":
            display(self.widget())
        else:
            display({"text/html": self._repr_html_()}, raw=True)

    def to_html(
        self,
        path: Optional[str | PathLike[str]] = None,
        *,
        custom_css: Optional[str] = None,
        animation_progress: Optional[float] = None,
        wasm_ticks: bool | Mapping[str, object] = False,
    ) -> str:
        """Standalone interactive HTML: JS client + spec + base64 buffers in
        one self-contained file (base64 carries a ~33% size tax). `custom_css`
        injects an author stylesheet so `class_names` utility classes
        (e.g. Tailwind) resolve in the export. ``wasm_ticks`` attaches
        hosted Rust/WASM ticks when explicit Worker/WASM URLs are available."""
        return export.to_html(
            self,
            path,
            custom_css=custom_css,
            animation_progress=animation_progress,
            wasm_ticks=wasm_ticks,
        )

    def html(
        self,
        path: Optional[str | PathLike[str]] = None,
        *,
        custom_css: Optional[str] = None,
        animation_progress: Optional[float] = None,
        wasm_ticks: bool | Mapping[str, object] = False,
    ) -> str:
        """Alias for ``to_html`` for component-style API symmetry."""
        return self.to_html(
            path,
            custom_css=custom_css,
            animation_progress=animation_progress,
            wasm_ticks=wasm_ticks,
        )

    def _repr_html_(self) -> str:
        """Notebook HTML repr isolated from the host document's styles."""
        return export.notebook_iframe(self.to_html(), width=self.width, height=self.height)

    def to_svg(
        self,
        path: Optional[str | PathLike[str]] = None,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> str:
        """Return static SVG, routing the supported subset through Rust Scene.

        Unsupported features take the documented compatibility renderer before
        compilation.  Invalid input and Rust-consumer failures propagate; they
        are never converted into a fallback.
        """
        from . import _scene_v3, _svg

        data = _scene_v3.public_static_export(self, "svg", width=width, height=height)
        if data is not None:
            svg = data.decode("utf-8")
            if path is not None:
                export._atomic_write_text(path, svg)
            return svg

        return _svg.to_svg(self, path, width=width, height=height)

    def to_scene(self, *, width: Optional[int] = None, height: Optional[int] = None) -> bytes:
        """Compile the migrated Scene mark subset for this figure.

        Supports cartesian scatter/line (including step), bar/column/histogram/
        violin rects, segments/errorbar/stem polylines, area/error_band/ribbon
        bands, triangle_mesh polyfills, and unlabeled rule/band annotations.
        Unsupported marks or customization raise explicitly; ordinary SVG and
        raster exports retain their established renderer until public Scene
        auto-selection covers remaining chrome and CSS-spelling parity.
        """
        from . import _scene_v3

        return _scene_v3.figure_scene(self, width=width, height=height)

    def to_png(
        self,
        path: Optional[str] = None,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        scale: float = 2.0,
        engine: export.Engine = export.Engine.default,
        optimize: bool = False,
        custom_css: Optional[str] = None,
        sandbox: bool = True,
        gl: str = "software",
    ) -> bytes:
        """Static PNG (export.py). `engine=Engine.default` paints the
        decimated payload with the built-in Rust rasterizer — no browser,
        millisecond export. `optimize=True` uses the slower size-oriented
        indexed encoder. `engine=Engine.chromium` screenshots the standalone
        HTML with an automatically discovered installed browser for browser
        CSS/WebGL fidelity (see export.find_browser); `gl` selects its WebGL
        backend — "software" (default, deterministic SwiftShader) or
        "hardware" (real GPU). `custom_css` is Chromium-only and injects an
        author stylesheet into the captured document."""
        return export.to_png(
            self,
            path,
            width=width,
            height=height,
            scale=scale,
            engine=engine,
            optimize=optimize,
            custom_css=custom_css,
            sandbox=sandbox,
            gl=gl,
        )

    def to_image(
        self,
        format: str = "png",
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        scale: float = 2.0,
        background: Optional[str] = None,
        engine: export.Engine | str = export.Engine.auto,
        quality: Optional[int] = None,
        optimize: bool = False,
        custom_css: Optional[str] = None,
        sandbox: bool = True,
        gl: str = "software",
    ) -> bytes:
        """Unified static export: PNG/JPEG/WebP/SVG/PDF bytes (export.py).

        `engine=Engine.auto` is deterministic — the browser-free native path
        for every format, Chromium only when `custom_css` needs a real CSS
        engine. See `export.to_image` for the format, quality, and background
        policies."""
        return export.to_image(
            self,
            format,
            width=width,
            height=height,
            scale=scale,
            background=background,
            engine=engine,
            quality=quality,
            optimize=optimize,
            custom_css=custom_css,
            sandbox=sandbox,
            gl=gl,
        )

    def write_image(
        self,
        path: str | PathLike[str],
        *,
        format: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        scale: float = 2.0,
        background: Optional[str] = None,
        engine: export.Engine | str = export.Engine.auto,
        quality: Optional[int] = None,
        optimize: bool = False,
        custom_css: Optional[str] = None,
        sandbox: bool = True,
        gl: str = "software",
    ) -> bytes:
        """Atomic file export with extension-inferred format (export.py):
        .png/.jpg/.jpeg/.webp/.svg/.pdf, plus .html routing to `to_html`."""
        return export.write_image(
            self,
            path,
            format=format,
            width=width,
            height=height,
            scale=scale,
            background=background,
            engine=engine,
            quality=quality,
            optimize=optimize,
            custom_css=custom_css,
            sandbox=sandbox,
            gl=gl,
        )

    def memory_report(self) -> dict[str, Any]:
        """Every byte class itemized; if it isn't in the report it isn't real."""
        from . import interaction  # method-local: no load-time cycle

        spec, blob = self.build_payload()
        report = self.store.memory_report()
        channel_arrays: list[np.ndarray] = []
        store_arrays = [column.values for column in self.store.columns]
        seen_channels: set[tuple[int, int]] = set()
        for trace in self.traces:
            for channel in (trace.color_ch, trace.size_ch):
                if channel is None:
                    continue
                values = (
                    getattr(channel, "codes", None)
                    if channel.mode == "categorical"
                    else channel.values
                )
                if values is None:
                    continue
                capacity = getattr(channel, "_buffer", None)
                arrays = [capacity if capacity is not None else values]
                counts = getattr(channel, "counts", None)
                if counts is not None:
                    arrays.append(counts)
                for array in arrays:
                    key = (int(array.__array_interface__["data"][0]), int(array.nbytes))
                    if key in seen_channels or any(
                        np.shares_memory(array, item) for item in store_arrays
                    ):
                        continue
                    seen_channels.add(key)
                    channel_arrays.append(array)
        report["channel_bytes"] = int(sum(array.nbytes for array in channel_arrays))
        report["transport_bytes_first_paint"] = len(blob)
        n_total = sum(t.n_points for t in self.traces) or 1
        report["transport_bytes_per_point"] = len(blob) / n_total
        report["pyramid_bytes"] = interaction.pyramid_report_bytes(self)
        report["pyramid_spilled_bytes"] = interaction.pyramid_spilled_bytes(self)
        report["bin_color_bytes"] = interaction.bin_color_cache_bytes(self)
        report["legend_vis_cache_bytes"] = interaction.legend_vis_cache_bytes(self)
        # Capacity, not live length: a streamed column's growth-buffer slack is
        # resident RAM (§27), and equals `canonical_bytes` when nothing appended.
        report["resident_array_bytes"] = (
            report["canonical_capacity_bytes"]
            + report["channel_bytes"]
            + report["pyramid_bytes"]
            + report["bin_color_bytes"]
            + report["legend_vis_cache_bytes"]
        )
        report["backend"] = kernels.BACKEND
        return report

    @staticmethod
    def _optional_state_style(
        value: Optional[dict[str, Any]], label: str
    ) -> dict[str, str | int | float]:
        if value is None:
            return {}
        return Figure._style_mapping(value, label)


# The AnnotationsMixin methods (in `_annotations.py`) and the mark
# implementations (in `marks.py`) carry `-> "Figure"` / `self: "Figure"`
# annotations; expose the concrete class in those modules so
# `typing.get_type_hints` resolves it at runtime without a load-time cycle.
_annotations.Figure = Figure
_marks.Figure = Figure

# The bound mark methods report Figure-owned identity in tracebacks and docs
# even though the function objects live in the declarative core.
for _name in (
    "line",
    "area",
    "error_band",
    "errorbar",
    "scatter",
    "histogram",
    "hist",
    "box",
    "violin",
    "ecdf",
    "hexbin",
    "contour",
    "step",
    "stairs",
    "stem",
    "bar",
    "column",
    "heatmap",
):
    getattr(_marks, _name).__qualname__ = f"Figure.{_name}"
del _name
