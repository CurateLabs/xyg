from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from xyg import _native

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "xyts_cross_host.json").read_text())


def _scene(case: str) -> tuple[dict[str, object], bytes]:
    entry = next(value for value in FIXTURE["successful"] if value["name"] == case)
    return entry, bytes.fromhex(entry["scene_hex"])


def _records(scene: bytes) -> list[tuple[int, int, int, tuple[float, ...]]]:
    count, styles = struct.unpack_from("<QQ", scene, 16)
    offset = 160 + styles * 16
    return [
        (
            scene[offset + index * 56],
            struct.unpack_from("<Q", scene, offset + index * 56 + 8)[0],
            scene[offset + index * 56 + 3],
            struct.unpack_from("<5d", scene, offset + index * 56 + 16),
        )
        for index in range(count)
    ]


def test_native_python_consumes_exact_rust_generated_xyts_scenes() -> None:
    assert FIXTURE["authority"] == "crates/xyg-wasm/src/compile.rs"
    assert FIXTURE["scene_version"] == 11
    assert FIXTURE["painter_version"] == 8
    for fixture in FIXTURE["successful"]:
        scene = bytes.fromhex(fixture["scene_hex"])
        assert scene[:4] == b"XYGS"
        assert struct.unpack_from("<I", scene, 4)[0] == FIXTURE["scene_version"]
        assert struct.unpack_from("<QQ", scene, 16) == (
            fixture["records"],
            fixture["styles"],
        )
        assert _native.scene_svg(scene).startswith('<svg xmlns="http://www.w3.org/2000/svg"')
        assert len(_native.scene_raster_commands(scene)) > 16
        assert _native.scene_browser_painter(scene) == bytes.fromhex(fixture["painter_hex"])


def test_rust_fixture_pins_exact_u64_identity_and_mark_semantics() -> None:
    _, scene = _scene("all_marks_reversed_domain")
    records = _records(scene)
    assert [record[0] for record in records] == [0, 0, 1, 1, 1, 2, 2, 2, 3, 3]
    assert [record[1] for record in records] == [
        0x5859_0100_0000_0000,
        91,
        0x8000_0000_0000_0001,
        0x8000_0000_0000_0001,
        0x8000_0000_0000_0001,
        0x8000_0000_0000_0002,
        0x8000_0000_0000_0003,
        0x8000_0000_0000_0004,
        700,
        700,
    ]
    # Literal XYTS identities that resemble the legacy annotation prefix stay data.
    assert records[0][2] == 0x80
    assert records[0][3][4] == pytest.approx(8.0)
    # Reversed authored domains remain reversed in Scene; Rust still chose 0.4
    # data-space half-width from the minimum positive bar spacing.
    assert struct.unpack_from("<2d", scene, 112) == (5.0, -5.0)
    bar_pixels = [record[3][:4] for record in records[5:8]]
    assert all(left < right for left, _, right, _ in bar_pixels)


def test_rust_fixture_pins_singleton_reversed_bar_default_and_failures() -> None:
    _, scene = _scene("singleton_bar_reversed_domain")
    (record,) = _records(scene)
    assert record[0] == 2 and record[1] == 44
    # Domain span is 10, so Rust's singleton fallback has half-width 4. The
    # projected endpoints span exactly the Rust-authored fallback rectangle.
    assert record[3][0] < record[3][2]
    assert {value["name"]: value["rust_error"] for value in FIXTURE["failures"]} == {
        "wrong_version": "Version",
        "unsupported_kind": "Length",
        "stable_id_overflow": "Limit",
        "nonfinite_geometry": "NonFinite",
    }
