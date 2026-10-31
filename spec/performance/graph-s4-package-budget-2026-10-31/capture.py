"""Bind the S4 policy source and actual shipping artifacts without replacing history."""

import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
base = "be7eb1d012f01c56f4317646eaf32f4164adf7e9"
reviewed = "cf81b750b0067ee76052d655bfdf40f628743fde"


def command(*argv: str) -> bytes:
    return subprocess.check_output(argv, cwd=root)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


names = command("git", "diff", "--name-only", base).decode().splitlines()
sources = {
    name: digest((root / name).read_bytes())
    for name in sorted(names)
    if not name.startswith("spec/performance/") and (root / name).is_file()
}
history = command("git", "ls-tree", "-r", reviewed, "--", "spec/performance")
historical_count = 0
for line in history.decode().splitlines():
    metadata, name = line.split("\t", 1)
    mode, kind, expected = metadata.split()
    assert kind == "blob", name
    data = (root / name).read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    assert actual == expected, f"Historical evidence changed: {name}"
    historical_count += 1

artifacts = [
    "target/release/libxyg_core.so",
    "target/wasm32-unknown-unknown/release/xyg_wasm.wasm",
    "packages/xy-client/dist/index.js",
    "packages/xy-client/dist/standalone.js",
    "packages/xy-client/dist/wasm-worker.js",
    "python/xyg/static/index.js",
    "python/xyg/static/standalone.js",
    "python/xyg/static/wasm-worker.js",
]
for name in ("xyg-wasm.wasm", "xyg-wasm-inline.js", "xyg-wasm.manifest.json"):
    browser = f"packages/xy-client/dist/{name}"
    python = f"python/xyg/static/{name}"
    assert (root / browser).read_bytes() == (root / python).read_bytes(), name
    artifacts.extend([browser, python])

node = command(
    "node",
    "--input-type=module",
    "-e",
    "import fs from 'node:fs'; import {gzipSync} from 'node:zlib';"
    "import {createHash} from 'node:crypto';"
    "const b=fs.readFileSync('packages/xy-client/dist/xyg-wasm.wasm'),g=gzipSync(b);"
    "const m=new WebAssembly.Module(b),e=new WebAssembly.Instance(m).exports;"
    "console.log(JSON.stringify({node:process.version,raw:b.length,gzip6:g.length,"
    "sha256:createHash('sha256').update(b).digest('hex'),"
    "gzip6Sha256:createHash('sha256').update(g).digest('hex'),"
    "imports:WebAssembly.Module.imports(m),exports:WebAssembly.Module.exports(m),"
    "abi:e.xyg_wasm_abi_version(),scene:e.xyg_wasm_scene_version(),"
    "painter:JSON.parse(fs.readFileSync('packages/xy-client/dist/xyg-wasm.manifest.json')).painter_version}));",
)
module = json.loads(node)
assert module["node"] == "v22.23.4", module["node"]
assert module["raw"] == 1860250 and module["gzip6"] == 759008, module
assert module["sha256"] == "25ee24fdf32ee8355598cff67da44e01556d0bb2914d5cc2d4ab4a3834c1769d"
assert module["gzip6Sha256"] == "5357262c8b2999858ffbf9953a7acd6cebc97d49440abbce1781ea860a1352f9"
assert module["imports"] == []
assert sum(e["kind"] == "function" for e in module["exports"]) == 65
assert (module["abi"], module["scene"], module["painter"]) == (35, 34, 17)

foundation = json.loads((receipt / "full-foundation.json").read_text())
screenshots = {p.name: digest(p.read_bytes()) for p in sorted(receipt.glob("*.png"))}
assert len(screenshots) == 6, screenshots
patch = command("git", "diff", "--binary", "--full-index", base, "--", ".", ":!spec/performance")
record = {
    "scope": "real source-checkout shipping assets; no installed cohort or release acceptance",
    "artifactCommit": None,
    "acceptedMain": base,
    "reviewedRepair": reviewed,
    "historyMerge": "1cd5d42e1677e8ca5c50d92175597140de8ed554",
    "nonreceiptBinaryFullIndexDiffSha256": digest(patch),
    "sources": sources,
    "historicalFilesUnchanged": historical_count,
    "historicalGitTreeListingSha256": digest(history),
    "artifacts": {
        p: {"bytes": (root / p).stat().st_size, "sha256": digest((root / p).read_bytes())}
        for p in artifacts
    },
    "module": module,
    "limits": {"raw": 1817 * 1024, "gzip6": 742 * 1024},
    "headroom": {"raw": 358, "gzip6": 800},
    "foundation": foundation,
    "foundationReportSha256": digest((receipt / "full-foundation.json").read_bytes()),
    "foundationHarnessSha256": digest((root / "scripts/wasm_foundation_smoke.mjs").read_bytes()),
    "screenshots": screenshots,
    "commands": {p.name: json.loads(p.read_text()) for p in sorted(receipt.glob("*.command.json"))},
    "environment": {
        "node": module["node"],
        "rustc": command("rustc", "-Vv").decode(),
        "chromium": command(
            "/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome", "--version"
        )
        .decode()
        .strip(),
    },
}
(receipt / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
print(
    json.dumps({"sourceCount": len(sources), "historicalFiles": historical_count, "module": module})
)
