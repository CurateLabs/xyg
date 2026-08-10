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

# no-sandbox test cwd is usually the runfiles tree; Cargo.toml is a symlink
# into the real checkout — resolve it so cargo/pytest see target/ and .venv.
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

# Last resort: walk parents for a checkout that has both MODULE.bazel and Cargo.toml.
d="${PWD}"
while [[ "${d}" != "/" ]]; do
  if [[ -f "${d}/MODULE.bazel" && -f "${d}/Cargo.toml" ]]; then
    # If this is a runfiles execroot copy, prefer the physical Cargo.toml path.
    if [[ -L "${d}/Cargo.toml" ]]; then
      _resolve_from_cargo_toml "${d}/Cargo.toml"
      exit 0
    fi
    printf '%s\n' "${d}"
    exit 0
  fi
  d="$(dirname "${d}")"
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
# tools/bazel -> repo root when scripts live in the real checkout.
if [[ -f "${HERE}/../../Cargo.toml" ]]; then
  _resolve_from_cargo_toml "${HERE}/../../Cargo.toml"
  exit 0
fi
printf '%s\n' "$(cd "${HERE}/../.." && pwd)"
