"""Unset text-annotation ``dx``/``dy`` resolve to one Rust-owned default (#1024).

Python and Node both leave the offsets unset; the Rust default (ABI 392) is the
only source, so all five static formats must match byte for byte, and the
unset export must equal an export that authors the Rust default explicitly.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

import xyg
from xyg import _native

ROOT = Path(__file__).resolve().parents[1]
FORMATS = ("svg", "png", "pdf", "jpeg", "webp")


def _chart(annotation: xyg.Annotation) -> xyg.Chart:
    return xyg.chart(
        xyg.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2),
        annotation,
        xyg.x_axis(domain=(0, 2), label="X"),
        xyg.y_axis(domain=(0, 4), label="Y"),
        xyg.legend(show=False),
        width=320,
        height=240,
    )


def test_rust_owns_the_default_offset() -> None:
    assert (_native.default_text_annotation_dx(), _native.default_text_annotation_dy()) == (
        6.0,
        -6.0,
    )


def test_unset_offsets_use_the_rust_default() -> None:
    unset = _chart(xyg.text(1, 2, "default offset")).to_svg()
    explicit = _chart(
        xyg.text(
            1,
            2,
            "default offset",
            dx=_native.default_text_annotation_dx(),
            dy=_native.default_text_annotation_dy(),
        )
    ).to_svg()
    zero = _chart(xyg.text(1, 2, "default offset", dx=0, dy=0)).to_svg()
    assert unset == explicit
    assert unset != zero


@pytest.fixture(scope="module")
def node_results() -> dict[str, Any]:
    if not shutil.which("node") or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node/koffi unavailable")
    process = subprocess.run(
        [
            "node",
            str(ROOT / "packages/xy-node/scripts/text_annotation_default_offset_cross_host.mjs"),
        ],
        text=True,
        capture_output=True,
        timeout=300,
        cwd=ROOT,
        env={**os.environ, "XYG_NATIVE_LIB": str(_native._lib._name)},
    )
    assert process.returncode == 0, process.stdout + process.stderr
    return json.loads(process.stdout)


@pytest.mark.parametrize("fmt", FORMATS)
def test_hosts_export_identical_bytes_without_offsets(
    fmt: str, node_results: dict[str, Any]
) -> None:
    expected = node_results["cases"]["default_offset"][fmt]
    options = {"quality": 90} if fmt == "jpeg" else {}
    data = _chart(xyg.text(1, 2, "default offset")).to_image(fmt, scale=1, **options)
    if fmt == "svg":
        assert data.decode() == expected["text"]
    else:
        assert hashlib.sha256(data).hexdigest() == expected["sha256"]
