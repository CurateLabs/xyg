#!/usr/bin/env python3
"""Fail early, with one actionable diagnostic, when packaged WASM assets are absent or stale.

The packaged direct-browser WASM tick assets are a generated artifact (§33): they are
never committed. One producer step creates them (``node js/build.mjs`` then
``npm run build:wasm``, which compiles ``xyg-wasm`` and runs ``js/package-wasm.mjs``).
Every consumer (CI jobs, wheel/sdist builds, benchmarks) runs this verifier before it
trusts the files, so a skipped/failed producer or a leftover from an older build cannot
reach a consumer silently. Stdlib only, so it runs before any dev environment exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCATIONS = ("packages/xy-client/dist", "python/xyg/static")
# Produced by `npm run build:wasm` (js/package-wasm.mjs) into both locations.
PACKAGED = ("xyg-wasm.wasm", "xyg-wasm-inline.js", "xyg-wasm.manifest.json")
# Produced by `node js/build.mjs`; the Worker is the paired half of the tick pair.
CLIENT = ("wasm-worker.js",)
WASM_MAGIC = b"\0asm\x01\0\0\0"
PRODUCER = (
    "node js/build.mjs && npm run build:wasm   "
    "(needs `rustup target add wasm32-unknown-unknown`; in CI this is the `wasm_assets` job, "
    "downloaded as the `wasm-assets` artifact)"
)
_INLINE_SHA = re.compile(r'__xygInlineWasm=\{sha256:"([0-9a-f]{64})"')
_INLINE_WORKER = re.compile(r"classicWorkerSource:(\".*\")\};\s*$", re.DOTALL)


def _read_manifest(root: Path) -> dict[str, int]:
    return json.loads((root / "spec" / "wasm" / "abi.json").read_text(encoding="utf-8"))


def verify_members(read: Callable[[str], bytes | None], locations: Sequence[str]) -> list[str]:
    """Check the self-consistency of packaged assets read through ``read(relative_path)``.

    Works for a checkout directory, a wheel, or an sdist: presence, WebAssembly magic,
    manifest hash/size, and that the inline copy embeds the same module. Returns one
    message per problem.
    """
    errors: list[str] = []
    for location in locations:
        names = (*PACKAGED, *CLIENT)
        missing = [name for name in names if read(f"{location}/{name}") is None]
        if missing:
            errors.append(f"{location}: missing {', '.join(missing)}")
            continue
        wasm = read(f"{location}/xyg-wasm.wasm") or b""
        digest = hashlib.sha256(wasm).hexdigest()
        if not wasm.startswith(WASM_MAGIC):
            errors.append(f"{location}/xyg-wasm.wasm is not a WebAssembly module")
        try:
            meta = json.loads(read(f"{location}/xyg-wasm.manifest.json") or b"")
        except ValueError as exc:
            errors.append(f"{location}/xyg-wasm.manifest.json is not valid JSON: {exc}")
            continue
        if meta.get("sha256") != digest or meta.get("bytes") != len(wasm):
            errors.append(
                f"{location}/xyg-wasm.wasm does not match its manifest "
                f"(sha256 {digest[:12]}.. bytes {len(wasm)} vs manifest "
                f"{str(meta.get('sha256'))[:12]}.. bytes {meta.get('bytes')})"
            )
        inline = (read(f"{location}/xyg-wasm-inline.js") or b"").decode("utf-8", "replace")
        found = _INLINE_SHA.search(inline)
        if not found or found.group(1) != digest:
            errors.append(
                f"{location}/xyg-wasm-inline.js embeds a different WASM than xyg-wasm.wasm"
            )
    return errors


def verify(root: Path = ROOT) -> list[str]:
    """Return one message per problem; an empty list means the assets are usable."""

    def read(relative: str) -> bytes | None:
        path = root / relative
        return path.read_bytes() if path.is_file() else None

    errors = verify_members(read, LOCATIONS)
    if errors:
        return errors

    abi = _read_manifest(root)
    classic = root / "packages/xy-client/dist/wasm-inline-worker.js"
    for location in LOCATIONS:
        directory = root / location
        meta = json.loads((directory / "xyg-wasm.manifest.json").read_text(encoding="utf-8"))
        for key in ("abi_version", "scene_version", "painter_version"):
            if meta.get(key) != abi.get(key):
                errors.append(
                    f"{location} manifest {key}={meta.get(key)!r} is stale; "
                    f"spec/wasm/abi.json has {abi.get(key)!r}"
                )
        inline = (directory / "xyg-wasm-inline.js").read_text(encoding="utf-8")
        worker = _INLINE_WORKER.search(inline)
        if worker and classic.is_file():
            try:
                embedded = json.loads(worker.group(1))
            except ValueError:
                embedded = None
            if embedded != classic.read_text(encoding="utf-8"):
                errors.append(
                    f"{location}/xyg-wasm-inline.js embeds a stale classic worker; "
                    "rebuild with node js/build.mjs then npm run build:wasm"
                )
    for name in PACKAGED:
        copies = {(root / location / name).read_bytes() for location in LOCATIONS}
        if len(copies) != 1:
            errors.append(f"{name} differs between the two packaged locations")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="checkout root to verify")
    args = parser.parse_args(argv)
    errors = verify(args.root.resolve())
    if errors:
        print("ERROR: packaged WASM assets are missing or stale:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print(f"Produce them with: {PRODUCER}", file=sys.stderr)
        return 1
    print("Packaged WASM assets verified (bytes, sha256, ABI/scene/painter versions, inline copy).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
