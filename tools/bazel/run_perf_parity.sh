#!/usr/bin/env bash
# Quick dual-host graph + kernel soft-ceiling gate (small N).
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
echo "perf_parity: dual-host graph (n=1000) + parity kernels (n=100000)"
run_py benchmarks/bench_dual_host_graph.py --sizes 1000
# Small fixed size for CI speed; baseline soft-compare skipped when keys absent.
run_py benchmarks/bench_parity_kernels.py --sizes 100000 --no-baseline
