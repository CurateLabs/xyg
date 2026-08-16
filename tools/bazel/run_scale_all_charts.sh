#!/usr/bin/env bash
# Scale scaffold soft gate: major mark families at --profile smoke.
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
export PYTHONPATH="${ROOT}/python${PYTHONPATH:+:${PYTHONPATH}}"

PYTHON="$(resolve_python "${ROOT}")"

run_py() {
  if [[ "${PYTHON}" == "uv" ]]; then
    (cd "${ROOT}" && uv run python "$@")
  else
    "${PYTHON}" "$@"
  fi
}

echo "XYG_NATIVE_LIB=${XYG_NATIVE_LIB}"
echo "scale_all_charts: --profile smoke"
run_py benchmarks/bench_scale_all_charts.py --profile smoke

if [[ -f "${ROOT}/packages/xy-node/src/index.js" ]]; then
  echo "scale_all_charts_node: --profile smoke"
  (cd "${ROOT}" && node benchmarks/bench_scale_all_charts_node.mjs --profile smoke)
fi

echo "tier3_pyramid: python + node"
run_py benchmarks/bench_tier3_pyramid.py
if [[ -f "${ROOT}/packages/xy-node/src/pyramid.js" ]]; then
  (cd "${ROOT}" && node benchmarks/bench_tier3_pyramid_node.mjs)
fi
