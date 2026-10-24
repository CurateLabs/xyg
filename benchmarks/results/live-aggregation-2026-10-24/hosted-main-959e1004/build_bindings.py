#!/usr/bin/env python3
"""Bind retained report hashes to historical Git objects; never create source arrays."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = "959e1004924774711a35df7ab1317cca30b18d68"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    listing = {}
    for entry in git("ls-tree", "-r", "-z", SOURCE).split(b"\0"):
        if entry:
            meta, path = entry.split(b"\t")
            listing[path.decode()] = meta.split()[2].decode()

    def record(path: str) -> dict:
        raw = git("show", f"{SOURCE}:{path}")
        return {"git_blob_oid": listing[path], "bytes": len(raw), "sha256": sha(raw)}

    result = {
        "source_commit": SOURCE,
        "git_tree_oid": git("rev-parse", SOURCE + "^{tree}").decode().strip(),
        "scope": "Historical Git objects and metadata only; no source regeneration, native calls or authority spoof.",
        "reports": {},
        "product_trees": {},
        "historical_files": {},
    }
    for folder, suffix in (("python/xyg", ".py"), ("crates", ".rs"), ("js/src", ".ts")):
        files = {
            p: record(p)
            for p in sorted(listing, key=Path)
            if p.startswith(folder + "/") and p.endswith(suffix)
        }
        digest = hashlib.sha256()
        for path, item in files.items():
            digest.update(path.encode() + b"\0")
            digest.update(bytes.fromhex(item["sha256"]))
        result["product_trees"][folder] = {
            "sha256": digest.hexdigest(),
            "pattern": "*" + suffix,
            "file_count": len(files),
            "files": files,
        }
    historical = [
        ".github/workflows/ceiling-benchmark.yml",
        "scripts/verify_density_comparison_report.py",
        "spec/design/comparison-count-oracle.md",
        "rust-toolchain.toml",
        "js/build.mjs",
        "package.json",
        "pyproject.toml",
        "uv.lock",
        "Cargo.toml",
        "crates/xyg-core/Cargo.toml",
        "crates/xyg-engine/Cargo.toml",
    ]
    for path in historical:
        result["historical_files"][path] = record(path)
    for path in HERE.glob("density-comparison-*.json.gz"):
        raw = gzip.decompress(path.read_bytes())
        report = json.loads(raw)
        assert report["environment"]["git"]["commit"] == SOURCE
        assert report["environment"]["git"]["dirty"] is False
        binding = {
            "decoded_sha256": sha(raw),
            "source_commit": SOURCE,
            "git_dirty": False,
            "provenance": {},
        }
        for key, recorded in report["provenance_sha256"].items():
            item = {"recorded_sha256": recorded}
            if key.endswith(":tree_sha256"):
                expected = result["product_trees"][key.split(":")[0]]["sha256"]
                item.update(
                    historical_sha256=expected,
                    matches=recorded == expected,
                    status="matched-historical-git-tree",
                )
                assert item["matches"], key
            elif key in listing:
                entry = record(key)
                item.update(
                    historical_sha256=entry["sha256"],
                    matches=recorded == entry["sha256"],
                    status="matched-historical-git-blob",
                    git_blob_oid=entry["git_blob_oid"],
                    bytes=entry["bytes"],
                )
                assert item["matches"], key
            else:
                item.update(
                    status="measured-executable-bytes-unavailable",
                    locally_verified=False,
                    execution_source_commit=SOURCE,
                    note="Producer-recorded hash; executable absent from artifact. No local build substituted.",
                )
            binding["provenance"][key] = item
        result["reports"][path.name] = binding
    assert result["reports"], "No report retained"
    (HERE / "source-bindings.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Historical source hashes bound:",
        {k: v["file_count"] for k, v in result["product_trees"].items()},
    )


if __name__ == "__main__":
    main()
