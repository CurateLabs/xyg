"""Record exact test/harness/fixture inputs beside the retained raw proof."""

import hashlib
import json
from pathlib import Path

receipt = Path(__file__).resolve().parent
paths = [
    "scripts/graph_session_controller_wasm_smoke.mjs",
    "scripts/graph_session_gpu_paint_smoke.mjs",
    "scripts/gen_graph_session_fixture.py",
    "scripts/wasm_foundation_smoke.mjs",
    "tests/browser/wasm_foundation_page.mjs",
    "tests/browser/graph_session_controller_page.mjs",
    "tests/browser/graph_session_encoder_test.mjs",
    "js/test/graph-session-controller-wire.test.mjs",
    "js/test/graph-session-gpu.test.mjs",
    "packages/xy-node/test/graph-session-wire.test.mjs",
    "js/test/package-wasm-contract.test.mjs",
    "js/test/package-wasm-manifest.test.mjs",
]
paths += [str(p) for p in Path("tests/fixtures/graphforge").rglob("*") if p.is_file()]
files = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(set(paths))}
with (receipt / "proof-inputs.json").open("x") as stream:
    json.dump({"files": files}, stream, indent=2)
    stream.write("\n")
print(f"recorded {len(files)} exact proof input hashes")
