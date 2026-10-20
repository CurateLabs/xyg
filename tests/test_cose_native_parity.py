"""Native Python CoSE positions match the committed cross-host golden bit-for-bit.

``golden.json`` is shared with the Node native and direct-WASM tests
(``packages/xy-node/test/cose-wasm-parity.test.mjs``); the tolerance policy is
bitwise equality of the f64 position and alpha checkpoints (spec/design/
graph-mark.md, "CoSE cross-host parity").
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT / "tests/fixtures/graphforge/cose-parity/golden.json").read_text())

_spec = importlib.util.spec_from_file_location(
    "gen_cose_parity_golden", ROOT / "scripts" / "gen_cose_parity_golden.py"
)
assert _spec is not None and _spec.loader is not None
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)


def test_golden_covers_compound_disconnected_and_both_repulsion_tiers() -> None:
    names = {case["name"] for case in GOLDEN["cases"]}
    assert {"compound", "disconnected", "random-200-exact-tier"} <= names
    assert any(n.startswith("random-700-grid-tier") for n in names)
    assert GOLDEN["schedule"] == _gen.SCHEDULE


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["name"])
def test_native_python_matches_golden_bitwise(case: dict) -> None:
    fixture = {k: v for k, v in case.items() if k != "expected"}
    got = _gen.run_native(fixture)
    assert got["checkpoints"] == case["expected"]["checkpoints"]
    assert got["x"] == case["expected"]["x"]
    assert got["y"] == case["expected"]["y"]
