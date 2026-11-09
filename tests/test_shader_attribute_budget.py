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


def _expand_fragments(
    body: str, fragments: dict[str, str], path: Path, seen: frozenset[str] = frozenset()
) -> str:
    def replace(token: re.Match[str]) -> str:
        name = token[1]
        if name not in fragments:
            return token[0]
        assert name not in seen, (path, name, "cyclic shader fragment")
        return _expand_fragments(fragments[name], fragments, path, seen | {name})

    return re.sub(r"\$\{(\w+)\}", replace, body)


def _vertex_shaders() -> dict[str, str]:
    shaders: dict[str, str] = {}
    for path in sorted(SRC.glob("*.ts")):
        text = path.read_text(encoding="utf-8")
        fragments = dict(re.findall(r"(?:export )?const (\w+) = `([^`]*)`;", text))

        for match in re.finditer(r"(?:export )?const (\w+) = `#version 300 es([^`]*)`;", text):
            name, body = match.groups()
            body = _expand_fragments(body, fragments, path, frozenset({name}))
            if "gl_Position" in body:
                shaders[f"{path.name}:{name}"] = body
    return shaders


def _inputs(body: str) -> int:
    """Attribute slots of top-level ``in`` declarations plus used built-ins."""
    count = 0
    for kind, names in re.findall(
        r"(?:^|(?<=;))[ \t]*(?:layout\s*\([^)]*\)\s*)?in[ \t]+(\w+)[ \t]+([^;]+);",
        body,
        re.M,
    ):
        if kind in SLOTS:
            count += SLOTS[kind] * (names.count(",") + 1)
    return count + ("gl_VertexID" in body) + ("gl_InstanceID" in body)


def test_client_has_vertex_shaders() -> None:
    assert len(_vertex_shaders()) >= 5


def test_retained_graph_shared_fragments_and_explicit_locations_are_counted() -> None:
    shaders = _vertex_shaders()
    assert _inputs(shaders["63_graph_gpu.ts:VERTEX"]) == 14
    # The shared body's reference-only branch still names gl_InstanceID;
    # conservatively count both built-ins even though that branch is dead.
    assert _inputs(shaders["63_graph_gpu.ts:NODE_VERTEX"]) == 2


def test_explicit_location_control_cannot_escape_the_attribute_limit() -> None:
    declarations = "\n".join(f"layout(location={i}) in float a{i};" for i in range(16))
    assert _inputs(declarations + "\nvoid main(){gl_VertexID;gl_InstanceID;}") == 18


@pytest.mark.parametrize("name", sorted(_vertex_shaders()))
def test_vertex_shader_inputs_fit_the_portable_budget(name: str) -> None:
    body = _vertex_shaders()[name]
    assert _inputs(body) <= LIMIT, (name, _inputs(body))
