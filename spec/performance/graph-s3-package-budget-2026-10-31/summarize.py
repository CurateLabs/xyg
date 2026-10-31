"""Index completed proof logs and artifact hashes without rerunning any check."""

import hashlib
import json
from pathlib import Path

receipt = Path(__file__).resolve().parent
commands = [json.loads(path.read_text()) for path in sorted(receipt.glob("*.command.json"))]
files = {
    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(receipt.iterdir())
    if path.is_file() and path.name not in {"results.json", "evidence-files.json"}
}
(receipt / "evidence-files.json").write_text(json.dumps(files, indent=2) + "\n")
results = {
    "status": "local implementation and package proofs passed; final independent review and CI pending",
    "historicalDisposition": "two candidates rejected/reverted by child; historical receipts unchanged",
    "parentDecision": "retain only inline validate hint; raw limit 1513 KiB, gzip unchanged 626 KiB",
    "s2Base": "d47968e1eb66f269ffe7c610fb282ac5da371c7b",
    "s3RepairBase": "80af7df777562605b7ce0bea240c3538a7ebfca7",
    "normalMerge": "91345354905348592effad4eaecb493b4a72fee7",
    "beforeRegression": {"failed": 2, "passed": 22, "log": "regression-before-compiled.txt.gz"},
    "finalChecks": {
        "workspace": {"engine": 1782, "core": 58, "wasm": 65, "integration": 5},
        "graphInteraction": 101,
        "pick": 24,
        "outlineAudit": 3,
        "temporalController": 13,
        "pythonNative": {"passed": 134, "deselectedBrowser": 4},
        "nodeNative": {"passed": 136, "skipped": 0},
        "nodePackaged": {"passed": 51, "skipped": 0},
        "nativeAbi": {"symbols": 529, "version": 396, "smokeChecks": 673},
        "clippy": "workspace all targets, deny warnings, passed",
        "fullStrictCspFoundation": "passed; original harness, actual source-dist package",
        "temporalActualWasm": "full foundation state, playback, delivery, stale/self-echo, lifecycle",
        "temporalActualNativeAbi": "Python and Node temporal/controller/graph tests",
        "goldensAndRenderAppend": "passed unchanged fixtures",
        "independentFinalReview": "required whole integrated S3; pending parent",
        "remoteCi": "pending",
    },
    "artifact": json.loads((receipt / "artifact.json").read_text()),
    "artifactCommit": None,
    "fullFoundationReport": {
        "file": "browser-foundation.json",
        "sha256": files["browser-foundation.json"],
        "screenshotCount": 6,
    },
    "sourceBuildManifest": {
        "file": "source-final-build.json",
        "sha256": files["source-final-build.json"],
    },
    "sourceFinalManifest": {"file": "source-final.json", "sha256": files["source-final.json"]},
    "historicalFiles": 2003,
    "evidenceFiles": files,
    "commands": commands,
    "limitations": [
        "Local software-rendered correctness only; no new benchmark or speed claim.",
        "No full multi-hour Python suite, unrelated geo diagnostics or blanket Rust formatting.",
        "No session ABI exports, host/controller completion, wheel/registry/platform acceptance.",
        "No #36, M4, #108 or release completion; final independent review and CI remain pending.",
    ],
}
(receipt / "results.json").write_text(json.dumps(results, indent=2) + "\n")
print(f"Indexed {len(commands)} exact command/log pairs and {len(files)} evidence files.")
