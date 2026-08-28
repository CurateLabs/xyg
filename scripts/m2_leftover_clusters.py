#!/usr/bin/env python3
"""Create or refresh M2 leftover-cluster sub-issues.

Idempotent: matches existing issues by exact title. Uses ``gh`` (needs
``issues:write``). Cloud Agent App tokens 403; a ``repo``-scoped token works.

    python3 scripts/m2_leftover_clusters.py --dry-run
    python3 scripts/m2_leftover_clusters.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

REPO = "CurateLabs/xyg"
MILESTONE = "M2: Rust-Owned Cross-Host Core"
LABELS = ("enhancement", "performance", "spec")
INVENTORY = (
    "Inventory after draft PR https://github.com/curatelabs/xyg/pull/286 "
    "HEAD ABI 188 (`c722fa4e`). Related: #24, #58, #59, tracker #54."
)
PARENT_MARKER = "<!-- m2-leftover-clusters -->"
COMMENT_MARKER = "M2 leftover clusters — sub-issues"
CONTRACT = """\
## Landing contract

- One leftover cluster per PR. Do not stack onto PR #286.
- Wait until the **current HEAD** required checks are green (Test, WASM
  foundation, Python 3.11 floor) before the next push on the same ref.
  `.github/workflows/ci.yml` cancels superseded runs on purpose.
- Close this issue independently. The parent stays open until every child
  is closed or recorded as a bounded fail-closed contract.
- **Delete Python only after** Rust owns the path **and** differential
  proof is green. Do not delete under this issue alone.
