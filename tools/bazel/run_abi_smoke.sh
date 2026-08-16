#!/usr/bin/env bash
# Stdlib-only C-ABI smoke against the Bazel-built (or cargo) cdylib.
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

LIB="$(find_native_lib "${ROOT}")" || {
  echo "libxyg_core.so not found; build //:xyg_core first" >&2
  exit 1
}
export XYG_NATIVE_LIB="${LIB}"

PYTHON="$(resolve_python "${ROOT}")"
echo "XYG_NATIVE_LIB=${XYG_NATIVE_LIB}"
if [[ "${PYTHON}" == "uv" ]]; then
  echo "running: uv run python scripts/abi_smoke.py"
  cd "${ROOT}"
  exec uv run python scripts/abi_smoke.py
fi
echo "running: ${PYTHON} scripts/abi_smoke.py"
exec "${PYTHON}" scripts/abi_smoke.py
