# Notebook review repair: command, event, append and remount ordering

Parent repair of independently reviewed candidate
`4fc50fe556b836507ceecaae6b88ef5673325d0b` in the owned
`t3-56fb3ea2` worktree. Both assigned reviews completed before source editing.
Five blocking findings were confirmed: pending-frame Python commands used the
wrong displayed revision; older messages copied unmodified state over newer
selection; inherited append crashed before mount and lost appended rows/envelope;
remount replaced committed ranges with home ranges; and selection clear did not
hold an arriving checkpoint until its reply. Earlier receipts remain unchanged.

Python mutations now wait for paint acceptance (including compilation in flight)
and belong to their mount epoch. The browser retains old readouts until their
exact reply; selection clears use that same pending-request backpressure. State
propagation compares changed facets and mutation versions rather than copying
all caches on every readout. Appended traces retain their native canonical
columns across rebuilds, with no host append journal; the existing Figure append
and renderer refresh own append behavior. The graph saved-state envelope stays
intact. Remount sends committed ranges/geometric selection before paint ACK;
opaque row-selection markers are non-durable and do not reconstruct a mask.

The five deterministic Python ordering/append/remount tests and three browser
transport controls exercise these exact paths. The browser controls use the
actual TypeScript adapter with a stub painter, and run in the existing notebook
CI step with fail-closed workflow verification. They are separate from the real
JupyterLab/IPython/anywidget/Chromium journey: 39 checkpoints, first passive step
1 and terminal step300, trusted unfinished interaction, two-widget isolation,
Python row selection, final pointer callback and cleanup, zero browser errors.
That normal five-node journey alone is not an adversarial-race or scale proof.

`current-bindings.json` binds corrected source bytes and preserves all previous
Core/notebook binding files by digest. Raw development/regression failures and
validation logs are losslessly gzip-compressed with raw/archive hashes. Real
notebook source HEAD names the reviewed parent; working-source hashes, not that
HEAD alone, identify the producer. JS was rebuilt after the browser changes;
native/WASM sources and limits are unchanged and qualified artifacts are reused.

Reproduce with Node22 and Cargo on PATH, the project uv environment, explicit
`XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so`, and Playwright Chromium:

```sh
uv run pytest -q tests/test_graph_widget.py tests/test_widget.py tests/test_channel.py tests/test_view_state.py tests/test_graph_layout_controller.py tests/test_graph_notebook_report.py tests/test_release_surface_gate.py tests/test_graphforge.py
node --test js/test/graph-host-transport.test.mjs
node js/build.mjs
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome XYG_GRAPH_NOTEBOOK_REPORT=target/review-repair-notebook.json node scripts/graph_notebook_progressive_smoke.mjs
.venv/bin/python scripts/verify_graph_notebook_report.py target/review-repair-notebook.json
uv run --with dunamai pytest -q tests/test_graphforge_contract_corpus.py tests/test_graphforge.py tests/test_release_version.py tests/test_check_release_version.py tests/test_verify_release_cohort.py
python3 scripts/verify_ci_workflow.py
uv run ty check
```

No #1015/#35/#36/#108 closure follows. UUID/per-layer projection and UUID
selection, complete frontend/export qualification, Aggregate row-space selection
persistence and the required rendered size ladder remain open. No ABI, resource,
timeout, tolerance or package-size policy changes, and no publication. Fresh
independent re-review, remote CI and required merge queue remain necessary.

The normal notebook capture uses `notebook-final.json`; `notebook.json` is the
earlier development-stage pass. Its exact Python runtime is preserved in
`notebook-runtime.py`. A subsequent narrow append-cache ownership and failed-queue cleanup change
uses dataclass replacement to share canonical columns while giving each frame
its own derived native-cache finalizers. Fresh focused append/widget/failure tests cover
those corrections. The normal notebook does not exercise append, and is reused
without claiming that this later source revision produced that earlier capture.
The unchanged rebuilt browser bundles and native artifact remain hash-bound.

A terminal worker failure clears queued Python mutations and refuses subsequent mutations with the existing stable failure code, rather than retaining an undeliverable queue. A replacement mount can create fresh native state.
