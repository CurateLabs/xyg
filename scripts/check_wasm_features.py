"""Check the resolved browser dependency graph, including shared frozen PNG.

Input: cargo tree -p xyg-wasm --target wasm32-unknown-unknown --edges normal
       --prefix none --format '{p}|{f}' --color never
Full native raster features and xyg-core must remain outside this graph.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = re.compile(r"([A-Za-z0-9_-]+) v([^ ()|]+)(?: \(([^|]+)\))?")


@dataclass(frozen=True)
class Dependency:
    version: str
    path: str | None
    features: frozenset[str]


def check(text: str, root: Path = ROOT) -> None:
    packages: dict[str, set[Dependency]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        package, separator, features = line.removesuffix(" (*)").partition("|")
        match = PACKAGE.fullmatch(package)
        if not separator or match is None:
            raise ValueError(f"malformed Cargo dependency evidence: {line!r}")
        name, version, path = match.groups()
        packages.setdefault(name, set()).add(
            Dependency(version, path, frozenset(filter(None, features.split(","))))
        )
    if "xyg-core" in packages:
        raise ValueError("browser dependency graph includes native xyg-core")
    for name, path in [("xyg-wasm", "crates/xyg-wasm"), ("xyg-engine", "crates/xyg-engine")]:
        entries = packages.get(name, set())
        if len(entries) != 1:
            raise ValueError(f"expected exactly one local {name} dependency")
        entry = next(iter(entries))
        if entry.path is None or Path(entry.path).resolve() != (root / path).resolve():
            raise ValueError(f"{name} must use the local workspace source")
        expected = frozenset({"frozen-raster"}) if name == "xyg-engine" else frozenset()
        if entry.features != expected:
            raise ValueError(
                f"{name} features must be {sorted(expected)}, got {sorted(entry.features)}"
            )
    png = packages.get("png", set())
    if len(png) != 1:
        raise ValueError("shared frozen PNG requires exactly one PNG dependency")
    entry = next(iter(png))
    if (
        entry.version != "0.18.1"
        or entry.path is None
        or Path(entry.path).resolve() != (root / "vendor/png").resolve()
        or entry.features
    ):
        raise ValueError(
            "shared frozen PNG must use the pinned vendored PNG without extra features"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree", type=Path)
    args = parser.parse_args()
    try:
        check(args.tree.read_text())
    except (OSError, ValueError) as error:
        parser.exit(1, f"WASM feature validation failed: {error}\n")
    print(
        "WASM features verified: shared frozen PNG, no full raster/default features or native core"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
