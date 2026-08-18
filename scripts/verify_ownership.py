#!/usr/bin/env python3
"""Validate the exhaustive production-source ownership ledger.

The gate is stdlib-only and inventories tracked files so build output,
dependencies, and untracked user files never enter the audit.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "spec" / "design" / "ownership-audit.json"
REQUIRED_ENTRY_FIELDS = {
    "path",
    "current_owner",
    "policy",
    "disposition",
    "follow_up_issue",
    "rationale",
}
REQUIRED_POLICY_FIELDS = {
    "current_owner",
    "disposition",
    "follow_up_issue",
    "allowed_responsibilities",
    "forbidden_responsibilities",
    "forbidden_patterns",
    "rationale",
}


def _tracked_files(root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        detail = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"git ls-files failed: {detail or 'unknown error'}")
    return {item.decode() for item in result.stdout.split(b"\0") if item}


def _in_scope(path: str, roots: Iterable[dict[str, Any]]) -> bool:
    suffix = Path(path).suffix
    return any(
        path.startswith(str(rule.get("prefix", ""))) and suffix in rule.get("extensions", [])
        for rule in roots
    )


def _load_manifest(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"manifest missing: {path}"]
    except json.JSONDecodeError as exc:
        return None, [f"manifest malformed at line {exc.lineno}, column {exc.colno}: {exc.msg}"]
    if not isinstance(value, dict):
        return None, ["manifest malformed: top-level value must be an object"]
    return value, []


def validate(
    root: Path,
    manifest_path: Path,
    *,
    tracked_files: set[str] | None = None,
) -> list[str]:
    """Return deterministic diagnostics; an empty list means conformance."""
    manifest, errors = _load_manifest(manifest_path)
    if manifest is None:
        return errors
    if manifest.get("schema_version") != 1:
        errors.append("manifest malformed: schema_version must be 1")

    scope = manifest.get("scope")
    if not isinstance(scope, dict) or not isinstance(scope.get("roots"), list):
        errors.append("manifest malformed: scope.roots must be a list")
        roots: list[dict[str, Any]] = []
    else:
        roots = scope["roots"]
        for index, rule in enumerate(roots):
            if not isinstance(rule, dict) or not isinstance(rule.get("prefix"), str):
                errors.append(f"manifest malformed: scope.roots[{index}] needs a string prefix")
            if not isinstance(rule, dict) or not isinstance(rule.get("extensions"), list):
                errors.append(f"manifest malformed: scope.roots[{index}] needs extensions")

    policies = manifest.get("policies")
    if not isinstance(policies, dict):
        errors.append("manifest malformed: policies must be an object")
        policies = {}
    for name, policy in sorted(policies.items()):
        if not isinstance(policy, dict):
            errors.append(f"policy {name!r} malformed: expected an object")
            continue
        missing = sorted(REQUIRED_POLICY_FIELDS - policy.keys())
        if missing:
            errors.append(f"policy {name!r} malformed: missing {', '.join(missing)}")
        for field in ("allowed_responsibilities", "forbidden_responsibilities"):
            value = policy.get(field)
            if (
                not isinstance(value, list)
                or not value
                or not all(isinstance(v, str) for v in value)
            ):
                errors.append(f"policy {name!r} malformed: {field} must be a non-empty string list")
        patterns = policy.get("forbidden_patterns", [])
        if not isinstance(patterns, list):
            errors.append(f"policy {name!r} malformed: forbidden_patterns must be a list")
        else:
            for index, item in enumerate(patterns):
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("pattern"), str)
                    or not isinstance(item.get("instruction"), str)
                ):
                    errors.append(
                        f"policy {name!r} malformed: forbidden_patterns[{index}] needs pattern and instruction"
                    )
                    continue
                try:
                    re.compile(item["pattern"])
                except re.error as exc:
                    errors.append(
                        f"policy {name!r} malformed: invalid pattern {item['pattern']!r}: {exc}"
                    )

    entries = manifest.get("files")
    if not isinstance(entries, list):
        errors.append("manifest malformed: files must be a list")
        entries = []
    by_path: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"file entry {index} malformed: expected an object")
            continue
        missing = sorted(REQUIRED_ENTRY_FIELDS - entry.keys())
        if missing:
            errors.append(f"file entry {index} malformed: missing {', '.join(missing)}")
            continue
        path = entry.get("path")
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or ".." in Path(path).parts
        ):
            errors.append(
                f"file entry {index} malformed: path must be a safe repository-relative string"
            )
            continue
        if path in by_path:
            duplicates.add(path)
        else:
            by_path[path] = entry
        if roots and not _in_scope(path, roots):
            errors.append(
                f"classification outside production scope: {path}; remove it or extend scope.roots deliberately"
            )
        policy_name = entry.get("policy")
        policy = policies.get(policy_name)
        if not isinstance(policy, dict):
            errors.append(
                f"invalid classification: {path} references unknown policy {policy_name!r}"
            )
            continue
        for field in ("current_owner", "disposition", "follow_up_issue", "rationale"):
            if entry.get(field) != policy.get(field):
                errors.append(
                    f"invalid classification: {path} {field} must match policy {policy_name!r}"
                )
        issue = entry.get("follow_up_issue")
        if entry.get("disposition") not in {
            "keep-rust",
            "keep-host",
            "keep-shared-client",
        } and (not isinstance(issue, int) or issue <= 0):
            errors.append(
                f"invalid classification: {path} migration/generation disposition "
                "needs a positive follow_up_issue"
            )

    for path in sorted(duplicates):
        errors.append(f"duplicate classification: {path}; keep exactly one file entry")

    tracked = _tracked_files(root) if tracked_files is None else tracked_files
    production = {path for path in tracked if _in_scope(path, roots)}
    classified = set(by_path)
    for path in sorted(production - classified):
        errors.append(
            f"unclassified production source: {path}; add one ownership-audit.json entry and the human ledger row"
        )
    for path in sorted(classified - production):
        errors.append(
            f"stale classification: {path}; remove it or restore/rename the tracked production file"
        )

    human_value = manifest.get("human_audit")
    if not isinstance(human_value, str):
        errors.append("manifest malformed: human_audit must be a repository-relative path")
    else:
        human_path = root / human_value
        try:
            human = human_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            errors.append(f"human audit missing: {human_value}")
        else:
            marker = "<!-- xyg-ownership-schema: 1 -->"
            if marker not in human:
                errors.append(f"human audit stale: {human_value} must contain {marker}")
            section = human.partition("## File ledger")[2].partition("## Contributor rule")[0]
            human_paths = set(re.findall(r"^\| `([^`]+)` \|", section, flags=re.MULTILINE))
            for path in sorted(classified - human_paths):
                errors.append(f"human audit stale: {human_value} is missing file ledger row {path}")
            for path in sorted(human_paths - classified):
                errors.append(f"human audit stale: {human_value} has extra file ledger row {path}")

    for path in sorted(production & classified):
        entry = by_path[path]
        policy = policies.get(entry.get("policy"), {})
        source_path = root / path
        try:
            source = source_path.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        for rule in policy.get("forbidden_patterns", []):
            pattern = rule.get("pattern")
            if isinstance(pattern, str) and re.search(pattern, source, flags=re.IGNORECASE):
                errors.append(
                    f"boundary violation: {path} matches forbidden pattern {pattern!r} "
                    f"for policy {entry['policy']!r}; {rule['instruction']}"
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    manifest = (
        args.manifest.resolve() if args.manifest else root / "spec/design/ownership-audit.json"
    )
    try:
        errors = validate(root, manifest)
    except RuntimeError as exc:
        print(f"ownership audit failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("ownership audit failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    data = json.loads(manifest.read_text(encoding="utf-8"))
    print(f"ownership audit ok: {len(data['files'])} tracked production files classified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
