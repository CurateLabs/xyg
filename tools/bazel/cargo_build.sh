#!/usr/bin/env bash
# Build the release cdylib via cargo and copy it to the Bazel outs path.
# Usage: cargo_build.sh <path-to-Cargo.toml> <output-libxy_core.so>
set -euo pipefail

CARGO_TOML="${1:?Cargo.toml path required}"
OUT="${2:?output library path required}"

ROOT="$(cd "$(dirname "$(readlink -f "${CARGO_TOML}" 2>/dev/null || realpath "${CARGO_TOML}")")" && pwd)"
cd "${ROOT}"

if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo not found on PATH; install the Rust toolchain (see rust-toolchain.toml)" >&2
  exit 1
fi

echo "cargo build --release (cwd=${ROOT})"
cargo build --release

if [[ "$(uname -s)" == "Darwin" ]]; then
  SRC="${ROOT}/target/release/libxy_core.dylib"
else
  SRC="${ROOT}/target/release/libxy_core.so"
fi

if [[ ! -f "${SRC}" ]]; then
  echo "expected release library missing: ${SRC}" >&2
  exit 1
fi

mkdir -p "$(dirname "${OUT}")"
cp -f "${SRC}" "${OUT}"
echo "wrote ${OUT}"
