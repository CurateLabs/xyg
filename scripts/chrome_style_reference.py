#!/usr/bin/env python3
"""Reproducible Matplotlib reference for XYG chrome slot customization (#1004).

Renders the same title / axis-title / tick-label customization through XYG's
native SVG export and Matplotlib's SVG backend (text kept as text), then
records the resolved text decisions of both next to the environment. The
contract is the *decision* (size, weight, style, paint), not pixel identity:
XYG keeps its fixed DejaVu-metric font, as documented.

    uv run --with matplotlib python scripts/chrome_style_reference.py --write
    uv run --with matplotlib python scripts/chrome_style_reference.py   # check
"""

from __future__ import annotations

import argparse
import io
import json
import platform
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import xyg  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "spec" / "benchmarks" / "chrome-style-reference-1004.json"

#: One customization, spelled once per library: (title, axis title, tick label).
AUTHORED = {
    "title": {"size": 20, "weight": "bold", "style": "normal", "color": "#102030"},
    "axis_title": {"size": 16, "weight": "normal", "style": "italic", "color": "#ff0000"},
    "tick_label": {"size": 10, "weight": "bold", "style": "normal", "color": "#00aa00"},
}


def _xyg_svg() -> str:
    def css(slot: dict[str, object]) -> dict[str, str]:
        out = {"font-size": f"{slot['size']}px", "color": str(slot["color"])}
        if slot["weight"] != "normal":
            out["font-weight"] = str(slot["weight"])
        if slot["style"] != "normal":
            out["font-style"] = str(slot["style"])
        return out

    chart = xyg.chart(
        xyg.line([0, 1], [0, 1]),
        xyg.x_axis(domain=(0, 1), label="X"),
        xyg.y_axis(domain=(0, 1), label="Y"),
        styles={slot: css(style) for slot, style in AUTHORED.items()},
        title="Title",
        width=320,
        height=240,
    )
    return chart.to_svg()


def _matplotlib_svg() -> str:
    plt.rcParams["svg.fonttype"] = "none"
    fig, ax = plt.subplots(figsize=(320 / 72, 240 / 72), dpi=72)
    ax.plot([0, 1], [0, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    spec = AUTHORED
    ax.set_title(
        "Title",
        fontsize=spec["title"]["size"],
        fontweight=spec["title"]["weight"],
        fontstyle=spec["title"]["style"],
        color=spec["title"]["color"],
    )
    for setter, text in ((ax.set_xlabel, "X"), (ax.set_ylabel, "Y")):
        setter(
            text,
            fontsize=spec["axis_title"]["size"],
            fontweight=spec["axis_title"]["weight"],
            fontstyle=spec["axis_title"]["style"],
            color=spec["axis_title"]["color"],
        )
    tick = spec["tick_label"]
    ax.tick_params(labelsize=tick["size"], labelcolor=tick["color"])
    for label in (*ax.get_xticklabels(), *ax.get_yticklabels()):
        label.set_fontweight(tick["weight"])
    buffer = io.BytesIO()
    fig.savefig(buffer, format="svg")
    plt.close(fig)
    return buffer.getvalue().decode()


def _xyg_decisions(svg: str) -> dict[str, dict[str, object]]:
    found = {}
    for match in re.finditer(r"<text ([^>]*)>([^<]*)</text>", svg):
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', match.group(1)))
        rgba = re.match(r"rgba\((\d+),(\d+),(\d+),", attrs.get("fill", ""))
        found[match.group(2)] = {
            "size": float(attrs["font-size"]),
            "weight": "bold" if attrs.get("font-weight") == "700" else "normal",
            "style": attrs.get("font-style", "normal"),
            "color": "#" + "".join(f"{int(v):02x}" for v in rgba.groups()) if rgba else None,
        }
    return found


def _matplotlib_decisions(svg: str) -> dict[str, dict[str, object]]:
    found = {}
    for match in re.finditer(r'<text style="([^"]*)"[^>]*>([^<]*)</text>', svg):
        style = dict(
            part.strip().split(": ", 1) for part in match.group(1).split(";") if ":" in part
        )
        found[match.group(2)] = {
            "size": float(style["font-size"].removesuffix("px")),
            "weight": "bold" if style.get("font-weight") in {"700", "bold"} else "normal",
            "style": style.get("font-style", "normal"),
            "color": style.get("fill", "").lower() or None,
        }
    return found


def build() -> dict[str, object]:
    xyg_found = _xyg_decisions(_xyg_svg())
    mpl_found = _matplotlib_decisions(_matplotlib_svg())
    probes = {"Title": "title", "X": "axis_title", "Y": "axis_title", "0.0": "tick_label"}
    rows = {}
    for text, slot in probes.items():
        rows[text] = {
            "slot": slot,
            "authored": AUTHORED[slot],
            "xyg": xyg_found[text],
            "matplotlib": mpl_found[text],
        }
    return {
        "schema": "xyg.chrome-style-reference/v1",
        "issue": "CurateLabs/xyg#1004",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(terse=True),
            "matplotlib": matplotlib.__version__,
            "xyg": xyg.__version__ if hasattr(xyg, "__version__") else None,
        },
        "output_contract": "per-slot size/weight/style/color decisions; fixed DejaVu font",
        "reproduce": "uv run --with matplotlib python scripts/chrome_style_reference.py --write",
        "rows": rows,
    }


def check(payload: dict[str, object]) -> list[str]:
    problems = []
    for text, row in payload["rows"].items():  # type: ignore[union-attr]
        for key in ("size", "weight", "style"):
            if (
                row["xyg"][key] != row["authored"][key]
                or row["matplotlib"][key] != row["authored"][key]
            ):
                problems.append(f"{text}: {key} xyg={row['xyg'][key]} mpl={row['matplotlib'][key]}")
        for library in ("xyg", "matplotlib"):
            if row[library]["color"] != row["authored"]["color"]:
                problems.append(f"{text}: {library} color {row[library]['color']}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build()
    problems = check(payload)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    text = json.dumps(payload, indent=2) + "\n"
    if args.write:
        OUT.write_text(text)
        print(f"wrote {OUT.relative_to(ROOT)}")
        return 0
    if not OUT.is_file():
        print("missing reference; run with --write", file=sys.stderr)
        return 1
    stored = json.loads(OUT.read_text())
    stored["environment"] = payload["environment"]
    if stored != payload:
        print("reference drifted; re-run with --write", file=sys.stderr)
        return 1
    print("chrome-style reference: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
