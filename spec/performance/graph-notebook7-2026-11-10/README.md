# Actual Notebook7 graph frontend — bounded compatibility qualification

Parent: `d73e128835b5723413b91d734056f2e9151c5f9f`.

The existing public graph notebook and strict routed-identity harness run in
actual JupyterLab 4.6.5 and stock Notebook 7.5.8. The latter uses its compatible
JupyterLab 4.5.11 dependencies in an isolated environment and loads
`/notebooks/graph.ipynb` and `/static/notebook` assets. Application name,
namespace, semantic major version, route, observed resource URLs and a named
idle kernel are required. A Lab report cannot qualify Notebook7 by relabeling it.

Both applications retain the public-widget assertions: native initial and
progressive pictures, concurrent kernel cell execution, trusted pointer and
keyboard input, all five property-edge UUIDs including parallel edges/self-loop,
layered result ID/row, actual delivered node/edge GPU UUID masks, public Node
pick parity, two-widget isolation, fresh final pointer and private-owner cleanup.
No forced clicks, synthetic callbacks, disabled default virtualization or
alternate renderer are used. The connected-cluster range patch and small-fixture
limits remain disclosed by the parent qualification.

Normal CI adds a bounded stock 7.5.8 invocation to the existing Release surfaces
`test` job, isolated from the main Lab 4.6.5 environment. Each application retains
its four-minute step ceiling. Exact command-list guards reject missing setup,
execution or explicit frontend/routed report requirements. No new required status,
product dependency, native ABI/WASM export, build policy, cap or deadline changes.
Runtime artifacts and compiled inputs remain parent-exact; no rebuild is credited.
The capability matrix is refreshed through its official generator.

The environments are isolated under task directories; borrowed environments were
not synchronized or modified. `checks.json` binds exact package versions,
source history, commands/exits, logs, actual notebook PNG/identity artifacts,
known failing reports and runtime reuse. Example reproduction (project dev
requirements/native library/client must already be available):

```sh
uv venv --python .venv/bin/python /var/tmp/xyg-notebook7-env
uv pip install --python /var/tmp/xyg-notebook7-env/bin/python \
  notebook==7.5.8 jupyterlab==4.5.11 ipykernel==7.4.0 anywidget==0.11.0 \
  numpy==2.4.6 pillow==13.0.0 pytest==9.2.0
XYG_GRAPH_JUPYTER=/var/tmp/xyg-notebook7-env/bin/jupyter-notebook \
  XYG_CHROMIUM=/path/to/chromium XYG_GRAPH_NOTEBOOK_REPORT=/var/tmp/notebook7.json \
  node scripts/graph_notebook_progressive_smoke.mjs --frontend notebook7
uv run --no-sync python scripts/verify_graph_notebook_report.py \
  /var/tmp/notebook7.json --require-routed --frontend notebook7
```

# Stock Notebook 7.6.4 remains unqualified

The actual 7.6.4 widget journey returns the expected identities/masks, but its
strict report verification fails due to an unhandled exception in the stock
notebook's bundled shortcuts settings registry. The captured exact column and
scope identify the shortcuts plugin's own missing registry entry; document-manager
loading triggers the callback. This matches open
[upstream Notebook issue 7862](https://github.com/jupyter/notebook/issues/7862).
It is not a proved XYG renderer/identity defect, and it is still a failed frontend
qualification. No page error is filtered and no notebook asset/plugin is patched
or disabled. `notebook764-failed.json.gz` retains the actual failed report; normal
regressions require rejection. Passing 7.5.8 is additional stock-host coverage,
not a repair or waiver for 7.6.4 or a claim about every Notebook7 version.

# Other failure disposition and limits

The Lab-only textual Idle wait failed in Notebook7. An isolated setup lacked
pytest, imported by the existing fixture helper. Another early-submission run
left its first cell unexecuted and produced no qualifying report. Inspection
exposed initial `No Kernel`/idle state; the final driver requires a named kernel
and idle indicator, with Lab's textual check retained. This closes an observed
readiness gap, not all historical startup/Worker/watchdog failures. A 7.5 run
also lost its original exception when failure diagnostics raced navigation;
each diagnostic now records its own unavailability without masking the original
failure. Both original failures remain failed. Verifying absent failed-run reports
was an inspection error. Bare system-Python capability generation lacked numpy;
its corrected `uv run --no-sync` invocation is recorded separately. Real Git CRLF
verification caught the newly bound guide's missing LF pin; the pin is corrected.

#1015 and milestones 4–7 remain open. Newer Notebook7 coverage, VS Code Jupyter,
graph-specific geometric edge policies, derived/aggregate/compound notebook
routing, selected/annotated exports, the full notebook ladder, accessibility,
platform/performance and competitor acceptance remain required. Small actual-host
journeys do not qualify massive graphs or whole-image antialiasing parity.
Independent final review, actual-main integration, new-head hosted gates and
merge queue remain necessary for delivery.
