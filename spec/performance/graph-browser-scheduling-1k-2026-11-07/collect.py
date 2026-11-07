import hashlib
import json
import platform
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

root = Path.cwd()
out = root / "spec/performance/graph-browser-scheduling-1k-2026-11-07"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


paths = subprocess.check_output(
    [
        "git",
        "ls-files",
        "crates",
        "js",
        "Cargo.lock",
        "Cargo.toml",
        "rust-toolchain.toml",
        "package.json",
        "package-lock.json",
        "scripts/graph_session_controller_wasm_smoke.mjs",
        "scripts/wasm_foundation_smoke.mjs",
        "tests/browser/graph_session_controller_page.mjs",
        "spec/wasm/abi.json",
    ],
    text=True,
).splitlines()
inputs = {p: sha(root / p) for p in paths if (root / p).is_file()}
(out / "producer-inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
artifacts = {}
for p in [
    "target/wasm32-unknown-unknown/release/xyg_wasm.wasm",
    "packages/xy-client/dist/index.js",
    "packages/xy-client/dist/wasm-worker.js",
    "packages/xy-client/dist/xyg-wasm.wasm",
    "packages/xy-client/dist/xyg-wasm.manifest.json",
]:
    f = root / p
    artifacts[p] = {"sha256": sha(f), "bytes": f.stat().st_size}
node = "/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin/node"
size = json.loads(
    subprocess.check_output(
        [
            node,
            "-e",
            "const f=require('fs'),z=require('zlib'),b=f.readFileSync('packages/xy-client/dist/xyg-wasm.wasm');console.log(JSON.stringify({raw:b.length,gzip6:z.gzipSync(b,{level:6}).length}))",
        ],
        text=True,
    )
)
env = {
    "workspace": str(root),
    "branch": subprocess.check_output(["git", "branch", "--show-current"], text=True).strip(),
    "dispatchBase": "74195403ccd18c760e3d20a18f024daab95d711a",
    "acceptedMain": "80e841542462eaf5509ac90e1f17a80cae974164",
    "mergeBase": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "testPython": sys.version,
    "systemPython": subprocess.check_output(["/usr/bin/python3", "--version"], text=True).strip(),
    "platform": platform.platform(),
    "node": subprocess.check_output([node, "--version"], text=True).strip(),
    "chromium": "/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome",
    "cargoBuildJobs": 2,
    "artifacts": artifacts,
    "wasmSize": size,
    "producerInputsSha256": sha(out / "producer-inputs.json"),
}
(out / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
r = json.loads((out / "final-isolation.json").read_text())
summary = {"refusals": r["refusals"], "views": []}
for p in r["views"]:
    frames = p["painted"]
    intervals = [b["at"] - a["at"] for a, b in pairwise(frames)]
    beats = p["heartbeats"]
    admitted = [c for c in p["clicks"] if c["prevented"]]
    latency = [
        s["at"] - max(c["at"] for c in admitted if c["at"] <= s["at"])
        for s in p["selections"]
        if any(c["at"] <= s["at"] for c in admitted)
    ]
    summary["views"].append(
        {
            "id": p["id"],
            "arena": p["arena"],
            "workerStartupMs": p["workerReady"] - p["started"],
            "initialPublicationMs": p["frames"][0]["at"] - p["started"],
            "firstPixelSampleMs": frames[0]["at"] - p["started"],
            "paintedSamples": len(frames),
            "distinctPaintHashes": len(set(f["hash"] for f in frames)),
            "unfinishedPaintedSteps": len(
                set(
                    f["progress"]["steps"]
                    for f in frames
                    if not f["progress"]["done"] and f["pixels"]
                )
            ),
            "maxPaintIntervalMs": max(intervals),
            "maxHeartbeatGapMs": max(b - a for a, b in pairwise(beats)),
            "pickReplyLatencyMs": latency,
            "hostPanLatencyMs": [e["returned"] - e["at"] for e in p["pans"] if "after" in e],
            "payloadBytes": p["payloadBytes"],
            "cleanupMs": p["cleanupMs"],
            "finalSteps": p["frames"][-1]["progress"]["steps"],
        }
    )
(out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
