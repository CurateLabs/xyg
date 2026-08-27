#!/usr/bin/env bash
# One-shot: assign M2 follow-on issues to Milestone 2, label them, close
# permission-probe leftovers, and rescope #276 after PR #284 tick-adapter
# retirement. Idempotent. Uses Actions GITHUB_TOKEN (issues: write).
# Cloud Agent App tokens get 403 on issues:write / milestones:write.
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-CurateLabs/xyg}"
if [[ -z "${GH_TOKEN:-${GITHUB_TOKEN:-}}" ]]; then
  echo "GH_TOKEN or GITHUB_TOKEN is required" >&2
  exit 1
fi
export GH_TOKEN="${GH_TOKEN:-$GITHUB_TOKEN}"

MILESTONE_NUMBER=2
MILESTONE_TITLE="M2: Rust-Owned Cross-Host Core"
LABELS='["enhancement","performance","spec"]'
FOLLOW_ONS=(271 272 273 274 275 276 277 278 279 280 281 282 283)
PROBES=(267 268 269 270)
P0S=(271 272 273 274)
LEDGER_MARKER="M2 follow-on ledger — PR #284 tick-adapter retirement"
PROBE_MARKER="Permission probe leftover — not planned"

issue_json() {
  gh api "repos/${REPO}/issues/$1"
}

has_marker_comment() {
  local number="$1"
  local marker="$2"
  local bodies
  bodies="$(gh api "repos/${REPO}/issues/${number}/comments" --paginate --jq '.[].body')"
  [[ "$bodies" == *"$marker"* ]]
}

ensure_comment() {
  local number="$1"
  local marker="$2"
  local body="$3"
  if has_marker_comment "$number" "$marker"; then
    echo "issue #${number} already has marker comment"
    return 0
  fi
  gh api -X POST "repos/${REPO}/issues/${number}/comments" -f body="$body" >/dev/null
  echo "posted comment on #${number}"
}

assign_follow_on() {
  local number="$1"
  local current_milestone labels_csv
  current_milestone="$(issue_json "$number" | jq -r '.milestone.number // empty')"
  if [[ "$current_milestone" != "$MILESTONE_NUMBER" ]]; then
    gh api -X PATCH "repos/${REPO}/issues/${number}" \
      -F "milestone=${MILESTONE_NUMBER}" >/dev/null
    echo "assigned #${number} → milestone ${MILESTONE_NUMBER}"
  else
    echo "issue #${number} already on milestone ${MILESTONE_NUMBER}"
  fi

  # Add labels idempotently (POST is additive; duplicates are ignored).
  gh api -X POST "repos/${REPO}/issues/${number}/labels" \
    --input - <<<"${LABELS}" >/dev/null
  labels_csv="$(issue_json "$number" | jq -r '[.labels[].name] | join(",")')"
  echo "labels on #${number}: ${labels_csv}"
}

close_probe() {
  local number="$1"
  local state
  state="$(issue_json "$number" | jq -r .state)"
  ensure_comment "$number" "$PROBE_MARKER" "$(cat <<EOF
## ${PROBE_MARKER}

Auth / permission probe created while diagnosing Cloud Agent \`issues: write\`
limits (403 App token). Not product work — closing as not planned.
EOF
)"
  if [[ "$state" == "closed" ]]; then
    echo "probe #${number} already closed"
    return 0
  fi
  gh api -X PATCH "repos/${REPO}/issues/${number}" \
    -f state=closed \
    -f state_reason=not_planned >/dev/null
  echo "closed probe #${number} as not_planned"
}

rescope_276() {
  local body
  body="$(cat <<'EOF'
## Context

Post-close **M2 follow-on debt** from the Python core-debt inventory. Inventory concluded **SAFE TO REMOVE NOW was empty**. Related: #24, #58, #59; tracker #54.

**Update:** automatic tick-family wrappers / `try_public_*` adapters were already retired in PR https://github.com/CurateLabs/xyg/pull/284. This issue no longer covers removing those automatic adapters.

## Problem

Rust tick records are still incomplete for the **remaining** tick/format policy that Python owns in `python/xyg/_svg.py` and related helpers:

- authored filtering and authored labels
- minor ticks
- polar / secondary axes
- rich formats
- collision helpers

Product path still reaches Python for those leftovers (not the retired automatic family adapters).

## Objective

Complete Rust tick records for authored filtering, labels, minors, polar/secondary, rich formats, and collision helpers; retire the corresponding Python tick/format leftovers only after Scene consumers stop calling them.

## Scope

- Extend Rust tick ABI/records for authored filtering, labels, minors, polar/secondary, rich formats, and collision helpers.
- Keep f64 tick/hover math invariants (§4/§16).
- Do **not** re-litigate automatic tick-family adapter removal (done in PR #284).
- Retire remaining Python formatters only with differential label proofs.

## Acceptance

- Scene/export tick labels match prior Python behavior for authored, minor, secondary/polar, rich formats, and collision cases without the remaining `_svg` tick helpers.
- Proof via Scene/SVG/export tests covering those remaining cases.
- **Delete Python only after** Rust owns the path **and** differential proof is green.

## Priority

P1.
EOF
)"
  gh api -X PATCH "repos/${REPO}/issues/276" -f body="$body" >/dev/null
  echo "rescoped issue #276 body"
}

post_p0_ledger() {
  local number="$1"
  ensure_comment "$number" "$LEDGER_MARKER" "$(cat <<EOF
## ${LEDGER_MARKER}

Shared ledger for M2 follow-on P0 issues (this thread is the record; no auto-close intent):

- PR https://github.com/CurateLabs/xyg/pull/284 retired \`try_public_*\` and automatic tick-family adapters on the Python Scene path.
- Remaining M2 follow-on work stays on milestone **${MILESTONE_TITLE}** (issues 271–283).
- Tick leftovers beyond that retirement are tracked under issue 276 (authored filtering, labels, minors, polar/secondary, rich formats, collision helpers).
EOF
)"
}

echo "Ensuring milestone ${MILESTONE_NUMBER} (${MILESTONE_TITLE}) stays open"
ms_state="$(gh api "repos/${REPO}/milestones/${MILESTONE_NUMBER}" --jq .state)"
if [[ "$ms_state" != "open" ]]; then
  gh api -X PATCH "repos/${REPO}/milestones/${MILESTONE_NUMBER}" -f state=open >/dev/null
  echo "reopened milestone ${MILESTONE_NUMBER}"
else
  echo "milestone ${MILESTONE_NUMBER} already open"
fi

echo "Assigning follow-on issues ${FOLLOW_ONS[*]}"
for n in "${FOLLOW_ONS[@]}"; do
  assign_follow_on "$n"
done

echo "Rescoping #276"
rescope_276

echo "Closing permission probes ${PROBES[*]}"
for n in "${PROBES[@]}"; do
  close_probe "$n"
done

echo "Posting P0 ledger note on #271 only (single ledger)"
post_p0_ledger 271

echo "Verification summary:"
for n in "${FOLLOW_ONS[@]}"; do
  gh api "repos/${REPO}/issues/${n}" \
    --jq '{number,state,milestone:(.milestone.title//null),labels:[.labels[].name]}'
done
for n in "${PROBES[@]}"; do
  gh api "repos/${REPO}/issues/${n}" \
    --jq '{number,state,state_reason}'
done

echo "M2 assign/close sequence finished"
