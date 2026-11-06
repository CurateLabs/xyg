"""Reproduce #889 review images using only the native Scene/XYST route.

Run from the repository root:
    uv run python spec/matplotlib/evidence/889/completion/render_examples.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[5]
    sys.path.insert(0, str(root))
    from tests.test_static_document_registry_cross_host import _build

    import xyg
    import xyg.pyplot as plt
    from xyg import _native

    output = Path(__file__).parent / "examples"
    output.mkdir(exist_ok=True)
    figure, axes = plt.subplots(1, 2, figsize=(6.4, 3.2))
    axes[0].scatter([0, 1], [0, 1], c=[0.0, 1.0], cmap="viridis", alpha=0.4, s=200)
    axes[0].set(xlabel="colormapped faces and edges", ylabel="shared frame")
    handles = axes[1].plot([0, 1, 2], [1, 3, 2])
    axes[1].legend(handles, ["Relabelled"], frameon=False)
    axes[1].set(xlabel="authored legend items", ylabel="shared frame")
    figure.savefig(output / "shared-route.svg", format="svg")
    plt.close("all")
    polar = xyg.polar_chart(
        xyg.line([0, 90, 180, 270], [1, 3, 2, 2], color="#2563eb"),
        xyg.theta_axis(unit="degrees", style={"tick_label_color": "#ff0000"}),
        xyg.r_axis(style={"grid_color": "#ff00ff"}),
        width=400,
        height=400,
    )
    (output / "polar-chrome.png").write_bytes(polar.to_image("png", scale=1))
    document, _scenes, _scale, _quality = _build("document_overlap_red_blue")
    (output / "overlap-red-blue.png").write_bytes(
        _native.static_document_export(document, "png", scale=1)
    )


if __name__ == "__main__":
    main()
