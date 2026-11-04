"""Bind R2 harnesses, source, command logs and unchanged historical receipt paths."""

import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
base = "b0de6a55814f7c799d551c40fbd5c82227707cd3"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


artifacts = json.loads((receipt / "artifacts.json").read_text())
for field in ("sourceInputs", "artifacts"):
    for path, value in artifacts[field].items():
        expected = value if isinstance(value, str) else value["sha256"]
        assert sha(Path(path).read_bytes()) == expected, path
paths = subprocess.check_output(["git", "diff", "--name-only", base]).decode().splitlines()
paths += [
    "scripts/wasm_foundation_smoke.mjs",
    "tests/browser/wasm_foundation_page.mjs",
    "js/test/package-wasm-contract.test.mjs",
    "js/test/package-wasm-manifest.test.mjs",
    "spec/wasm/abi.json",
    str(receipt.relative_to(Path.cwd()) / "capture-artifacts.mjs"),
    str(receipt.relative_to(Path.cwd()) / "capture-proof.py"),
    str(receipt.relative_to(Path.cwd()) / "run.py"),
]
files = {
    path: sha(Path(path).read_bytes())
    for path in sorted(set(paths))
    if not path.startswith("spec/performance/") or path.endswith((".mjs", ".py"))
}
commands = {}
for command in sorted(receipt.glob("*.command.json")):
    obj = json.loads(command.read_text())
    log = receipt / (command.name.removesuffix(".command.json") + ".log")
    assert sha(log.read_bytes()) == obj["log_sha256"], log
    commands[command.name] = {
        "exit": obj["exit"],
        "recordSha256": sha(command.read_bytes()),
        "logSha256": obj["log_sha256"],
    }
historical = (
    subprocess.check_output(["git", "diff", "--name-only", base, "--", "spec/performance/"])
    .decode()
    .splitlines()
)
assert not historical, historical
nonreceipt = subprocess.check_output(
    ["git", "diff", "--binary", "--full-index", base, "--", ".", ":(exclude)spec/performance/**"]
)
fixture_changes = (
    subprocess.check_output(["git", "diff", "--name-only", base, "--", "tests/fixtures/"])
    .decode()
    .splitlines()
)
assert not fixture_changes, fixture_changes
prior_proof = Path("spec/performance/graph-s5b-attachment-2026-11-04/proof-inputs.json")
value = {
    "base": base,
    "priorReviewedFixtureProof": {
        "path": str(prior_proof),
        "sha256": sha(prior_proof.read_bytes()),
        "fixtureChangesSinceBase": fixture_changes,
    },
    "files": files,
    "commands": commands,
    "allPriorReceiptTrackedFilesUnchanged": True,
    "newReceiptIsSeparate": str(receipt.relative_to(Path.cwd())),
    "r2NonreceiptDiffSha256": sha(nonreceipt),
    "wholeFinalHash": "Emitted at committed handoff; storing a hash inside its own complete diff would be self-referential.",
}
with (receipt / "proof-inputs.json").open("x") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
print(
    f"verified {len(artifacts['sourceInputs'])} build inputs and {len(artifacts['artifacts'])} artifacts"
)
print(f"bound {len(files)} source/proof files and {len(commands)} exact command/log pairs")
print(f"R2 nonreceipt diff sha256: {value['r2NonreceiptDiffSha256']}")
