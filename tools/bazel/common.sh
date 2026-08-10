#!/usr/bin/env bash
# Shared helpers for Bazel sh_test wrappers.
# shellcheck shell=bash

_bazel_tools_dir() {
  local here cand
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -f "${here}/workspace_root.sh" ]]; then
    printf '%s\n' "${here}"
    return 0
  fi
  for cand in \
    "${TEST_SRCDIR:-}/_main/tools/bazel" \
    "${TEST_SRCDIR:-}/xy/tools/bazel" \
    "${TEST_SRCDIR:-}/${TEST_WORKSPACE:-_main}/tools/bazel" \
    "${BUILD_WORKSPACE_DIRECTORY:-}/tools/bazel"; do
    if [[ -n "${cand}" && -f "${cand}/workspace_root.sh" ]]; then
      printf '%s\n' "${cand}"
      return 0
    fi
  done
  printf '%s\n' "${here}"
}

find_native_lib() {
  local cand root="${1:-}"
  if [[ -n "${XY_NATIVE_LIB:-}" && -f "${XY_NATIVE_LIB}" ]]; then
    printf '%s\n' "${XY_NATIVE_LIB}"
    return 0
  fi
  for cand in \
    "${TEST_SRCDIR:-}/_main/libxy_core.so" \
    "${TEST_SRCDIR:-}/xy/libxy_core.so" \
    "${TEST_SRCDIR:-}/${TEST_WORKSPACE:-_main}/libxy_core.so" \
    "${BUILD_WORKSPACE_DIRECTORY:-}/bazel-bin/libxy_core.so" \
    "${root}/bazel-bin/libxy_core.so" \
    "${root}/target/release/libxy_core.so" \
    "${root}/target/debug/libxy_core.so"; do
    if [[ -n "${cand}" && -f "${cand}" ]]; then
      printf '%s\n' "${cand}"
      return 0
    fi
  done
  if [[ -n "${TEST_SRCDIR:-}" ]]; then
    cand="$(find "${TEST_SRCDIR}" -name 'libxy_core.so' -type f 2>/dev/null | head -n 1 || true)"
    if [[ -n "${cand}" ]]; then
      printf '%s\n' "${cand}"
      return 0
    fi
  fi
  return 1
}

resolve_python() {
  local root="${1}"
  if [[ -x "${root}/.venv/bin/python" ]]; then
    printf '%s\n' "${root}/.venv/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  echo "python3 not found" >&2
  return 1
}

expected_abi_from_source() {
  local root="${1}"
  local native_py="${root}/python/xy/_native.py"
  if [[ -f "${native_py}" ]]; then
    sed -n 's/^ABI_VERSION = //p' "${native_py}" | head -n 1
    return 0
  fi
  local lib_rs="${root}/src/lib.rs"
  if [[ -f "${lib_rs}" ]]; then
    sed -n 's/^pub const ABI_VERSION: u32 = \([0-9]*\);/\1/p' "${lib_rs}" | head -n 1
    return 0
  fi
  return 1
}

workspace_root() {
  local tools
  tools="$(_bazel_tools_dir)"
  "${tools}/workspace_root.sh"
}
