"""Validate retained evidence and unchanged history without modifying either."""

import gzip
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RECEIPT = Path(__file__).resolve().parent
BASE = "80af7df777562605b7ce0bea240c3538a7ebfca7"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(name: str) -> dict:
    return json.loads((RECEIPT / name).read_text())


def original(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT)


def main() -> None:
    history = load("history-before.json")
    for name, digest in history.items():
        assert sha((ROOT / name).read_bytes()) == digest, f"historical file changed: {name}"

    changed = subprocess.check_output(
        ["git", "diff", "--name-only", BASE, "--", "crates", "js", "python", "packages"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    assert sorted(changed) == sorted(
        [
            "crates/xyg-engine/src/coordination.rs",
            "crates/xyg-engine/src/graphforge/interaction/paint.rs",
            "crates/xyg-engine/src/graphforge/interaction/tests/pick.rs",
            "js/package-wasm.mjs",
        ]
    ), changed
    gate = "crates/xyg-engine/src/coordination.rs"
    assert (ROOT / gate).read_bytes().replace(b"    #[inline]\n", b"", 1) == original(gate)
    for name in [
        "crates/xyg-engine/src/graphforge/interaction/coordination.rs",
        "crates/xyg-engine/src/graphforge/interaction/update.rs",
        "crates/xyg-engine/src/edge_route.rs",
        "scripts/wasm_foundation_smoke.mjs",
        "tests/browser/wasm_foundation_page.mjs",
        "spec/wasm/abi.json",
    ]:
        assert (ROOT / name).read_bytes() == original(name), f"shared contract changed: {name}"

    source = load("source-final.json")
    for name, digest in source.items():
        assert sha((ROOT / name).read_bytes()) == digest, f"final source changed: {name}"
    build_source = load("source-final-build.json")
    build_inputs = [name for name in build_source if not name.startswith("spec/")]
    for name in build_inputs:
        assert source[name] == build_source[name], f"build input changed after proof: {name}"

    commands = []
    allowed_failures = {
        "baseline-repro-build": 1,
        "regression-before": 101,
        "regression-before-compiled": 101,
        "focused-final": 101,
        "environment": 1,
    }
    for path in sorted(RECEIPT.glob("*.command.json")):
        command = json.loads(path.read_text())
        packed = (RECEIPT / command["log"]).read_bytes()
        assert sha(packed) == command["gzipSha256"], path
        assert sha(gzip.decompress(packed)) == command["rawSha256"], path
        assert command["exitCode"] == allowed_failures.get(command["name"], 0), path
        commands.append(command)

    artifact = load("artifact.json")
    assert artifact["node"] == "v22.23.4"
    assert artifact["rawGate"] == 1513 * 1024 and artifact["gzipGate"] == 626 * 1024
    assert artifact["rawHeadroom"] == artifact["rawGate"] - artifact["rawBytes"] >= 0
    assert artifact["gzipHeadroom"] == artifact["gzipGate"] - artifact["gzip6Bytes"] >= 0
    for name, binding in artifact["files"].items():
        data = (ROOT / name).read_bytes()
        assert len(data) == binding["bytes"] and sha(data) == binding["sha256"], name
    assert sha((ROOT / artifact["source"]).read_bytes()) == artifact["sourceSha256"]
    assert (
        sha((RECEIPT / artifact["sourceManifest"]).read_bytes()) == artifact["sourceManifestSha256"]
    )
    assert (RECEIPT / "packaged-wasm.manifest.json").read_bytes() == (
        ROOT / "packages/xy-client/dist/xyg-wasm.manifest.json"
    ).read_bytes()

    foundation = load("browser-foundation.json")
    assert foundation["status"] == "passed" and foundation["scope"] == "full-foundation"
    assert foundation["artifactSource"] == "source-dist" and foundation["artifactCommit"] is None
    assert foundation["externalRequests"] == [] and foundation["node"] == "v22.23.4"
    assert foundation["assets"]["xyg-wasm.wasm"]["sha256"] == artifact["sha256"]
    assert foundation["csp"] == (
        "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; "
        "worker-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'"
    )
    for name, binding in foundation["assets"].items():
        data = (ROOT / "packages/xy-client/dist" / name).read_bytes()
        assert sha(data) == binding["sha256"] and len(data) == binding["bytes"]
    for name, digest in foundation["harness"].items():
        assert sha((ROOT / name).read_bytes()) == digest == sha(original(name))
    screenshots = foundation["densityNoRefinement"]
    assert len(screenshots) == 6
    for scenario in screenshots:
        binding = scenario["screenshot"]
        data = (RECEIPT / binding["file"]).read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n") and sha(data) == binding["sha256"]

    provenance = load("node-module-provenance.json")
    native = Path(provenance["nativeLibraryPath"]).read_bytes()
    assert provenance["node"] == "v22.23.4" and provenance["nativeAbi"] == 396
    assert (
        sha(native)
        == provenance["nativeSha256"]
        == load("environment.json")["files"]["target/release/libxyg_core.so"]["sha256"]
    )

    inventory_path = "spec/releases/0.6.0-api-inventory.json"
    inventory = json.loads((ROOT / inventory_path).read_bytes())
    before_inventory = json.loads(original(inventory_path))
    for key in ["acceptance", "contracts", "gaps", "contractSha256"]:
        assert inventory[key] == before_inventory[key], f"inventory {key} changed"

    print(
        json.dumps(
            {
                "historicalFilesUnchanged": len(history),
                "finalSourceHashes": len(source),
                "buildInputsUnchangedSinceProof": len(build_inputs),
                "commandLogPairsVerified": len(commands),
                "incrementalProductFiles": changed,
                "wholeS3IndependentReview": "pending parent-owned final re-review",
                "inventoryAcceptanceAndContractsAndGaps": "unchanged",
                "fullFoundation": "passed source-dist, null artifactCommit, zero external requests",
                "screenshotHashesVerified": len(screenshots),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
