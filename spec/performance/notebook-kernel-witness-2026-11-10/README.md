# Atomic named-idle kernel witness

PR1119 hosted run42751719507 at efe193dc completed the actual JupyterLab
4.6.5 graph journey but failed the strict frontend verifier: the stored kernel
status was busy. The harness first awaited a named idle kernel, then sampled
its status in a separate browser call. That second sample can see another
startup transition. The failed run and its original report remain failed.

The harness now retains the exact name/status object returned by the readiness
predicate, serializes it through its JSHandle and releases that handle even on
serialization failure. The readiness predicate, 45-second deadline, subsequent
cell execution, native provenance, progress, callback, UUID, pixel, isolation,
route/asset and cleanup checks remain intact. The report verifier is unchanged.
This certifies the state at admission, not continuous kernel idleness.

A real Chromium149 counterfactual changes the indicator after its first read.
The archived parent code records busy; the correction records the one admitted
idle snapshot. No Kernel, empty name, busy, missing editor and missing Lab Idle
text still refuse; Notebook7 still uses its named indicator. Normal pytest
executes the 13 Node contract cases; the same helper drives both actual
frontends. Actual Lab4.6.5 and stock Notebook7.5.8 are rerun separately with
explicit executables and their strict --require-routed/--frontend verifier.

Reproduce with Node22 on PATH:

```sh
uv run --no-sync pytest -q tests/test_graph_notebook_report.py
node --test js/test/graph-notebook-kernel-witness.test.mjs
XYG_GRAPH_JUPYTER=/path/to/jupyter-lab XYG_GRAPH_NOTEBOOK_REPORT=/tmp/lab.json \
  node scripts/graph_notebook_progressive_smoke.mjs --frontend jupyterlab
uv run --no-sync python scripts/verify_graph_notebook_report.py /tmp/lab.json \
  --require-routed --frontend jupyterlab
```

Use the compatible recorded Notebook7 cohort for its separate frontend route.
New source/history bindings preserve all prior receipts and pins. Native/WASM,
client and 324 compiled inputs are reused after byte equality; no rebuild is
needed. The first local rerun lacked an explicit Jupyter executable and failed
ENOENT; it receives no pass credit. A final counterfactual browser launch
without disk-backed TMPDIR exited SIGTRAP; that failure remains unexplained.
The explicit /var/tmp invocation passed; it does not establish a crash repair.
Corrected invocations are separate. The
real-browser transition control is deliberate and does not reconstruct the
precise hosted timing. No generic startup or Worker reliability repair, whole
issue/milestone completion, hosted CI or queue success is established here.
