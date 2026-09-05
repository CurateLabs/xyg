"""FacetGrid layout and static export composition."""

from __future__ import annotations

import copy
from collections.abc import Sequence
from os import PathLike
from pathlib import Path
from typing import Any, Optional

from . import export


class FacetGrid:
    """A rendered grid of independent XYG figures."""

    def __init__(
        self,
        figures: Sequence[Any],
        labels: Sequence[str],
        *,
        cols: int,
        width: int,
        height: int,
        gap: int = 12,
        title: Optional[str] = None,
    ) -> None:
        if len(figures) != len(labels) or not figures:
            raise ValueError("FacetGrid needs one label per non-empty panel")
        self.figures = tuple(figures)
        self.labels = tuple(labels)
        self.cols = int(cols)
        self.width = int(width)
        self.height = int(height)
        self.gap = int(gap)
        self.title = title

    @property
    def rows(self) -> int:
        """Number of grid rows implied by the panel count and ``cols``."""
        return (len(self.figures) + self.cols - 1) // self.cols

    @property
    def panel_width(self) -> int:
        """Width of one panel in pixels (grid width split across columns)."""
        return max(120, (self.width - (self.cols - 1) * self.gap) // self.cols)

    @property
    def panel_height(self) -> int:
        """Height of one panel in pixels."""
        return self.height

    # Grid-level title strip height, shared by the HTML/SVG composers and the
    # chromium PNG viewport math (panel titles carry the facet labels).
    _TITLE_H = 24

    @property
    def _title_height(self) -> int:
        return self._TITLE_H if self.title else 0

    @property
    def grid_height(self) -> int:
        """Total composed height: panels + gaps + the grid title strip."""
        return self.rows * self.panel_height + max(0, self.rows - 1) * self.gap

    def to_html(
        self,
        path: Optional[str | PathLike[str]] = None,
        *,
        custom_css: Optional[str] = None,
    ) -> str:
        """A self-contained HTML document laying the panels out as a grid.

        Writes it to ``path`` when given; returns the HTML either way.
        """
        panels: list[str] = []
        for i, fig in enumerate(self.figures):
            spec, blob = fig.build_payload(px_width=self.panel_width)
            panels.append(
                "{" + f'"id":"xy-facet-{i}",'
                f'"spec":{export._json_for_inline_script(spec)},'
                f'"chunks":{export._json_for_inline_script(export._base64_chunks(blob))},'
                f'"n":{len(blob)}' + "}"
            )
        js = export._javascript_for_inline_script(export._bundled_js("standalone"))
        title = export._html.escape(self.title or "XYG facets")
        # Grid title rendered once here; each panel's own chart title is its
        # facet label, so labels are not duplicated in a separate strip.
        heading = (
            f'<div class="xy-facet-title">{export._html.escape(self.title)}</div>'
            if self.title
            else ""
        )
        css = export._custom_css_block(custom_css)
        doc = f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{export._STANDALONE_CSP}">
<title>{title}</title>
<style>
.xy-facet-document{{margin:0;width:100%;min-height:100%;font-family:system-ui,sans-serif;background:#fff;}}
.xy-facet-document .xy-facet-title{{height:{self._TITLE_H}px;line-height:{self._TITLE_H}px;font:600 14px system-ui,sans-serif;margin:0;text-align:center;color:#1e293b;}}
.xy-facet-document .xy-facet-grid{{display:grid;grid-template-columns:repeat({self.cols}, minmax(0, 1fr));gap:{self.gap}px;}}
.xy-facet-document .xy-facet-panel{{min-width:0;}}
</style>
{css}</head><body class="xy-facet-document">
{heading}<div class="xy-facet-grid" id="xy-facet-grid"></div>
<script>{js}</script>
<script>
{export._DECODE_B64_JS}
const panels=[{",".join(panels)}];
const grid=document.getElementById("xy-facet-grid");
for(const p of panels){{
  const panel=document.createElement("div"); panel.className="xy-facet-panel";
  const host=document.createElement("div"); host.id=p.id; panel.append(host); grid.appendChild(panel);
  const buf=xyDecodeB64(p.chunks,p.n); xy.renderStandalone(host,p.spec,buf);
}}
</script></body></html>"""
        if path is not None:
            export._atomic_write_text(path, doc)
        return doc

    def to_svg(
        self,
        path: Optional[str | PathLike[str]] = None,
        *,
        background: Optional[str] = None,
    ) -> str:
        """Compose every admitted panel through Rust StaticDocument."""
        from . import _native

        doc = _native.static_document_export(
            self._static_document(background=background),
            "svg",
        ).decode("utf-8")
        if path is not None:
            export._atomic_write_text(path, doc)
        return doc

    def _static_document(
        self,
        *,
        background: Optional[str] = None,
        optimize_png: bool = False,
    ) -> bytes:
        """Marshal facet placement; Rust owns validation and composition."""
        from . import _scene_v3, _static_document

        layout = _static_document.resolve_facet_layout(
            len(self.figures),
            columns=self.cols,
            width=self.width,
            panel_height=self.height,
            gap=self.gap,
            title=self.title,
        )
        panels = []
        for index, (figure, offset, panel_size) in enumerate(
            zip(self.figures, layout.offsets, layout.panel_sizes, strict=True)
        ):
            panel_width, panel_height = panel_size
            projected = copy.deepcopy(figure)
            if not getattr(projected, "show_legend", False):
                projected.legend_options = {}
            reason, scene = _scene_v3._public_scene_or_reason(
                projected,
                width=panel_width,
                height=panel_height,
            )
            if reason is not None or scene is None:
                raise _static_document.UnsupportedStaticExport(
                    f"facet panel {index}: {reason or 'XYG_STATIC_UNSUPPORTED_PANEL'}"
                )
            panels.append(
                _static_document.Panel(
                    scene,
                    offset[0],
                    offset[1],
                    panel_width,
                    panel_height,
                )
            )
        return _static_document.encode(
            panels,
            width=layout.width,
            height=layout.height,
            background=background,
            title=self.title,
            title_x=layout.title_x,
            title_y=layout.title_baseline,
            optimize_png=optimize_png,
        )

    def to_png(
        self,
        path: Optional[str | PathLike[str]] = None,
        *,
        scale: float = 2.0,
        engine: export.Engine = export.Engine.default,
        optimize: bool = False,
        custom_css: Optional[str] = None,
        sandbox: bool = True,
        gl: str = "software",
    ) -> bytes:
        """A PNG render of the composed grid, returned as bytes.

        ``scale`` multiplies the pixel density; ``engine`` picks the
        raster path (native or headless Chromium). Written to ``path``
        when given.
        """
        optimize = export._bool_option(optimize, "facet PNG optimize")
        resolved_engine = export._png_engine(engine, "facet PNG")
        if resolved_engine == "browser":
            data = export.html_to_png(
                self.to_html(custom_css=custom_css),
                self.width,
                # Match the actual HTML height: panels + gaps + title strip.
                self.grid_height + self._title_height,
                scale=scale,
                sandbox=sandbox,
                gl=gl,
            )
        elif resolved_engine == "native":
            if custom_css is not None:
                raise ValueError("custom_css requires engine=Engine.chromium")
            from . import _native

            data = _native.static_document_export(
                self._static_document(optimize_png=optimize),
                "png",
                scale=scale,
            )
        else:  # `_png_engine` returns only these two internal values.
            raise AssertionError(f"unreachable PNG engine {resolved_engine!r}")
        if path is not None:
            Path(path).write_bytes(data)
        return data

    def to_image(
        self,
        format: str = "png",
        *,
        scale: float = 2.0,
        background: Optional[str] = None,
        engine: "export.Engine | str" = export.Engine.auto,
        quality: Optional[int] = None,
        optimize: bool = False,
        custom_css: Optional[str] = None,
        sandbox: bool = True,
        gl: str = "software",
    ) -> bytes:
        """Unified static export of the composed grid (same matrix as single
        charts): PNG/JPEG/WebP/SVG/PDF bytes.

        The grid's pixel geometry is fixed by its panels, so there are no
        width/height overrides here; `scale` still multiplies raster density.
        Native raster output composes the browser-free panel renders (no grid
        title strip — the native rasterizer has no free-standing text path);
        SVG/PDF compose the vector panels, title included. Engine, quality,
        and background policies match `export.to_image`."""
        fmt = export._normalize_format(format)
        resolved_engine = export._resolve_image_engine(engine, fmt, custom_css)
        quality = export._validated_quality(quality, fmt, resolved_engine)
        background = export._validated_background(background, fmt)
        scale = export._positive_finite_float(scale, "export scale")
        optimize = export._bool_option(optimize, "export optimize")
        sandbox = export._bool_option(sandbox, "export sandbox")
        gl = export._gl_option(gl)
        if resolved_engine == "native":
            from . import _native

            return _native.static_document_export(
                self._static_document(
                    background=background,
                    optimize_png=optimize and fmt == "png",
                ),
                fmt,
                scale=scale,
                quality=quality or 90,
            )
        # The background override must actually reach the captured document,
        # exactly as in the single-chart browser path — the CDP transparency
        # flag below only clears Chromium's default white page backdrop.
        bg_css = export._background_css(background)
        doc = self.to_html(custom_css=(bg_css + (custom_css or "")) or None)
        total_h = self.grid_height + self._title_height
        with export._browser_session(gl=gl, sandbox=sandbox) as session:
            if fmt == "pdf":
                return session.render_pdf(doc, self.width, total_h)
            return session.render_image(
                doc,
                self.width,
                total_h,
                format=fmt,
                scale=scale,
                quality=quality,
                transparent=background == "transparent",
            )

    def write_image(
        self,
        path: str | PathLike[str],
        *,
        format: Optional[str] = None,
        scale: float = 2.0,
        background: Optional[str] = None,
        engine: "export.Engine | str" = export.Engine.auto,
        quality: Optional[int] = None,
        optimize: bool = False,
        custom_css: Optional[str] = None,
        sandbox: bool = True,
        gl: str = "software",
    ) -> bytes:
        """Atomic file export with extension-inferred format; ".html" routes
        to `to_html`. Options match `to_image`."""
        fmt = (
            export._normalize_format(format, allow_html=True)
            if format is not None
            else export._infer_format(path)
        )
        if fmt == "html":
            return self.to_html(path, custom_css=custom_css).encode("utf-8")
        data = self.to_image(
            fmt,
            scale=scale,
            background=background,
            engine=engine,
            quality=quality,
            optimize=optimize,
            custom_css=custom_css,
            sandbox=sandbox,
            gl=gl,
        )
        export._atomic_write_bytes(path, data)
        return data

    def widget(self) -> list[Any]:
        """Live notebook widgets, one per facet panel."""
        from .widget import FigureWidget

        return [FigureWidget(fig) for fig in self.figures]

    def show(self, display: Optional[str] = None) -> Any:
        """Display the facet grid: the panel widgets, or one standalone-HTML
        view of the whole grid on the html display host (see `Chart.show`)."""
        if export.notebook_display_mode(display) == "widget":
            return self.widget()
        return export.HtmlView(
            export.notebook_iframe(
                self.to_html(),
                width=self.width,
                height=self.grid_height + self._title_height,
            )
        )

    def memory_report(self) -> dict[str, Any]:
        """Aggregated data/cache buffer accounting across all panels."""
        reports = [fig.memory_report() for fig in self.figures]
        return {
            "panels": len(reports),
            "transport_bytes_first_paint": sum(r["transport_bytes_first_paint"] for r in reports),
            "store_bytes": sum(r["store_bytes"] for r in reports),
            "backend": "native",
        }
