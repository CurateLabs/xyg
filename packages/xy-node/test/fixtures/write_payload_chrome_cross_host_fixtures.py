"""Write Python-authoritative payload chrome cross-host golden fixtures.

Produces ``tests/fixtures/payload_chrome_cross_host.json`` consumed by
``tests/test_payload_chrome_cross_host.py``.

Run from repo root::

    uv run python packages/xy-node/test/fixtures/write_payload_chrome_cross_host_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "python"))

from xyg import _native  # noqa: E402
from xyg._figure import Figure  # noqa: E402
from xyg.config import PROTOCOL_VERSION  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "payload_chrome_cross_host.json"

CASE_NAMES = (
    "show_legend_default",
    "show_legend_false",
    "legend_loc_upper_right",
    "legend_loc_best",
    "dom_class_name",
    "dom_style",
    "dom_class_names",
    "chrome_combined",
)


def _build_case(name: str) -> Figure:
    fig = Figure(width=240, height=160)
    if name == "show_legend_false" or name == "chrome_combined":
        fig.show_legend = False
    if name == "legend_loc_upper_right":
        fig.legend_options = {"loc": "upper right", "title": "Series"}
    if name == "legend_loc_best":
        fig.legend_options = {"loc": "best"}
    if name in ("dom_class_name", "chrome_combined"):
        fig.class_name = "root-node"
    if name == "dom_style":
        fig.style = {"width": "100%"}
    if name == "dom_class_names":
        fig.class_names = {"title": "t"}
    if name == "chrome_combined":
        fig.style = {"height": "320px"}
        fig.class_names = {"canvas": "p"}
    fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
    fig.traces[0].id = 7
    return fig


def main() -> None:
    cases = []
    for name in CASE_NAMES:
        spec, _ = _build_case(name).build_payload()
        cases.append(
            {
                "name": name,
                "show_legend": spec["show_legend"],
                "legend": spec.get("legend"),
                "dom": spec.get("dom"),
            }
        )
    payload = {
        "schema": "xyg.payload-chrome-cross-host/v1",
        "authority": "python/xyg/_payload.py build_payload show_legend, legend, and _dom_spec",
        "protocol": PROTOCOL_VERSION,
        "abi_version": int(_native.ABI_VERSION),
        "cases": cases,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