"""

# Each cluster is one closeable GitHub sub-issue. ``parent`` is the GitHub
# parent issue. ``also_blocks`` are extra umbrellas that close when this does.
CLUSTERS: list[dict[str, Any]] = [
    {
        "key": "271-predicates",
        "parent": 271,
        "also_blocks": [],
        "priority": "P0",
        "title": "[M2 follow-on][P0][#271] Remaining Scene eligibility predicates in `_scene_v3.py`",
        "problem": (
            "`figure_scene` already calls Rust `scene_encode_product`, but Python "
            "still decides Scene vs compatibility for heatmap/hexbin tessellation "
            "and some style allowlists before packing. Hosts should pack; Rust "
            "XYFS should fail closed."
        ),
        "objective": (
            "Move remaining product-policy eligibility predicates out of "
            "`python/xyg/_scene_v3.py` into Rust figure-compile support so Python "
            "and Node stay thin packers."
        ),
        "proof": "`tests/test_scene_export_support.py`, `tests/test_figure_scene_v3.py`, Node `sceneExportSupportReason`.",
    },
    {
        "key": "272-css",
        "parent": 272,
        "also_blocks": [273, 275],
        "priority": "P0",
        "title": "[M2 follow-on][P0][#272] Custom fonts / CSS / classes Scene contract",
        "problem": (
            "`SCENE_FEATURE_CUSTOM_FONT` and `SCENE_FEATURE_BROWSER_CSS` still "
            "select the compatibility SVG/raster renderers. Custom `font-family`, "
            "chart/theme CSS, and `class_name` stay on `_svg.py` / `_raster.py`."
        ),
        "objective": (
            "Either admit a bounded literal subset into Scene, or record the "
            "fail-closed diagnostic as the product contract and stop treating "
            "browser CSS as open P0 migration debt. Default-font Scene figures "
            "must not need `_svg.to_svg` / `_raster` fallback."
        ),
        "proof": "`tests/test_scene_export_support.py` custom_font/browser_css cases; SVG/PNG differentials for default-font figures.",
    },
    {
        "key": "272-var-gradients",
        "parent": 272,
        "also_blocks": [273],
        "priority": "P0",
        "title": "[M2 follow-on][P0][#272] Unresolved `var()` / theme CSS gradients",
        "problem": (
            "Unresolved browser-only gradients (`var()`, chart/theme CSS) still "
            "fail closed. ABI 146 owns constant mark-fill linear-gradients; this "
            "cluster is the unresolved/CSS remainder."
        ),
        "objective": (
            "Admit resolved literal gradients already in scope, and either admit "
            "or pin `var()` / theme CSS as the bounded fail-closed contract."
        ),
        "proof": "`tests/test_scene_export_support.py`, `tests/test_export_style_survival.py`.",
    },
    {
        "key": "272-ribbon-color2",
        "parent": 272,
        "also_blocks": [273],
        "priority": "P0",
        "title": "[M2 follow-on][P0][#272] Per-item two-ended ribbon `color2_ch`",
        "problem": (
            "ABI 183 admits constant ribbon `color2_ch` as XYGR mark-space right. "
            "Per-item two-ended `color2_ch` arrays still force compatibility."
        ),
        "objective": (
            "Admit per-item two-ended ribbon paint on the product Scene, or pin "
            "the constant-only allowlist as the bounded contract with tests."
        ),
        "proof": "`tests/test_figure_scene_v3.py`, `tests/test_scene_export_support.py`, ribbon SVG/PNG differentials.",
    },
    {
        "key": "272-marker-glyph",
        "parent": 272,
        "also_blocks": [273],
        "priority": "P0",
        "title": "[M2 follow-on][P0][#272] Multi-character `marker_glyph`",
        "problem": (
            "ABI 170 admits constant single-character `marker_glyph`. Combined "
            "`marker_path` + `marker_glyph` and multi-character glyphs still "
            "fail closed."
        ),
        "objective": (
            "Admit multi-character glyphs (and/or the combined path+glyph case) "
            "or pin single-character-only as the bounded Scene contract."
        ),
        "proof": "`tests/test_figure_scene_v3.py` marker_glyph cases; SVG `<text>` / raster `OP_TEXT`.",
    },
    {
        "key": "272-polar-heatmap",
        "parent": 272,
        "also_blocks": [273],
        "priority": "P0",
        "title": "[M2 follow-on][P0][#272] Polar heatmap inverse-raster",
        "problem": (
            "Polar heatmap tessellates lattice Rects to wedges on Scene, but "
            "inverse-raster polar heatmap still selects compatibility."
        ),
        "objective": (
            "Make inverse-raster polar heatmap Scene-eligible, or pin the "
            "forward-tessellation-only contract with a stable diagnostic."
        ),
        "proof": "`tests/test_scene_export_support.py`, polar heatmap SVG/PNG differentials.",
    },
    {
        "key": "272-heatmap-hexbin-stroke",
        "parent": 272,
        "also_blocks": [273],
        "priority": "P0",
        "title": "[M2 follow-on][P0][#272] Heatmap/hexbin `stroke_opacity`",
        "problem": (
            "Heatmap/hexbin `fill_opacity` is Scene-owned. `stroke_opacity` stays "
            "on the fill-only allowlist and selects compatibility."
        ),
        "objective": (
            "Admit heatmap/hexbin `stroke_opacity` on XYMS, or pin fill-only as "
            "the bounded contract so this is not open P0 debt."
        ),
        "proof": "`tests/test_scene_export_support.py` heatmap/hexbin opacity cases.",
    },
    {
        "key": "272-polar-hexbin",
        "parent": 272,
        "also_blocks": [273],
        "priority": "P0",
        "title": "[M2 follow-on][P0][#272] Polar hexbin / custom reducers / categorical `direct_rgba`",
        "problem": (
            "ABI 186 admits cartesian colormap hexbin as 1xN XYHP. Polar hexbin, "
            "custom reducers, and categorical / `direct_rgba` color channels "
            "still fail closed."
        ),
        "objective": (
            "Admit those hexbin leftover paths on Scene, or pin cartesian "
            "colormap-only as the bounded contract with diagnostics."
        ),
        "proof": "`tests/test_figure_scene_v3.py`, `tests/test_scene_export_support.py`, Node hexbin Scene tests.",
    },
    {
        "key": "272-mesh-role",
        "parent": 272,
        "also_blocks": [273],
        "priority": "P0",
        "title": "[M2 follow-on][P0][#272] Triangle-mesh custom `role` / per-item color/stroke",
        "problem": (
            "Bounded fill-only unjoined meshes and ABI 182 `joined_fill` are "
            "Scene-owned. Custom `role` and per-item color/stroke still select "
            "compatibility."
        ),
        "objective": (
            "Admit custom role / per-item mesh paint, or pin the bounded mesh "
            "allowlist as the product contract."
        ),
        "proof": "`tests/test_scene_export_support.py` triangle_mesh cases; SVG/PNG differentials.",
    },
    {
        "key": "272-scatter-per-item",
        "parent": 272,
        "also_blocks": [273],
        "priority": "P0",
        "title": "[M2 follow-on][P0][#272] Scatter per-item stroke / width / opacity arrays",
        "problem": (
            "Constant scatter stroke/width/opacity is Scene-owned. Per-item "
            "stroke, width, and opacity arrays still force `_svg._scatter_marks` "
            "/ raster emitters."
        ),
        "objective": (
            "Admit per-item scatter stroke/width/opacity on Scene, or pin "
            "constant-only as the bounded contract."
        ),
        "proof": "`tests/test_scene_export_support.py` builtin_symbol_cutover fail-closed cases; scatter SVG/PNG differentials.",
    },
    {
        "key": "275-css-room",
        "parent": 275,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#275] CSS-room / custom font measurement leftovers",
        "problem": (
            "ABI 125 owns default-font text-block measure and cartesian axis "
            "rooms. Custom `font-family` on `chrome_styles` still fail-closes "
            "(`SCENE_FEATURE_CUSTOM_FONT`). Compatibility `_svg._*room` still "
            "runs CSS-dependent measurement."
        ),
        "objective": (
            "Retire Python `_*room` for default-font Scene figures. Keep custom "
            "font measurement fail-closed unless a later admit lands. Do not "
            "admit CSS-room custom fonts as a silent DejaVu substitute."
        ),
        "proof": "`tests/test_scene_export_support.py`, layout/export differentials, pyplot tight-layout where it shares rooms.",
    },
    {
        "key": "275-legendfit",
        "parent": 275,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#275] Remaining `_legendfit.py` / legend box leftovers",
        "problem": (
            'ABI 120 owns `loc="best"` occupancy and ABI 124 owns static legend '
            "box packing. `python/xyg/_legendfit.py` and `_svg._legend_layout` "
            "still run CSS/polar remaps on the compatibility path."
        ),
        "objective": (
            "Stop calling Python legend-fit/layout for Scene-eligible figures. "
            "Retire `_legendfit.py` only after those callers are gone."
        ),
        "proof": "Legend layout/export tests; Scene SVG/PNG with primary legend.",
    },
    {
        "key": "275-tight-layout",
        "parent": 275,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#275] Remaining tight-layout / padding / polar recut leftovers",
        "problem": (
            "ABI 126/127 own static-export padding, title-band, colorbar extra, "
            "and the pyplot tight-layout grid solve. Compatibility SVG/raster "
            "and some pyplot paths still combine those with Python chrome "
            "measurement."
        ),
        "objective": (
            "Make Scene and pyplot tight-layout consumers use the Rust layout "
            "combination for in-scope figures without Python padding/recut policy."
        ),
        "proof": "pyplot tight-layout tests; static-export padding/polar recut differentials.",
    },
    {
        "key": "276-authored",
        "parent": 276,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#276] Authored tick filtering and authored labels",
        "problem": (
            "ABI 128 owns authored tick-window resolve/filter as a kernel, but "
            "compatibility `_svg._tick_window` / authored `tick_labels` still "
            "present labels on the product path. Automatic family adapters were "
            "retired in PR #284; this is the leftover."
        ),
        "objective": (
            "Scene/export tick labels match prior Python behavior for authored "
            "values and authored label strings without `_svg` tick helpers."
        ),
        "proof": "Scene/SVG tick tests covering authored `tick_values` / `tick_labels`.",
    },
    {
        "key": "276-minors",
        "parent": 276,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#276] Minor ticks",
        "problem": (
            "Rust tick records still omit remaining minor-tick policy that "
            "compatibility `_svg.py` owns."
        ),
        "objective": "Complete Rust minor-tick records for Scene-eligible axes; retire the Python leftover after differentials.",
        "proof": "Scene/SVG tests covering minor ticks on linear/log/symlog axes.",
    },
    {
        "key": "276-polar-secondary",
        "parent": 276,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#276] Polar / secondary axis ticks",
        "problem": (
            "Polar and secondary-axis tick placement/formatting still reach "
            "Python compatibility helpers. Angular `tick_label_strategy` other "
            "than none/off is refused on polar rims (polar-axes.md)."
        ),
        "objective": (
            "Rust-own polar/secondary tick records in scope. Keep documented "
            "polar rim collision refusals explicit."
        ),
        "proof": "Polar/secondary Scene/SVG tick tests; `spec/design/polar-axes.md` contract tests.",
    },
    {
        "key": "276-rich-formats",
        "parent": 276,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#276] Rich tick formats",
        "problem": (
            "ABI 96/130 own bounded numeric formats for Scene-eligible "
            "linear/log/symlog axes. Richer format strings still use "
            "`_svg._tick_text` / `_fmt_axis`."
        ),
        "objective": (
            "Extend Rust tick formatting for the remaining in-scope rich "
            "formats, or pin the ABI 96 subset as the bounded Scene contract."
        ),
        "proof": "Tick format Scene/SVG tests; `_tick_text` callers gone for in-scope figures.",
    },
    {
        "key": "276-collision",
        "parent": 276,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#276] Tick collision / `tick_label_strategy`",
        "problem": (
            "ABI 123 owns tick-label collision thinning as a kernel. Public "
            "`tick_label_strategy` `auto`/`hide`/`rotate`/`stagger`/`preserve` "
            'and `axis_options["x"]["collision"]="hide"` still fail closed '
            "on Scene. `none`/`off` are polar-documented but not the full "
            "cartesian leftover."
        ),
        "objective": (
            "Admit the remaining public strategies on Scene, or pin which "
            "values are product vs fail-closed, with tests for each."
        ),
        "proof": "`tests/test_scene_ir.py` collision case; Scene/SVG tick-layout differentials.",
    },
    {
        "key": "278-html",
        "parent": 278,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#278] Annotation `html`",
        "problem": (
            "ABI 184-188 admit cartesian unwrapped text and labelled marker "
            "`dx`/`dy`/`anchor`/`rotation`. Annotation `html` still fail-closes."
        ),
        "objective": "Admit bounded annotation html, or pin it as fail-closed with a stable diagnostic.",
        "proof": "`tests/test_scene_export_support.py`, annotation SVG/raster tests.",
    },
    {
        "key": "278-class-name",
        "parent": 278,
        "also_blocks": [272],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#278] Annotation `class_name`",
        "problem": "Annotation `class_name` still fail-closes with browser CSS. Rotation/layout admits did not cover it.",
        "objective": "Admit bounded class names, or pin `SCENE_FEATURE_BROWSER_CSS` as the annotation contract too.",
        "proof": "`tests/test_scene_export_support.py` class_name annotation case.",
    },
    {
        "key": "278-collision",
        "parent": 278,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#278] Annotation collision",
        "problem": (
            "Annotation `collision` directives still select compatibility. "
            "This is separate from ABI 123 tick-label collision."
        ),
        "objective": "Admit annotation collision policy on Scene, or pin it fail-closed with tests.",
        "proof": "`tests/test_scene_ir.py` / `tests/test_scene_export_support.py` annotation collision cases.",
    },
    {
        "key": "278-markup",
        "parent": 278,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#278] Annotation markup",
        "problem": "Rich annotation markup still fail-closes; Scene owns literal text only.",
        "objective": "Admit a bounded markup subset, or pin literal-text-only as the Scene contract.",
        "proof": "Annotation SVG/raster tests; `tests/test_scene_ir.py` wrapping/markup fail-closed cases.",
    },
    {
        "key": "278-typography",
        "parent": 278,
        "also_blocks": [275],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#278] Annotation custom typography",
        "problem": (
            "Custom annotation typography still fail-closes with "
            "`SCENE_FEATURE_CUSTOM_FONT`. Public `Figure.text()` / `Figure.marker()` "
            "do not take `rotation=` as a keyword; pyplot still puts rotation on "
            "style, which stays fail-closed with custom typography."
        ),
        "objective": (
            "Admit bounded annotation typography, or pin default-font Scene "
            "annotations as the contract and keep custom fonts compatibility."
        ),
        "proof": "Annotation typography SVG/raster tests; Scene support diagnostics.",
    },
    {
        "key": "279-compat-geometry",
        "parent": 279,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#279] Compatibility emitters still call `_scene.py` geometry",
        "problem": (
            "ABI 121 owns `ribbon_edge` / `ribbon_polygon` / `curve_flatten` / "
            "`rounded_rect_poly`. Product Scene no longer needs Python geometry, "
            "but compatibility `_svg.py` / `_raster.py` still call "
            "`python/xyg/_scene.py` wrappers (`curve_points`, ribbon helpers, "
            "`rounded_rect_poly`, `grid_*`)."
        ),
        "objective": (
            "Point remaining compatibility emitters at the Rust kernels (thin "
            "packers). Retire `_scene.py` helpers only after those callers are gone."
        ),
        "proof": "Geometry/export differentials; grep that product Scene compile does not import `_scene.py`.",
    },
    {
        "key": "282-m4",
        "parent": 282,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#282] Remaining `_m4_decimate` policy",
        "problem": (
            "ABI 122 owns compile-time payload LOD and the visible-row mask. "
            "`python/xyg/_payload.py` `_m4_decimate` still decides live emit "
            "decimation beside that kernel."
        ),
        "objective": (
            "Rust-own remaining M4 decimation decisions and §28 metadata so "
            "Python only packs/ships columns."
        ),
        "proof": "Payload/LOD tests; browser smokes as applicable; no silent decimation.",
    },
    {
        "key": "282-emit",
        "parent": 282,
        "also_blocks": [],
        "priority": "P1",
        "title": "[M2 follow-on][P1][#282] Remaining `_payload._emit_*` sampling / density / masks",
        "problem": (
            "ABI 132 owns first-paint density emit policy. Remaining "
            "`_emit_*` sampling, density, and mask assembly in `_payload.py` "
            "still risk host drift."
        ),
        "objective": (
            "Finish Rust-owned live paint payload bytes and §28 LOD metadata "
            "for remaining emit paths. Preserve offset-f32 wire invariants (§29)."
        ),
        "proof": "Payload/LOD tests and browser smokes; Python/Node/WASM payload agreement.",
    },
    {
        "key": "283-paint",
        "parent": 283,
        "also_blocks": [],
        "priority": "P2",
        "title": "[M2 follow-on][P2][#283] Remaining LUT / `_paint.py` / `_trace_paint_rgba` policy",
        "problem": (
            "Bounded Scene styles still leave Python paint/colormap/gradient "
            "helpers (`_lut`, `_trace_paint_rgba`, `_paint.py`) beside Scene on "
            "the compatibility path."
        ),
        "objective": (
            "Bound Scene styles so those helpers are unused on the product "
            "path. Do not block P0/P1 deletions on this cluster."
        ),
        "proof": "`tests/test_export_style_survival.py` and related style-survival / export differentials.",
    },
]


def cluster_body(cluster: dict[str, Any]) -> str:
    also = cluster["also_blocks"]
    also_line = f" Also blocks {', '.join(f'#{n}' for n in also)}." if also else ""
    return f"""## Context

