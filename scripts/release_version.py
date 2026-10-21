"""Single authority for XYG release-version spelling across ecosystems.

One release has three spellings of the same version:

* Git tag (canonical): ``xyg-v0.6.0`` / ``xyg-v0.6.0-rc.5``
  (also ``-alpha.N`` / ``-beta.N``).
* npm (semver):        ``0.6.0`` / ``0.6.0-rc.5``
* Python (PEP 440):    ``0.6.0`` / ``0.6.0rc5``

The legacy PEP 440 tag spelling (``xyg-v0.6.0rc5``) is still accepted for
already-cut tags (``xyg-v0.0.1a1``); it normalizes to the same Python and npm
versions. Dev, post, local, malformed, leading-zero, and other spellings are
rejected with an actionable message. This module covers ecosystem version
spelling only; native ABI, Scene, wire, painter, and WASM identifiers keep
their own explicit contracts and are never derived from it.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

_NUM = r"(?:0|[1-9][0-9]*)"
_BASE = rf"(?P<base>{_NUM}\.{_NUM}\.{_NUM})"
TAG_PREFIX = "xyg-v"

_SEMVER_LABELS = {"alpha": "a", "beta": "b", "rc": "rc"}
_PEP440_LABELS = {value: key for key, value in _SEMVER_LABELS.items()}

_TAG_SEMVER = re.compile(
    rf"^{re.escape(TAG_PREFIX)}{_BASE}(?:-(?P<label>alpha|beta|rc)\.(?P<num>{_NUM}))?$",
    re.ASCII,
)
_TAG_PEP440 = re.compile(
    rf"^{re.escape(TAG_PREFIX)}{_BASE}(?:(?P<pep>a|b|rc)(?P<num>{_NUM}))?$", re.ASCII
)
_PY = re.compile(rf"^{_BASE}(?:(?P<pep>a|b|rc)(?P<num>{_NUM}))?$", re.ASCII)
_NPM = re.compile(rf"^{_BASE}(?:-(?P<label>alpha|beta|rc)\.(?P<num>{_NUM}))?$", re.ASCII)

TAG_SHAPE = "xyg-vX.Y.Z or xyg-vX.Y.Z-rc.N (also -alpha.N / -beta.N)"


class ReleaseVersion(NamedTuple):
    base: str
    stage: Optional[str]  # "alpha" | "beta" | "rc" | None
    number: Optional[int]

    @property
    def tag(self) -> str:
        return TAG_PREFIX + self.npm

    @property
    def npm(self) -> str:
        if self.stage is None:
            return self.base
        return f"{self.base}-{self.stage}.{self.number}"

    @property
    def python(self) -> str:
        if self.stage is None:
            return self.base
        return f"{self.base}{_SEMVER_LABELS[self.stage]}{self.number}"


def _build(match: re.Match[str], label_key: str) -> ReleaseVersion:
    raw = match.group(label_key)
    if raw is None:
        return ReleaseVersion(match.group("base"), None, None)
    stage = _PEP440_LABELS[raw] if label_key == "pep" else raw
    return ReleaseVersion(match.group("base"), stage, int(match.group("num")))


def _explain(text: str, what: str) -> str:
    hint = ""
    if re.search(r"(?:dev|post|\+)", text):
        hint = "; dev, post, and local versions are never releasable"
    elif re.search(r"[A-Za-z]0[0-9]", text) or re.search(r"(?:^|[.v-])0[0-9]", text):
        hint = "; leading zeros are not allowed"
    elif re.search(r"(?:alpha|beta|rc|a|b)\d", text) or "-rc" in text or "-alpha" in text:
        hint = "; use -alpha.N, -beta.N or -rc.N with a plain integer N"
    return f"invalid XYG release {what} {text!r}; expected {TAG_SHAPE}{hint}"


def parse_tag(tag: str) -> ReleaseVersion:
    """Parse a release tag (canonical semver or legacy PEP 440 spelling)."""

    match = _TAG_SEMVER.fullmatch(tag)
    if match is not None:
        return _build(match, "label")
    match = _TAG_PEP440.fullmatch(tag)
    if match is not None:
        return _build(match, "pep")
    raise ValueError(_explain(tag, "tag"))


def parse_python(version: str) -> ReleaseVersion:
    match = _PY.fullmatch(version)
    if match is None:
        raise ValueError(
            f"invalid XYG Python version {version!r}; expected X.Y.Z or X.Y.ZrcN "
            "(PEP 440 aN/bN/rcN, no leading zeros, no dev/post/local)"
        )
    return _build(match, "pep")


def parse_npm(version: str) -> ReleaseVersion:
    match = _NPM.fullmatch(version)
    if match is None:
        raise ValueError(
            f"invalid XYG npm version {version!r}; expected X.Y.Z or X.Y.Z-rc.N "
            "(-alpha.N/-beta.N/-rc.N, no leading zeros, no build metadata)"
        )
    return _build(match, "label")
