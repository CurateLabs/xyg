"""Byte-exact Python/native and Node/native proof for the shared XYTK resolver."""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from xyg import _native

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "packed_ticks_cross_host.json"
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "packed_ticks_cross_host.mjs"


def _malformed_requests(request: bytes) -> dict[str, bytes]:
    cases: dict[str, bytes] = {}

    embedded_nul = bytearray(request)
    format_offset = struct.unpack_from("<I", embedded_nul, 32 + 92)[0]
    embedded_nul[format_offset] = 0
    cases["embedded-nul"] = bytes(embedded_nul)

    irrelevant_category = bytearray(request)
    struct.pack_into("<I", irrelevant_category, 32 + 4 * 96 + 8, 0)
    cases["category-plane-on-linear"] = bytes(irrelevant_category)

    irrelevant_labels = bytearray(request)
    struct.pack_into("<I", irrelevant_labels, 32 + 1 * 96 + 12, 2)
    cases["label-plane-on-minor"] = bytes(irrelevant_labels)

    irrelevant_format = bytearray(request)
    struct.pack_into("<I", irrelevant_format, 32 + 12, 2)
    cases["format-plane-on-minor"] = bytes(irrelevant_format)
    return cases


def _native_lib() -> Path:
    if sys.platform == "win32":
        name = "xyg_core.dll"
    elif sys.platform == "darwin":
        name = "libxyg_core.dylib"
    else:
        name = "libxyg_core.so"
    return ROOT / "target" / "release" / name


def test_python_native_packed_ticks_match_exact_fixture() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    request = bytes.fromhex(fixture["request_hex"])
    assert _native.tick_resolve_packed(request).hex() == fixture["output_hex"]

    malformed = bytearray(request)
    malformed[0] ^= 0xFF
    with pytest.raises(ValueError, match="rejected"):
        _native.tick_resolve_packed(malformed)
    for malformed_request in _malformed_requests(request).values():
        with pytest.raises(ValueError, match="rejected"):
            _native.tick_resolve_packed(malformed_request)


def test_native_packed_tick_seam_is_capacity_aware() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = np.frombuffer(bytes.fromhex(fixture["request_hex"]), dtype=np.uint8)
    required = int(
        _native._lib.xyg_tick_resolve_packed(  # noqa: SLF001 - ABI proof
            _native._ptr_u8(source),
            len(source),
            0,
            0,  # noqa: SLF001
        )
    )
    assert required == len(bytes.fromhex(fixture["output_hex"]))
    short = np.empty(required - 1, dtype=np.uint8)
    assert (
        int(
            _native._lib.xyg_tick_resolve_packed(  # noqa: SLF001 - ABI proof
                _native._ptr_u8(source),  # noqa: SLF001
                len(source),
                _native._ptr_u8(short),  # noqa: SLF001
                len(short),
            )
        )
        == required
    )


@pytest.mark.skipif(not shutil.which("node"), reason="Node is not installed")
def test_node_native_packed_ticks_match_python_fixture() -> None:
    if not (ROOT / "packages" / "xy-node" / "node_modules").is_dir():
        pytest.skip("run npm ci --prefix packages/xy-node")
    env = {**os.environ, "XYG_NATIVE_LIB": str(_native_lib())}
    result = subprocess.run(
        [shutil.which("node") or "node", str(NODE_SCRIPT)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert result.stdout.strip() == fixture["output_hex"]
