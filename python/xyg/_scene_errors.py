"""Map Rust Scene encode errors to host-facing Python exceptions."""

from __future__ import annotations

from typing import Any, NoReturn

from . import _native
from ._scene_observations import UnsupportedSceneV3


def raise_trace_compile(error: _native.SceneTraceCompileError, figure: Any) -> NoReturn:
    traces = list(getattr(figure, "traces", None) or [])
    trace = traces[error.index] if 0 <= error.index < len(traces) else None
    style = getattr(trace, "style", None) or {} if trace is not None else {}
    if error.code == -5:
        raise ValueError("trace opacity must be finite and in [0, 1]") from error
    if error.code == -12:
        raise ValueError("trace opacity channels must be finite and in [0, 1]") from error
    if error.code == -6:
        symbol = str(style.get("symbol", "circle"))
        raise UnsupportedSceneV3(f"Scene v12 does not support scatter symbol {symbol!r}") from error
    if error.code == -7:
        raise UnsupportedSceneV3(
            f"Scene v12 does not support step mode {style.get('step')!r}"
        ) from error
    if error.code == -8:
        raise UnsupportedSceneV3("Scene v25 area stroke_perimeter must be a boolean") from error
    if error.code == -9:
        raise UnsupportedSceneV3(
            "Scene v12 hexbin requires finite hex_dx/hex_dy cell pitch"
        ) from error
    if error.code == -10:
        raise UnsupportedSceneV3(
            "Scene v12 does not yet encode two-ended ribbon gradients"
        ) from error
    if error.code == -11:
        kind = getattr(trace, "kind", "mark") if trace is not None else "mark"
        raise UnsupportedSceneV3(f"Scene v12 does not yet encode {kind} non-CSS fills") from error
    if error.code == -13:
        raise UnsupportedSceneV3(
            "Scene v12 does not yet support data-driven paint channels"
        ) from error
    if error.code == -2:
        raise ValueError("invalid scene trace compile facts version") from error
    raise ValueError("invalid scene trace compile packing") from error


def raise_trace_attach(error: _native.SceneTraceAttachError, figure: Any) -> NoReturn:
    if error.code == -5:
        raise UnsupportedSceneV3("Scene v12 heatmap requires a rows x cols grid_shape") from error
    if error.code == -6:
        raise UnsupportedSceneV3("Scene v12 heatmap requires a positive grid_shape") from error
    if error.code == -7:
        raise ValueError("heatmap Scene v12 compilation requires a scalar grid") from error
    if error.code == -8:
        raise UnsupportedSceneV3("Scene v12 heatmap grid must match rows x cols") from error
    if error.code == -9:
        raise UnsupportedSceneV3(
            "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
        ) from error
    if error.code == -10:
        raise UnsupportedSceneV3("Scene heatmap RGBA plane must match rows x cols") from error
    if error.code == -11:
        raise UnsupportedSceneV3("Scene heatmap truecolor requires four RGBA planes") from error
    if error.code == -12:
        traces = list(getattr(figure, "traces", None) or [])
        trace = traces[error.index] if 0 <= error.index < len(traces) else None
        label = "density" if getattr(trace, "kind", None) == "scatter" else "heatmap"
        raise UnsupportedSceneV3(f"Scene {label} colormap requires RGB stops") from error
    if error.code == -13:
        raise ValueError("Scene density columns must have equal length") from error
    if error.code == -14:
        raise ValueError("Scene density mean-color source is invalid") from error
    if error.code == -2:
        raise ValueError("invalid scene trace attach facts version") from error
    raise ValueError("invalid scene trace attach packing") from error


def raise_trace_rows(error: _native.SceneTraceRowsError) -> NoReturn:
    if error.code == -5:
        raise UnsupportedSceneV3(
            "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
        ) from error
    if error.code == -6:
        raise UnsupportedSceneV3("Scene v12 does not support product kind") from error
    if error.code == -1:
        raise UnsupportedSceneV3("invalid scene trace packing") from error
    if error.code == -2:
        raise ValueError("invalid scene trace column facts version") from error
    raise ValueError("invalid scene trace column packing") from error


def raise_trace_sidecars(error: _native.SceneTraceSidecarsError) -> NoReturn:
    if error.code == -2:
        raise ValueError("invalid scene sidecar facts version") from error
    raise ValueError("invalid scene sidecar packing") from error


def raise_annotation_splice(error: _native.SceneAnnotationSpliceError) -> NoReturn:
    if error.code == -2:
        raise ValueError("invalid scene annotation splice version") from error
    raise ValueError("invalid scene annotation splice packing") from error
