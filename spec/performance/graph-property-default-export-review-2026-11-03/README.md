# Default property export proof: review erratum, 2026-11-03

Independent reviewer: `m4_defaults_audit`. The parent reported approval of
proof commit `f9cd80496489ee00270dd45d8dcc469dfa2954c1`, conditional only
on this append-only receipt correction. Reviewed canonical binary/full-index
diff SHA-256: `ee2f4485a77be250099998d7ff16497a274be23831e22a27383c9c388581c2db`
(accepted base `030c79062138bb8287df2dc93ab6fdc0ecc8747b` to the proof commit).

No browser installation was performed; existing Playwright Chromium was used.
Pre-commit did download `virtualenv`: the historical
[`pre-commit.txt`](../graph-property-default-export-2026-11-03/pre-commit.txt)
records `Downloading virtualenv (5.3MiB)`. The original README's
no-dependency-download wording was overbroad. This erratum corrects that
statement without editing the original receipt or its logs.

The independent audit verified 27 artifact hashes and 18 source hashes. These
hashes were also checked against the available files during this erratum task;
the original 43 changed paths remain byte-identical to the proof commit.
The inventories remain in the original receipt's
[`artifacts.json`](../graph-property-default-export-2026-11-03/artifacts.json),
[`source.json`](../graph-property-default-export-2026-11-03/source.json) and
[`changed-paths.txt`](../graph-property-default-export-2026-11-03/changed-paths.txt).

All four actual visual failures remain failures. The measured values from
[`browser.json`](../graph-property-default-export-2026-11-03/outputs/browser.json)
are unchanged:

| Comparison | Theme | Mean maximum RGB-channel difference | Fraction of pixels with difference >96 | Result |
|---|---|---:|---:|---|
| Canonical PNG vs WASM browser | light | 10.463013392857142 | 0.016878720238095238 | FAIL |
| Canonical PNG vs initial native browser | light | 11.272161458333333 | 0.028463541666666668 | FAIL |
| Canonical PNG vs WASM browser | dark | 9.653229166666666 | 0.015773809523809523 | FAIL |
| Canonical PNG vs initial native browser | dark | 236.71340773809524 | 0.9927752976190476 | FAIL |

The existing limits remain mean <3.5 and fraction <0.01. The normal smoke
invocation still returns failure; no masks, tolerance changes, layout changes
or gap waivers are introduced. Review approval applies to the proof's accuracy,
not product acceptance. #934, #935, M4 and #108 are not accepted or closed;
#935 repair is separately owned, and #36 S5–S7 dependencies remain outstanding.

This change adds only this erratum. The already-green proof was not rerun for
this documentation-only correction. Mandatory full-worktree pre-commit, Ruff
check and Ruff format check are run before committing. No product, test,
helper, other specification or historical receipt is changed. No push, PR or
remote action is performed; parent owns integration.
