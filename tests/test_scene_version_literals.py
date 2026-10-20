"""Scene readers never restate the schema version as a literal.

The canonical Scene version is owned by Rust (`SCENE_VERSION`). Browser readers
import the generated `XYG_WASM_SCENE_VERSION`, Node readers call
`sceneVersion()`, and Python readers call `scene_version()`. A literal in any
reader silently rejects every Scene after the next bump (or, worse, accepts the
wrong one), so this guard fails the build on any numeric `XYGS` version check.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Reader trees and the suffixes that carry hand-written reader code.
READER_TREES = (
    (ROOT / "js" / "src", (".ts",)),
    (ROOT / "packages" / "xy-node" / "src", (".js",)),
    (ROOT / "python" / "xyg", (".py",)),
)
GENERATED = ("_abi_generated", "wasm_abi_generated", "_wasm_aggregate_generated")

# A version word compared with a numeric literal immediately after the Scene
# magic check (`XYGS` / `0x53475958`; sibling `XYGU` tile checks are separate
# formats and are not Scene readers), plus the baked-in header pair and
# versioned diagnostic names ("Scene32") that restate the same number.
LITERAL_READERS = (
    re.compile(
        r"""(?:["']XYGS["']|0x53475958)\)?\s*\|\|\s*\w+\.(?:getUint32|readUInt32LE)"""
        r"""\(\s*4\s*(?:,\s*true\s*)?\)\s*[!=]==?\s*\d+"""
    ),
    re.compile(
        r"(?:getUint32|readUInt32LE)\(\s*4\s*(?:,\s*true\s*)?\)\s*[!=]==?\s*\d+"
        r"[^;\n]*?(?:getUint32|readUInt32LE)\(\s*8\s*(?:,\s*true\s*)?\)\s*[!=]==?\s*160\b"
    ),
    re.compile(r"""\(\s*b?["']XYGS["']\s*,\s*\d+\s*\)"""),
    re.compile(r"""unpack_from\([^)]*\)\s*!=\s*\(\s*\d+\s*,\s*160\s*\)"""),
    re.compile(r"\bScene\d{2}\b"),
)


def literal_version_readers(text: str) -> list[str]:
    """Return every line that restates the Scene schema version as a literal."""
    return [
        line.strip()
        for line in text.splitlines()
        if any(pattern.search(line) for pattern in LITERAL_READERS)
    ]


def test_guard_flags_the_retired_literal_readers() -> None:
    retired = [
        "if(String.fromCharCode(...scene.subarray(0,4))!=='XYGS'||sv.getUint32(4,true)!==32)throw 1;",
        "if(sv.getUint32(0,true)!==0x53475958||sv.getUint32(4,true)!==32)throw 1;",
        "||sv.getUint32(4,true)!==32||sv.getUint32(8,true)!==160||tile",
        'if struct.unpack_from("<4sI", b, 2304) != (b"XYGS", 32):',
        'or struct.unpack_from("<II", self.scene, 4) != (32, 160)',
        'raise ValueError("invalid Scene32 packet")',
    ]
    for line in retired:
        assert literal_version_readers(line), line
    owned = [
        "if(String.fromCharCode(...scene.subarray(0,4))!=='XYGS'||sv.getUint32(4,true)!==XYG_WASM_SCENE_VERSION)throw 1;",
        "if(sv.getUint32(0,true)!==0x53475958||sv.getUint32(4,true)!==sceneVersion())throw 1;",
        'struct.unpack_from("<II", self.scene, 4) != (scale.scene_version(), 160)',
        'struct.unpack_from("<4sI", b, 2304) != (b"XYGS", scale.scene_version())',
    ]
    for line in owned:
        assert not literal_version_readers(line), line


def test_no_reader_restates_the_scene_version() -> None:
    offenders: list[str] = []
    for tree, suffixes in READER_TREES:
        for path in sorted(tree.rglob("*")):
            if path.suffix not in suffixes or any(name in path.name for name in GENERATED):
                continue
            for line in literal_version_readers(path.read_text(encoding="utf-8")):
                offenders.append(f"{path.relative_to(ROOT)}: {line[:140]}")
    assert not offenders, "Scene readers must use the owning version constant:\n" + "\n".join(
        offenders
    )
