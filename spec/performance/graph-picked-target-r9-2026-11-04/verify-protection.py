"""Bind the CI/test-only repair to unchanged production and historical bytes."""

import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
base = "8b231d70d03e53e380f7198b4f618c0f33ec9ddf"


def sha(data):
    return hashlib.sha256(data).hexdigest()


inputs = json.loads(
    Path(
        "spec/performance/graph-picked-target-r6-2026-11-04/r5-production-inputs-reuse.json"
    ).read_text()
)
assert len(inputs) == 285
assert all(sha(Path(path).read_bytes()) == expected["actual"] for path, expected in inputs.items())
artifacts = json.loads((receipt / "artifacts-before.json").read_text())
assert len(artifacts) == 15
assert all(
    sha(Path(path).read_bytes()) == expected["expected"] for path, expected in artifacts.items()
)
prior = json.loads((receipt / "prior-receipts-before.json").read_text())
assert all(sha(Path(path).read_bytes()) == expected for path, expected in prior.items())
# All inherited history outside the new R9 receipt stays unchanged, including
# the separately authorized and approved R8 version of the R7 README.
changed_history = (
    subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            base,
            "--",
            "spec/performance/",
            ":(exclude)spec/performance/graph-picked-target-r9-2026-11-04/**",
        ]
    )
    .decode()
    .splitlines()
)
assert changed_history == []
fixture = "crates/xyg-engine/src/graphforge/interaction/tests/wire/picked.rs"
old = subprocess.check_output(["git", "show", base + ":" + fixture]).decode()
expected = old.replace(
    'wire::decode_refs(c.get("pick.ref.bytes", 0).unwrap().payload).unwrap(), [reference.clone()]',
    'wire::decode_refs(c.get("pick.ref.bytes", 0).unwrap().payload).unwrap().as_slice(), std::slice::from_ref(&reference)',
).replace(
    "s.session().selection().unwrap(), [reference.clone()]",
    "s.session().selection().unwrap().as_slice(), std::slice::from_ref(&reference)",
)
assert expected != old and Path(fixture).read_text() == expected
base_inventory = json.loads(
    subprocess.check_output(["git", "show", base + ":spec/releases/0.6.0-api-inventory.json"])
)
current = json.loads(Path("spec/releases/0.6.0-api-inventory.json").read_text())
assert base_inventory["contracts"] == current["contracts"]
assert len(base_inventory["gaps"]) == len(current["gaps"]) == 685
record = {
    "base": base,
    "production_inputs_exact": len(inputs),
    "qualified_artifacts_exact": artifacts,
    "prior_R1_R8_receipt_files_exact": len(prior),
    "all_other_inherited_performance_history_unchanged": True,
    "Rust_change_scope": "exactly two test-only borrowed-slice assertions; full comparison semantics retained",
    "production_Rust_client_packager_and_caps_unchanged": True,
    "inventory_contracts_and_classifications_unchanged": True,
    "preparation_gaps": 685,
    "release_native_WASM_client_browser_rebuild": False,
    "qualification_reuse": "R8 qualified production source/artifact/runtime/capture proof only; new assertions and CI wiring have fresh checks; remote CI and final independent review remain pending",
}
with (receipt / "protected-identity.json").open("x") as stream:
    stream.write(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
