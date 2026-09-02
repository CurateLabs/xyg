"""Thin figure-to-Scene v12 compiler for the migrated core-mark subset.

Rust owns mapping, clipping, record semantics, SVG construction, and raster
display-list construction. This module only projects already-validated Figure
objects into the typed ABI and rejects features whose canonical Scene record
does not exist yet.
"""

from __future__ import annotations

import struct
from typing import Any

from . import _native
from ._scene_annotations import (
    annotation_allowed_style as _annotation_allowed_style,  # noqa: F401
)
from ._scene_annotations import (
    colorbar_input as _colorbar_input,
)
from ._scene_annotations import (
    pack_xyaf as _pack_xyaf,  # noqa: F401
)
from ._scene_annotations import (
    pack_xyaf_bulk as _pack_xyaf_bulk,
)
from ._scene_errors import (
    raise_annotation_splice as _raise_annotation_splice,
)
from ._scene_errors import (
    raise_trace_attach as _raise_trace_attach,
)
from ._scene_errors import (
    raise_trace_compile as _raise_trace_compile,
)
from ._scene_errors import (
    raise_trace_rows as _raise_trace_rows,
)
from ._scene_errors import (
    raise_trace_sidecars as _raise_trace_sidecars,
)
from ._scene_marshal import pack_public_export_support as _pack_public_export_support

# Re-export observation helpers for existing imports (tests, scripts).
from ._scene_observations import (  # noqa: F401
    _ANNOTATION_TYPOGRAPHY_STYLE_KEYS,
    _POLAR_COLLISION_KEYS,
    _SCENE_AXIS_STYLE_KEYS,
    UnsupportedSceneV3,
    _admitted_fill_gradient,
    _admitted_fill_gradient_from_fill,
    _annotation_has_custom_typography,
    _annotation_has_markup,
    _channel_constant_css,
    _channel_end_rgba8,
    _classify_ribbon_color2,
    _colormap_stop_bytes,
    _constant_color,
    _density_aggregates_color,
    _fill_is_gradient_authoring,
    _heatmap_extent,
    _heatmap_grid_values,
    _heatmap_shape,
    _hexbin_cell_rgba8,
    _hexbin_count,
    _hexbin_packs_colormap_plane,
    _hexbin_packs_paint_plane,
    _hexbin_packs_rgba_plane,
    _hexbin_pitch,
    _item_apply_opacity,
    _item_fill_rgba8,
    _item_stroke_rgba8,
    _mesh_count,
    _mesh_joined_fill,
    _mesh_packs_paint_plane,
    _parse_scene_dash,
    _ribbon_color2_class_code,
    _ribbon_count,
    _ribbon_end_rgba_pair,
    _ribbon_packs_end_paints,
    _scatter_count,
    _scatter_packs_paint_plane,
    _scene_side_mask,
    _scene_tick_label_strategy,
    _significant_scene_axis_keys,
    _trace_column,
    _trace_source_color_css,
    _xyta_hexbin_plane_observations,
)
from ._scene_sidecars import (
    _XYFS_TRACE_CORNER_RADIUS,  # noqa: F401
    _XYFS_TRACE_RECT_GRADIENT,  # noqa: F401
    _XYFS_TRACE_WEDGE_GAP,  # noqa: F401
)
from ._scene_sidecars import (
    pack_gradient_spec as _pack_gradient_spec,  # noqa: F401
)
from ._scene_sidecars import (
    pack_marker_blob as _pack_marker_blob,  # noqa: F401
)
from ._scene_sidecars import (
    pack_xycl as _pack_xycl,
)
from ._scene_sidecars import (
    pack_xynm as _pack_xynm,
)
from ._scene_sidecars import (
    pack_xyta_colormap as _pack_xyta_colormap,  # noqa: F401
)
from ._scene_sidecars import (
    parse_scene_linecap as _parse_scene_linecap,  # noqa: F401
)
from ._scene_sidecars import (
    rect_extra_flags as _rect_extra_flags,  # noqa: F401
)
from ._scene_unpack import (  # noqa: F401
    _unpack_gradient_blob,
    _unpack_marker_blob,
    _unpack_xyas,
    _unpack_xycc,
    _xycc_tick_labels,
)

_XYTC_HEADER = struct.Struct("<4sIII")
_XYTA_HEADER = struct.Struct("<4sIII")


def _scene_tick_anchor_code(options: dict[str, Any]) -> int | None:
    raw = options.get("tick_label_anchor")
    if raw is None:
        return None
    return _native.scene_tick_anchor(str(raw))


def _scene_chrome_style(figure: Any) -> bytes:
    """Pack authored chrome literals; Rust owns the 200-byte Scene style."""
    from ._scene_marshal import scene_chrome_style

    return scene_chrome_style(figure)


