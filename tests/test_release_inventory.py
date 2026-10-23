"""Declaration drift controls for the release preparation inventory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import check_release_inventory as inventory


def snapshot(contracts):
    return {
        "schema": "xyg.release-api-inventory/v1",
        "contracts": contracts,
        "contractSha256": inventory.digest(contracts),
    }


def python_surface(root: Path, source: str):
    package = root / "python/example"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(source)
    return inventory.PythonInventory(root).surface("example")


BASE_PYTHON = """__all__ = ["build"]
def build(values: list[float], *, width: int = 640) -> str:
    return "chart"
"""


@pytest.mark.parametrize(
    "replacement",
    [
        BASE_PYTHON.replace("width: int = 640", "width: int = 800"),
        BASE_PYTHON.replace("width: int", "height: int"),
        BASE_PYTHON.replace("list[float]", "list[int]"),
        BASE_PYTHON.replace('__all__ = ["build"]', '__all__ = ["build", "other"]')
        + "\ndef other():\n    pass\n",
    ],
)
def test_public_python_export_signature_or_default_change_fails(root_path: Path, replacement: str):
    expected = snapshot({"surface": python_surface(root_path, BASE_PYTHON)})
    actual = snapshot({"surface": python_surface(root_path, replacement)})
    assert inventory.compare(expected, actual) == [
        "API contract drift: surface; review and run python3 scripts/check_release_inventory.py --write"
    ]


@pytest.fixture
def root_path(tmp_path: Path) -> Path:
    return tmp_path


def test_python_body_only_change_passes_without_misrepresenting_source_hash(root_path: Path):
    expected = snapshot({"surface": python_surface(root_path, BASE_PYTHON)})
    actual = snapshot(
        {
            "surface": python_surface(
                root_path,
                BASE_PYTHON.replace('return "chart"', 'result = "chart"\n    return result'),
            )
        }
    )
    expected["sourceSha256"] = {"source.py": "old generation-time bytes"}
    actual["sourceSha256"] = {"source.py": "new working-tree bytes"}
    assert expected["sourceSha256"] != actual["sourceSha256"]
    assert inventory.compare(expected, actual) == []


def test_python_class_fields_methods_errors_and_lifecycle_are_declared(root_path: Path):
    source = """__all__ = ["Session"]
class Session:
    timeout: int = 10
    def __init__(self, *, size=64): pass
    def close(self) -> None: pass
    def query(self, values):
        raise ValueError("bad values")
    def _private(self): pass
