"""Record #888 named-colorbar domain behavior against Matplotlib 3.11.0.

Run after ``cargo build --release`` with Matplotlib and Pillow installed:
    uv run --no-sync python scripts/compare_named_colorbar_domains.py --output /tmp/colorbar-888

This is a correctness probe, not a timing benchmark or pixel-parity claim.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import itertools
import json
import math
import platform
import struct
import subprocess
import sys
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib
import numpy as np
from PIL import Image

matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.cm import ScalarMappable  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402
from matplotlib.figure import Figure as MplFigure  # noqa: E402

from xyg import _native, scatter_chart  # noqa: E402
from xyg._scene_v3 import UnsupportedSceneV3  # noqa: E402

DOMAINS = {
    "ordinary": (0.0, 1.0),
    "wide_positive": (0.0, 1.7e308),
    "wide_signed": (-1.7e308, 1.7e308),
    "adjacent": (1.0, math.nextafter(1.0, math.inf)),
    "reversed_invalid": (2.0, 1.0),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def floats(values) -> list[str]:
    """Exact f64 evidence, including non-finite Matplotlib results, as JSON strings."""
    return [float(value).hex() for value in values]


def error(exc: Exception) -> dict:
    return {"type": type(exc).__name__, "message": str(exc)}


def png_evidence(data: bytes) -> dict:
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        rgba = image.convert("RGBA")
        colors = np.unique(np.asarray(rgba).reshape(-1, 4), axis=0)
        return {
            "size": list(rgba.size),
            "rgba_sha256": digest(rgba.tobytes()),
            "unique_rgba": len(colors),
        }


def save_artifact(output: Path, name: str, data: bytes) -> dict:
    original_sha256 = digest(data)
    if name.endswith(".svg"):
        # Matplotlib emits trailing spaces in path data; preserve XML whitespace separators.
        data = ("\n".join(line.rstrip() for line in data.decode().splitlines()) + "\n").encode()
    (output / name).write_bytes(data)
    result = {
        "file": name,
        "bytes": len(data),
        "sha256": digest(data),
        "original_sha256": original_sha256,
    }
    if name.endswith(".png"):
        result["decoded"] = png_evidence(data)
    return result


def xyg_probe(domain: tuple[float, float], output: Path, name: str) -> dict:
    # Same canonical Scene entry point used by the #1048 cross-host witnesses.
    figure = scatter_chart(width=320, height=240).figure()
    figure.scatter([0.0, 1.0], [0.0, 1.0])
    figure.colorbar_options = {"domain": list(domain), "colormap": "viridis"}
    try:
        scene = figure.to_scene()
    except UnsupportedSceneV3 as exc:
        return {"status": "rejected", "error": error(exc)}
    at = scene.index(b"XYCB")
    count = struct.unpack_from("<I", scene, at + 12)[0]
    stops = [struct.unpack_from("<d4B", scene, at + 56 + i * 12) for i in range(count)]
    values = [stop[0] for stop in stops]
    assert count == 11 and values[0] == domain[0] and values[-1] == domain[1]
    assert all(a < b for a, b in itertools.pairwise(values))
    svg = _native.scene_svg(scene)
    bands = [
        node.attrib
        for node in ET.fromstring(svg).iter()
        if node.get("data-xy-slot") == "colorbar_band"
    ]
    assert bands and all(
        math.isfinite(float(band[key])) for band in bands for key in ("x", "y", "width", "height")
    )
    png = _native.scene_static_export(scene, "png", scale=1.0, width=320, height=240)
    decoded = Image.open(io.BytesIO(png)).convert("RGBA")
    # Decode and inspect real palette pixels, rather than accepting only a PNG signature.
    for band in bands:
        x = int(float(band["x"]) + float(band["width"]) / 2)
        y = int(float(band["y"]) + float(band["height"]) / 2)
        assert decoded.getpixel((x, y))[:3] == tuple(
            int(channel) for channel in band["fill"].split("(")[1].split(")")[0].split(",")[:3]
        )
    return {
        "status": "exported",
        "scene_sha256": digest(scene),
        "stop_values_hex": floats(values),
        "stop_rgba": [list(stop[1:]) for stop in stops],
        "svg_bands": bands,
        "svg": save_artifact(output, f"{name}-xyg.svg", svg.encode()),
        "png": save_artifact(output, f"{name}-xyg.png", png),
    }


def mpl_probe(domain: tuple[float, float], output: Path, name: str) -> dict:
    result = {}
    for stage in ("normalize", "colorbar"):
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            norm = Normalize(vmin=domain[0], vmax=domain[1])
            operation = stage
            try:
                if stage == "normalize":
                    values = norm(np.array(domain))
                    result[stage] = {"status": "returned", "endpoint_values_hex": floats(values)}
                else:
                    figure = MplFigure(figsize=(3.2, 2.4), dpi=100)
                    FigureCanvasAgg(figure)
                    operation = "colorbar construction"
                    figure.colorbar(
                        ScalarMappable(norm=norm, cmap="viridis"),
                        cax=figure.add_axes([0.25, 0.15, 0.2, 0.7]),
                    )
                    exports = {}
                    for extension in ("svg", "png"):
                        operation = f"{extension} export"
                        stream = io.BytesIO()
                        try:
                            figure.savefig(
                                stream,
                                format=extension,
                                metadata={"Date": None} if extension == "svg" else {},
                            )
                            exports[extension] = {
                                "status": "exported",
                                **save_artifact(
                                    output, f"{name}-mpl.{extension}", stream.getvalue()
                                ),
                            }
                        except (ValueError, OverflowError) as exc:
                            exports[extension] = {"status": "error", "error": error(exc)}
                    status = (
                        "exported"
                        if all(value["status"] == "exported" for value in exports.values())
                        else "export_error"
                    )
                    result[stage] = {"status": status, **exports}
            except (ValueError, OverflowError) as exc:
                result[stage] = {"status": "error", "operation": operation, "error": error(exc)}
            result[stage]["domain_after_hex"] = floats([norm.vmin, norm.vmax])
            result[stage]["warnings"] = sorted(
                {f"{type(item.message).__name__}: {item.message}" for item in captured}
            )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if matplotlib.__version__ != "3.11.0":
        parser.error("this versioned evidence requires matplotlib==3.11.0")
    args.output.mkdir(parents=True, exist_ok=True)
    matplotlib.rcdefaults()
    matplotlib.rcParams["svg.hashsalt"] = "xyg-888"
    report = {
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "packages": {
                name: importlib.metadata.version(name)
                for name in (
                    "matplotlib",
                    "numpy",
                    "pillow",
                    "contourpy",
                    "cycler",
                    "fonttools",
                    "kiwisolver",
                    "packaging",
                    "pyparsing",
                    "python-dateutil",
                    "six",
                    "tzdata",
                )
            },
            "matplotlib_backend": matplotlib.get_backend(),
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "probe_sha256": digest(Path(__file__).read_bytes()),
            "abi_version": _native.ABI_VERSION,
            "native_sha256": digest(_native._find_library().read_bytes()),
        },
        "cases": {},
    }
    for name, domain in DOMAINS.items():
        xyg = xyg_probe(domain, args.output, name)
        assert (xyg["status"] == "rejected") == (name in ("adjacent", "reversed_invalid"))
        if xyg["status"] == "rejected":
            assert xyg["error"]["message"].startswith("XYG_SCENE_UNSUPPORTED_COLORBAR: ")
        report["cases"][name] = {
            "domain_hex": floats(domain),
            "xyg": xyg,
            "matplotlib": mpl_probe(domain, args.output, name),
        }
    ordinary_palette = report["cases"]["ordinary"]["xyg"]["stop_rgba"]
    assert all(
        case["xyg"]["stop_rgba"] == ordinary_palette
        for case in report["cases"].values()
        if case["xyg"]["status"] == "exported"
    )
    (args.output / "results.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Recorded {len(DOMAINS)} cases in {args.output / 'results.json'}")


if __name__ == "__main__":
    main()
