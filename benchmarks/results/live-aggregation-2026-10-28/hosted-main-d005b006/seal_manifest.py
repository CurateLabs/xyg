#!/usr/bin/env python3
"""Seal local retained bytes; no GitHub calls, benchmark execution or acceptance claim."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    entries = {}
    for path in sorted(HERE.iterdir()):
        if not path.is_file() or path.name in ("manifest.json", "SHA256SUMS"):
            continue
        raw = path.read_bytes()
        entry = {"bytes": len(raw), "sha256": sha(raw)}
        if path.suffix == ".gz":
            decoded = gzip.decompress(raw)
            entry.update(decoded_bytes=len(decoded), decoded_sha256=sha(decoded))
        entries[path.name] = entry
    manifest = HERE / "manifest.json"
    manifest.write_text(json.dumps(entries, indent=2) + "\n")
    sums = {name: entry["sha256"] for name, entry in entries.items()}
    sums[manifest.name] = sha(manifest.read_bytes())
    (HERE / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(sums.items()))
    )
    print(f"Sealed {len(entries)} retained files plus manifest.")


if __name__ == "__main__":
    main()
