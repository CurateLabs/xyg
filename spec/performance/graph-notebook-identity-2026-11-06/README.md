# Notebook typed identity candidate — 2026-11-06

This is a bounded implementation candidate for #1015 and the notebook portion
of #36, based on accepted PR1100. It does not close #1015/#36/#35 or M4–M7.
No workflow, ABI, budget, renderer or tolerance changes are included.

Public behavior: callback rows add `graphforge` records and Selection objects
add `graphforge`; Python `widget.select(uuids=...)` uses native SelectUuids and
ordinary binary selection masks. Rust owns UUID resolution, derived refs and
per-layer provenance. The original compiler, axes, legends, styling, ChartView,
append bookkeeping and off-loop layout scheduling remain in use.

The private GraphSession is required here because the existing Python
GraphForgeComposition.identify/select methods decode planes and look up UUIDs
in Python; they cannot establish Rust-owned resolution. Sessions use existing
preset positions, not a second layout. Their paint output is discarded. Native
Companion provides exact derived refs; hosts never infer pair/path keys.
Retired/closed sessions release even if a callback retains a Selection.

Focused proof covers node and every source edge (including loops and parallel
edges), layer/result-id/row projection, derived edges, binary UUID mask rows,
queued commands, two-widget isolation, displayed-old and retired revisions,
remount, hidden-state preservation, existing append and presentation journeys.
The real existing JupyterLab smoke adds exact typed node assertions and issues
a public node+edge UUID selection; it observes selection delivery, two widgets,
continued frames and a final trusted pointer callback. It does not independently
pixel-diff the UUID mask or prove every routed-edge pointer hit in a notebook.
Node parity here compares the common identity fields against the existing
composition identity oracle, not a fresh cross-process Node browser test.

Remaining acceptance: exact graph-specific box/lasso edge policy and UUID sets,
aggregate/compound UUID highlights, all notebook loop/parallel pointer journeys,
Jupyter Notebook 7 and VS Code frontend qualification, matching selected exports,
keyboard/accessibility parity, actual 1k/10k/100k/1M rendered first-paint/cadence,
and the broader browser/WASM scheduling and interaction work in #35/#36.
Unknown UUIDs are unmatched; UUID highlights are non-durable across remount.
Static HTML has no Python callback channel. No performance or competitor win
against Matplotlib, Seaborn, Plotly, Bokeh, Altair, Datashader or HoloViews/hvPlot
is claimed from these small correctness fixtures.

Reproduce from repository root using the supplied Node 22/Cargo PATH:

```sh
cargo build --release
node js/build.mjs
uv pip install jupyterlab ipykernel pillow
uv run pytest tests/test_graph_widget.py tests/test_graphforge.py tests/test_graph_session_python_transport.py -q
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome XYG_GRAPH_NOTEBOOK_REPORT=$PWD/target/notebook-identity-report.json node scripts/graph_notebook_progressive_smoke.mjs
uv run pytest tests/test_graphforge_contract_corpus.py -q
uv run ty check
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Raw logs, failed attempts, notebook report, environment versions and artifact
hashes are retained beside this file. The first notebook run used the existing
qualified native artifact copied from the prepared sibling checkout; the final
run uses a fresh local release build. Historical producer and PR1100 receipts
are unchanged. `current-bindings.json` binds current bytes separately and chains
the prior receipt. No publication, push, PR or GitHub mutation was performed.
