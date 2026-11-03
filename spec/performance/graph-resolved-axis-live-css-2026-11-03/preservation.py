"""Pin historical receipts and independently verify unchanged producers."""

import hashlib
import json
from pathlib import Path

root = Path.cwd()
out = Path(__file__).resolve().parent
old = root / "spec/performance/graph-resolved-scene-integration-2026-11-03"


def sha(data):
    return hashlib.sha256(data).hexdigest()


history = {
    str(p.relative_to(root)): sha(p.read_bytes())
    for p in (root / "spec/performance").rglob("*")
    if p.is_file() and out not in p.parents
}
(out / "history-snapshot.json").write_text(json.dumps(history, indent=2) + "\n")
inputs = list((out / "inputs").iterdir())
assert len(inputs) == 149
for p in inputs:
    assert p.read_bytes() == (old / "inputs" / p.name).read_bytes(), p.name
for name in ("slot.scene", "slot.svg", "precision.scene", "precision.svg"):
    assert (out / name).read_bytes() == (old / name).read_bytes(), name
standalone = (root / "packages/xy-client/dist/standalone.js").read_text()
# Kernel-generated HTML uses the current actual shipping bundle, escaped only
# for safe embedding inside the HTML script container.
escaped = standalone.replace("</", "<\\/")
html = {}
for theme in ("light", "dark"):
    path = out / "property" / f"{theme}.native.html"
    if not path.exists():
        path = out / "property" / f"{theme}.html"
    text = path.read_text()
    assert escaped in text
    html[theme] = {"path": str(path.relative_to(root)), "freshStandaloneEmbedded": True}
result = {
    "unchangedMatrixInputs": len(inputs),
    "slotPrecisionFreshProducerExact": True,
    "historyFiles": len(history),
    "standaloneSha256": sha(standalone.encode()),
    "html": html,
}
(out / "producer-preservation.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
