"""Independent numeric score oracle plus Python/Node XYLF seam parity."""

from __future__ import annotations

import base64
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest

from xyg import _native

ROOT = Path(__file__).resolve().parents[1]
HEADER = struct.Struct("<4s11I12d")
OUTPUT = struct.Struct("<4s3I21d")
ANCHORS = [(1, 1), (0, 1), (0, 0), (1, 0), (1, 0.5), (0, 0.5), (0.5, 0), (0.5, 1), (0.5, 0.5)]


def _frame(kind: int, x, y, *, base=(), width=(), reverse=False, styled=False) -> bytes:
    texts = [b"Title" if styled else b"", b"14px" if styled else b"", b"0.6em", b"0.4em"]
    out = bytearray(
        HEADER.pack(
            b"XYLF",
            1,
            int(reverse),
            1,
            1,
            1,
            *(len(t) for t in texts),
            0,
            0,
            10.0,
            20.0,
            300.0,
            200.0,
            0.0,
            1.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            4.0,
        )
    )
    out.extend(b"".join(texts))
    out.extend(struct.pack("<I", 6) + b"Series")
    out.extend(struct.pack("<6I", kind, len(x), len(y), len(base), len(width), 0))
    for column in (x, y, base, width):
        out.extend(np.asarray(column, dtype="<f8").tobytes())
    return bytes(out)


def _node(frames: list[bytes]) -> list[dict[str, str]]:
    if shutil.which("node") is None or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node host dependencies are not installed")
    process = subprocess.run(
        ["node", str(ROOT / "packages/xy-node/scripts/static_legend_fit_cross_host.mjs")],
        input=json.dumps([base64.b64encode(frame).decode() for frame in frames]),
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
        env={**os.environ, "XYG_NATIVE_LIB": str(_native._lib._name)},
    )
    return json.loads(process.stdout)


def _geometry(styled: bool):
    # Existing independent ABI124 box geometry is the frozen footprint oracle;
    # it does not call the new placement/scoring query.
    return _native.scene_legend_box_layout(
        plot={"x": 0, "y": 0, "w": 300, "h": 200},
        names=["Series"],
        title="Title" if styled else None,
        loc="upper right",
        font_size=14 if styled else 11,
        handlelength=None,
        handletextpad=None,
        handleheight=None,
        ncols=1,
        padding_em=0.6,
        row_gap_em=0.4,
        anchor=None,
        border_axes_pad=4,
    )


def _reference_scores(kind, x, y, styled, reverse):
    geometry = _geometry(styled)
    bw, bh = geometry["box_w"] / 300, geometry["box_h"] / 200
    px, py = 4 / 300, 4 / 200
    boxes = [
        (px + hx * max(0, 1 - 2 * px - bw), py + vy * max(0, 1 - 2 * py - bh)) for hx, vy in ANCHORS
    ]
    x, y = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    total = len(x)
    budget = 4096 if kind == 1 else 512
    if total > budget:
        indices = np.linspace(0, total - 1, budget, dtype=np.intp)
        if np.any(np.isfinite(x[indices]) & np.isfinite(y[indices])):
            x, y = x[indices], y[indices]
    weight = total / len(x) if len(x) else 1
    if reverse:
        x = 1 - x
    scores = []
    for xl, yl in boxes:
        xh, yh = xl + bw, yl + bh
        count = np.count_nonzero((x > xl) & (x < xh) & (y > yl) & (y < yh))
        hit = False
        if kind == 0:
            for ax, ay, zx, zy in zip(x[:-1], y[:-1], x[1:], y[1:], strict=True):
                if not np.isfinite([ax, ay, zx, zy]).all():
                    continue
                # Independent Liang-Barsky segment clipping, including edges.
                low, high = 0.0, 1.0
                for p, q in [
                    (-(zx - ax), ax - xl),
                    (zx - ax, xh - ax),
                    (-(zy - ay), ay - yl),
                    (zy - ay, yh - ay),
                ]:
                    if p == 0:
                        if q < 0:
                            high = -1.0
                            break
                    elif p < 0:
                        low = max(low, q / p)
                    else:
                        high = min(high, q / p)
                if low <= high:
                    hit = True
                    break
            hit = hit or bool(count)
        scores.append(float(count) * weight + float(hit))
    return geometry, np.asarray(scores)


@pytest.mark.parametrize("kind", [0, 1])
@pytest.mark.parametrize("styled,reverse", [(False, False), (True, True)])
def test_measured_scores_match_independent_oracle_and_both_hosts(kind, styled, reverse):
    rng = np.random.default_rng(873)
    x = rng.uniform(-0.2, 1.2, 5003)
    y = rng.uniform(-0.2, 1.2, 5003)
    x[::17] = np.nan
    frame = _frame(kind, x, y, styled=styled, reverse=reverse)
    raw = _native.static_legend_fit(frame)
    node = _node([frame])[0]
    assert base64.b64decode(node["output"]) == raw
    magic, version, chosen, used, *values = OUTPUT.unpack(raw)
    assert (magic, version, used) == (b"XYLR", 1, 1)
    geometry, scores = _reference_scores(kind, x, y, styled, reverse)
    assert values[4:6] == pytest.approx([geometry["box_w"], geometry["box_h"]], abs=1e-12)
    assert values[8:17] == pytest.approx(scores, abs=1e-12)
    assert chosen == np.flatnonzero(scores <= scores.min() * (1 + 1e-9))[0]
    assert values[19:21] == values[4:6]


def test_expanded_footprints_and_sparse_sampling_cross_hosts():
    sparse_x = np.full(1001, np.nan)
    sparse_y = np.full(1001, np.nan)
    sampled = set(np.linspace(0, 1000, 512, dtype=np.intp))
    index = next(i for i in range(1001) if i not in sampled)
    sparse_x[index], sparse_y[index] = 0.9, 0.95
    frames = [
        _frame(0, sparse_x, sparse_y),
        _frame(2, [0.9], [1.1], base=[-0.1], width=[0.3]),
        _frame(3, [0.95], [1.1], base=[-0.1], width=[0.3]),
        _frame(4, [0.0, 1.0], [0.95]),
        _frame(5, [1.0, 0.8, np.nan, 0.9], []),
        _frame(6, [0.0, 1.0], [0.95, 0.95]),
    ]
    for frame, node in zip(frames, _node(frames), strict=True):
        raw = _native.static_legend_fit(frame)
        assert base64.b64decode(node["output"]) == raw
        unpacked = OUTPUT.unpack(raw)
        assert unpacked[3] == 1
        assert unpacked[12] > 0  # upper-right score


def test_malformed_and_unsupported_legend_inputs_reject_on_both_hosts():
    valid = _frame(0, [0, 1], [0, 1])
    frames = [valid[:n] for n in (0, 3, 143, 144, len(valid) - 1)] + [valid + b"\0"]
    for offset, value in [(4, 2), (8, 32), (12, 4097), (40, 1)]:
        frame = bytearray(valid)
        struct.pack_into("<I", frame, offset, value)
        frames.append(bytes(frame))
    frames.append(_frame(7, [0], [0]))
    for frame, node in zip(frames, _node(frames), strict=True):
        with pytest.raises((ValueError, RuntimeError)):
            _native.static_legend_fit(frame)
        assert "error" in node and "output" not in node
    assert "XYG_STATIC_UNSUPPORTED_LEGEND_FOOTPRINT" in _node([frames[-1]])[0]["error"]
