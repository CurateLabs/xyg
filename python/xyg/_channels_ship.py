"""Channel wire encode and payload ship registry."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import numpy.typing as npt

from . import _channels_labels as _labels
from . import _validate, config, kernels
from ._channels_lut import categorical_palette
from ._channels_types import ColorChannel, SizeChannel, StyleChannel

_finite_scalar = _validate.finite_scalar
_as_real_array = _labels._as_real_array


def _wire_encode_plan(
    role: str,
    mode: str,
    *,
    n_categories: int = 0,
    style_dtype_u8: bool = False,
    quantize_continuous: bool = False,
) -> dict[str, bool | str]:
    """Rust-owned buffer/transform policy for ``channels.ship_*`` (ABI 312)."""
    return kernels.payload_channel_wire_encode(
        role,
        mode,
        n_categories=n_categories,
        style_dtype_u8=style_dtype_u8,
        quantize_continuous=quantize_continuous,
    )


def _ship_wire_buffer(
    plan: dict[str, bool | str],
    ship_scalar: Any,
    ship_u8: Any,
    *,
    vals: Optional[npt.NDArray[np.float64]] = None,
    domain: Optional[tuple[float, float]] = None,
    packed_rgba: Optional[npt.NDArray[np.uint8]] = None,
    raw: Optional[np.ndarray] = None,
    sel: Any = None,
    role: str = "color",
    mode: str = "continuous",
    n_categories: int = 0,
    n_palette: int = 0,
) -> Any:
    """Apply the ABI 312 transform via ``payload_channel_materialize`` (ABI 320)."""
    transform = plan["transform"]
    if transform == "none":
        return None
    sel_arr = None if sel is None else np.asarray(sel, dtype=np.uint32)
    if transform == "rgba_pack":
        if packed_rgba is None:
            raise ValueError("direct RGBA wire encode missing packed values")
        rgba = np.ascontiguousarray(packed_rgba, dtype=np.float64).reshape(-1)
        if rgba.size and rgba.max(initial=0.0) > 1.0:
            rgba = rgba / 255.0
        materialized = kernels.payload_channel_materialize(
            role=role,
            mode="direct_rgba",
            n_categories=0,
            style_dtype_u8=False,
            quantize_continuous=False,
            domain=(0.0, 1.0),
            n_palette=0,
            sel=sel_arr,
            values_f64=rgba,
            values_u8=None,
        )
    elif transform in {"quantize_u8", "normalize"}:
        if vals is None or domain is None:
            raise ValueError("continuous wire encode missing values or domain")
        materialized = kernels.payload_channel_materialize(
            role=role,
            mode=mode,
            n_categories=n_categories,
            style_dtype_u8=False,
            quantize_continuous=transform == "quantize_u8",
            domain=domain,
            n_palette=n_palette,
            sel=sel_arr,
            values_f64=vals,
            values_u8=None,
        )
    elif transform == "raw":
        if raw is None:
            raise ValueError("raw wire encode missing values")
        materialized = kernels.payload_channel_materialize(
            role=role,
            mode=mode,
            n_categories=n_categories,
            style_dtype_u8=bool(plan.get("mark_dtype_u8", False)),
            quantize_continuous=False,
            domain=(0.0, 1.0),
            n_palette=n_palette,
            sel=sel_arr,
            values_f64=raw.astype(np.float64, copy=False) if raw.dtype != np.uint8 else None,
            values_u8=raw.astype(np.uint8, copy=False) if raw.dtype == np.uint8 else None,
        )
    else:
        raise ValueError("invalid payload_channel_wire_encode transform")
    if materialized["buf_kind"] == 0:
        return None
    enc = np.frombuffer(
        materialized["bytes"],
        dtype=np.uint8 if plan["buf_kind"] == "u8" else np.float32,
    )
    if plan["buf_kind"] == "u8":
        return ship_u8(enc)
    return ship_scalar(enc)


def ship_registry_attach(
    entry: dict[str, Any],
    trace: Any,
    sel: Any,
    ship_scalar: Any,
    ship_u8: Any,
    plan: dict[str, Any],
) -> None:
    """Attach channels listed in a Rust-owned ship registry plan (ABI 311).

    Hosts call ``payload_channel_ship_plan`` for policy; this function
    materializes the listed rows via ``ship_*`` using ABI 312 wire encode."""
    for ch in plan["channels"]:
        key = ch["registry_key"]
        method = ch["ship_method"]
        if method == "color_size":
            entry["color"], entry["size"] = ship_channels(trace, sel, ship_scalar, ship_u8)
        elif method == "color":
            channel = getattr(trace, ch["trace_slot"])
            entry[key] = ship_color_channel(channel, sel, ship_scalar, ship_u8)
        elif method == "style":
            entry[key] = ship_style_channels(trace.style_channels, sel, ship_scalar, ship_u8)


def ship_channels(
    trace: Any,
    sel: Any,
    ship_scalar: Any,
    ship_u8: Any,
    *,
    quantize_continuous: bool = False,
) -> tuple[Any, Any]:
    """Ship a trace's color and size channels in the standard wire shape
    (design dossier §29/§36c): per-point channels carry a `buf` index into the blob; constant
    channels ship spec-only. Used by the build path and by drill-in view
    updates for any chart kind with per-mark channels.

    Slices *before* normalizing: normalization is element-wise over a
    precomputed global domain, and drill updates call this per zoom step —
    normalizing all N rows to ship a 200k window is O(N) work for nothing.

    `quantize_continuous` ships continuous color/size as u8 LUT coordinates
    (`dtype: "u8"` marker) instead of unit f32. Live-interaction paths opt in:
    their hover/pick answers come from the server's canonical columns, so the
    quantization is invisible. The build path must NOT opt in — the client keeps
    the shipped columns CPU-side and denormalizes them for tooltip readouts,
    where 8-bit steps would show as wrong digits.
    Returns (color_spec, size_spec)."""
    cc = trace.color_ch or ColorChannel(mode="constant", constant=None)
    color_spec = ship_color_channel(
        cc, sel, ship_scalar, ship_u8, quantize_continuous=quantize_continuous
    )
    sc = trace.size_ch or SizeChannel(mode="constant")
    size_spec = sc.spec()
    if sc.mode == "continuous":
        values = sc.values
        domain = sc.domain
        if values is None or domain is None:
            raise ValueError("continuous size channel missing values or domain")
        vals = values if sel is None else values[sel]
        plan = _wire_encode_plan(
            "size",
            sc.mode,
            quantize_continuous=quantize_continuous,
        )
        size_spec["buf"] = _ship_wire_buffer(plan, ship_scalar, ship_u8, vals=vals, domain=domain)
        if plan["mark_dtype_u8"]:
            size_spec["dtype"] = "u8"
    return color_spec, size_spec


def resolve_direct_rgba(cc: ColorChannel) -> ColorChannel:
    """Sample a LUT-encoded color channel down to per-item RGBA, CPU-side.

    For marks that ship **resolved paints only**. The ribbon program binds two
    per-instance RGBA attributes (one per band end) and has no LUT path —
    `a_rgba2` shares its attribute slot with `a_style`, so the cval/LUT route
    physically cannot coexist with the two-ended gradient. Resolving here keeps
    the numeric `color=` encodings of the mark signature working and makes the
    renderers agree by construction: continuous values run through the same
    ``normalize_to_unit`` + ``kernels.colormap_lut`` chain the static exporters
    apply to the shipped buffer, and categorical codes index the same
    ``palette_rows_rgba8`` table, so the resolved bytes match what the exporters
    computed for themselves before this existed. Only sensible on small-N
    direct-tier marks, where four bytes per item is noise.
    """
    if cc.mode == "continuous":
        if cc.values is None or cc.domain is None:
            raise ValueError("continuous color channel missing values or domain")
        rgba = kernels.color_channel_direct_rgba_f64_continuous(cc.values, cc.domain, cc.colormap)
        return ColorChannel(mode="direct_rgba", rgba=rgba)
    if cc.mode == "categorical":
        if cc.codes is None:
            raise ValueError("categorical color channel missing codes")
        palette = list(cc.palette or config.DEFAULT_PALETTE)
        rgba = kernels.color_channel_direct_rgba_f64_categorical(cc.codes, palette)
        return ColorChannel(mode="direct_rgba", rgba=rgba)
    return cc


def ship_color_channel(
    cc: ColorChannel,
    sel: Any,
    ship_scalar: Any,
    ship_u8: Any,
    *,
    quantize_continuous: bool = False,
) -> dict[str, Any]:
    """Ship one fill/stroke paint channel in the common wire representation."""
    color_spec = cc.spec()
    plan = _wire_encode_plan(
        "color",
        cc.mode,
        n_categories=len(cc.categories or []),
        quantize_continuous=quantize_continuous,
    )
    if plan["transform"] == "none":
        return color_spec
    if cc.mode == "direct_rgba":
        rgba = cc.rgba
        if rgba is None:
            raise ValueError("direct RGBA color channel missing values")
        values = rgba if sel is None else rgba[sel]
        if values.dtype != np.uint8:
            values = np.ascontiguousarray((np.clip(values, 0.0, 1.0) * 255.0).astype(np.uint8))
        packed_rgba = np.ascontiguousarray(values, dtype=np.uint8)
        color_spec["buf"] = _ship_wire_buffer(
            plan,
            ship_scalar,
            ship_u8,
            packed_rgba=packed_rgba,
            sel=None,
            role="color",
            mode="direct_rgba",
        )
    elif cc.mode == "continuous":
        values = cc.values
        domain = cc.domain
        if values is None or domain is None:
            raise ValueError("continuous color channel missing values or domain")
        vals = values if sel is None else values[sel]
        color_spec["buf"] = _ship_wire_buffer(
            plan,
            ship_scalar,
            ship_u8,
            vals=vals,
            domain=domain,
            sel=None,
            role="color",
            mode="continuous",
        )
    elif cc.mode == "categorical":
        code_values = cc.codes
        categories = cc.categories
        if code_values is None or categories is None:
            raise ValueError("categorical color channel missing codes or categories")
        codes = code_values if sel is None else code_values[sel]
        color_spec["buf"] = _ship_wire_buffer(
            plan,
            ship_scalar,
            ship_u8,
            raw=codes,
            sel=None,
            role="color",
            mode="categorical",
            n_categories=len(categories),
            n_palette=len(categories),
        )
        if plan["ship_palette"]:
            color_spec["palette"] = categorical_palette(cc.colors, len(categories))
    else:
        raise ValueError(f"unsupported color channel mode for wire encode: {cc.mode}")
    if plan["mark_dtype_u8"]:
        color_spec["dtype"] = "u8"
    if plan["set_n"]:
        if cc.mode == "direct_rgba":
            color_spec["n"] = int(len(values))
        else:
            raise ValueError("wire encode set_n without direct_rgba color channel")
    return color_spec


def ship_style_channels(
    style_channels: dict[str, StyleChannel], sel: Any, ship_scalar: Any, ship_u8: Any
) -> dict[str, Any]:
    """Ship direct style channels after applying the geometry row selection."""
    result: dict[str, Any] = {}
    for name, channel in style_channels.items():
        values = channel.values if sel is None else channel.values[sel]
        values = np.ascontiguousarray(values, dtype=np.float64).reshape(-1)
        spec = channel.spec()
        plan = _wire_encode_plan("style", "direct", style_dtype_u8=channel.dtype == "u8")
        spec["buf"] = _ship_wire_buffer(
            plan, ship_scalar, ship_u8, raw=values, role="style", mode="direct"
        )
        if plan["set_n"]:
            spec["n"] = int(len(values))
        result[name] = spec
    return result
