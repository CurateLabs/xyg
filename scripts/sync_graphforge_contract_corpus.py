#!/usr/bin/env python3
"""Export the pinned Core-owned algorithm/schema registry as data for XYG CI.

Uses Core's actual Rust registry and descriptor iterator, not a second schema
mapping. A tiny test-time rustc harness supplies only Core's unrelated error
shell. Core remains absent from XYG's runtime dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "tests/fixtures/graphforge/core"
ALGORITHMS = "crates/graphforge-core/src/algorithms.rs"
DESCRIPTORS = "crates/graphforge-api/src/invocation_descriptor.rs"


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True)


def _item(source: str, declaration: str) -> str:
    start = source.index(declaration)
    opening = source.index("{", start)
    depth = 1
    for index in range(opening + 1, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[start : index + 1]
    raise ValueError(f"unclosed Core declaration: {declaration}")


def export(repo: Path, ref: str) -> tuple[bytes, bytes]:
    commit = _git(repo, "rev-parse", f"{ref}^{{commit}}").strip()
    sources = {path: _git(repo, "show", f"{commit}:{path}") for path in (ALGORITHMS, DESCRIPTORS)}
    descriptor = sources[DESCRIPTORS]
    constants = []
    for name in ("ALGORITHM_CONTRACT_VERSION", "RESULT_SCHEMA_VERSION"):
        match = re.search(rf"(?m)^const {name}: u32 = [0-9]+;$", descriptor)
        if match is None:
            raise ValueError(f"Core no longer exposes {name} in its expected registry form")
        constants.append(match.group())
    registry = "\n".join(
        [
            *constants,
            _item(descriptor, "pub struct AlgorithmDescriptorContract"),
            _item(descriptor, "pub fn algorithm_descriptor_contracts()"),
        ]
    )
    harness = r"""#![allow(dead_code)]
#[derive(Debug)]
pub enum GfError { Validation(String) }
mod algorithms;
use algorithms::*;
CORE_REGISTRY
fn main() {
    println!("verb\talgorithm\talgorithm_version\tresult_schema_version\tnode_properties\tfields");
    for contract in algorithm_descriptor_contracts() {
        let schema = contract.algorithm.result_schema();
        let fields: Vec<_> = schema.fields.iter().map(|f|
            format!("{}:{:?}:{}", f.name, f.data_type, f.nullable)).collect();
        println!("{}\t{}\t{}\t{}\t{}\t{}", contract.algorithm.verb().as_str(),
            contract.algorithm.as_str(), contract.algorithm_version,
            contract.result_schema_version, schema.includes_node_properties, fields.join(","));
    }
}
""".replace("CORE_REGISTRY", registry)
    with tempfile.TemporaryDirectory(prefix="xyg-core-contracts-") as temporary:
        directory = Path(temporary)
        (directory / "algorithms.rs").write_text(sources[ALGORITHMS])
        (directory / "export.rs").write_text(harness)
        binary = directory / "export"
        subprocess.run(
            ["rustc", "--edition=2021", str(directory / "export.rs"), "-o", str(binary)], check=True
        )
        corpus = subprocess.check_output([str(binary)])
    version = tomllib.loads(_git(repo, "show", f"{commit}:Cargo.toml"))["workspace"]["package"][
        "version"
    ]
    provenance = {
        "schemaVersion": 1,
        "repository": "https://github.com/CurateLabs/graphforge",
        "commit": commit,
        "coreVersion": version,
        "sources": {
            path: hashlib.sha256(source.encode()).hexdigest() for path, source in sources.items()
        },
        "corpusSha256": hashlib.sha256(corpus).hexdigest(),
    }
    return corpus, (json.dumps(provenance, indent=2) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-repo", type=Path, required=True)
    parser.add_argument("--ref", help="Core commit/tag; defaults to the committed provenance pin")
    parser.add_argument("--output", type=Path, default=DESTINATION)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    ref = args.ref or json.loads((args.output / "provenance.json").read_text())["commit"]
    corpus, provenance = export(args.core_repo, ref)
    expected = {"contracts.tsv": corpus, "provenance.json": provenance}
    if args.write:
        args.output.mkdir(parents=True, exist_ok=True)
        for name, value in expected.items():
            (args.output / name).write_bytes(value)
        print(f"wrote Core schema/descriptor corpus to {args.output}")
    else:
        for name, value in expected.items():
            if (args.output / name).read_bytes() != value:
                raise SystemExit(
                    f"Core schema/descriptor corpus changed: {name}; qualify and regenerate deliberately"
                )
        print("pinned Core schema/descriptor corpus is current")


if __name__ == "__main__":
    main()
