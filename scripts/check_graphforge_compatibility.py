"""Check XYG's exact Core result-schema declaration and immutable corpus.

This proves the declared schema corpus, not Core Hub/CLI launch readiness.
Rust's ledger tests compose these raw IPC results through the shared engine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    from release_version import parse_npm, parse_tag
except ImportError:
    from scripts.release_version import parse_npm, parse_tag

ROOT = Path(__file__).resolve().parents[1]
DECLARATION = ROOT / "spec/graphforge-compatibility.json"


def check_compatibility(
    declaration: dict, *, root: Path, core_version: str | None = None, tag: str | None = None
) -> list[str]:
    """Refuse unqualified Core versions and corrupted or stale retained evidence."""
    if declaration.get("schema") != "xyg.graphforge-compatibility/v1":
        raise ValueError("unsupported GraphForge compatibility declaration schema")
    if tag is not None and parse_tag(tag).base != declaration["xygReleaseLine"]:
        raise ValueError("XYG release line has no declared Core compatibility; qualify its corpus")
    entries = declaration["supportedCoreResults"]
    if core_version is not None:
        parse_npm(core_version)
        entries = [entry for entry in entries if entry["version"] == core_version]
        if not entries:
            raise ValueError(
                f"Core {core_version} has no qualified XYG result-schema declaration; "
                "qualify the exact Core corpus before selecting this release pair"
            )
    if not entries:
        raise ValueError("no qualified Core result-schema corpus is declared")
    checked = []
    for entry in entries:
        version = entry["version"]
        normalized = parse_npm(version)
        if entry["pythonVersion"] != normalized.python or any(
            package["version"] != version for package in entry["packages"]
        ):
            raise ValueError(f"Core {version}: package versions do not match the exact declaration")
        if entry["qualification"] != "result-schema-corpus":
            raise ValueError(f"Core {version}: unsupported qualification scope")
        corpus = root / entry["corpus"]
        if not corpus.resolve().is_relative_to(root.resolve()):
            raise ValueError("Core corpus must remain inside the repository")
        expected_files = entry["files"]
        actual_files = {
            str(path.relative_to(corpus)) for path in corpus.rglob("*") if path.is_file()
        }
        if actual_files != set(expected_files):
            raise ValueError(f"Core {version}: corpus file inventory differs from declaration")
        for name, expected in expected_files.items():
            data = (corpus / name).read_bytes()
            if (
                len(data) != expected["bytes"]
                or hashlib.sha256(data).hexdigest() != expected["sha256"]
            ):
                raise ValueError(f"Core {version}: corpus integrity mismatch for {name}")
        manifest = json.loads((corpus / "results/manifest.json").read_text())
        descriptors = json.loads((corpus / "descriptors.json").read_text())
        if manifest["graphforgeVersion"] != version or manifest["failures"]:
            raise ValueError(f"Core {version}: incomplete or mismatched native-produced corpus")
        if (
            len(descriptors) != entry["descriptorCount"]
            or len(manifest["fixtures"]) != entry["resultCount"]
        ):
            raise ValueError(f"Core {version}: descriptor/result count differs from declaration")
        tsv = ["algorithm\tverb\talgorithm_version\tresult_schema_version\tbase"]
        for descriptor, contract in zip(descriptors, manifest["contracts"], strict=True):
            algorithm = descriptor["algorithm"]
            if any(
                descriptor[key] != contract[key]
                for key in ("algorithm", "verb", "resultSchemaVersion")
            ):
                raise ValueError(f"Core {version}: descriptor and result contract differ")
            tsv.append(
                "\t".join(
                    str(value)
                    for value in (
                        algorithm,
                        descriptor["verb"],
                        descriptor["algorithmVersion"],
                        descriptor["resultSchemaVersion"],
                        manifest["fixtures"][algorithm]["base"],
                    )
                )
            )
        if (corpus / "contracts.tsv").read_text() != "\n".join(tsv) + "\n":
            raise ValueError(
                f"Core {version}: Rust contract projection differs from native descriptors"
            )
        checked.append(version)
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--declaration", type=Path, default=DECLARATION)
    parser.add_argument("--core-version")
    parser.add_argument("--tag")
    args = parser.parse_args()
    try:
        checked = check_compatibility(
            json.loads(args.declaration.read_text()),
            root=ROOT,
            core_version=args.core_version,
            tag=args.tag,
        )
    except (ValueError, KeyError, OSError) as error:
        print(f"GraphForge compatibility failed: {error}", file=sys.stderr)
        return 1
    print(
        f"Qualified Core result-schema corpora: {', '.join(checked)}; launch pairing remains separate"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
