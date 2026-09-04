"""Write Python-authoritative payload attach cross-host golden fixtures.

Produces ``tests/fixtures/payload_attach_cross_host.json`` consumed by
``tests/test_payload_attach_cross_host.py``.

Run from repo root::

    uv run python packages/xy-node/test/fixtures/write_payload_attach_cross_host_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "python"))

from xyg import _native  # noqa: E402
from xyg._figure import Figure  # noqa: E402
from xyg.config import PROTOCOL_VERSION  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "payload_attach_cross_host.json"

CASE_NAMES = (
    "wasm_density_automatic_split",
    "wasm_density_unsupported_split",
    "frame_sides_bottom_left",
    "show_modebar_false",
    "export_formats",
    "show_tooltip_false",
    "tooltip_fields",
    "mark_style_hover",
    "interaction_select",
    "animation_duration",
    "graph_meta",
    "palette_list",
    "palette_map",
)


def _column_dtype(columns: dict[str, Any] | list[dict[str, Any]], col_ref: Any) -> str | None:
    if col_ref is None:
        return None
    if isinstance(columns, list):
        if not isinstance(col_ref, int) or col_ref < 0 or col_ref >= len(columns):
            return None
        return columns[col_ref].get("dtype")
    return columns.get(col_ref, {}).get("dtype")


def _wasm_density_meta(spec: dict[str, Any]) -> dict[str, Any] | None:
    wasm_density = spec.get("wasm_density")
    if wasm_density is None:
        return None
    source = wasm_density.get("source")
    columns = spec.get("columns") or {}
    source_meta = None
    if source is not None:
        source_meta = {
            "kind": source.get("kind"),
            "point_count": source.get("point_count"),
            "trace_id": source.get("trace_id"),
            "capacity": source.get("capacity"),
            "ownership": source.get("ownership"),
            "x_dtype": _column_dtype(columns, source.get("x")),
            "y_dtype": _column_dtype(columns, source.get("y")),
        }
    return {
        "automatic": wasm_density.get("automatic"),
        "unsupported": wasm_density.get("unsupported"),
        "source": source_meta,
    }


def _attach_entry(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "wasm_density": _wasm_density_meta(spec),
        "frame_sides": spec.get("frame_sides"),
        "show_modebar": spec.get("show_modebar"),
        "export": spec.get("export"),
        "show_tooltip": spec.get("show_tooltip"),
        "tooltip": spec.get("tooltip"),
        "mark_style": spec.get("mark_style"),
        "interaction": spec.get("interaction"),
        "animation": spec.get("animation"),
        "graph": spec.get("graph"),
        "palette": spec.get("palette"),
        "buffer_layout": spec.get("buffer_layout"),
    }


def _build_case(name: str) -> Figure:
    fig = Figure(width=240, height=160)
    if name == "wasm_density_automatic_split":
        fig.scatter([1.0, 10.0], [1.0, 10.0], density=True)
        fig.traces[0].id = 41
        return fig
    if name == "wasm_density_unsupported_split":
        fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5], density=True, color=[1, 2, 3])
        fig.traces[0].id = 42
        return fig
    if name == "frame_sides_bottom_left":
        fig.frame_sides = ["bottom", "left"]
    if name == "show_modebar_false":
        fig.show_modebar = False
    if name == "export_formats":
        fig.export_options = {"formats": ["png", "svg"]}
    if name == "show_tooltip_false":
        fig.show_tooltip = False
    if name == "tooltip_fields":
        fig.tooltip = {
            "fields": ["x", "y"],
            "title": "{x}",
            "format": {"x": ".2f"},
        }
    if name == "mark_style_hover":
        fig.set_mark_style(hover={"color": "#111111", "size": 10})
    if name == "interaction_select":
        fig.set_interaction(select=True)
    if name == "animation_duration":
        fig.animation_options = {"enabled": True, "duration": 250.0}
    if name == "graph_meta":
        fig._graph_meta = [{"layout": "force", "node_trace": 0, "edge_trace": 1}]  # noqa: SLF001
    if name == "palette_list":
        fig.palette = ["#ff0000", "#00ff00", "#0000ff"]
    if name == "palette_map":
        fig.palette = {"a": "#ff0000", "b": "#00ff00", "c": "#0000ff"}
    fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
    fig.traces[-1].id = 7
    return fig


def _build_case_payload(name: str) -> dict[str, Any]:
    fig = _build_case(name)
    if name.startswith("wasm_density_"):
        spec, _ = fig.build_payload_split(wasm_source=name == "wasm_density_automatic_split")
    else:
        spec, _ = fig.build_payload()
    return {"name": name, **_attach_entry(spec)}


def main() -> None:
    cases = [_build_case_payload(name) for name in CASE_NAMES]
    payload = {
        "schema": "xyg.payload-attach-cross-host/v1",
        "authority": (
            "python/xyg/_payload.py build_payload ABI 303 attach flags "
            "(wasm_density, frame_sides, tooltip, mark_style, interaction, export, "
            "show_modebar, show_tooltip, animation, graph, palette)"
        ),
        "protocol": PROTOCOL_VERSION,
        "abi_version": int(_native.ABI_VERSION),
        "cases": cases,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
