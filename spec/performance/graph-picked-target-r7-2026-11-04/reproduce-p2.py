"""Reproduce the reviewer's production-module omission without editing the repo."""

import importlib.util
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("inventory", "scripts/check_release_inventory.py")
assert spec and spec.loader
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / "hatch_build.py").write_text("")
    source = root / "crates/xyg-engine/src"
    (source / "tests").mkdir(parents=True)
    (source / "lib.rs").write_text("pub mod tests;\npub mod live;\n")
    body = 'pub fn enabled() { std::env::var("XYG_PRODUCTION_UNDER_TESTS"); }\n'
    (source / "tests/mod.rs").write_text(body)
    (source / "live.rs").write_text(body)
    result = inventory.environment_inventory(root, inventory.PythonInventory(root))
    print(result)
    found = next(row for row in result if row["name"] == "XYG_PRODUCTION_UNDER_TESTS")
    paths = {lookup["source"] for lookup in found["lookups"]}
    print("paths:", sorted(paths))
    assert paths == {"crates/xyg-engine/src/live.rs", "crates/xyg-engine/src/tests/mod.rs"}
