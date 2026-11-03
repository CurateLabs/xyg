"""Bind combined browser evidence to exact sources, artifacts and old receipts."""

import gzip
import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
base = "6997e767a01b97381f3334392c06d0c48ed17ae6"
child = "a95f7e91d9f69787dc9aab98114dd968918e402f"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=root)


def sha(data):
    return hashlib.sha256(data).hexdigest()


history = {}
for commit in (base, child):
    listing = git("ls-tree", "-r", commit, "--", "spec/performance")
    for line in listing.decode().splitlines():
        metadata, name = line.split("\t", 1)
        raw = (root / name).read_bytes()
        blob = b"blob " + str(len(raw)).encode() + b"\0" + raw
        assert hashlib.sha1(blob).hexdigest() == metadata.split()[2], name
    history[commit] = {"files": len(listing.splitlines()), "listingSha256": sha(listing)}

for name in git("ls-tree", "-r", "--name-only", base, "--", "crates").decode().splitlines():
    assert (root / name).read_bytes() == git("show", f"{base}:{name}"), name
for name in git("ls-tree", "-r", "--name-only", child, "--", "js/src").decode().splitlines():
    assert (root / name).read_bytes() == git("show", f"{child}:{name}"), name
for name in ("js/package-wasm.mjs", "Cargo.toml", "Cargo.lock", ".cargo/config.toml"):
    assert (root / name).read_bytes() == git("show", f"{base}:{name}"), name

module = json.loads((receipt / "module.json").read_text())
assert module["source"] == "production-dist" and module["diagnosticModule"] is False
assert module["sha256"] == "717440524b63cf87e0127161c128c4f81efdca87e5112f9b05a42e820b456fde"
assert module["rawLimit"] == 1838 * 1024 and module["gzip6Limit"] == 751 * 1024
assets = ["target/release/libxyg_core.so"]
for name in (
    "index.js",
    "standalone.js",
    "wasm-worker.js",
    "xyg-wasm.wasm",
    "xyg-wasm-inline.js",
    "xyg-wasm.manifest.json",
):
    node, python = f"packages/xy-client/dist/{name}", f"python/xyg/static/{name}"
    assert (root / node).read_bytes() == (root / python).read_bytes(), name
    assets.extend((node, python))
assert (
    sha((root / assets[0]).read_bytes())
    == "6df9cb7ed06048d08d59ec8c068da0e0be9b5a3eb6b10d1b86f08527a8fd2485"
)
assert (
    sha((root / "packages/xy-client/dist/index.js").read_bytes())
    == "b2c2066b1d6ed2687a1a248c3f7e8eb1541d4bf6a39ae56a75a99968b5a13f6b"
)

property_result = json.loads((receipt / "property/browser.json").read_text())
assert [v["label"] for v in property_result["failures"]] == [
    f"{theme}: scene_vs_initial_native pixels" for theme in ("light", "dark")
]
for theme in ("light", "dark"):
    assert property_result["pixels"][theme]["wasm_scene"]["passed"]
helper = "tests/browser/graph_property_default_export.mjs"
assert (root / helper).read_bytes() == git("show", f"{child}:{helper}")

canonical = json.loads((receipt / "canonical-proof.json").read_text())
assert canonical["status"] == "PASS" and canonical["native_svg_plot_cases"] == 111
assert canonical["actual_svg_spines_checked"] == 276
focused = json.loads((receipt / "after/observations.json").read_text())
assert not focused["failures"] and not focused["skipped"]
assert len(focused["cases"]) == len(focused["switches"]) == 12
pixels = json.loads((receipt / "after-pixels.json").read_text())
assert all(v["different_pixels"] == 0 for v in pixels["comparisons"].values())
slots = json.loads((receipt / "slots/observations.json").read_text())
assert len(slots["cases"]) == 144 and not slots["failures"]
foundation = json.loads((receipt / "foundation.json").read_text())
assert foundation["scope"] == "full-foundation" and foundation["status"] == "passed"
assert foundation["artifactCommit"] is None and foundation["externalRequests"] == []
assert len(foundation["densityNoRefinement"]) == 6
for case in foundation["densityNoRefinement"]:
    shot = case["screenshot"]
    assert sha((receipt / shot["file"]).read_bytes()) == shot["sha256"]

commands = {}
for path in sorted(receipt.glob("*.command.json")):
    record = json.loads(path.read_text())
    packed = (receipt / record["log"]).read_bytes()
    raw = gzip.decompress(packed)
    assert sha(packed) == record["gzipSha256"] and sha(raw) == record["rawSha256"]
    commands[path.name] = record
names = git("diff", "--name-only", base).decode().splitlines()
sources = {
    name: sha((root / name).read_bytes())
    for name in names
    if not name.startswith("spec/performance/") and (root / name).is_file()
}
result = {
    "base": base,
    "child": child,
    "artifactCommit": None,
    "scope": "Resolved Scene browser repair; native presentation and release acceptance remain open",
    "sources": sources,
    "nonreceiptDiffSha256": sha(
        git("diff", "--binary", "--full-index", base, "--", ".", ":!spec/performance")
    ),
    "historicalReceipts": history,
    "artifacts": {
        name: {"bytes": (root / name).stat().st_size, "sha256": sha((root / name).read_bytes())}
        for name in assets
    },
    "module": module,
    "property": property_result,
    "canonical": canonical,
    "commands": commands,
}
(receipt / "evidence.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {"sources": len(sources), "commands": len(commands), "history": history, "module": module}
    )
)
