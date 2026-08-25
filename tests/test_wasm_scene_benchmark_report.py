from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def report() -> dict[str, object]:
    typed = [
        {
            "count": count,
            "typedSeries": True,
            "firstPaintMs": 1.0,
            "copyCount": 1,
            "copyBytesLo": count * 16,
            "copyBytesHi": 0,
            "arenaHighWaterBytes": count * 16,
            "memoryBytes": 65_536,
            "memoryHighWaterBytes": 65_536,
            "mainThreadRecordVisits": 0,
            "framedSeries": 1,
        }
        for count in [100, 10_000, 100_000, 1_000_000]
    ]
    return {
        "schema": "xyg-wasm-scene-browser-v3",
        "gitSha": "abc123",
        "measurements": [
            *typed,
            *[
                {
                    "count": count,
                    "authoredScene": True,
                    "sceneBytes": count * 20,
                    "painterBytes": count * 12,
                    "workerPrepareMs": 1.0,
                    "hydrateUploadMs": 1.0,
                    "firstPaintMs": 1.0,
                    "browserVisualTolerancePx": 1,
                    "visibleCanvasPixels": 64,
                    "plotMeanRgbDelta": 1.0,
                    "plotDifferingFraction": 0.01,
                    "calloutGeometryDeltaPx": 0.0,
                    "copyCount": 1,
                    "copyBytesLo": count * 16,
                    "copyBytesHi": 0,
                    "arenaHighWaterBytes": count * 16,
                    "memoryBytes": 65_536,
                    "memoryHighWaterBytes": 65_536,
                    "legendSemantics": True,
                    "colorbarSemantics": True,
                    "annotationSemantics": True,
                }
                for count in [100, 10_000, 100_000, 1_000_000]
            ],
            {
                "count": 1_000_000,
                "fragmented": True,
                "rejectedTraceLimit": 1024,
                "browserChildren": 0,
            },
        ],
    }


def verify(tmp_path: Path, value: dict[str, object]) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "scripts/verify_wasm_scene_benchmark.py", str(path), "--sha", "abc123"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_accepts_complete_sha_keyed_four_size_browser_evidence(tmp_path: Path) -> None:
    result = verify(tmp_path, report())
    assert result.returncode == 0, result.stderr


def test_rejects_main_thread_record_work(tmp_path: Path) -> None:
    value = report()
    rows = value["measurements"]
    assert isinstance(rows, list) and isinstance(rows[0], dict)
    rows[0]["mainThreadRecordVisits"] = 1
    result = verify(tmp_path, value)
    assert result.returncode != 0
    assert "main-thread record work" in result.stderr


def test_rejects_missing_authored_scene_semantics(tmp_path: Path) -> None:
    value = report()
    rows = value["measurements"]
    assert isinstance(rows, list) and isinstance(rows[4], dict)
    rows[4]["annotationSemantics"] = False
    result = verify(tmp_path, value)
    assert result.returncode != 0
    assert "annotationSemantics" in result.stderr


def test_rejects_empty_authored_scene_payload(tmp_path: Path) -> None:
    value = report()
    rows = value["measurements"]
    assert isinstance(rows, list) and isinstance(rows[4], dict)
    rows[4]["painterBytes"] = 0
    result = verify(tmp_path, value)
    assert result.returncode != 0
    assert "empty payload" in result.stderr


def test_rejects_authored_scene_visual_tolerance_failure(tmp_path: Path) -> None:
    value = report()
    rows = value["measurements"]
    assert isinstance(rows, list) and isinstance(rows[4], dict)
    rows[4]["browserVisualTolerancePx"] = 2
    result = verify(tmp_path, value)
    assert result.returncode != 0
    assert "visual-tolerance" in result.stderr


def test_rejects_authored_scene_visual_differential_failure(tmp_path: Path) -> None:
    value = report()
    rows = value["measurements"]
    assert isinstance(rows, list) and isinstance(rows[7], dict)
    rows[7]["calloutGeometryDeltaPx"] = 1.1
    result = verify(tmp_path, value)
    assert result.returncode != 0
    assert "visual-differential" in result.stderr
