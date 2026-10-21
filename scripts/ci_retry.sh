#!/usr/bin/env bash
# Retry a flaky network-bound CI command: ci_retry.sh ATTEMPTS COMMAND [ARGS...]
# Used only for package/browser installs in the post-merge benchmark jobs (#1008), where a
# transient registry or CDN failure must not turn main's Release surfaces aggregate red.
# The last attempt's exit status is returned; CI_RETRY_DELAY (seconds, default 15) scales
# the linear back-off between attempts.
set -u
attempts="${1:?usage: ci_retry.sh ATTEMPTS COMMAND [ARGS...]}"
shift
[ "$#" -gt 0 ] || { echo "ci_retry.sh: missing command" >&2; exit 2; }
case "$attempts" in '' | *[!0-9]* | 0) echo "ci_retry.sh: ATTEMPTS must be a positive integer" >&2; exit 2 ;; esac
attempt=1
while true; do
  "$@" && exit 0
  status=$?
  if [ "$attempt" -ge "$attempts" ]; then
    echo "ci_retry.sh: '$*' failed after $attempt attempt(s) (exit $status)" >&2
    exit "$status"
  fi
  echo "ci_retry.sh: attempt $attempt/$attempts failed (exit $status); retrying" >&2
  sleep $((attempt * ${CI_RETRY_DELAY:-15}))
  attempt=$((attempt + 1))
done
