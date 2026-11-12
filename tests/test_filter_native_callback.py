"""Reproducible paged source and actual binary callback/painter boundary."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "filter_fixture", ROOT / "scripts/gen_filter_paged_fixture.py"
)
assert SPEC is not None and SPEC.loader is not None
AUTHOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTHOR)


def test_materialized_fixture_refuses_overwrite_and_detects_canonical_corruption(tmp_path):
    directory = tmp_path / "fixture"
    manifest = AUTHOR.generate(directory, rows=257, chunk=64)
    result = AUTHOR.verify(directory)
    assert result["fullCanonicalScan"] and result["physicalFiles"] == 4
    assert all(r["completeRowsVerified"] == 257 for r in result["results"])
    with pytest.raises(FileExistsError):
        AUTHOR.generate(directory, rows=257, chunk=64)
    path = Path(manifest["files"][0]["path"])
    with path.open("r+b") as file:
        header = file.read(64)
        offset = struct.unpack_from("<Q", header, 24)[0]
        file.seek(offset + 123 * 16 + 8)
        file.write(struct.pack("<d", 999999))
    with pytest.raises(ValueError, match="dimension plane"):
        AUTHOR.verify(directory)


def test_fixture_verification_bounds_metadata_before_header_reads(tmp_path):
    directory = tmp_path / "fixture"
    AUTHOR.generate(directory, rows=17, chunk=8)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["rows"], manifest["chunkRows"] = (1 << 32) - 1, 1
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="metadata exceeds"):
        AUTHOR.verify(directory)


@pytest.mark.parametrize("pixel_index", [False, True])
def test_actual_native_callback_five_rendered_views(tmp_path, pixel_index):
    chromium = os.environ.get("XYG_CHROMIUM") or os.environ.get("XYG_TEST_CHROMIUM")
    node = shutil.which("node")
    if not chromium or not node:
        if os.environ.get("XY_REQUIRE_BROWSER") == "1":
            pytest.fail("native callback proof requires explicit Chromium and Node")
        pytest.skip("set XYG_CHROMIUM and provide Node for the actual callback journey")
    directory = tmp_path / "fixture"
    AUTHOR.generate(directory, rows=140003)
    AUTHOR.verify(directory)
    output = tmp_path / "browser"
    subprocess.run(
        [
            node,
            str(ROOT / "scripts/filter_native_callback_browser.mjs"),
            str(directory),
            str(output),
        ],
        cwd=ROOT,
        check=True,
        timeout=120,
        env={
            **{key: value for key, value in os.environ.items() if key != "XYG_FILTER_ACTIVE_CELLS"},
            "XYG_CHROMIUM": chromium,
            **({"XYG_FILTER_ACTIVE_CELLS": "pixel"} if pixel_index else {}),
        },
    )
    result = json.loads((output / "report.json").read_text())
    assert result["countChecks"] == 100000 and result["textureChecks"] == 400000
    assert result["membershipBits"] == 40 and result["sourceArraysInBrowser"] == 0
    assert result["pageErrors"] == [] and result["performanceQualification"] is False
    cells = 346 if pixel_index else 4
    assert result["activeCells"] == cells and result["pixelIndex"] is pixel_index
    assert result["traces"][0]["indexBytes"] == str(
        4 * (cells + 1) * 50001 + 16 * 50001 + 16 * cells
    )
    assert [r["op"] for r in result["traces"]] == [10, 11, 5, 11, 9]
