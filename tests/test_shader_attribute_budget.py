"""Vertex shaders stay within the portable 16-input attribute budget.

WebGL2 guarantees only 16 vertex attributes, and some SwiftShader/ANGLE
builds count the ``gl_VertexID`` / ``gl_InstanceID`` built-ins against that
limit ("program link: Too many attributes (gl_VertexID)"). A shader over the
budget links in some browsers and fails in others, so every vertex shader in
the client is held to 16 inputs including those built-ins.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "js" / "src"
LIMIT = 16
SLOTS = {"float": 1, "int": 1, "uint": 1, "bool": 1}
SLOTS.update({f"{p}vec{n}": 1 for p in ("", "i", "u", "b") for n in (2, 3, 4)})
SLOTS.update({f"mat{n}": n for n in (2, 3, 4)})


def _vertex_shaders() -> dict[str, str]:
    shaders: dict[str, str] = {}
    for path in sorted(SRC.glob("*.ts")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(?:export )?const (\w+) = `#version 300 es(.*?)`;", text, re.S):
            name, body = match.groups()
            if "gl_Position" in body:
                shaders[f"{path.name}:{name}"] = body
    return shaders


def _inputs(body: str) -> int:
    """Attribute slots of top-level ``in`` declarations plus used built-ins."""
    count = 0
    for kind, names in re.findall(r"(?:^|(?<=;))[ \t]*in[ \t]+(\w+)[ \t]+([^;]+);", body, re.M):
        if kind in SLOTS:
            count += SLOTS[kind] * (names.count(",") + 1)
    return count + ("gl_VertexID" in body) + ("gl_InstanceID" in body)


def test_client_has_vertex_shaders() -> None:
    assert len(_vertex_shaders()) >= 5


@pytest.mark.parametrize("name", sorted(_vertex_shaders()))
def test_vertex_shader_inputs_fit_the_portable_budget(name: str) -> None:
    body = _vertex_shaders()[name]
    assert _inputs(body) <= LIMIT, (name, _inputs(body))
