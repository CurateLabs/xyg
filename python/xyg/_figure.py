"""The Figure: a data-less spec + column handles (§9).

The spec is tiny JSON — trace kinds, styles, axis config, and *references* into
the column store. Data never rides in the spec: encoded f32 columns travel as
one binary blob beside it (§29: no JSON numbers, no re-encoding, parse-shaped
work is forbidden on the client).
"""

from __future__ import annotations

from typing import Any, Optional, TypeAlias, Union

import numpy as np

from . import (
    _annotations,
    _validate,
    interaction,
)
from . import _figure_autorange as _autorange
from . import _figure_axis as _axis
from . import _figure_dom as _dom
from . import _figure_export as _export
from . import _figure_ingest as _ingest
from . import _figure_interaction as _interaction
from . import _figure_palette as _palette
from . import _figure_runtime as _runtime
from . import _figure_traces as _traces
from . import _figure_view_state as _view_state
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
    PROTOCOL_VERSION,
    SCATTER_DENSITY_THRESHOLD,
    default_palette_color,
)

_FigureCheckpoint: TypeAlias = tuple[ColumnStoreCheckpoint, int, dict[str, list[str]], int]


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

    palette_cycle = property(_palette.palette_cycle)
    colors = property(_palette.colors)
    palette_color = _palette.palette_color
    next_series_color = _palette.next_series_color

    dom_class_strings = _dom.dom_class_strings
    _dom_spec = _dom._dom_spec

    density_view = _runtime.density_view
    pick = _runtime.pick
    select_range = _runtime.select_range
    select_polygon = _runtime.select_polygon
    to_shipped_indices = _runtime.to_shipped_indices
    decimate_view = _runtime.decimate_view
    legend_toggle = _runtime.legend_toggle
    append = _runtime.append

    _validated_state_ranges = _view_state.validated_state_ranges
    _validated_state_selection = staticmethod(_view_state.validated_state_selection)
    state_patch_message = _view_state.state_patch_message
    view_nav_message = _view_state.view_nav_message
    selection_rows_message = _view_state.selection_rows_message
    view_state = _view_state.view_state
    _record_view_ranges = _view_state.record_view_ranges
    _record_selection = _view_state.record_selection

    widget = _export.widget
    show = _export.show
    _ipython_display_ = _export.ipython_display_
    to_html = _export.to_html
    html = _export.html
    _repr_html_ = _export.repr_html_
    to_svg = _export.to_svg
    to_scene = _export.to_scene
    to_png = _export.to_png
    to_image = _export.to_image
    write_image = _export.write_image
    memory_report = _export.memory_report
    set_axis = _axis.set_axis
    set_interaction = _interaction.set_interaction
    set_mark_style = _interaction.set_mark_style
    _set_axis_domain = _axis._set_axis_domain
    _axis_dim = staticmethod(_axis._axis_dim)
    _axis_policy = _axis._axis_policy
    _axis_scale = _axis._axis_scale
    _axis_coord = _axis._axis_coord
    _axis_kind = _axis._axis_kind
    _axis_spec = _axis._axis_spec
    _range_columns = _axis._range_columns
    _default_drag_action = staticmethod(_interaction._default_drag_action)
    _zoom_limit_pair = staticmethod(_interaction._zoom_limit_pair)
    _zoom_limits = _interaction._zoom_limits
    _interaction_axes = _interaction._interaction_axes
    _validate_coords = _interaction._validate_coords
    _zoom_enabled = _interaction._zoom_enabled
    _validate_interaction = _interaction._validate_interaction
    _interaction_spec = _interaction._interaction_spec
    _mark_style_spec = _interaction._mark_style_spec
    _optional_state_style = _interaction._optional_state_style

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

    # Interaction handlers live in interaction.py (§17/§34); these delegates are
    # the public API the widget and users call.


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
