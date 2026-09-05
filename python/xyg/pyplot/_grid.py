"""Multi-panel composition — the shim-owned replacement for an engine grid.

HTML: one self-contained document (same zero-dependency offline story as
`Chart.to_html`): the render client ships once and every panel hydrates into
a host div, so all panels share the page-level WebGL context governor. A
panel-per-iframe composition put each panel in its own document with its own
governor, and a dense subplot grid exceeded the browser's per-page context
cap — only the first ~dozen panels ever rendered. The shared governor
snapshots and releases over-budget panels instead; pointer entry revives
them.

PNG: each panel renders through the engine's native rasterizer to an RGBA
array; NumPy composites them onto one canvas and the engine's PNG encoder
writes the file. Absolutely placed panels are rendered on a transparent canvas
and alpha-composited, because a panel is wider than its gridspec cell — its
tick labels and title live outside the plot rect — and an opaque paste made
each column erase the one to its left. This module and `_mplfig.savefig` are
the only places the shim
reaches past the public API (via `Chart.figure()` + the `_raster`/`_png`
modules); everything else goes through `xy`' public surface.
"""

from __future__ import annotations

import copy
import html as _html
from typing import Any, Optional


def _html_figure_labels(labels: list[dict[str, Any]]) -> str:
    body = []
    for label in labels:
        anchor = str(label.get("anchor", "middle"))
        shift_x = {"start": "0%", "middle": "-50%", "end": "-100%"}.get(anchor, "-50%")
        alignment = str(label.get("vertical_align", "center"))
        shift_y = {
            "top": "0%",
            "baseline": "-100%",
            "bottom": "-100%",
            "center": "-50%",
            "center_baseline": "-50%",
        }.get(alignment, "-50%")
        angle = -float(label.get("rotation", 0.0))
        body.append(
            "<div class='xy-figure-label' style='position:absolute;"
            f"left:{float(label.get('x', 0.5)) * 100:g}%;"
            f"top:{(1.0 - float(label.get('y', 0.5))) * 100:g}%;"
            f"transform:translate({shift_x},{shift_y}) rotate({angle:g}deg);"
            f"font-size:{float(label.get('size', 12.0)):g}px;"
            f"font-family:{_html.escape(str(label.get('family', 'system-ui,sans-serif')))};"
            f"font-style:{_html.escape(str(label.get('font_style', 'normal')))};"
            f"font-weight:{_html.escape(str(label.get('weight', 'normal')))};"
            f"color:{_html.escape(str(label.get('color', '#262626')))};"
            f"opacity:{float(label.get('opacity', 1.0)):g}'>"
            f"{_html.escape(str(label.get('text', '')))}</div>"
        )
    return "".join(body)


def _html_figure_legend(legend: Optional[dict[str, Any]]) -> str:
    if not legend or not legend.get("items"):
        return ""
    options = legend.get("style") or {}
    rows = []
    for item in legend["items"]:
        item_style = item.get("style") or {}
        color = _html.escape(str(item_style.get("color", "#4c78a8")))
        kind = str(item.get("kind", "line"))
        if kind in {"line", "segments", "step", "stairs", "errorbar"}:
            swatch_style = (
                "height:0;background:transparent;"
                f"border-top:{float(item_style.get('width', 2.0)):g}px "
                f"{'dashed' if item_style.get('dash') else 'solid'} {color}"
            )
        elif kind == "scatter":
            swatch_style = f"width:9px;height:9px;border-radius:50%;background:{color}"
        else:
            swatch_style = f"height:9px;background:{color}"
        rows.append(
            "<div class='xy-figure-legend-row'>"
            f"<span class='xy-figure-legend-swatch' style='{swatch_style}'></span>"
            f"<span>{_html.escape(str(item.get('name', '')))}</span></div>"
        )
    ncols = max(1, int(legend.get("ncols", 1)))
    loc = (
        "upper right"
        if legend.get("figure_loc") == "outside right upper"
        else str(legend.get("loc", "upper right"))
    )
    transforms = []
    if "left" in loc:
        horizontal = "left:6px;"
    elif "right" in loc:
        horizontal = "right:6px;"
    else:
        horizontal = "left:50%;"
        transforms.append("translateX(-50%)")
    vertical = "top:6px;" if "upper" in loc else "bottom:6px;" if "lower" in loc else "top:50%;"
    if "upper" not in loc and "lower" not in loc:
        transforms.append("translateY(-50%)")
    transform = f"transform:{' '.join(transforms)};" if transforms else ""
    title = legend.get("title")
    title_html = (
        "<div class='xy-figure-legend-title' "
        f"style='grid-column:1/{ncols + 1}'>{_html.escape(str(title))}</div>"
        if title
        else ""
    )
    return (
        "<div class='xy-figure-legend' style='position:absolute;"
        f"{horizontal}{vertical}{transform}"
        f"grid-template-columns:repeat({ncols},max-content);"
        f"font-size:{_html.escape(str(options.get('fontSize', '11px')))};"
        f"color:{_html.escape(str(options.get('color', '#262626')))};"
        f"background:{_html.escape(str(options.get('background', 'rgba(255,255,255,.92)')))};"
        f"border-color:{_html.escape(str(options.get('borderColor', '#cccccc')))}'>"
        f"{title_html}{''.join(rows)}</div>"
    )


