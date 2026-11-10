# Routed notebook graph identity — bounded qualification

Parent: `f0b9f7574ab61fb645caea5c944cfd7fd73d9f52`.

The existing actual JupyterLab/IPython/anywidget journey now also proves all five
property-graph edge identities (including parallel edges and a self-loop), a
layered node's exact result ID and row, delivered GPU UUID selection masks,
public Node graphforgePick parity and private identity-session release. It
preserves the earlier unfinished-layout, plain default presentation, two-widget
isolation and fresh final-pointer requirements. No product, Rust, native ABI,
WASM, generated client, resource cap, deadline or selection policy changes.

The extra identity phase uses the public Python range patch to inspect the
connected cluster, whose distant isolated node otherwise compresses parallel
strokes. Geometry inspection only locates a stroke; canonical fixture UUIDs,
source membership, actual kernel callbacks and the public Node API provide the
oracles. No forced click or synthetic callback can satisfy the trusted-input
checks. Node's documented resultId spelling is normalized to Python result_id;
all identity values and row integers remain exact.

`checks.json` binds commands/results, raw failed attempts, actual notebook
artifacts, unchanged runtime/compiled inputs and successor source history.
Earlier receipts remain immutable. Setup, coordinate-origin, overlapping-node,
modebar/axis occlusion, wrong set_view call, missing hover callback and the
secondary-widget frame-observer errors remain recorded as failed attempts.
Passing later runs are not evidence of repairs to unrelated historical startup,
Worker, watchdog or small-scale context-loss failures.

Normal CI runs the existing notebook command and requires its report with
`--require-routed`. Focused commands use explicit native/source/Chromium paths:

```sh
XYG_GRAPH_JUPYTER=/path/to/qualified/jupyter-lab XYG_CHROMIUM=/path/to/chromium \
  XYG_GRAPH_NOTEBOOK_REPORT=/var/tmp/notebook.json node scripts/graph_notebook_progressive_smoke.mjs
uv run --no-sync python scripts/verify_graph_notebook_report.py /var/tmp/notebook.json --require-routed
uv run --no-sync pytest -q tests/test_graph_notebook_report.py tests/test_graph_widget.py
```

Report mutations reject missing edges, changed parallel/loop membership,
provenance rows/result IDs, contradictory Node replies, changed binary
compositions, altered masks, missing trusted actions and retained private owners.
A workflow mutation removing the current report requirement is rejected.

# Remaining acceptance

#1015, #35, #36 and milestones 4–7 remain open. Graph-specific box/lasso edge
policies, derived/aggregate/compound routing, Notebook 7/VS Code Jupyter,
selected/annotated exports, full accessibility, full notebook scale ladder,
resource/performance/competitor and installed-platform qualification remain.
The GPU mask check proves delivery, not complete visual/export parity. Fresh
final-diff review, hosted candidate gates and the required queue remain necessary.
