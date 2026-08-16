#!/usr/bin/env bash
# Node host golden tests against the shared libxyg_core.so.
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

PKG="${ROOT}/packages/xy-node"
if [[ ! -f "${PKG}/package.json" ]]; then
  echo "packages/xy-node missing; create the Node binding package first" >&2
  exit 1
fi

LIB="$(find_native_lib "${ROOT}")" || {
  echo "libxyg_core.so not found; build //:xyg_core first" >&2
  exit 1
}
export XYG_NATIVE_LIB="${LIB}"

if [[ -z "${XYG_EXPECTED_ABI:-}" ]]; then
  XYG_EXPECTED_ABI="$(expected_abi_from_source "${ROOT}" || true)"
  if [[ -n "${XYG_EXPECTED_ABI}" ]]; then
    export XYG_EXPECTED_ABI
  fi
fi

if [[ ! -d "${PKG}/node_modules" ]]; then
  echo "npm ci in packages/xy-node"
  (cd "${PKG}" && npm ci)
fi

echo "XYG_NATIVE_LIB=${XYG_NATIVE_LIB}"
echo "XYG_EXPECTED_ABI=${XYG_EXPECTED_ABI:-<unset>}"
echo "running: npm test (cwd=${PKG})"
cd "${PKG}"
exec npm test
