"""Seal the local public graph scale receipt; no remote actions or old rewrites."""

import gzip
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / "spec/performance/graph-public-scale-ownership-2026-11-08"
CAPTURE = ROOT / "target/task-tmp/graph-public-scale"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pin(path):
    path = Path(path)
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "bytes": len(data),
        "sha256": digest(data),
    }


def seal(path, kind):
    path = Path(path)
    data = path.read_bytes()
    raw = pin(path)
    destination = OUT / "blobs" / (raw["sha256"] + ".gz")
    destination.parent.mkdir(exist_ok=True)
    if not destination.exists():
        destination.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
    assert gzip.decompress(destination.read_bytes()) == data
    return {"scope": kind, "raw": raw, "gzip": pin(destination)}


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main():
    changed = command("git", "diff", "HEAD", "--name-only").splitlines()
    changed += command("git", "ls-files", "--others", "--exclude-standard").splitlines()
    changed = sorted(
        {
            p
            for p in changed
            if not p.startswith("spec/performance/graph-public-scale-ownership-2026-11-08/")
            and p != "TASKS"
            and p != "TASKS.md"
        }
    )
    source = {p: digest((ROOT / p).read_bytes()) for p in changed}
    previous = ROOT / "spec/performance/graph-source-sharing-2026-11-08/current-bindings.json"
    bindings = json.loads(previous.read_text())
    bindings["parents"] = [pin(previous)] + bindings["parents"]
    bindings["predecessor"] = pin(previous)
    bindings["sourceIdentity"] = (
        "Public100k/1M phase/class ownership + Rust work admission + bounded input intent; native405/551 and WASM38/68 unchanged; full original host/M4/performance acceptance remains open"
    )
    bindings["sourceSha256"].update(source)
    write("current-bindings.json", bindings)
    logs = {
        p.name: seal(p, "raw local build/test/failure log")
        for p in sorted(Path("/var/tmp").glob("graph-next-*.log"))
    }
    captures = [
        seal(p, "raw public/foundation/export capture")
        for p in sorted(CAPTURE.rglob("*"))
        if p.is_file() and p.suffix != ".trace"
    ]
    manual = []
    for name in ["wire-phases.rs", "wire-phases-external.rs", "wire-trace.rs"]:
        src = ROOT / "target/task-tmp/graph-source-sharing" / name
        dst = OUT / name
        shutil.copyfile(src, dst)
        manual.append(pin(dst))
    manual.append(pin(OUT / "trace_inputs.py"))
    module = ROOT / "packages/xy-client/dist/xyg-wasm.wasm"
    (OUT / "shipping-module.wasm.gz").write_bytes(
        gzip.compress(module.read_bytes(), compresslevel=9, mtime=0)
    )
    for src, dst in [
        ("public100k38b.json.9101.live.png", "public100k-live.png"),
        ("public1m38b.json.9101.live.png", "public1m-live.png"),
        ("public1m38b.json.9102.initial.png", "peer-useful-initial.png"),
    ]:
        shutil.copyfile(CAPTURE / src, OUT / dst)
    artifacts = [
        pin(ROOT / p)
        for p in [
            "target/release/libxyg_core.so",
            "target/wasm32-unknown-unknown/release/xyg_wasm.wasm",
            "packages/xy-client/dist/index.js",
            "packages/xy-client/dist/standalone.js",
            "packages/xy-client/dist/wasm-worker.js",
            "packages/xy-client/dist/wasm-inline-worker.js",
            "packages/xy-client/dist/xyg-wasm.wasm",
            "packages/xy-client/dist/xyg-wasm-inline.js",
            "packages/xy-client/dist/xyg-wasm.manifest.json",
        ]
    ]
    views = {}
    for name in ["public100k38b", "public1m38b"]:
        data = json.loads((CAPTURE / (name + ".json")).read_text())
        views[name] = [
            {
                "id": v["id"],
                "sourceNodes": v["sourceNodes"],
                "sourceEdges": v["sourceEdges"],
                "arena": v["actualArena"],
                "frames": len(v["frames"]),
                "commands": len(v["replay"]),
                "progress": v["beforeDispose"]["relayout"],
                "pixels": v["pixels"],
                "bounds": v["bounds"],
                "errors": v["errors"],
                "disposed": v["disposed"],
            }
            for v in data["views"]
        ]
    write(
        "run.json",
        {
            "schema": "xyg.public-graph-scale-ownership/v1",
            "status": "BOUNDED PUBLIC100k/1M RUNGS QUALIFIED; original remaining AC retained",
            "base": command("git", "rev-parse", "HEAD"),
            "orderedParents": [command("git", "rev-parse", "HEAD")],
            "changedProductAndSpecPaths": changed,
            "sourceSha256": source,
            "bindingProducer": pin(Path(__file__).resolve()),
            "receiptReadme": pin(OUT / "README.md"),
            "diagnosticArtifacts": [
                pin(ROOT / "target/release/deps/libxyg_engine-c08e762ddb3a6e01.rlib"),
                pin(Path("/var/tmp/graph-next-wire-trace37final")),
                pin(Path("/var/tmp/graph-next-wire-external37")),
            ],
            "manualSources": manual,
            "artifacts": artifacts,
            "shippingModuleGzip": pin(OUT / "shipping-module.wasm.gz"),
            "package": json.loads(Path("/var/tmp/graph-next-artifact37.json").read_text()),
            "caps": {
                "raw": 1927168,
                "node22Gzip6": 786432,
                "browserDefault": 16777216,
                "maxLogical": 402653184,
                "forceWork": 4000000,
            },
            "nativeABI": 405,
            "nativeDeclarations": 551,
            "wasmABI": 38,
            "wasmExports": 68,
            "publicViews": views,
            "memory": {
                "nativeWireFirstRender100k": 87557574,
                "nativeWireFirstRender1M": 266629384,
                "nativeWireForce100k": 156981018,
                "nativeWireForce1M": 372154060,
                "nativeWireForceWithCallerOutput100k": 192592682,
                "nativeWireForceWithCallerOutput1M": 396758012,
                "native1MPreflightWithCallerOutput": 400020004,
                "nativeCompleteInteractionTrace100k": 192593698,
                "nativeCompleteInteractionTrace1M": 397232796,
                "nativeDefaultPeerTrace": 8761546,
                "traceRemainingOwnersAfterDispose": 0,
                "scope": "requested allocations exclude fixture/caller input baseline; active staging and caller output loans charged; WASM linear/page/RSS/GPU separate",
                "wasmLinearPublic100k": 229507072,
                "wasmLinearPublic1M": 430309376,
                "rss": "not measured",
                "gpu": "shared storage/resource accounting in reports; opaque driver memory not measured",
            },
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "node": "22.23.4",
                "rust": "1.96.0",
                "binaryen": "132",
                "chromium": "/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome",
                "tmpdir": "/var/tmp",
                "native": str(ROOT / "target/release/libxyg_core.so"),
                "pythonpath": str(ROOT / "python"),
                "pythonEnvironment": "own .venv; uv --no-sync; offline",
                "author": command("git", "var", "GIT_AUTHOR_IDENT"),
                "producer": "wasmO2/inline-threshold0/stripnone; Binaryen132 O3/all-features/reorder-functions-by-name/stripdebug; unchanged features/exports/caps",
            },
            "fresh": {
                "rustWorkspace": "68 core +1884 engine +76 WASM + allocator/integration/doc tests PASS",
                "python": "86 parity/session/ABI/scene/semantic/geometry tests PASS",
                "nativeABISmoke": "673 checks PASS",
                "broadController": "69 cases PASS, zero skips; registry and historical ABI fixture diagnosed",
                "public10k": "PASS primary/peer through convergence; exact full native/WASM replay; historical contention failure retained",
                "mandatoryHooks": "pre-commit all files, Ruff check and Ruff format --check PASS; raw logs bound",
                "normalPackage": "PASS raw and Node22 gzip6; matching native/client/WASM",
                "normalFoundation": "PASS scheduling,45 structural keyboard/camera tests, retained temporal,7 frozen PNG/offline exports,aggregate parity",
                "public100k": "PASS final package + default1k peer + trusted Tab/key/pointer/camera/later progress/cancel/dispose",
                "public1M": "PASS final package + default1k peer + trusted Tab/key/pointer/camera/later progress/cancel/dispose",
                "completeReplyReplay": "PASS full bytes + canonical state + CSR + GPU joins + opacity/LOD/pick; first uncached native complete capacity; small10 admitted;1M3-step refusal/stale/cache and closed handles",
            },
            "inheritedOnly": [
                "Original nonexecuted host matrix, accessibility/performance/competitor evidence",
                "Historical receipts remain unchanged and are not substituted for current public rendering",
            ],
            "failures": [
                "Package-size ownership/code-sharing trials retained without producer weakening",
                "100k pre-mailbox input starvation and watchdogs",
                "100k mailbox run overlapping package optimization hit unchanged watchdog; not a reliability repair",
                "Fixture observer assertions for authored button/trusted-key field and replay typed-array/aggregate zero placeholder corrected",
                "First foundation invocation used ignored CHROMIUM rather than explicit XYG_CHROMIUM and lost default-browser GL context",
                "Default1k global pick envelope refusal fixed with actual source/index class bounds and native allocator regressions",
                "Manual scale harness array-tail assumption exposed reverse Worker startup; fixed primary lookup by exact instance identity without reply ordering",
                "Keyboard capture synchronous-command assumption fixed by binding queued intent to actual command/reply, with negative structural controls",
                "Broad registry v1 fixture name corrected to actual v2; historical module is ABI35 and explicitly rejected by ABI38",
                "Historical 10k contention/watchdog failure retained in predecessor; passing rerun is not general reliability repair",
            ],
            "remainingAC": [
                "Independent Root complete-diff review, integration freshness, PR CI and merge queue",
                "Full original milestones4-7 and #35/#36/#108 remaining host/accessibility/performance/competitor acceptance",
                "Full M4 and issue closure",
                "General contention/watchdog reliability and hardware GPU/AA/other required hosts not established by a bounded SwiftShader rung",
            ],
            "remoteActions": False,
            "children": False,
            "logs": logs,
            "captures": captures,
        },
    )


if __name__ == "__main__":
    main()