Sub-issue of #{cluster["parent"]}.{also_line}
{INVENTORY}

## Problem

{cluster["problem"]}

## Objective

{cluster["objective"]}

## Scope

{CONTRACT}

## Acceptance

- The leftover in **Problem** is gone from the product path, or is recorded as a bounded fail-closed contract with a stable `XYG_SCENE_UNSUPPORTED_*` diagnostic and tests.
- Proof: {cluster["proof"]}
- **Delete Python only after** Rust owns the path **and** differential proof is green.

## Priority

{cluster["priority"]}.
"""


def gh(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["gh", *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def gh_json(*args: str) -> Any:
    return json.loads(gh(*args))


def issue_meta(number: int) -> dict[str, Any]:
    meta = gh_json("api", f"repos/{REPO}/issues/{number}")
    return {
        "id": meta["id"],
        "number": meta["number"],
        "title": meta["title"],
        "state": meta["state"],
        "url": meta["html_url"],
    }


def existing_issues_by_title() -> dict[str, dict[str, Any]]:
    issues = gh_json(
        "issue",
        "list",
        "--repo",
        REPO,
        "--milestone",
        "2",
        "--state",
        "all",
        "--limit",
        "200",
        "--json",
        "number,title,state,url",
    )
    return {issue["title"]: issue_meta(int(issue["number"])) for issue in issues}


def create_issue(title: str, body: str) -> dict[str, Any]:
    url = gh(
        "issue",
        "create",
        "--repo",
        REPO,
        "--title",
        title,
        "--body",
        body,
        "--milestone",
        MILESTONE,
        *[arg for label in LABELS for arg in ("--label", label)],
    )
    number = int(url.rstrip("/").rsplit("/", 1)[-1])
    return issue_meta(number)


def link_sub_issue(parent: int, child_id: int) -> None:
    try:
        gh_json_input(
            "POST",
            f"repos/{REPO}/issues/{parent}/sub_issues",
            {"sub_issue_id": child_id},
        )
    except RuntimeError as error:
        message = str(error)
        if "already" in message.lower() or "422" in message:
            return
        raise


def gh_json_input(method: str, path: str, payload: dict[str, Any]) -> Any:
    result = subprocess.run(
        [
            "gh",
            "api",
            "-X",
            method,
            path,
            "-H",
            "Accept: application/vnd.github+json",
            "--input",
            "-",
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh api {method} {path} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return json.loads(result.stdout) if result.stdout.strip() else None


def has_marker_comment(number: int, marker: str) -> bool:
    comments = gh_json("api", f"repos/{REPO}/issues/{number}/comments")
    return any(marker in (item.get("body") or "") for item in comments)


def ensure_comment(number: int, marker: str, body: str) -> None:
    if has_marker_comment(number, marker):
        return
    gh_json_input("POST", f"repos/{REPO}/issues/{number}/comments", {"body": body})


def prepend_parent_section(parent: int, child_lines: list[str]) -> None:
    issue = gh_json("api", f"repos/{REPO}/issues/{parent}")
    body = issue.get("body") or ""
    if PARENT_MARKER in body:
        return
    section = (
        "## Leftover clusters\n\n"
        f"{PARENT_MARKER}\n\n"
        "Close children independently. This parent stays open until every "
        "child is closed or recorded as a bounded fail-closed contract. "
        f"{INVENTORY}\n\n" + "\n".join(f"- {line}" for line in child_lines) + "\n\n"
    )
    gh_json_input("PATCH", f"repos/{REPO}/issues/{parent}", {"body": section + body})


def spec_table(created: dict[str, dict[str, Any]]) -> str:
    rows = [
        "| Key | Parent | Also blocks | P | Issue | Title |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for cluster in CLUSTERS:
        issue = created[cluster["key"]]
        also = ", ".join(f"#{n}" for n in cluster["also_blocks"]) or "—"
        rows.append(
            f"| `{cluster['key']}` | #{cluster['parent']} | {also} | "
            f"{cluster['priority']} | [#{issue['number']}]({issue['url']}) | "
            f"{cluster['title']} |"
        )
    return "\n".join(rows)


def render_spec(created: dict[str, dict[str, Any]]) -> str:
    table = spec_table(created)
    return f"""# M2 leftover clusters

