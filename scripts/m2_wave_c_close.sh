#!/usr/bin/env bash
# Wave C closer / completion-comment backfill for Milestone 2 claimed subsets.
# Idempotent: closes open issues, and posts the completion comment when missing
# even if the issue is already closed. Related to #58 / #59 / #24 without using
# Fixes/Closes/Resolves keywords in PR bodies that auto-close issues.
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-CurateLabs/xyg}"
if [[ -z "${GH_TOKEN:-${GITHUB_TOKEN:-}}" ]]; then
  echo "GH_TOKEN or GITHUB_TOKEN is required" >&2
  exit 1
fi
export GH_TOKEN="${GH_TOKEN:-$GITHUB_TOKEN}"

issue_state() {
  gh api "repos/${REPO}/issues/$1" --jq .state
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
  local body_file="$3"
  if has_marker_comment "$number" "$marker"; then
    echo "issue #${number} already has completion comment"
    return 0
  fi
  gh api -X POST "repos/${REPO}/issues/${number}/comments" \
    -f body="$(cat "$body_file")" >/dev/null
  echo "posted completion comment on #${number}"
}

ensure_closed() {
  local number="$1"
  local state
  state="$(issue_state "$number")"
  if [[ "$state" == "closed" ]]; then
    echo "issue #${number} already closed"
    return 0
  fi
  gh api -X PATCH "repos/${REPO}/issues/${number}" \
    -f state=closed \
    -f state_reason=completed >/dev/null
  echo "closed #${number}"
}

comment_and_close() {
  local number="$1"
  local marker="$2"
  local body_file="$3"
  ensure_comment "$number" "$marker" "$body_file"
  ensure_closed "$number"
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat >"$TMP/58.md" <<'EOF'
## M2 Wave C completion record

The bounded Cartesian Scene/static-export scope for this epic is complete on `main` at `879115f` (plus closer #265):

- Python and Node produce identical Scene v25 goldens for constant-style Cartesian hexbin (`count` / `mean` / `sum`) and heatmap (`public_hexbin_sha256`, `public_heatmap_sha256` in `tests/fixtures/figure_scene_v3.json`).
- Eligible hexbin and heatmap route through the canonical Rust SVG, raster/PNG, PDF-via-SVG, and browser-painter consumers (`tests/test_scene_export_support.py`, `packages/xy-node/test/scene.test.mjs`).
- Committed export baselines record Scene/painter/SVG/PNG/PDF sizes, construction/export timings, and peak memory (`spec/benchmarks/public-scene-export-local.json`).
- The Wave B ledger is in `spec/benchmarks/results.md` (PR #263).

Landed slices: #259 (hexbin Scene), #261 (heatmap Scene), #263 (evidence). Disposition: #264.

Remaining features stay **loud compatibility routes**, not silent approximations:

- polar Scene projection/chrome and alternate-axis variants;
- custom fonts, CSS/classes, markup, rotation, collision/layout text, and rich annotations;
- gradients, rounded corners, curves/dashes, custom marker paths/glyphs, and per-item styles;
- LOD/density and over-budget meshes, hexbin painter groups, or heatmap cell counts;
- hexbin custom reducers and metric colormaps;
- heatmap metric colormaps, truecolor RGBA, and irregular grids.

These keepers are documented in `spec/design/host-parity.md`, `spec/design/scene-ir.md`, and `spec/design/ownership-audit.md`.
EOF

cat >"$TMP/59.md" <<'EOF'
## M2 claimed-subset completion record

Delivered on `main` (disposition #264 at `879115f`):

- Worker/WASM foundation and strict-CSP offline contract
- Packaged WASM tick assets for hosted `to_html` / notebooks (#258)
- ChartView authored / authored-empty ticks (#257); category / UTC-time (#252)
- ChartView colorbar ticks (#262)
- Reflex `XYChart` packaged-asset auto-attach (#260)
- Cross-host Scene/painter goldens and interpreted 100–1M hosted budgets (`spec/benchmarks/results.md`, #263)

Angular/polar and secondary-axis ChartView paths remain **frozen deferred keepers** on the JavaScript tick path.

Work outside this claimed subset is tracked as post-M2 follow-ups under #54 (see `spec/design/browser-wasm.md` § M2 #59 disposition):

- Prove Reflex packaged WASM tick auto-attach in a real browser
- Expand direct-browser aggregate production beyond the density/Scene vertical
- Refresh hosted WASM evidence and prove density no-refinement degradation
EOF

cat >"$TMP/24.md" <<'EOF'
## M2 complete

Children #58 and #59 are complete for the M2 claimed subsets. Architectural context #18, #22, #23, #56, and #57 were already done. Post-M2 release-matrix work continues under #54.
EOF

comment_and_close 58 "M2 Wave C completion record" "$TMP/58.md"
comment_and_close 59 "M2 claimed-subset completion record" "$TMP/59.md"
comment_and_close 24 "M2 complete" "$TMP/24.md"

milestone_state="$(gh api "repos/${REPO}/milestones/2" --jq .state)"
if [[ "$milestone_state" == "closed" ]]; then
  echo "milestone 2 already closed"
else
  gh api -X PATCH "repos/${REPO}/milestones/2" -f state=closed >/dev/null
  echo "closed milestone 2"
fi

echo "Wave C close sequence finished"