def _pack_chrome_facts(
    figure: Any,
    *,
    width: int,
    height: int,
    margins: tuple[float, float, float, float] | None,
    colorbar_ok: bool,
) -> bytes:
    """Marshal chrome observations and bulk-pack XYCF via Rust (ABI 321)."""
    from ._scene_marshal import pack_chrome_facts

    return pack_chrome_facts(
        figure,
        width=width,
        height=height,
        margins=margins,
        colorbar_ok=colorbar_ok,
    )


def _marshal_xyta_trace_record(trace: Any, figure: Any, *, polar: bool) -> bytes:
    """Marshal one attach trace and pack an XYTA record via Rust (ABI 323→318)."""
    from xyg._scene_marshal import marshal_xyta_trace_obs

    obs = marshal_xyta_trace_obs(trace, figure, polar=polar)
    materialized = _native.scene_xyta_trace_observations_materialize(obs)
    return _native.scene_xyta_trace_pack(**materialized)


def _pack_xyta(figure: Any) -> bytes:
    """Pack authored heatmap/density attach facts as XYTA v1; Rust emits XYTT."""
    traces = list(getattr(figure, "traces", None) or [])
    records = bytearray(_XYTA_HEADER.pack(b"XYTA", 1, len(traces), 0))
    figure_plan = _native.scene_xyta_figure_plan(
        polar=str(getattr(figure, "coords", "cartesian") or "cartesian") == "polar"
    )
    polar = figure_plan["polar"]
    for trace in traces:
        records.extend(_marshal_xyta_trace_record(trace, figure, polar=polar))
    return bytes(records)


def _marshal_xytc_trace_record(trace: Any, *, show_legend: bool) -> bytes:
    """Marshal one trace and pack an XYTR record via Rust (ABI 317)."""
    from xyg._scene_marshal import marshal_xytc_trace_obs

    obs = marshal_xytc_trace_obs(trace, show_legend=show_legend)
    materialized = _native.scene_xytc_trace_observations_materialize(obs)
    return _native.scene_xytc_trace_pack(**materialized)


def _pack_xytc(figure: Any) -> bytes:
    """Pack authored per-trace style literals as XYTC v1; Rust compiles XYTO."""
    traces = list(getattr(figure, "traces", None) or [])
    records = bytearray(_XYTC_HEADER.pack(b"XYTC", 1, len(traces), 0))
    figure_plan = _native.scene_xytc_figure_plan(
        show_legend=bool(getattr(figure, "show_legend", True))
    )
    show_legend = figure_plan["show_legend"]
    for trace in traces:
        records.extend(_marshal_xytc_trace_record(trace, show_legend=show_legend))
    return bytes(records)


def figure_scene(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
    margins: tuple[float, float, float, float] | None = None,
) -> bytes:
    """Compile migrated cartesian marks plus x/y axes to Scene v12."""
    annotations = list(getattr(figure, "annotations", None) or [])
    colorbar_unsupported = False
    try:
        _colorbar_input(figure)
    except UnsupportedSceneV3:
        colorbar_unsupported = True

    polar = str(getattr(figure, "coords", "cartesian") or "cartesian") == "polar"
    attach_plan = _native.scene_encode_product_attach_plan(polar=polar)

    # Hosts pack XYTC, XYTA, XYNM, XYCL, XYAF, XYCF, polar, and XYFS; Rust owns
    # compile, attach, sidecars, rows, annotation facts, style sidecars,
    # splice, XYCC/extras packing, viewport/axis scalars, assembled encode,
    # and the figure-compile support probe (ABI 165). Earlier ABIs 148–164
    # remain available for tests. Empty XYFS skips the probe.
    x_span = tuple(float(value) for value in figure._range("x"))
    y_span = tuple(float(value) for value in figure._range("y"))
    x_domain = (x_span[0], x_span[1])
    y_domain = (y_span[0], y_span[1])
    annotation_facts = _pack_xyaf_bulk(annotations)
    w = int(width if width is not None else figure.width)
    h = int(height if height is not None else figure.height)
    try:
        return _native.scene_encode_product(
            compile_facts=_pack_xytc(figure),
            attach_facts=_pack_xyta(figure),
            names=_pack_xynm(figure),
            columns=_pack_xycl(figure),
            annotation_facts=annotation_facts,
            style_ref_base=len(figure.traces),
            x_domain=x_domain,
            y_domain=y_domain,
            chrome_facts=_pack_chrome_facts(
                figure,
                width=w,
                height=h,
                margins=margins,
                colorbar_ok=not colorbar_unsupported,
            ),
            polar=_pack_polar_scene_input(figure) if attach_plan["attach_xypl"] else b"",
            figure_support=_pack_figure_support(figure, annotations, colorbar_unsupported),
        )
    except _native.SceneFigureSupportError as error:
        raise UnsupportedSceneV3(str(error)) from error
    except _native.SceneTraceCompileError as error:
        _raise_trace_compile(error, figure)
    except _native.SceneTraceAttachError as error:
        _raise_trace_attach(error, figure)
    except _native.SceneTraceSidecarsError as error:
        _raise_trace_sidecars(error)
    except _native.SceneTraceRowsError as error:
        _raise_trace_rows(error)
    except _native.SceneAnnotationFactsError as error:
        raise UnsupportedSceneV3(str(error)) from error
    except _native.SceneStyleSidecarsError as error:
        if error.code == -2:
            raise ValueError("invalid scene style sidecar facts version") from error
        raise ValueError("invalid scene style sidecar packing") from error
    except _native.SceneAnnotationSpliceError as error:
        _raise_annotation_splice(error)
    except _native.SceneEncodeAssembledError as error:
        raise ValueError("invalid canonical scene batch") from error
    except ValueError as error:
        message = str(error)
        if message.startswith(("Scene v12 ", "Scene v19 ")):
            raise UnsupportedSceneV3(message) from error
        raise


