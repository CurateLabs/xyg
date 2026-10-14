"""Compile trusted repository chart examples into native first-paint snapshots.

Chart authoring is framework-free. Stateful examples show their initial data
and explicitly identify the application host needed for updates.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import xyg
from xyg._facets_grid import FacetGrid
from xyg._figure import Figure
from xyg.channel import encode_frame

APP = Path(__file__).resolve().parents[1]
DOCS = APP.parent
FENCES = re.compile(
    r"^(?P<fence>~{3,}|`{3,})(?P<info>[^\n]*)\n(?P<code>.*?)^(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
EXCLUDED = {
    "integrations/reflex.md",
    "styling/component-variations.md",
    "styling/mark-styles.md",
    "styling/playground.md",
    "styling/recipes.md",
}
BLOCKED_MODULES = {"reflex", "reflex_xy", "reflex_components_internal", "xy_docs"}


def collect_charts(value: Any, result: list[Any], seen: set[int]) -> None:
    if id(value) in seen:
        return
    seen.add(id(value))
    if isinstance(value, (xyg.Chart, xyg.FacetChart, FacetGrid, Figure)):
        result.append(value)
    elif isinstance(value, (tuple, list)):
        for child in value:
            collect_charts(child, result, seen)
    elif isinstance(value, dict):
        for child in value.values():
            collect_charts(child, result, seen)


def write_preview(chart: Any, output: Path, index: int) -> dict[str, str]:
    figure = chart if isinstance(chart, Figure) else chart.figure()
    # The documentation owns the display width. Compile this supported fluid
    # viewport through Rust; preserve the example's data, marks, and height.
    figure.width = "100%"
    spec, blob = figure.build_payload(px_width=960)
    frame = encode_frame(spec, [blob])
    digest = hashlib.sha256(frame).hexdigest()[:24]
    path = output / f"{digest}.xyf"
    path.write_bytes(frame)
    title = str(getattr(chart, "title", None) or f"XYG chart {index + 1}")
    return {"src": f"/docs/xy/xy/{digest}.xyf", "title": title}


def write_chart_previews(
    chart: Any, output: Path, group_key: str, index: int
) -> list[dict[str, Any]]:
    """Preserve the SDK's facet grouping around individually compiled panels."""
    grid = chart.figure() if isinstance(chart, xyg.FacetChart) else chart
    if not isinstance(grid, FacetGrid):
        return [write_preview(chart, output, index)]
    group = hashlib.sha256(group_key.encode()).hexdigest()[:24]
    previews = []
    for panel_index, panel in enumerate(grid.figures):
        preview: dict[str, Any] = write_preview(panel, output, panel_index)
        preview["facet"] = {
            "group": group,
            "cols": grid.cols,
            "gap": grid.gap,
            "title": grid.title,
            "height": grid.panel_height,
            "panel": panel_index,
            "count": len(grid.figures),
        }
        previews.append(preview)
    return previews


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=DOCS)
    args = parser.parse_args()
    output = APP / "public" / "xy"
    generated = APP / ".generated"
    output.mkdir(parents=True, exist_ok=True)
    generated.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.xyf"):
        stale.unlink()
    records: dict[str, list[dict[str, Any]]] = {}
    errors = []
    preview_count = 0
    for page in sorted(args.docs.rglob("*.md")):
        relative = page.relative_to(args.docs).as_posix()
        if relative.startswith("app/") or relative in EXCLUDED:
            continue
        page_records = []
        namespace: dict[str, Any] = {"__name__": "__xyg_docs_demo__"}
        for block, match in enumerate(FENCES.finditer(page.read_text())):
            info = match.group("info").strip().split()
            if not info or info[0] != "python" or "exec" not in info:
                continue
            if "demo" not in info and "demo-only" not in info:
                continue
            source = match.group("code")
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = (
                        [node.module or ""]
                        if isinstance(node, ast.ImportFrom)
                        else [alias.name for alias in node.names]
                    )
                    if any(name.split(".")[0] in BLOCKED_MODULES for name in names):
                        raise ValueError(
                            f"{relative}: documentation demos must use framework-free chart authoring"
                        )
            if relative == "index.md" and (
                "xy_sdf_plot_grid" in source or "build_sdf_plots" in source
            ):
                from xyg_examples import build_sdf_plots

                code = "from xyg_examples import build_sdf_plots\n\nplots = build_sdf_plots()"
                charts = list(build_sdf_plots().reading_order)
                note = None
            else:
                code = source.strip()
                charts = []
                previous = {id(value) for value in namespace.values()}
                exec(compile(source, str(page), "exec"), namespace)
                for value in tuple(namespace.values()):
                    collect_charts(value, charts, previous)
                note = (
                    "This static preview shows the initial chart. Python callbacks, dataset changes, "
                    "and streaming updates require an application host; they do not run on this docs page."
                    if "# Static snapshot:" in source
                    else None
                )
            previews = []
            for index, chart in enumerate(charts):
                try:
                    previews.extend(
                        write_chart_previews(chart, output, f"{relative}:{block}:{index}", index)
                    )
                except Exception as error:
                    errors.append({"page": relative, "block": block, "error": str(error)})
                    note = "This example could not be exported as a static preview."
            record: dict[str, Any] = {"block": block, "code": code, "previews": previews}
            if note:
                record["note"] = note
            page_records.append(record)
            preview_count += len(previews)
        if page_records:
            records[relative] = page_records
    (generated / "examples.json").write_text(json.dumps(records, indent=2) + "\n")
    summary = {"pages": len(records), "previews": preview_count, "errors": errors}
    (generated / "examples-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Generated {preview_count} native chart previews across {len(records)} pages.")
    if errors:
        print(json.dumps(errors, indent=2))
        raise SystemExit("Documentation example compilation failed; fix the reported sources.")


if __name__ == "__main__":
    main()
