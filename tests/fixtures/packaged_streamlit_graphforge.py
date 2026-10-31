"""Direct public-host oracle for the repository Streamlit GraphForge consumer.

Run with the clean installed wheel interpreter, outside checkout import paths.
Core-produced IPC fixtures are inputs, not a dependency on GraphForge bindings.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import xyg

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "tests/fixtures/graphforge/results"


def main(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((RESULTS / "manifest.json").read_text())
    inputs = {"manifest.json": hashlib.sha256((RESULTS / "manifest.json").read_bytes()).hexdigest()}
    cases = {}
    for kind, name in (("graphforge-property", "property"), ("graphforge-pagerank", "cyclic")):
        base = manifest["bases"][name]
        tables = [(RESULTS / f"{base[key]}.arrow") for key in ("nodes", "edges")]
        source = {
            "tables": [path.read_bytes() for path in tables],
            "generation": base["generation"],
        }
        layers = []
        if name == "cyclic":
            result = RESULTS / "pagerank.arrow"
            tables.append(result)
            layers = [
                {
                    "result": result.read_bytes(),
                    "intent": "graph",
                    "result_id": "pagerank",
                    "generation": base["generation"],
                }
            ]
        for path in tables:
            inputs[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        # Omit layers entirely for the plain property-graph acceptance case.
        composition = (
            xyg.compose_graphforge(base=source)
            if name == "property"
            else xyg.compose_graphforge(base=source, layers=layers)
        )
        chart = xyg.graphforge_chart(composition, title=kind, width=720, height=360)
        artifacts = {
            "html": chart.to_html().encode(),
            "svg": chart.to_svg().encode(),
            "png": chart.to_png(),
        }
        hashes = {}
        for extension, data in artifacts.items():
            filename = f"streamlit-{kind}.{extension}"
            (output / filename).write_bytes(data)
            hashes[extension] = {
                "file": filename,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        cases[kind] = {
            "nodes": composition.nodes.count,
            "edges": composition.edges.count,
            "generation": base["generation"],
            "layers": len(layers),
            "captions": list(composition.nodes.label),
            "legend": [row["text"] for row in composition.legend["rows"]],
            "artifacts": hashes,
        }
    (output / "streamlit-graphforge-direct.json").write_text(
        json.dumps({"inputs": inputs, "cases": cases}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