def compose_html(
    charts: list[Any],
    nrows: int,
    ncols: int,
    suptitle: Optional[str],
    suptitle_style: Optional[dict[str, Any]] = None,
    *,
    figure_labels: Optional[list[dict[str, Any]]] = None,
    figure_legend: Optional[dict[str, Any]] = None,
    positions: Optional[list[tuple[float, float, float, float]]] = None,
    canvas_size: Optional[tuple[int, int]] = None,
) -> str:
    """Compose panel documents into one page.

    Default: a CSS grid of panels. With ``positions`` (whole-panel
    [left, bottom, width, height] figure fractions, bottom-origin like
    matplotlib) and ``canvas_size`` px, panels are absolutely placed on a
    fixed-size canvas instead — the add_axes/subplots_adjust layout path.
    Document order stacks later axes above earlier ones, as matplotlib draws.
    """
    from xyg import export

    absolute = positions is not None and canvas_size is not None
    panels = []
    payloads = []
    for index, chart in enumerate(charts):
        figure = chart.figure()
        spec, blob = figure.build_payload()
        # Exact chart size: absolute placement relies on the panel's plot box
        # landing on its matplotlib rect, so a dense grid's sub-120px panels
        # must not be inflated here (the client honors small explicit sizes).
        width = int(figure.width)
        height = int(figure.height)
        placement = ""
        if absolute:
            left, bottom, _width, panel_height = positions[index]
            x = round(left * canvas_size[0])
            y = round((1.0 - bottom - panel_height) * canvas_size[1])
            placement = f"position:absolute;left:{x}px;top:{y}px;"
        panels.append(
            '<div class="xy-panel" data-xy-pyplot-panel '
            f'style="{placement}width:{width}px;height:{height}px"></div>'
        )
        payloads.append(
            "{" + f'"spec":{export._json_for_inline_script(spec)},'
            f'"chunks":{export._json_for_inline_script(export._base64_chunks(blob))},'
            f'"n":{len(blob)}' + "}"
        )
    style = suptitle_style or {}
    title_css = (
        f"font-size:{float(style.get('size', 16)):g}px;font-weight:{_html.escape(str(style.get('weight', 'normal')))};"
        f"font-family:{_html.escape(str(style.get('family', 'system-ui, sans-serif')))};"
        f"color:{_html.escape(str(style.get('color', '#262626')))}"
    )
    if not suptitle:
        title_html = ""
    elif absolute:
        # The suptitle anchors at figure-fraction (x, y) on the canvas itself.
        shift = {"left": "0%", "center": "-50%", "right": "-100%"}.get(
            str(style.get("ha", "center")), "-50%"
        )
        title_html = (
            "<div class='xy-suptitle' style='position:absolute;"
            f"left:{float(style.get('x', 0.5)) * 100:g}%;"
            f"top:{(1.0 - float(style.get('y', 0.98))) * 100:g}%;"
            f"transform:translate({shift},0);margin:0;{title_css}'>"
            f"{_html.escape(suptitle)}</div>"
        )
    else:
        title_html = f"<h2 class='xy-suptitle' style='{title_css}'>{_html.escape(suptitle)}</h2>"
    if absolute:
        grid_css = (
            f".xy-grid {{ position: relative; width: {canvas_size[0]}px; "
            f"height: {canvas_size[1]}px; overflow: hidden; }}"
        )
        decorations = (
            title_html
            + _html_figure_labels(figure_labels or [])
            + _html_figure_legend(figure_legend)
        )
        grid = "\n".join(panels) + ("\n" + decorations if decorations else "")
        title_html = ""
    else:
        grid_css = (
            f".xy-grid {{ display: grid; grid-template-columns: repeat({ncols}, max-content); "
            "gap: 4px; padding: 4px; overflow-x: auto; }}"
        )
        grid = "\n".join(panels)
    client_js = export._javascript_for_inline_script(export._bundled_js("standalone"))
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{export._STANDALONE_CSP}">
<style>
  body {{ margin: 0; font-family: system-ui, sans-serif; background: #ffffff; }}
  .xy-suptitle {{ text-align: center; margin: 8px 0 0; font-size: 16px; color: #262626; white-space: pre-line; line-height: 1.2; }}
  {grid_css}
  .xy-panel {{ position: relative; }}
  .xy-figure-label {{ z-index: 4; white-space: pre-line; line-height: 1.2; pointer-events: none; }}
  .xy-figure-legend {{ z-index: 4; display: grid; gap: 5px; padding: 5px 7px; border: 1px solid; border-radius: 4px; }}
  .xy-figure-legend-row {{ display: flex; align-items: center; gap: 7px; white-space: nowrap; }}
  .xy-figure-legend-title {{ font-weight: 600; }}
  .xy-figure-legend-swatch {{ box-sizing: border-box; display: inline-block; width: 18px; height: 3px; }}
</style>
</head>
<body>
{title_html}
<div class="xy-grid">
{grid}
</div>
<script>{client_js}</script>
<script>
{export._DECODE_B64_JS}
const panels = [{",".join(payloads)}];
const hosts = document.querySelectorAll("[data-xy-pyplot-panel]");
panels.forEach((p, i) => {{
  xy.renderStandalone(hosts[i], p.spec, xyDecodeB64(p.chunks, p.n));
}});
</script>
</body>
</html>"""


def compose_svg(
    charts: list[Any],
    nrows: int,
    ncols: int,
    suptitle: Optional[str],
    suptitle_style: Optional[dict[str, Any]] = None,
    *,
    figure_labels: Optional[list[dict[str, Any]]] = None,
    figure_legend: Optional[dict[str, Any]] = None,
    positions: Optional[list[tuple[float, float, float, float]]] = None,
    canvas_size: Optional[tuple[int, int]] = None,
    facecolor: Optional[str] = None,
) -> str:
    """Compose subplot Scenes through the Rust StaticDocument kernel."""
    from xyg import _native

    document = _pyplot_static_document(
        charts,
        nrows,
        ncols,
        suptitle,
        suptitle_style,
        figure_labels=figure_labels,
        figure_legend=figure_legend,
        positions=positions,
        canvas_size=canvas_size,
        facecolor=facecolor,
    )
    return _native.static_document_export(document, "svg").decode("utf-8")


def _pyplot_static_document(
    charts: list[Any],
    nrows: int,
    ncols: int,
    suptitle: Optional[str],
    suptitle_style: Optional[dict[str, Any]] = None,
    *,
    figure_labels: Optional[list[dict[str, Any]]] = None,
    figure_legend: Optional[dict[str, Any]] = None,
    positions: Optional[list[tuple[float, float, float, float]]] = None,
    canvas_size: Optional[tuple[int, int]] = None,
    facecolor: Optional[str] = None,
    optimize_png: bool = False,
    tight_crop: bool = False,
    crop_padding: int = 0,
    colorbar: Optional[dict[str, Any]] = None,
) -> bytes:
    """Marshal pyplot panels; Rust owns document rendering and composition."""
    from xyg import _scene_v3, _static_document

    figures = [_pyplot_scene_figure(chart.figure()) for chart in charts]
    if not figures:
        raise ValueError("figure has no axes to save")
    style = suptitle_style or {}
    size = float(style.get("size", 16))
    layout = _static_document.resolve_layout(
        [(int(figure.width), int(figure.height)) for figure in figures],
        nrows=nrows,
        ncols=ncols,
        title=suptitle,
        title_size=size,
        title_x_fraction=float(style.get("x", 0.5)),
        title_y_fraction=float(style.get("y", 0.98)),
        positions=positions,
        canvas_size=canvas_size,
        shared_colorbar=colorbar is not None,
    )
    offsets = layout.offsets
    total_size = (layout.width, layout.height)
    panels = []
    for index, (figure, offset) in enumerate(zip(figures, offsets, strict=True)):
        width, height = int(figure.width), int(figure.height)
        reason, scene = _scene_v3._public_scene_or_reason(figure, width=width, height=height)
        if reason is not None or scene is None:
            raise _static_document.UnsupportedStaticExport(
                f"pyplot panel {index}: {reason or 'XYG_STATIC_UNSUPPORTED_PANEL'}"
            )
        panels.append(
            _static_document.Panel(
                scene,
                offset[0],
                offset[1],
                width,
                height,
                figure._static_document_chrome_metrics,
                figure._static_document_colorbar_layout,
                figure._static_document_annotation_font_size,
                figure._static_document_arrow_metrics,
                figure._static_document_axis_sides,
                figure._static_document_annotation_text_flags,
                figure._static_document_annotation_padding,
                figure._static_document_title_style,
                figure._static_document_annotation_vertical_align,
                figure._static_document_colorbar_scale,
                figure._static_document_colorbar_extend,
                figure._static_document_colorbar_pyplot_label,
                figure._static_document_colorbar_fill_plot,
                grid_dash=getattr(figure, "_static_document_grid_dash", None),
            )
        )
    panel_legends = [
        figure._static_document_panel_legend
        for figure in figures
        if figure._static_document_panel_legend is not None
    ]
    if panel_legends:
        if len(figures) != 1 or len(panel_legends) != 1 or figure_legend is not None:
            raise _static_document.UnsupportedStaticExport(
                "XYG_STATIC_UNSUPPORTED_MULTIPLE_PANEL_LEGENDS"
            )
        figure_legend = panel_legends[0]
    anchor = {"left": 0, "center": 1, "right": 2}.get(str(style.get("ha", "center")), 1)
    family = str(style.get("family", "system-ui,sans-serif")).lower().replace(" ", "")
    if suptitle and family not in {"system-ui,sans-serif", "dejavusans", "sans-serif"}:
        raise _static_document.UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_TITLE_STYLE")
    font_style = str(style.get("font_style", "normal")).lower()
    weight = str(style.get("weight", "normal")).lower()
    bold_weights = {"bold", "semibold", "demibold", "heavy", "black", "600", "700", "800", "900"}
    if suptitle and (
        font_style not in {"normal", "italic", "oblique"}
        or weight not in {"normal", "regular", "book", "400"} | bold_weights
    ):
        raise _static_document.UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_TITLE_STYLE")
    title_flags = (1 if font_style != "normal" else 0) | (2 if weight in bold_weights else 0)
    return _static_document.encode(
        panels,
        width=total_size[0],
        height=total_size[1],
        background=facecolor,
        title=suptitle,
        title_color=str(style.get("color", "#262626")),
        title_size=size,
        title_x=layout.title_x,
        title_y=layout.title_baseline,
        title_anchor=anchor,
        title_flags=title_flags,
        optimize_png=optimize_png,
        labels=figure_labels,
        tight_crop=tight_crop,
        crop_padding=crop_padding,
        colorbar=None if colorbar is None else str(colorbar.get("colormap", "viridis")),
        legend=figure_legend,
    )


#: Pyplot grid dash spellings -> XYST fact codes; the pattern table is Rust's.
_GRID_DASH_CODES = {"solid": 0, "dashed": 1, "dotted": 2, "dashdot": 3}


def _pyplot_scene_figure(figure: Any) -> Any:
    """Translate pyplot's fixed CSS theme into literal Scene chrome facts.

    This is API coercion, not a renderer: output geometry/ticks/paint remain
    owned by the same Rust Scene compiler used by Node.
    """
    from xyg import _native, _static_document

    projected = copy.copy(figure)
    projected.traces = []
    for trace in figure.traces:
        cloned = copy.copy(trace)
        cloned.style = {
            key: value
            for key, value in (trace.style or {}).items()
            if not str(key).startswith("_legend_")
        }
        if (
            trace.kind == "heatmap"
            and trace.grid is not None
            and trace.grid_shape is not None
            and not _native.scene_finite_all(trace.grid.values)
        ):
            rows, cols = trace.grid_shape
            stops = _native.colormap_stops(str(cloned.style.get("colormap", "viridis")))
            domain = tuple(float(value) for value in cloned.style.get("domain", (0.0, 1.0)))
            alpha = round(255.0 * float(cloned.style.get("opacity", 1.0)))
            rgba = _native.colormap_rgba_canonical(
                trace.grid.values,
                cols,
                rows,
                domain,
                stops,
                alpha,
            )
            planes = tuple(
                projected.store.ingest(rgba[..., channel].reshape(-1).astype("float64") / 255.0)
                for channel in range(4)
            )
            cloned.grid = planes[0]
            cloned.rgba_grid = planes
            cloned.style.pop("colormap", None)
            cloned.style["truecolor"] = True
        projected.traces.append(cloned)
    projected.axis_options = copy.deepcopy(figure.axis_options)
    projected._axis_categories = copy.deepcopy(figure._axis_categories)

    resolved_annotations = _static_document.resolve_annotation_styles(figure.annotations)
    projected.annotations = resolved_annotations.annotations
    arrow_metrics = set()
    for annotation in projected.annotations:
        annotation_style = annotation.get("style") or {}
        if annotation.get("kind") == "arrow" and any(
            key in annotation_style for key in ("head_size", "shaft_width_start", "shaft_width_end")
        ):
            head = float(annotation_style.pop("head_size", 8.0))
            start = float(
                annotation_style.pop("shaft_width_start", annotation_style.get("width", 1.5))
            )
            end = float(annotation_style.pop("shaft_width_end", start))
            if start != end:
                raise _static_document.UnsupportedStaticExport(
                    "XYG_STATIC_UNSUPPORTED_TAPERED_ANNOTATION_ARROW"
                )
            annotation_style["width"] = start
            arrow_metrics.add((head, start, end))
    if len(arrow_metrics) > 1:
        raise _static_document.UnsupportedStaticExport(
            "XYG_STATIC_UNSUPPORTED_HETEROGENEOUS_ARROW_METRICS"
        )
    metrics: dict[str, tuple[float, float, float]] = {}
    grid_dash: dict[str, Optional[int]] = {"x": None, "y": None}
    grid_dash_minor: dict[str, Optional[int]] = {"x": None, "y": None}
    root = dict(getattr(figure, "style", None) or {})
    if getattr(figure, "_pyplot_static_mathtext", False):
        raise _static_document.UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_MATHTEXT_STYLE")
    allowed_root = {
        "background",
        "--chart-bg",
        "--chart-grid",
        "--chart-axis",
        "--chart-text",
        "font-family",
        "font-size",
    }
    if set(root) - allowed_root:
        raise _static_document.UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_BROWSER_CSS")
    family = str(root.get("font-family", "DejaVu Sans, sans-serif")).lower().replace(" ", "")
    if family not in {"dejavusans,sans-serif", "system-ui,sans-serif", "sans-serif"}:
        raise _static_document.UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_CUSTOM_FONT")
    title_style = dict((getattr(figure, "chrome_styles", None) or {}).get("title") or {})
    for slot, chrome_style in (getattr(figure, "chrome_styles", None) or {}).items():
        allowed = (
            {
                "fontSize",
                "background",
                "borderColor",
                "borderStyle",
                "borderWidth",
                "--xy-legend-frame-alpha",
                "padding",
                "rowGap",
            }
            if slot == "legend"
            else {"font-size", "color", "font-weight", "font-family"}
            if slot in {"title", "axis_title", "tick_label"}
            else set()
        )
        if not allowed or set(chrome_style) - allowed:
            raise _static_document.UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_CHROME_STYLE")
        if slot == "legend":
            continue
        chrome_family = str(chrome_style.get("font-family", "DejaVu Sans")).lower()
        if chrome_family not in {"dejavu sans", "dejavusans", "sans-serif"}:
            raise _static_document.UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_CUSTOM_FONT")
    grid = root.get("--chart-grid")
    axis = root.get("--chart-axis")
    text = root.get("--chart-text")
    for axis_id, options in projected.axis_options.items():
        style = dict(options.get("style") or {})
        minor = dict(options.get("minor_style") or {})
        if axis_id in {"x", "y"}:
            metrics[axis_id] = (
                float(style.pop("tick_label_size", style.pop("tick_size", 12.0))),
                float(style.pop("label_size", 12.0)),
                float(style.pop("tick_padding", 4.0)),
            )
            raw_dash = style.pop("grid_dash", None)
            if raw_dash is not None:
                if raw_dash not in _GRID_DASH_CODES:
                    raise _static_document.UnsupportedStaticExport(
                        "XYG_STATIC_UNSUPPORTED_GRID_DASH"
                    )
                grid_dash[axis_id] = _GRID_DASH_CODES[raw_dash]
            raw_minor_dash = minor.pop("grid_dash", None)
            if raw_minor_dash is not None:
                if raw_minor_dash not in _GRID_DASH_CODES:
                    raise _static_document.UnsupportedStaticExport(
                        "XYG_STATIC_UNSUPPORTED_GRID_DASH"
                    )
                grid_dash_minor[axis_id] = _GRID_DASH_CODES[raw_minor_dash]
        for key in ("tick_label_size", "tick_size", "label_size", "tick_padding"):
            minor.pop(key, None)
        if grid is not None:
            style["grid_color"] = grid
            minor["grid_color"] = grid
        if axis is not None:
            style["axis_color"] = axis
            style["tick_color"] = axis
            minor["tick_color"] = axis
        if text is not None:
            style.setdefault("label_color", text)
            style.setdefault("tick_label_color", text)
        if style:
            options["style"] = style
        else:
            options.pop("style", None)
        if minor:
            options["minor_style"] = minor
        else:
            options.pop("minor_style", None)
        categories = projected._axis_categories.pop(axis_id, None)
        if categories is not None and options.get("tick_labels") is None:
            options["tick_labels"] = [str(value) for value in categories]
        if options.get("domain") is None:
            options["domain"] = tuple(float(value) for value in figure._range(axis_id))
    projected.style = {
        key: value for key, value in root.items() if key in {"background", "--chart-bg"}
    }
    projected.chrome_styles = {}
    projected._static_document_title_style = None
    if getattr(figure, "title", None):
        raw_size = str(title_style.get("font-size", "14px"))
        if not raw_size.endswith("px"):
            raise _static_document.UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_TITLE_STYLE")
        projected._static_document_title_style = (
            float(raw_size[:-2]),
            str(title_style.get("color", text or "#262626")),
        )
    projected.title_options = []
    panel_legend = None
    if projected.show_legend:
        if projected.extra_legends:
            raise _static_document.UnsupportedStaticExport(
                "XYG_STATIC_UNSUPPORTED_MULTIPLE_PANEL_LEGENDS"
            )
        legend_items = [
            {"kind": trace.kind, "name": trace.name, "style": dict(trace.style or {})}
            for trace in projected.traces
            if trace.name
        ]
        if legend_items:
            panel_legend = {**copy.deepcopy(projected.legend_options), "items": legend_items}
    projected.show_legend = False
    projected.legend_options = {}
    projected.extra_legends = []
    colorbar = dict(getattr(figure, "colorbar_options", None) or {})
    projected._static_document_colorbar_layout = None
    projected._static_document_colorbar_scale = None
    projected._static_document_colorbar_extend = None
    projected._static_document_colorbar_pyplot_label = False
    projected._static_document_colorbar_fill_plot = False
    if colorbar:
        supported = {
            "colormap",
            "domain",
            "label",
            "orientation",
            "shrink",
            "anchor",
            "minor_ticks",
            "ticks",
            "scale",
            "extend",
            "pad",
            "levels",
            "boundaries",
            "placement",
        }
        if set(colorbar) - supported:
            raise _static_document.UnsupportedStaticExport(
                "XYG_STATIC_UNSUPPORTED_PANEL_COLORBAR_STYLE"
            )
        domain = tuple(float(value) for value in colorbar.get("domain", (0.0, 1.0)))
        if len(domain) != 2 or not domain[0] < domain[1]:
            raise _static_document.UnsupportedStaticExport(
                "XYG_STATIC_UNSUPPORTED_PANEL_COLORBAR_DOMAIN"
            )
        orientation = str(colorbar.get("orientation", "vertical"))
        if orientation not in {"vertical", "horizontal"}:
            raise _static_document.UnsupportedStaticExport(
                "XYG_STATIC_UNSUPPORTED_PANEL_COLORBAR_LAYOUT"
            )
        projected.colorbar_options = {
            "domain": list(domain),
            "colormap": str(colorbar.get("colormap", "viridis")),
            "orientation": orientation,
            "minor_ticks": bool(colorbar.get("minor_ticks")),
            "label": str(colorbar.get("label", "")),
        }
        if colorbar.get("ticks") is not None:
            projected.colorbar_options["ticks"] = [float(value) for value in colorbar["ticks"]]
        anchor = tuple(float(value) for value in colorbar.get("anchor", (0.5, 0.5)))
        if len(anchor) != 2:
            raise _static_document.UnsupportedStaticExport(
                "XYG_STATIC_UNSUPPORTED_PANEL_COLORBAR_LAYOUT"
            )
        projected._static_document_colorbar_layout = (
            float(colorbar.get("shrink", 1.0)),
            anchor[0],
            anchor[1],
        )
        projected._static_document_colorbar_scale = str(colorbar.get("scale", "linear"))
        projected._static_document_colorbar_extend = str(colorbar.get("extend", "neither"))
        projected._static_document_colorbar_pyplot_label = True
        projected._static_document_colorbar_fill_plot = colorbar.get("placement") == "axes"
    projected._static_document_chrome_metrics = (*metrics["x"], *metrics["y"])
    projected._static_document_grid_dash = (
        None
        if all(value is None for value in grid_dash.values())
        and all(value is None for value in grid_dash_minor.values())
        else (
            grid_dash["x"] or 0,
            grid_dash["y"] or 0,
            grid_dash_minor["x"] or 0,
            grid_dash_minor["y"] or 0,
        )
    )
    projected._static_document_annotation_font_size = resolved_annotations.font_size
    projected._static_document_arrow_metrics = next(iter(arrow_metrics), None)
    projected._static_document_panel_legend = panel_legend
    projected._static_document_annotation_text_flags = resolved_annotations.text_flags
    projected._static_document_annotation_padding = resolved_annotations.padding
    projected._static_document_annotation_vertical_align = resolved_annotations.vertical_align
    frame_sides = set(getattr(figure, "frame_sides", ("left", "bottom")))
    projected._static_document_axis_sides = (
        (1 if "bottom" in frame_sides else 0) | (2 if "top" in frame_sides else 0),
        (1 if "left" in frame_sides else 0) | (2 if "right" in frame_sides else 0),
    )
    return projected


def stitch_png(
    charts: list[Any],
    nrows: int,
    ncols: int,
    suptitle: Optional[str],
    colorbar: Optional[dict[str, Any]] = None,
    *,
    suptitle_style: Optional[dict[str, Any]] = None,
    figure_labels: Optional[list[dict[str, Any]]] = None,
    figure_legend: Optional[dict[str, Any]] = None,
    positions: Optional[list[tuple[float, float, float, float]]] = None,
    canvas_size: Optional[tuple[int, int]] = None,
    facecolor: str = "white",
    bbox_tight: bool = False,
    pad_pixels: int = 0,
) -> bytes:
    from xyg import _native

    # pyplot charts are already built at ``figsize * dpi`` logical pixels.
    # Rasterizing those pixels at the core exporter's 2x quality default made
    # savefig silently double both output dimensions and every point-sized
    # artist compared with Matplotlib.  The pyplot compatibility boundary is
    # physical pixels, so keep its raster scale at one; callers that use the
    # native Figure API directly retain that API's explicit 2x default.
    scale = 1.0
    document = _pyplot_static_document(
        charts,
        nrows,
        ncols,
        suptitle,
        suptitle_style,
        figure_labels=figure_labels,
        figure_legend=figure_legend,
        positions=positions,
        canvas_size=canvas_size,
        facecolor=facecolor,
        tight_crop=bbox_tight,
        crop_padding=pad_pixels,
        colorbar=None if positions is not None else colorbar,
    )
    return _native.static_document_export(document, "png", scale=scale)
