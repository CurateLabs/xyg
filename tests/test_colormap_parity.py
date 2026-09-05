"""Colormap table parity: Python copy ↔ JS client ↔ native ABI 135."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from xyg import _native, channels
from xyg._channels_colormap import COLORMAP_STOPS

ROOT = Path(__file__).resolve().parents[1]


def test_colormap_stops_stay_in_sync_with_js_client() -> None:
    """The Python tables are ports of 10_colormaps.ts — every stop must appear
    verbatim in the JS source, and the map names must match."""
    js = (ROOT / "js" / "src" / "10_colormaps.ts").read_text(encoding="utf-8")
    body = js.split("COLORMAP_STOPS = {", 1)[1].split("};", 1)[0]
    js_names = set(re.findall(r"^\s*(\w+): (?:\[|flagStops\(\))", body, re.MULTILINE))
    assert js_names == set(COLORMAP_STOPS), "colormap names diverged from 10_colormaps.ts"
    for name, stops in COLORMAP_STOPS.items():
        if name == "flag":
            assert "function flagStops()" in js
            assert "x * 31.5 + 0.25" in js
            assert "x * 31.5 - 0.25" in js
            continue
        for r, g, b in stops:
            assert f"[{r}, {g}, {b}]" in body, (
                f"{name} stop ({r},{g},{b}) missing in 10_colormaps.ts"
            )
    assert set(COLORMAP_STOPS) == set(channels.COLORMAPS), (
        "renderer and public colormap registries diverged"
    )
    from xyg import _native

    for name, stops in COLORMAP_STOPS.items():
        native = [tuple(int(v) for v in row) for row in _native.colormap_stops(name)]
        assert native == list(stops), f"native colormap {name} diverged from COLORMAP_STOPS"
        reversed_native = [
            tuple(int(v) for v in row) for row in _native.colormap_stops(f"{name}_r")
        ]
        assert reversed_native == list(reversed(stops))


def test_matplotlib_gallery_colormap_stops_and_reversal() -> None:
    from xyg.pyplot._colors import resolve_cmap

    expected = {
        "reds": [
            (255, 245, 240),
            (254, 229, 216),
            (253, 202, 181),
            (252, 171, 143),
            (252, 138, 106),
            (251, 105, 74),
            (241, 68, 50),
            (217, 37, 35),
            (188, 20, 26),
            (152, 12, 19),
            (103, 0, 13),
        ],
        "bone": [
            (0, 0, 0),
            (22, 22, 30),
            (45, 45, 62),
            (66, 66, 93),
            (89, 92, 121),
            (112, 123, 144),
            (134, 154, 166),
            (157, 185, 188),
            (185, 210, 210),
            (221, 233, 233),
            (255, 255, 255),
        ],
        "autumn": [
            (255, 0, 0),
            (255, 25, 0),
            (255, 51, 0),
            (255, 76, 0),
            (255, 102, 0),
            (255, 128, 0),
            (255, 153, 0),
            (255, 179, 0),
            (255, 204, 0),
            (255, 230, 0),
            (255, 255, 0),
        ],
        "winter": [
            (0, 0, 255),
            (0, 25, 242),
            (0, 51, 230),
            (0, 76, 217),
            (0, 102, 204),
            (0, 128, 191),
            (0, 153, 178),
            (0, 179, 166),
            (0, 204, 153),
            (0, 230, 140),
            (0, 255, 128),
        ],
        "bupu": [
            (247, 252, 253),
            (229, 239, 246),
            (204, 221, 236),
            (178, 202, 225),
            (154, 180, 214),
            (140, 149, 198),
            (140, 116, 181),
            (138, 81, 165),
            (133, 45, 144),
            (118, 12, 113),
            (77, 0, 75),
        ],
        "rdylbu": [
            (165, 0, 38),
            (214, 47, 38),
            (244, 109, 67),
            (252, 172, 96),
            (254, 224, 144),
            (254, 254, 192),
            (224, 243, 247),
            (169, 216, 232),
            (116, 173, 209),
            (68, 115, 179),
            (49, 54, 149),
        ],
        "ylgn": [
            (255, 255, 229),
            (248, 252, 194),
            (229, 244, 171),
            (200, 232, 154),
            (162, 216, 137),
            (119, 197, 120),
            (75, 176, 98),
            (46, 146, 76),
            (21, 120, 62),
            (0, 96, 51),
            (0, 69, 41),
        ],
        "wistia": [
            (228, 255, 122),
            (238, 245, 84),
            (249, 236, 45),
            (255, 223, 21),
            (255, 206, 10),
            (255, 188, 0),
            (255, 177, 0),
            (255, 165, 0),
            (254, 153, 0),
            (253, 139, 0),
            (252, 127, 0),
        ],
        "puor": [
            (127, 59, 8),
            (177, 87, 6),
            (224, 130, 20),
            (252, 182, 97),
            (254, 224, 182),
            (246, 246, 246),
            (216, 218, 235),
            (177, 169, 209),
            (128, 115, 172),
            (83, 38, 134),
            (45, 0, 75),
        ],
    }
    for name, stops in expected.items():
        assert COLORMAP_STOPS[name] == stops
        assert channels.is_colormap(name)
        assert channels.is_colormap(f"{name}_r")
        assert resolve_cmap(name) == name
        assert resolve_cmap(f"{name}_r") == f"{name}_r"
        assert [list(map(int, row)) for row in _native.colormap_stops(f"{name}_r")] == [
            list(row) for row in reversed(stops)
        ]


def test_flag_colormap_matches_matplotlib_lut_and_gray_aliases() -> None:
    """Gallery cmap names resolve without flattening flag's rapid color cycle."""
    from xyg.pyplot._colors import resolve_cmap

    flag = COLORMAP_STOPS["flag"]
    assert len(flag) == 256

    # Full Matplotlib 3.11 ``colormaps["flag"](linspace(...), bytes=True)``
    # parity. The digest guards every channel of all 256 entries, including
    # the truncation behavior that sparse samples previously missed.
    flag_bytes = np.asarray(flag, dtype=np.uint8).tobytes()
    assert hashlib.sha256(flag_bytes).hexdigest() == (
        "c84ac1f0b2edd3a53ed05fc90dcf6a41e78c2cf52adf1b2288b2d03777505443"
    )

    js_path = ROOT / "js" / "src" / "10_colormaps.ts"
    encoded_source = base64.b64encode(js_path.read_bytes()).decode("ascii")
    completed = subprocess.run(
        [
            "node",
            "--input-type=module",
            "--eval",
            (
                f'const module = await import("data:text/javascript;base64,{encoded_source}");'
                'console.log(JSON.stringify(module.colormapStops("flag")));'
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert json.loads(completed.stdout) == [list(rgb) for rgb in flag]

    assert channels.is_colormap("flag")
    assert channels.is_colormap("flag_r")
    assert [list(map(int, row)) for row in _native.colormap_stops("flag_r")] == [
        list(row) for row in reversed(flag)
    ]
    assert resolve_cmap("flag") == "flag"
    assert resolve_cmap("flag_r") == "flag_r"

    assert resolve_cmap("gray") == "gray"
    assert resolve_cmap("grey") == "gray"
    assert resolve_cmap("gray_r") == "gray_r"
    assert resolve_cmap("grey_r") == "gray_r"
