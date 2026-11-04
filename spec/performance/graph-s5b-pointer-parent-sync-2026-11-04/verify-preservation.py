"""Prove metadata-only normal merge preservation without rebuilding artifacts."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
inputs = json.loads((receipt / "merge-inputs.json").read_text())


def retain(name, value):
    path = receipt / name
    data = json.dumps(value, indent=2) + "\n"
    if path.exists():
        assert path.read_text() == data, f"refusing to overwrite {path}"
    else:
        path.write_text(data)


def git_bytes(commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=root)


def actual(path, metadata):
    file = root / path
    data = os.readlink(file).encode() if metadata["mode"] == "120000" else file.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    assert blob == metadata["blob"], path
    if metadata["mode"] in ("100644", "100755"):
        assert bool(file.stat().st_mode & 0o111) == (metadata["mode"] == "100755"), path
    return hashlib.sha256(data).hexdigest()


protected = {
    path: actual(path, metadata) for path, metadata in inputs["protectedNonReceiptPaths"].items()
}
historical = {path: actual(path, metadata) for path, metadata in inputs["historicalUnion"].items()}
tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
current_nonreceipt = {p for p in tracked if p and not p.startswith("spec/performance/")}
assert current_nonreceipt == set(protected) | set(inputs["allowedMetadataPaths"])
child = inputs["pointerParent"]
parent = inputs["incomingParent"]
path = "spec/design/browser-wasm.md"
old = git_bytes(child, path).decode()
parent_text = git_bytes(parent, path).decode()
old_start = "not asserted. Native property-graph initial home-view, caption and theme\n"
end = "records the fresh all-pixel default-property comparisons;"
start = "not asserted. The #1089 consumer receipts retain the historical native\n"
old_block = old[old.index(old_start) : old.index(end)]
new_block = parent_text[parent_text.index(start) : parent_text.index(end)]
marker = "The authored collision header at bytes 76-79 is zeroed in the painter."
landing_start = "The resolved Scene plot/axis and live CSS repairs merged as #1089 at\n"
landing = parent_text[parent_text.index(landing_start) : parent_text.index(marker)]
assert landing.count("S5b keyboard/GPU/companion") == 1
landing = landing.replace("S5b keyboard/GPU/companion", "S5b primary-click/keyboard/GPU/companion")
expected = old.replace(old_block, new_block, 1).replace(marker, landing + marker, 1)
assert (root / path).read_text() == expected, (
    "browser prose must be exact additive metadata resolution"
)
old_inventory = json.loads(git_bytes(child, "spec/releases/0.6.0-api-inventory.json"))
inventory = json.loads((root / "spec/releases/0.6.0-api-inventory.json").read_text())
for key in old_inventory:
    if key not in ("sourceProvenance", "sourceSha256"):
        assert inventory[key] == old_inventory[key], key
assert inventory["sourceProvenance"]["baseCommit"] == child
assert len(inventory["gaps"]) == 685
changed_hashes = [
    path
    for path, value in inventory["sourceSha256"].items()
    if value != old_inventory["sourceSha256"][path]
]
assert changed_hashes == ["spec/design/browser-wasm.md"], changed_hashes
assert inventory["sourceSha256"][path] == hashlib.sha256(expected.encode()).hexdigest()
qualified = inputs["artifacts"]
for path, digest in qualified["sourceInputs"].items():
    assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest, path
for path, fact in qualified["artifacts"].items():
    data = (root / path).read_bytes()
    assert len(data) == fact["bytes"] and hashlib.sha256(data).hexdigest() == fact["sha256"], path
compressed = json.loads(
    subprocess.check_output(
        [
            "node",
            "--input-type=module",
            "-e",
            'import{readFileSync}from"node:fs";import{gzipSync}from"node:zlib";'
            'import{createHash}from"node:crypto";'
            "const b=readFileSync(process.argv[1]),g=gzipSync(b,{level:6});"
            'console.log(JSON.stringify({bytes:b.length,gzip6:g.length,sha256:createHash("sha256").update(b).digest("hex"),gzip6Sha256:createHash("sha256").update(g).digest("hex")}));',
            str(root / "packages/xy-client/dist/xyg-wasm.wasm"),
        ],
        text=True,
    )
)
for key, value in compressed.items():
    assert value == qualified["optimized"][key], key
logs = {}
for directory, count in [
    ("graph-s5b-attachment-r2-2026-11-04", 29),
    ("graph-s5b-pointer-selection-2026-11-04", 47),
    ("graph-s5b-pointer-motion-path-repair-2026-11-04", 19),
]:
    folder = receipt.parent / directory
    records = sorted(folder.glob("*.command.json"))
    assert len(records) == count, (directory, len(records))
    checks = {}
    for record in records:
        command = json.loads(record.read_text())
        streams = {}
        for suffix, field in [
            ("log", "log_sha256"),
            ("stdout", "stdout_sha256"),
            ("stderr", "stderr_sha256"),
        ]:
            if field in command:
                stream = record.with_name(record.name.replace(".command.json", "." + suffix))
                digest = hashlib.sha256(stream.read_bytes()).hexdigest()
                assert digest == command[field], stream
                streams[suffix] = digest
        checks[record.name] = {"exit": command["exit"], "streamHashes": streams}
    if directory == "graph-s5b-attachment-r2-2026-11-04":
        original = json.loads((folder / "proof-inputs.json").read_text())["commands"]
        assert len(original) == 28
        for name, facts in original.items():
            record = folder / name
            command = json.loads(record.read_text())
            assert hashlib.sha256(record.read_bytes()).hexdigest() == facts["recordSha256"]
            assert command["exit"] == facts["exit"]
            assert command["log_sha256"] == facts["logSha256"]
        assert set(checks) - set(original) == {"proof-inputs.command.json"}
    logs[directory] = checks
retain(
    "preservation.json",
    {
        "protectedNonReceiptCount": len(protected),
        "protectedNonReceiptSha256": protected,
        "historicalPointerCount": inputs["pointerHistoricalCount"],
        "historicalIncomingCount": inputs["incomingHistoricalCount"],
        "historicalUnionCount": len(historical),
        "historicalSha256": historical,
        "metadataPaths": inputs["allowedMetadataPaths"],
        "inventoryGapCount": 685,
        "inventoryChangedSourceHashes": changed_hashes,
        "browserResolution": "Exact parent historical-failure/current-six-pair qualification and actual #1089 landing prose added to b610, preserving all pointer prose and naming its primary-click subset in the imported summary.",
    },
)
retain("reused-qualification.json", {"logs": logs, "freshRuntimeClaim": False})
retain(
    "source-artifact-preservation.json",
    {
        "qualifiedBase": child,
        "buildInputs": qualified["sourceInputs"],
        "artifacts": qualified["artifacts"],
        "optimized": qualified["optimized"],
        "versions": qualified["versions"],
        "freshBuildClaim": False,
    },
)
print(
    f"PASS: {len(protected)} protected nonreceipt paths; {len(historical)} historical files; "
    "301 producer inputs;15 actual artifacts;95 historical command records (including28 original R2 qualification records);685 inventory gaps"
)
