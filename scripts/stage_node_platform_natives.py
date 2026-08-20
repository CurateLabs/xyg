#!/usr/bin/env python3
"""Stage libxyg_core into exact-platform Node packages (#52).

Copies a built cdylib into the matching `@curatelabs/xyg-node-<platform>-<arch>`
package directory (and optionally into `packages/xy-node/_native_lib/` for
source-checkout fallbacks). Never searches system library paths.

Examples:
  python3 scripts/stage_node_platform_natives.py
  python3 scripts/stage_node_platform_natives.py --lib target/release/libxyg_core.so
  python3 scripts/stage_node_platform_natives.py --platform linux --arch x64 --lib path/to/libxyg_core.so
  python3 scripts/stage_node_platform_natives.py --dry-run
"""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = REPO_ROOT / "packages"

# Exact optional package matrix from packages/xy-node/src/native-path.js.
PLATFORM_PACKAGES: dict[tuple[str, str], tuple[str, str]] = {
    ("darwin", "arm64"): ("xyg-node-darwin-arm64", "libxyg_core.dylib"),
    ("darwin", "x64"): ("xyg-node-darwin-x64", "libxyg_core.dylib"),
    ("linux", "x64"): ("xyg-node-linux-x64", "libxyg_core.so"),
    ("linux", "arm64"): ("xyg-node-linux-arm64", "libxyg_core.so"),
    ("win32", "x64"): ("xyg-node-win32-x64", "xyg_core.dll"),
}

NODE_PLATFORM = {
    "Darwin": "darwin",
    "Linux": "linux",
    "Windows": "win32",
}

NODE_ARCH = {
    "arm64": "arm64",
    "aarch64": "arm64",
    "x86_64": "x64",
    "AMD64": "x64",
    "x64": "x64",
}


def detect_platform_arch() -> tuple[str, str]:
    sys_name = platform.system()
    machine = platform.machine()
    node_platform = NODE_PLATFORM.get(sys_name)
    node_arch = NODE_ARCH.get(machine)
    if node_platform is None or node_arch is None:
        raise SystemExit(f"unsupported host for Node native staging: {sys_name}/{machine}")
    if (node_platform, node_arch) == ("win32", "arm64"):
        raise SystemExit(
            "XYG Node does not support Windows arm64 (no @curatelabs/xyg-node-win32-arm64 package)."
        )
    if (node_platform, node_arch) not in PLATFORM_PACKAGES:
        raise SystemExit(
            f"no exact-platform package for {node_platform}-{node_arch}; "
            f"supported: {', '.join(f'{p}-{a}' for p, a in PLATFORM_PACKAGES)}"
        )
    return node_platform, node_arch


def default_lib_path(node_platform: str, lib_name: str) -> Path:
    release = REPO_ROOT / "target" / "release" / lib_name
    debug = REPO_ROOT / "target" / "debug" / lib_name
    if release.is_file():
        return release
    if debug.is_file():
        return debug
    raise SystemExit(
        f"native library not found at {release} or {debug}. "
        "Pass --lib or run `cargo build --release` first."
    )


def stage(
    *,
    node_platform: str,
    arch: str,
    lib: Path,
    also_facade: bool,
    dry_run: bool,
) -> list[Path]:
    key = (node_platform, arch)
    if key not in PLATFORM_PACKAGES:
        raise SystemExit(f"unsupported platform/arch: {node_platform}-{arch}")
    package_dir_name, expected_name = PLATFORM_PACKAGES[key]
    if lib.name != expected_name:
        raise SystemExit(
            f"library basename {lib.name!r} does not match "
            f"{node_platform}-{arch} expected {expected_name!r}"
        )
    if not lib.is_file():
        raise SystemExit(f"library file not found: {lib}")

    destinations: list[Path] = [
        PACKAGES / package_dir_name / expected_name,
    ]
    if also_facade:
        destinations.append(PACKAGES / "xy-node" / "_native_lib" / expected_name)

    written: list[Path] = []
    for dest in destinations:
        if dry_run:
            print(f"dry-run: {lib} -> {dest}")
            written.append(dest)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(lib, dest)
        print(f"staged {dest.relative_to(REPO_ROOT)} ({lib.stat().st_size} bytes)")
        written.append(dest)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=sorted({p for p, _ in PLATFORM_PACKAGES}))
    parser.add_argument("--arch", choices=sorted({a for _, a in PLATFORM_PACKAGES}))
    parser.add_argument("--lib", type=Path, help="path to the built cdylib/DLL")
    parser.add_argument(
        "--also-facade",
        action="store_true",
        help="also copy into packages/xy-node/_native_lib/",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the supported platform package matrix and exit",
    )
    args = parser.parse_args(argv)

    if args.list:
        for (plat, arch), (pkg, lib_name) in sorted(PLATFORM_PACKAGES.items()):
            print(f"{plat}-{arch}\t@curatelabs/{pkg}\t{lib_name}")
        return 0

    if (args.platform is None) ^ (args.arch is None):
        raise SystemExit("provide both --platform and --arch, or neither")

    node_platform, arch = (
        (args.platform, args.arch) if args.platform and args.arch else detect_platform_arch()
    )
    _, expected_name = PLATFORM_PACKAGES[(node_platform, arch)]
    lib = (args.lib or default_lib_path(node_platform, expected_name)).resolve()
    stage(
        node_platform=node_platform,
        arch=arch,
        lib=lib,
        also_facade=args.also_facade,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
