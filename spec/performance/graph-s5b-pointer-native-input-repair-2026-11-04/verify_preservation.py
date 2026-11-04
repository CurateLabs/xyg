"""Seal native-input proof without rewriting historical artifacts or receipts."""

import base64
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]


def sha(data):
    return hashlib.sha256(data).hexdigest()


before = json.loads((receipt / "before-identity.json").read_text())
assert before["head"] == "04476ac36d6b9dce84810b07629aae68ad2f6f56"
assert all(sha((root / p).read_bytes()) == s for p, s in before["history"].items())
path = "spec/releases/0.6.0-api-inventory.json"
old = json.loads(subprocess.check_output(["git", "show", before["head"] + ":" + path]))
new = json.loads((root / path).read_text())
changed = [k for k in old if old[k] != new[k]]
assert set(changed) <= {"sourceProvenance", "sourceSha256"}, changed
assert len(new["gaps"]) == 685
stored = (receipt / "captured-requests.json").read_bytes()
records = json.loads(stored)
assert len(records) == 19
assert sum(r["operation"] == 1 for r in records) == 17
assert all(
    r["nativeEvent"]["trusted"] and r["nativeEvent"]["canvas"] and r["nativeEvent"]["zoom"] == 1
    for r in records
    if r["operation"] == 1
)
# The old capture is retained only for a historical comparison, never replayed
# to qualify the new mapper. The fresh capture is the default wire-test input.
historical = json.loads(
    gzip.decompress(
        (
            receipt.parent / "graph-s5b-pointer-selection-2026-11-04/captured-requests.json.gz"
        ).read_bytes()
    )
)
request_changes = [i for i, r in enumerate(records) if r["request"] != historical[i]["request"]]
assert request_changes, "the old rectangle-based capture cannot qualify native input"
assert all(base64.b64decode(r["request"]) for r in records)
compressed = gzip.compress(stored, compresslevel=6, mtime=0)
destination = receipt / "captured-requests.json.gz"
if destination.exists():
    assert destination.read_bytes() == compressed
else:
    destination.write_bytes(compressed)
report = sys.argv[1] if len(sys.argv) > 1 else "controller.json"
expected_cases = 69 if report == "controller-final.json" else 65
browser = json.loads((receipt / report).read_text())
assert len(browser["cases"]) == expected_cases and browser["status"] == "passed"
assert browser["cspViolations"] == browser["pageErrors"] == []
result = {
    "base": before["head"],
    "historyFilesPreservedByteExact": len(before["history"]),
    "inventoryChangedKeys": changed,
    "gaps": len(new["gaps"]),
    "nativeBrowserJourneys": len(browser["cases"]),
    "browserVersion": browser["browser"],
    "freshCaptureSha256": sha(stored),
    "freshCaptureGzipSha256": sha(compressed),
    "requests": len(records),
    "selectAt": 17,
    "requestIndicesDifferentFromHistoricalRectangleCapture": request_changes,
    "qualification": "Fresh native-coordinate capture and full native/WASM/browser XYGR byte replay; old capture remains historical only",
}
text = json.dumps(result, indent=2) + "\n"
destination = receipt / (
    "preservation-final.json" if report == "controller-final.json" else "preservation.json"
)
if destination.exists():
    assert destination.read_text() == text
else:
    destination.write_text(text)
print(text)
