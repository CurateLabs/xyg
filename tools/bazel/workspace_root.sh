#!/usr/bin/env bash
# Resolve the repository root for cargo-wrapping Bazel actions.
# Prefer Bazel-provided workspace paths; fall back to Cargo.toml discovery.
set -euo pipefail

_resolve_from_cargo_toml() {
  local toml="$1"
  local physical
  physical="$(readlink -f "${toml}" 2>/dev/null || realpath "${toml}")"
  cd "$(dirname "${physical}")" && pwd
}

if [[ -n "${BUILD_WORKSPACE_DIRECTORY:-}" && -f "${BUILD_WORKSPACE_DIRECTORY}/Cargo.toml" ]]; then
  printf '%s\n' "${BUILD_WORKSPACE_DIRECTORY}"
  exit 0
fi

if [[ -n "${TEST_WORKSPACE_DIRECTORY:-}" && -f "${TEST_WORKSPACE_DIRECTORY}/Cargo.toml" ]]; then
  printf '%s\n' "${TEST_WORKSPACE_DIRECTORY}"
  exit 0
fi

# no-sandbox test cwd is usually the execroot; Cargo.toml is a symlink into
# the real checkout — resolve it so cargo writes to the developer's target/.
if [[ -f "${PWD}/Cargo.toml" ]]; then
  _resolve_from_cargo_toml "${PWD}/Cargo.toml"
  exit 0
fi

for cand in \
  "${TEST_SRCDIR:-}/_main/Cargo.toml" \
  "${TEST_SRCDIR:-}/xy/Cargo.toml" \
  "${TEST_SRCDIR:-}/${TEST_WORKSPACE:-_main}/Cargo.toml"; do
  if [[ -n "${cand}" && -f "${cand}" ]]; then
    _resolve_from_cargo_toml "${cand}"
    exit 0
  fi
done

if command -v git >/dev/null 2>&1; then
  if root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    if [[ -f "${root}/Cargo.toml" ]]; then
      printf '%s\n' "${root}"
      exit 0
    fi
  fi
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
printf '%s\n' "$(cd "${HERE}/../.." && pwd)"
