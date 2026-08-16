#!/usr/bin/env bash
# Pytest gate for the Python graph / sankey host binding.
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

tests=()
[[ -f tests/test_graph.py ]] && tests+=(tests/test_graph.py)
[[ -f tests/test_sankey.py ]] && tests+=(tests/test_sankey.py)

if [[ ${#tests[@]} -eq 0 ]]; then
  echo "no graph/sankey pytest files found under tests/" >&2
  exit 1
fi

echo "XYG_NATIVE_LIB=${XYG_NATIVE_LIB}"
if [[ "${PYTHON}" == "uv" ]]; then
  echo "running: uv run python -m pytest -q ${tests[*]}"
  cd "${ROOT}"
  exec uv run python -m pytest -q "${tests[@]}"
fi
echo "running: ${PYTHON} -m pytest -q ${tests[*]}"
exec "${PYTHON}" -m pytest -q "${tests[@]}"
