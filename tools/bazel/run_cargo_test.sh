#!/usr/bin/env bash
# Run `cargo test` against the workspace Cargo.toml (graph MVP gate).
set -euo pipefail

_TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "${_TOOLS}/common.sh" ]]; then
  for _cand in \
    "${TEST_SRCDIR:-}/_main/tools/bazel" \
    "${TEST_SRCDIR:-}/xy/tools/bazel" \
    "${TEST_SRCDIR:-}/${TEST_WORKSPACE:-_main}/tools/bazel"; do
    if [[ -f "${_cand}/common.sh" ]]; then
      _TOOLS="${_cand}"
      break
    fi
  done
fi
# shellcheck source=common.sh
source "${_TOOLS}/common.sh"

ROOT="$(workspace_root)"
cd "${ROOT}"

if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo not found on PATH; install the Rust toolchain (see rust-toolchain.toml)" >&2
  exit 1
fi

echo "cargo test (cwd=${ROOT})"
exec cargo test
