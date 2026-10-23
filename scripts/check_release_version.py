#!/usr/bin/env python3
"""Release gate: the pushed tag and the package's CHANGELOG must agree.

The tag *is* the version now — each pyproject derives it via
uv-dynamic-versioning — so the old tag-vs-pyproject leg of this gate is gone
along with the drift it existed to catch. What a tag cannot vouch for is that
anyone wrote down what changed, so this runs first in the publish job on tag
pushes: the package's changelog must carry a dated entry for the tagged
version (an "unreleased" heading fails — date it as part of cutting the
release).

The ``xyg`` distribution uses `xyg-vX.Y.Z` tags and `CHANGELOG.md`. Its bundled
The Python package and browser client ship on the same version line.

Tags use the canonical semver spelling `xyg-vX.Y.Z` or `xyg-vX.Y.Z-rc.N` (also
`-alpha.N` / `-beta.N`); the legacy PEP 440 tag spelling (`xyg-v0.6.0rc5`) is
still accepted for already-cut tags. Both name the same release: npm
`0.6.0-rc.5`, Python/PyPI `0.6.0rc5` (see `scripts/release_version.py`, the
single conversion authority). PyPI accepts pre-releases but does not serve them
to default `pip install`. A pre-release needs its own dated changelog entry,
written with either the Python or the npm spelling of its version.

Docs-deploy CalVer tags (2026.WW.N) do not match the release shape.
Dev/post/local shapes stay rejected: dev versions are the between-tags marker
and must stay unpublishable.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple, Optional

try:
    from release_version import parse_tag
except ModuleNotFoundError:
    from scripts.release_version import parse_tag

ROOT = Path(__file__).resolve().parents[1]


class _Package(NamedTuple):
    changelog: Path


PACKAGES = {
    "xy": _Package(changelog=ROOT / "CHANGELOG.md"),
}
DEFAULT_CHANGELOG = PACKAGES["xy"].changelog


def check_release(tag: str, changelog: Path, package: str = "xy") -> list[str]:
    errors: list[str] = []
    try:
        release = parse_tag(tag)
    except ValueError as exc:
        return [f"{exc} (this is not a release tag for {package})"]
    try:
        text = changelog.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot read {changelog}: {exc}")
        return errors
    # A heading with a real date. The gate checks substance (this version has
    # dated notes), not heading style: both spellings used in this repo pass —
    # Keep-a-Changelog brackets (`## [0.0.2] — 2026-07-24`) and the plain
    # v-prefixed form v0.0.2 was actually documented with
    # (`## v0.0.2 - 2026-07-24`); em dash or hyphen either way. A pre-release
    # heading may use the Python (`0.6.0rc5`) or npm (`0.6.0-rc.5`) spelling.
    spellings = "|".join(re.escape(v) for v in dict.fromkeys((release.python, release.npm)))
    dated = re.compile(
        rf"^## (?:\[(?:{spellings})\]|v?(?:{spellings})) [—-] "
        rf"\d{{4}}-\d{{2}}-\d{{2}}\s*$",
        re.M,
    )
    if not dated.search(text):
        errors.append(
            f"{changelog.name} has no dated '## [{release.npm}]' (or '[{release.python}]') "
            "entry — date the release section before tagging"
        )
    return errors


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag",
        default=os.environ.get("GITHUB_REF_NAME", ""),
        help="release tag (defaults to $GITHUB_REF_NAME)",
    )
    parser.add_argument(
        "--package",
        choices=sorted(PACKAGES),
        default="xy",
        help="which release line the tag belongs to (default: xy)",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=None,
        help="changelog to gate against (defaults to the package's own)",
    )
    args = parser.parse_args(argv)

    if not args.tag:
        print("release version gate: no tag provided (--tag or GITHUB_REF_NAME)", file=sys.stderr)
        return 1
    changelog = args.changelog if args.changelog is not None else PACKAGES[args.package].changelog
    errors = check_release(args.tag, changelog, args.package)
    if errors:
        print("release version gate failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"release version gate OK: {args.tag} has a dated {changelog.name} entry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
