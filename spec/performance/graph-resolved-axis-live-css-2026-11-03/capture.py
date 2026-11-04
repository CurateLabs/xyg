"""Bind the final source diff, actual shipping assets and complete raw evidence."""

import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
out = Path(__file__).resolve().parent
base = "e768ce25194bf3ebcc1a0de1df37696da3948295"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_record(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": sha(data)}


sources = [
    "js/src/50_chartview.ts",
    "spec/design/browser-wasm.md",
    "tests/browser/resolved_axis_live_css.mjs",
    "tests/test_static_client_security.py",
    "tests/browser/resolved_axis_spines.mjs",
    "tests/browser/resolved_axis_slots.mjs",
    "tests/browser/resolved_axis_precision.mjs",
    "tests/browser/resolved_axis_eligibility.mjs",
    "tests/browser/graph_property_default_export.mjs",
]
for name in sources[4:]:
    assert (root / name).read_bytes() == subprocess.check_output(["git", "show", f"{base}:{name}"])
assert (
    subprocess.check_output(
        ["git", "diff", base, "--", "crates", "Cargo.toml", "Cargo.lock", "rust-toolchain.toml"]
    )
    == b""
)
for name, expected in json.loads((out / "history-snapshot.json").read_text()).items():
    assert sha((root / name).read_bytes()) == expected, name
artifacts = {}
for name in (
    "target/release/libxyg_core.so",
    "packages/xy-client/dist/index.js",
    "packages/xy-client/dist/standalone.js",
    "packages/xy-client/dist/wasm-worker.js",
    "packages/xy-client/dist/xyg-wasm.wasm",
    "packages/xy-client/dist/xyg-wasm-inline.js",
    "packages/xy-client/dist/xyg-wasm.manifest.json",
    "python/xyg/static/index.js",
    "python/xyg/static/standalone.js",
    "python/xyg/static/wasm-worker.js",
    "python/xyg/static/xyg-wasm.wasm",
    "python/xyg/static/xyg-wasm-inline.js",
    "python/xyg/static/xyg-wasm.manifest.json",
    "target/task-tmp/before-index.js",
    "target/task-tmp/resolved-spine-188f-baseline/packages/xy-client/dist/index.js",
):
    artifacts[name] = file_record(root / name)
for name in (
    "index.js",
    "standalone.js",
    "wasm-worker.js",
    "xyg-wasm.wasm",
    "xyg-wasm-inline.js",
    "xyg-wasm.manifest.json",
):
    assert (root / "packages/xy-client/dist" / name).read_bytes() == (
        root / "python/xyg/static" / name
    ).read_bytes()
assert (
    artifacts["target/release/libxyg_core.so"]["sha256"]
    == "6df9cb7ed06048d08d59ec8c068da0e0be9b5a3eb6b10d1b86f08527a8fd2485"
)
assert (
    artifacts["packages/xy-client/dist/xyg-wasm.wasm"]["sha256"]
    == "717440524b63cf87e0127161c128c4f81efdca87e5112f9b05a42e820b456fde"
)
assert (
    artifacts["target/task-tmp/before-index.js"]["sha256"]
    == "b2c2066b1d6ed2687a1a248c3f7e8eb1541d4bf6a39ae56a75a99968b5a13f6b"
)
module = (root / "packages/xy-client/dist/xyg-wasm.wasm").read_bytes()
module_info = json.loads((out / "module.json").read_text())
assert len(module) == module_info["bytes"] == 1881508
assert module_info["sha256"] == sha(module)
assert module_info["gzip6Bytes"] == 768134
commands = {}
for p in sorted(out.glob("*.command.json")):
    record = json.loads(p.read_text())
    packed = (out / record["log"]).read_bytes()
    raw_path = out / f"{record['name']}.txt"
    raw = raw_path.read_bytes() if raw_path.exists() else gzip.decompress(packed)
    assert sha(raw) == record["rawSha256"] and sha(packed) == record["gzipSha256"]
    assert gzip.decompress(packed) == raw
    commands[record["name"]] = {
        "argv": record["command"],
        "exitCode": record["exitCode"],
        "recordSha256": sha(p.read_bytes()),
    }
before = json.loads((out / "proof-before/observations.json").read_text())
after = json.loads((out / "proof-after/observations.json").read_text())
reference = json.loads((out / "html-reference/observations.json").read_text())
assert len(before["cases"]) == len(after["cases"]) == len(reference["cases"]) == 60
assert before["failures"] and not after["failures"] and not reference["failures"]
assert after["asset"]["sha256"] == artifacts["packages/xy-client/dist/index.js"]["sha256"]
property_result = json.loads((out / "property/browser.json").read_text())
assert len(property_result["failures"]) == 2
assert {r["label"] for r in property_result["failures"]} == {
    "light: scene_vs_initial_native pixels",
    "dark: scene_vs_initial_native pixels",
}
for theme in ("light", "dark"):
    assert property_result["pixels"][theme]["wasm_scene"]["passed"]
paths = sources[:4]
# Stage new source files before this capture. Receipts are intentionally
# excluded to avoid self-referential digests; the parent also receives the
# canonical binary/full-index digest for the entire committed diff.
diff = subprocess.check_output(
    ["git", "diff", "--cached", "--binary", "--full-index", base, "--", *paths]
)
assert diff and b"resolved_axis_live_css.mjs" in diff
result = {
    "base": base,
    "artifactCommit": None,
    "review": "New independent final review remains parent-owned; this is implementation evidence only",
    "nativeWasmSourcesAndBuildInputsUnchanged": True,
    "sources": {name: file_record(root / name) for name in sources},
    "receiptTools": {p.name: file_record(p) for p in sorted(out.glob("*.py"))}
    | {p.name: file_record(p) for p in sorted(out.glob("*.mjs"))},
    "nonreceiptBinaryFullIndexDiffSha256": sha(diff),
    "artifacts": artifacts,
    "module": {
        "bytes": len(module),
        "gzip6Bytes": module_info["gzip6Bytes"],
        "diagnosticModule": False,
        "rawLimit": 1882112,
        "gzip6Limit": 769024,
    },
    "commands": commands,
    "regression": {
        "beforeFailures": before["failures"],
        "afterFailures": after["failures"],
        "referenceFailures": reference["failures"],
        "capturesPerLane": 60,
    },
    "untouchedPropertyHelper": {
        "exitCode": commands["property-browser-ready"]["exitCode"],
        "pixels": property_result["pixels"],
        "failures": property_result["failures"],
    },
    "screenshots": {str(p.relative_to(out)): file_record(p) for p in sorted(out.rglob("*.png"))},
}
destination = out / (sys.argv[1] if len(sys.argv) > 1 else "evidence.json")
assert not destination.exists(), "append-only: use a fresh evidence filename"
destination.write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            "status": "PASS",
            "nonreceiptBinaryFullIndexDiffSha256": sha(diff),
            "screenshots": len(result["screenshots"]),
            "module": result["module"],
        },
        indent=2,
    )
)
