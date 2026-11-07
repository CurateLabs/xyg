"""Verify final sync with the sole explicitly authorized historical prose edit."""

import hashlib
import json
from pathlib import Path

receipt = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


history = json.loads((receipt / "history-identity.json").read_text())
local = json.loads((receipt / "local-tree-before.json").read_text())["files"]
production = json.loads((receipt / "source-identity.json").read_text())
artifacts = json.loads((receipt / "artifacts-before.json").read_text())
correction = json.loads((receipt / "authorized-r7-correction.json").read_text())
path = "spec/performance/graph-picked-target-r7-2026-11-04/README.md"
assert correction["path"] == path
before = Path(correction["pre_correction_snapshot"]).read_bytes()
after = Path(path).read_bytes()
assert sha(before) == correction["before_sha256"] == history[path]["sha256"]
assert sha(after) == correction["after_sha256"]
assert sha(before) == "ab7475ab1d5d89fc0d907ae7c0411766dd83f8ba65fca54142ba950f6c98ba74"
assert sha(after) == "f5e20b2ecfda517becdd5b51ae4a57282a645286e14f83bb00795d22c5d88442"
a = before.splitlines(keepends=True)
b = after.splitlines(keepends=True)
assert len(a) == len(b) and a[:15] == b[:15] and a[16:] == b[16:]
assert b[15].decode() == correction["after_line"] + "\n"
assert json.loads(
    Path("spec/performance/graph-picked-target-r7-2026-11-04/receipt-manifest.json").read_text()
)["README.md"]["sha256"] == sha(before)
for name, expected in history.items():
    if name == path:
        continue
    assert sha(Path(name).read_bytes()) == expected["sha256"], name
for name, expected in production.items():
    data = (
        str(Path(name).readlink()).encode()
        if local[name]["mode"] == "120000"
        else Path(name).read_bytes()
    )
    assert sha(data) == expected["sha256"], name
for name, expected in artifacts.items():
    assert sha(Path(name).read_bytes()) == expected["expected"], name
prior = json.loads((receipt / "prior-rust-receipts-before.json").read_text())
assert all(
    sha(Path(name).read_bytes()) == expected for name, expected in prior.items() if name != path
)
record = {
    "before_history_table_sha256": sha((receipt / "history-identity.json").read_bytes()),
    "historical_files_unchanged": len(history) - 1,
    "sole_authorized_historical_correction": correction,
    "R1_R7_files_unchanged": len(prior) - 1,
    "original_R7_readme_preserved_in_snapshot_and_commit": True,
    "original_R7_manifest_unchanged_binds_original_snapshot": True,
    "non_spec_product_build_test_files_exact_to_R7": len(production),
    "qualified_artifacts_exact": len(artifacts),
    "no_guard_or_runtime_change": True,
    "no_release_browser_client_rebuild": True,
    "final_independent_review": "PENDING",
}
with (receipt / "final-protection.json").open("x") as stream:
    stream.write(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