def figure_svg(figure: Any, **options: Any) -> str:
    return _native.scene_svg(figure_scene(figure, **options))


def figure_raster_commands(figure: Any, *, scale: float = 1.0, **options: Any) -> bytes:
    return _native.scene_raster_commands(figure_scene(figure, **options), scale)


def public_static_export(
    figure: Any,
    format: str,
    *,
    width: int | None = None,
    height: int | None = None,
    scale: float = 1.0,
    quality: int | None = None,
) -> bytes | None:
    """Render one supported public static format from the canonical Scene.

    This is the only selection seam for the migrated public SVG/PNG/PDF/JPEG/WebP
    subset.  It returns ``None`` only after the explicit support predicate
    selects compatibility *before* Scene compilation.  Once selected, every
    compiler or consumer error propagates: it is never a request to retry a
    compatibility renderer. The router reuses the predicate's compiled batch
    rather than compiling a second Scene for SVG, raster, or PDF consumers.
    Format dispatch is ABI 164 ``scene_static_export``. Explicit Scene callers
    still use ``figure_svg`` / ``figure_raster_commands``.
    """
    reason, scene = _public_scene_or_reason(figure, width=width, height=height)
    if reason is not None or scene is None:
        return None
    w = int(width if width is not None else figure.width)
    h = int(height if height is not None else figure.height)
    width_px = max(1, int(round(w * float(scale))))
    height_px = max(1, int(round(h * float(scale))))
    return _native.scene_static_export(
        scene,
        format,
        scale=scale,
        width=width_px,
        height=height_px,
        quality=90 if quality is None else int(quality),
    )


def _pack_polar_scene_input(figure: Any) -> bytes:
    """Marshal polar axis literals and pack XYPL via Rust (ABI 322)."""
    from ._scene_marshal import pack_polar_scene_input

    return pack_polar_scene_input(figure)


def _pack_figure_support(
    figure: Any,
    annotations: list[Any],
    colorbar_unsupported: bool,
) -> bytes:
    """Marshal figure support observations and materialize XYFS via Rust (ABI 322)."""
    from ._scene_marshal import pack_figure_support

    return pack_figure_support(figure, annotations, colorbar_unsupported)


def _public_scene_or_reason(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
) -> tuple[str | None, bytes | None]:
    """Compile the public Scene once, or return the support diagnostic.

    The predicate must still compile so it cannot disagree with the encoder.
    Product routers reuse the compiled batch instead of encoding a second time.
    """
    envelope = _pack_public_export_support(figure, width=width, height=height)
    reason = _native.scene_public_export_reason(envelope)
    if reason:
        return reason, None
    try:
        scene = figure_scene(figure, width=width, height=height)
    except UnsupportedSceneV3 as unsupported:
        if str(unsupported) == "invalid canonical scene plot layout":
            return "XYG_SCENE_UNSUPPORTED_VIEWPORT", None
        return str(unsupported), None
    except ValueError as exc:
        if str(exc) == "invalid canonical scene plot layout":
            return "XYG_SCENE_UNSUPPORTED_VIEWPORT", None
        raise
    return None, scene


def scene_export_support_reason(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
) -> str | None:
    """Return why a figure cannot compile to the canonical Rust Scene, or ``None``.

    This is the single support predicate the #117 public static-export router
    consults before selecting the Rust Scene path over the compatibility
    ``_svg`` / ``_raster`` renderers. It reports the stable
    ``XYG_SCENE_UNSUPPORTED_*`` diagnostic (or the compiler's own bounded
    message) so callers can log or surface an actionable reason for the fallback.

    Hosts pack authored XYEF facts (viewport flags, keys, axis codes, and
    column observations). Rust owns XYEP layout, kind/step/annotation codes,
    flag derivation, allowlists, check order, the public PolyFill group budget,
    and diagnostic wording. After that preflight the predicate still compiles
    the Scene so it cannot disagree with the encoder. ``public_static_export``
    and facet SVG/raster reuse that compiled batch rather than compiling a second
    Scene.
    """
    return _public_scene_or_reason(figure, width=width, height=height)[0]
