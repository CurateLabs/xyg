"""Apply ``payload_build_plan`` optional fields to a compiled payload spec."""

from __future__ import annotations

from typing import Any

import numpy as np

from . import kernels
from ._payload_writer import PayloadWriter


def attach_build_plan_fields(
    spec: dict[str, Any],
    figure: Any,
    pw: PayloadWriter,
    build_plan: dict[str, Any],
    *,
    spec_traces: list[dict[str, Any]],
    wasm_sources: list[Any],
    dom: Any,
    legend_opts: Any,
    mark_style: Any,
    interaction_spec: Any,
    annotations: Any,
) -> None:
    """Mutate ``spec`` with optional top-level attach fields from ABI 303."""
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
            for entry in figure.title_options
        ]
    if build_plan["attach_coords"]:
        spec["coords"] = figure.coords
    if build_plan["attach_palette"]:
        spec["palette"] = figure.palette_cycle
    if build_plan["attach_legend"]:
        legend = legend_opts
        if build_plan["resolve_legend_best"]:
            from ._legendfit import resolve_for_figure

            legend = {**legend, "loc": resolve_for_figure(figure)}
        spec["legend"] = legend
    if build_plan["attach_extra_legends"]:
        spec["extra_legends"] = getattr(figure, "extra_legends", None)
    if build_plan["attach_frame_sides"]:
        spec["frame_sides"] = list(figure.frame_sides)
    if build_plan["attach_colorbar"]:
        spec["colorbar"] = figure.colorbar_options
    if build_plan["attach_show_modebar"]:
        spec["show_modebar"] = False
    if build_plan["attach_export"]:
        spec["export"] = getattr(figure, "export_options", None)
    if build_plan["attach_show_tooltip"]:
        spec["show_tooltip"] = False
    if build_plan["attach_padding"]:
        spec["padding"] = list(figure.padding)
    if build_plan["attach_dom"]:
        spec["dom"] = dom
    if build_plan["attach_tooltip"]:
        spec["tooltip"] = figure.tooltip
    if build_plan["attach_mark_style"]:
        spec["mark_style"] = mark_style
    if build_plan["attach_interaction"]:
        spec["interaction"] = interaction_spec
    if build_plan["attach_annotations"]:
        spec["annotations"] = annotations
    if build_plan["attach_animation"]:
        spec["animation"] = dict(figure.animation_options)
    if build_plan["attach_graph"]:
        spec["graph"] = list(getattr(figure, "_graph_meta", None) or [])