Post-close M2 follow-on parents [#271](https://github.com/CurateLabs/xyg/issues/271)-[#283](https://github.com/CurateLabs/xyg/issues/283)
were too large to close: each leftover ABI admit left the parent open.
This file is the closeable cluster inventory.

{INVENTORY}

In-repo pointer: [`issues/m2-leftover-clusters.md`](../design/issues/m2-leftover-clusters.md).
Create/refresh GitHub sub-issues with `python3 scripts/m2_leftover_clusters.py`.

## Landing contract

- One leftover cluster per pull request.
- Do not stack further ABI slices onto [PR #286](https://github.com/curatelabs/xyg/pull/286).
- Wait until the **current HEAD** required checks are green (Test, WASM
  foundation, Python 3.11 floor) before the next push on the same ref.
- Close the **child** when that leftover is Scene-owned with differentials,
  or when spec+tests record it as a bounded fail-closed contract.
- Close the **parent** only when every child is closed.
- **Delete Python only after** Rust owns the path **and** differential proof
  is green.

## Cluster table

{table}

## Parents

| Parent | Role |
| --- | --- |
| #271 | Figure→Scene ingress / export predicate. Remaining product policy in `_scene_v3.py` predicates, not thin packing. |
| #272 | Scene-eligible `to_svg`. Children also block #273. |
| #273 | Scene-eligible PNG/RGBA. No unique children; closes when #272 children close with raster differentials. |
| #275 | Rust layout / `_svg._*room` / `_legendfit.py`. |
| #276 | Remaining tick/format policy after PR #284 adapter retirement. |
| #278 | Remaining annotation exceptions after ABI 184-188 (`dx`/`dy`/`anchor`/`rotation` already landed on #286). |
| #279 | Compatibility `_scene.py` geometry wrappers over ABI 121. |
| #282 | Live `_payload.py` LOD/emit leftovers over ABI 122/132. |
| #283 | P2 paint/colormap leftovers. Do not block P0/P1. |
"""


def pointer_spec() -> str:
    return """# Tracked work: M2 leftover clusters

**Parents:** [#271](https://github.com/CurateLabs/xyg/issues/271)-[#283](https://github.com/CurateLabs/xyg/issues/283).

Canonical cluster list and landing contract:
[`m2-leftover-clusters.md`](../../process/m2-leftover-clusters.md).

This file remains a stable in-repo pointer so specs can cite a path even if
child issue numbers move; prefer linking the child `#N` in commits and PRs.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print titles and bodies; do not call GitHub",
    )
    parser.add_argument(
        "--write-spec-only",
        action="store_true",
        help="Rewrite spec files from known milestone issues without creating",
    )
    args = parser.parse_args()

    if args.dry_run:
        for cluster in CLUSTERS:
            print(f"=== {cluster['title']} (parent #{cluster['parent']}) ===")
            print(cluster_body(cluster))
            print()
        print(f"{len(CLUSTERS)} clusters", file=sys.stderr)
        return 0

    existing = existing_issues_by_title()
    created: dict[str, dict[str, Any]] = {}
    for cluster in CLUSTERS:
        title = cluster["title"]
        if title in existing:
            created[cluster["key"]] = existing[title]
            print(f"exists #{existing[title]['number']}: {title}", file=sys.stderr)
            continue
        if args.write_spec_only:
            raise SystemExit(f"missing issue for {title}")
        issue = create_issue(title, cluster_body(cluster))
        created[cluster["key"]] = issue
        print(f"created #{issue['number']}: {title}", file=sys.stderr)

    if not args.write_spec_only:
        for cluster in CLUSTERS:
            child = created[cluster["key"]]
            link_sub_issue(cluster["parent"], int(child["id"]))
            print(
                f"linked #{child['number']} → parent #{cluster['parent']}",
                file=sys.stderr,
            )

        by_parent: dict[int, list[str]] = {}
        for cluster in CLUSTERS:
            child = created[cluster["key"]]
            line = f"#{child['number']} `{cluster['key']}` — {cluster['title']}"
            by_parent.setdefault(cluster["parent"], []).append(line)
            for extra in cluster["also_blocks"]:
                by_parent.setdefault(extra, []).append(f"{line} (also-blocks)")

        for parent, lines in sorted(by_parent.items()):
            prepend_parent_section(parent, lines)
            ensure_comment(
                parent,
                COMMENT_MARKER,
                f"## {COMMENT_MARKER}\n\n"
                "Closeable leftover clusters live as GitHub sub-issues. "
                "Land one cluster per PR; do not stack onto PR #286. "
                "See `spec/process/m2-leftover-clusters.md`.\n\n"
                + "\n".join(f"- {line}" for line in lines),
            )
            print(f"updated parent #{parent}", file=sys.stderr)

    spec_path = "spec/process/m2-leftover-clusters.md"
    pointer_path = "spec/design/issues/m2-leftover-clusters.md"
    with open(spec_path, "w", encoding="utf-8") as handle:
        handle.write(render_spec(created))
    with open(pointer_path, "w", encoding="utf-8") as handle:
        handle.write(pointer_spec())
    print(f"wrote {spec_path} and {pointer_path}", file=sys.stderr)
    print(json.dumps({key: created[key]["number"] for key in created}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