"""
    symbol = python_surface(root_path, source)[0]
    assert set(symbol["members"]) == {"__init__", "timeout", "close", "query"}
    assert symbol["members"]["timeout"] == {"annotation": "int", "default": "10"}
    assert symbol["members"]["query"][0]["raisedTypes"] == ["ValueError"]


def test_python_lazy_reexports_resolve_the_actual_signature(root_path: Path):
    package = root_path / "python/example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__all__ = ["build"]\n_EXPORTS = {"build": ".builders"}\n')
    (package / "builders.py").write_text("def build(*, width: int = 640):\n    return width\n")
    record = inventory.PythonInventory(root_path).surface("example")[0]
    assert record["reference"] == "python/example/builders.py#build"
    assert record["signatures"][0]["parameters"] == "*, width: int=640"


def js_root(tmp_path: Path) -> Path:
    if not (inventory.ROOT / "node_modules/typescript").exists():
        pytest.fail("release inventory tests require the pinned compiler: npm ci")
    (tmp_path / "node_modules").symlink_to(
        inventory.ROOT / "node_modules", target_is_directory=True
    )
    source = tmp_path / "packages/xy-node/src"
    source.mkdir(parents=True)
    (source.parent / "package.json").write_text(
        json.dumps(
            {"name": "@curatelabs/xyg-node", "type": "module", "exports": {".": "./src/index.js"}}
        )
    )
    (source / "index.js").write_text(
        "export function createEngine(width = 640) { return width + 1; }\n"
    )
    browser = tmp_path / "js/src"
    browser.mkdir(parents=True)
    (browser / "60_entries.ts").write_text(
        "export function render(width: number = 640): number { return width + 1; }\n"
    )
    (browser.parent / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "module": "ESNext",
                    "moduleResolution": "bundler",
                },
                "include": ["src/**/*.ts"],
            }
        )
    )
    return tmp_path


@pytest.mark.parametrize("surface", ["node", "browser"])
def test_compiler_rejects_public_default_and_accepts_body_only_edits(tmp_path: Path, surface: str):
    root = js_root(tmp_path)
    before = inventory.inspect_javascript(root)
    path = root / ("packages/xy-node/src/index.js" if surface == "node" else "js/src/60_entries.ts")
    source = path.read_text()
    path.write_text(source.replace("width + 1", "width + 2"))
    body = inventory.inspect_javascript(root)
    assert before["surfaces"] == body["surfaces"]
    path.write_text(source.replace("= 640", "= 800"))
    changed = inventory.inspect_javascript(root)
    assert before["surfaces"][surface] != changed["surfaces"][surface]
    assert "<repo>" not in json.dumps(changed["surfaces"]) or str(root) not in json.dumps(
        changed["surfaces"]
    )


def test_snapshot_contract_hash_cannot_be_relabelled():
    expected = snapshot({"declaration": "original"})
    expected["contracts"]["declaration"] = "changed without recording the hash"
    assert inventory.compare(expected, snapshot({"declaration": "original"})) == [
        "API inventory snapshot contract hash is invalid"
    ]


def test_checked_in_inventory_matches_current_declarations():
    expected = json.loads((inventory.ROOT / inventory.SNAPSHOT).read_text())
    actual = inventory.collect()
    assert inventory.compare(expected, actual) == []
    assert expected["acceptance"] == "preparation-only-not-a-freeze"
    assert expected["gaps"]
    assert inventory.SNAPSHOT.as_posix() not in expected["sourceSha256"]


def test_named_literal_python_default_is_part_of_the_contract(root_path: Path):
    source = "DEFAULT_WIDTH = 640\n" + BASE_PYTHON.replace("= 640", "= DEFAULT_WIDTH")
    expected = snapshot({"surface": python_surface(root_path, source)})
    actual = snapshot(
        {
            "surface": python_surface(
                root_path, source.replace("DEFAULT_WIDTH = 640", "DEFAULT_WIDTH = 800")
            )
        }
    )
    assert inventory.compare(expected, actual)


def test_existing_types_do_not_hide_changed_runtime_javascript_defaults(tmp_path: Path):
    root = js_root(tmp_path)
    node = root / "packages/xy-node/src"
    (node / "index.js").write_text('export { build } from "./builder.js";\n')
    (node / "builder.d.ts").write_text("export declare function build(width?: number): number;\n")
    runtime = node / "builder.js"
    runtime.write_text("export function build(width = 640) { return width; }\n")
    before = inventory.inspect_javascript(root)["surfaces"]["node"]
    assert before[0]["runtimeParameters"] == ["width = 640"]
    runtime.write_text("export function build(width = 800) { return width; }\n")
    after = inventory.inspect_javascript(root)["surfaces"]["node"]
    assert before != after


def test_arrow_function_defaults_are_not_hidden_in_variable_exports(tmp_path: Path):
    root = js_root(tmp_path)
    runtime = root / "packages/xy-node/src/index.js"
    runtime.write_text("export const build = (width = 640) => width;\n")
    before = inventory.inspect_javascript(root)["surfaces"]["node"]
    runtime.write_text("export const build = (width = 800) => width;\n")
    assert before != inventory.inspect_javascript(root)["surfaces"]["node"]


def test_acceptance_mode_rejects_unclassified_public_configuration(monkeypatch, capsys):
    monkeypatch.setattr(
        inventory,
        "collect",
        lambda: {
            "contracts": {
                "surfaces": {},
                "environmentVariables": [{"name": "XYG_BROWSER", "status": "unclassified"}],
            }
        },
    )
    assert inventory.main(["--require-classified"]) == 1
    assert "environment.XYG_BROWSER" in capsys.readouterr().err


def test_rust_runtime_switches_are_inventoried_but_test_fixtures_are_not(tmp_path: Path):
    (tmp_path / "hatch_build.py").write_text("")
    source = tmp_path / "crates/xyg-engine/src"
    source.mkdir(parents=True)
    (source / "simd.rs").write_text(
        'pub fn enabled() { std::env::var_os("XYG_SIMD").is_none_or(|v| v != "0"); }\n#[cfg(test)] mod tests { fn fixture() { std::env::var("XYG_TEST_ONLY"); } }\n'
    )
    result = inventory.environment_inventory(tmp_path, inventory.PythonInventory(tmp_path))
    assert [item["name"] for item in result] == ["XYG_SIMD"]
    assert 'v != "0"' in result[0]["lookups"][0]["expression"]


@pytest.mark.parametrize("typed", [False, True])
@pytest.mark.parametrize(
    "declaration",
    [
        "export function build(width = DEFAULT_WIDTH) { return width; }",
        "export const build = (width = DEFAULT_WIDTH) => { return width; };",
    ],
)
def test_named_javascript_default_bindings_survive_types_and_body_only_edits(
    tmp_path: Path, typed: bool, declaration: str
):
    root = js_root(tmp_path)
    node = root / "packages/xy-node/src"
    (node / "index.js").write_text('export { build } from "./builder.js";\n')
    if typed:
        (node / "builder.d.ts").write_text(
            "export declare function build(width?: number): number;\n"
        )
    runtime = node / "builder.js"
    source = "const DEFAULT_WIDTH = 640;\n" + declaration + "\n"
    runtime.write_text(source)
    before = inventory.inspect_javascript(root)["surfaces"]["node"]
    binding_key = "packages/xy-node/src/builder.js#DEFAULT_WIDTH"
    if typed:
        assert before[0]["runtimeDefaultBindings"] == {binding_key: "640"}
    else:
        assert before[0]["declarations"][0]["literalDefaultBindings"] == {binding_key: "640"}
    runtime.write_text(source.replace("return width;", "return width + 0;"))
    body = inventory.inspect_javascript(root)["surfaces"]["node"]
    assert inventory.compare(snapshot({"surface": before}), snapshot({"surface": body})) == []
    runtime.write_text(source.replace("DEFAULT_WIDTH = 640", "DEFAULT_WIDTH = 800"))
    changed = inventory.inspect_javascript(root)["surfaces"]["node"]
    assert inventory.compare(snapshot({"surface": before}), snapshot({"surface": changed}))
