"""Figure display and static export entry points."""

from __future__ import annotations

from collections.abc import Mapping
from os import PathLike
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import export, interaction, kernels

if TYPE_CHECKING:
    pass


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


def ipython_display_(self) -> None:
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


def repr_html_(self) -> str:
    """Notebook HTML repr isolated from the host document's styles."""
    return export.notebook_iframe(self.to_html(), width=self.width, height=self.height)


def to_svg(
    self,
    path: Optional[str | PathLike[str]] = None,
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> str:
    """Return Rust-owned StaticDocument SVG or fail closed."""
    from . import _static_document

    w = export._positive_pixel_count(
        width if width is not None else (self.width if isinstance(self.width, int) else 800),
        "SVG width",
    )
    h = export._positive_pixel_count(
        height if height is not None else (self.height if isinstance(self.height, int) else 500),
        "SVG height",
    )
    svg = _static_document.export_figure(self, "svg", width=w, height=h).decode("utf-8")
    if path is not None:
        export._atomic_write_text(path, svg)
    return svg


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
                getattr(channel, "codes", None) if channel.mode == "categorical" else channel.values
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
