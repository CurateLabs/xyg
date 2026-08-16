#!/usr/bin/env bash
# Build the release cdylib via cargo and copy it to the Bazel outs path.
# Usage: cargo_build.sh <path-to-Cargo.toml> <output-libxyg_core.so>
set -euo pipefail

CARGO_TOML="${1:?Cargo.toml path required}"
OUT_ARG="${2:?output library path required}"

# Resolve the Bazel-declared output to an absolute path *before* cd'ing into
# the checkout. Genrule $@ is often relative to the execroot; after we cd to
# the real workspace a relative cp would land in a bogus workspace bazel-out/.
OUT_DIR="$(dirname "${OUT_ARG}")"
mkdir -p "${OUT_DIR}"
OUT="$(cd "${OUT_DIR}" && pwd)/$(basename "${OUT_ARG}")"

ROOT="$(cd "$(dirname "$(readlink -f "${CARGO_TOML}" 2>/dev/null || realpath "${CARGO_TOML}")")" && pwd)"
cd "${ROOT}"

if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo not found on PATH; install the Rust toolchain (see rust-toolchain.toml)" >&2
  exit 1
fi

echo "cargo build --release (cwd=${ROOT})"
cargo build --release

if [[ "$(uname -s)" == "Darwin" ]]; then
  SRC="${ROOT}/target/release/libxyg_core.dylib"
else
  SRC="${ROOT}/target/release/libxyg_core.so"
fi

if [[ ! -f "${SRC}" ]]; then
  echo "expected release library missing: ${SRC}" >&2
  exit 1
fi

cp -f "${SRC}" "${OUT}"
echo "wrote ${OUT}"
