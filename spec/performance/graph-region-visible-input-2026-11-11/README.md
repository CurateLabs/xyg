# Trusted region input through visible host canvas

Parent: `2f1eb6e5e3206de8986e10854390e77c478a7160`.

PR1122 run42974000387 at `eb9f09d6` failed the ordinary JupyterLab region
journey at its required pan-end event. The archived job log identifies step41;
the later missing VS Code/consumer artifacts follow that failure. The ordinary
progressive notebook step40 passed. Neither this run nor the earlier failed
merge-group receives green credit.

The new bounded pointer diagnostics establish a missed input target in this
run: both final pan down/up target a host `DIV`, without native pan events.
The retained lasso screenshot shows Jupyter's right debugger sidebar covering
the output beyond viewport x904. The canvas still reports left378, width824;
the old 75% path starts at x996 and ends at1016, inside that sidebar. This is
different evidence from the earlier VS Code missing-terminal-event failure;
that older cause remains unconfirmed.

The shared journey now hit-tests seven positions along the existing 20/-12
CSS-pixel path before sending real mouse input. It keeps the original path
when exposed, otherwise chooses another fully exposed path of identical
length. It refuses if none reaches the canvas. Frame-local positions still
use the existing VS Code viewport-origin adapter. The successful report adds
the selected `panPath` for inspection.

No chart renderer, input handler, camera policy, timeout or assertion is
changed. The journey still requires a native pan end, wheel end, changed-camera
exact range/induced-edge identities, native GPU masks, accepted/refused pictures,
capacity/history atomicity and cleanup. It neither dismisses the sidebar nor
calls a synthetic event/state API to satisfy the gesture.

## Fresh controls and actual hosts

- The normal Python report suite discovers the new Node control. It checks the
  original unobstructed path, a sidebar covering the hosted boundary, an
  obstruction between clear endpoints, and refusal with the entire canvas
  covered. The predecessor coordinate calculation fails the final assertion;
  its source and failure are retained without claiming a whole-module mutant.
- A real Chromium DOM control at DPR1 and2 reproduces the old trusted press and
  release landing outside the canvas, verifies both replacement events target
  the canvas and remain trusted, and refuses complete coverage.
- Actual JupyterLab4.6.5 passes the complete shared journey at DPR1 and2.
  The initial DPR1 pass precedes only the additive `panPath` report field; a
  final DPR1 run also records that field. All original oracles remain active.
- Actual pinned VS Code/Jupyter passes the same journey and the unchanged strict
  desktop report verifier. Its coordinate adapter, original assertions and
  native-owner cleanup remain intact.

Exact commands, raw failures, successful captures, runtime pins and source
bindings are in `checks.json`. The host fixture's supported public-artifact
allowlist is used; private application profiles, Jupyter connection/runtime
files, authentication material and X cookies are excluded.

## Reproduce

Use Node22.23.4, the existing project environment without synchronization,
`TMPDIR=/var/tmp`, explicit matching native405 and the existing Chromium149.
Run `uv run --no-sync pytest -q tests/test_vscode_graph_regions_report.py`.
Run `node scripts/graph_notebook_regions_smoke.mjs` with explicit
`XYG_GRAPH_JUPYTER`, `XYG_CHROMIUM`, and a fresh `XYG_GRAPH_REGION_REPORT`;
repeat with `XYG_GRAPH_REGION_DPR=2`. The private two-DPR obstruction control is
archived as executable source.

The desktop command remains `xvfb-run --auto-servernum
--server-args='-screen 0 1280x900x24' uv run --no-sync python
scripts/graph_vscode_notebook_smoke.py --regions --code <pinned-code>
--extensions <pinned-extensions> --server-python <installed-server-python>
--node <Node22> --output <fresh-private-output>`, followed by
`uv run --no-sync python scripts/verify_vscode_graph_regions_report.py <output>`.

The successor preserves all46 provenance parents. All324 compiled inputs,
nine runtime artifacts and six static copies remain parent-exact; no native,
WASM or client rebuild is necessary or claimed. Full-worktree hooks/Ruff and
independent final-diff review remain explicit commit/delivery gates.

Fresh hosted CI and the required merge queue remain pending. This is a bounded
host-harness correction; public100k notebook acceptance, the earlier hosted
cause, global resource/reliability work and milestones4–7 remain open.
