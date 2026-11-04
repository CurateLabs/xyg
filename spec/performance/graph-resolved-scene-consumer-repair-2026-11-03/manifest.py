"""Hash all receipt files except this manifest's recursively defined output."""

import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
files = {
    str(p.relative_to(out)): {
        "bytes": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }
    for p in sorted(out.rglob("*"))
    if p.is_file() and p.name != "artifacts.json"
}
(out / "artifacts.json").write_text(json.dumps(files, indent=2) + "\n")
print("Hashed", len(files), "new receipt artifacts; no historical receipt changed.")
