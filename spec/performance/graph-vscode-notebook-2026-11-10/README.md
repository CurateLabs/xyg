# Actual VS Code Jupyter graph notebook qualification

Parent: `efe193dc8673b0c83a79f6d4ea5753471b8ad1d5`, whose tree is exactly the
independently reviewed embedded-keyboard correction. Accepted main
`6850637c5e96bbda79d3615cec2b4eb9ab7bd7d5` contains the earlier Lab/Notebook7
qualification through the required merge queue.

This source-checkout journey runs the unchanged ten-cell public graph notebook
in the actual Linux x86_64 VS Code 1.103.2 desktop application, embedded Node
22.17.0, Jupyter extension 2025.7.0 and its four pinned dependencies. Separate
Python 3.11.17 and 3.12.15 server environments use Notebook 7.5.8, Lab 4.5.11,
NbClassic 1.3.3, ipykernel 7.4.0, anywidget 0.11.0, ipywidgets 8.1.9,
widgetsnbextension 4.0.16 and jupyterlab_widgets 3.0.17. Kernel selection uses the
extension's public server-provider API and actual workbench picker. The Python
extension is absent; its local-environment discovery route is not qualified.

The pinned installer verifies complete official app/VSIX identities before use,
then compares every installed extension file with its source package. The stock
installer's `package.json.__metadata` is excluded from a canonical manifest
hash; the remaining fields and every other file must match. The driver repeats
these checks before startup. No app/extension/renderer source is patched.
New private profiles keep updates and telemetry disabled. Runtime auth tokens
are generated privately, never placed in command arguments or evidence. The
optional TCP Xvfb mode uses a private cookie; ordinary CI uses `xvfb-run`.

The driver executes all original cell sources in the same identity-proof order
as the existing Lab journey: `0,1,2,3,6,4,5,7,8,9`. It checks actual execution
orders and outputs, first/intermediate/terminal native paint, trusted unfinished
keyboard/pointer/wheel, a real concurrent cell finishing before terminal paint,
all five canonical edge UUIDs including parallel/self-loop, layered result ID
and row, actual node/edge GPU masks, public Node pick parity, two-widget
isolation and private identity-session release. Every used initial and layered
canvas is weakly bound by read-only CDP inspection to its actual cached ESM
module, byte-identical to the built shared client. No prototype is replaced and
no shared-context override or alternate picking oracle is installed. Inspection
provides no timing or garbage-collection evidence.

Real workbench screenshot clips are verified against file hashes, dimensions
and pixel statistics. A separate connected-cluster image must contain mark
pixels at all four canonical connected node centers, projected independently
from native f64 positions and the actual public view ranges. The four default
mark regions pass; clearing their centers while retaining the legend and
shifting the expected positions are rejected. This proves mark presence at
those centers, not every glyph/vector or whole-image antialiasing parity.

The original post-wheel terminal screenshot has only chrome: the retained
zoomed view puts all five final source positions outside it. The diagnostic
records those ranges and independently projected positions. This is not paint
loss and is not used as mark evidence. The fixture's already existing public
connected-range patch puts four source nodes in view; no renderer policy,
automatic-fit rule, data, camera retention or layout deadline was changed.

Application exit, attachment exit, normal GUI mode, idle disconnected Python
kernel, its own protocol-reported Python version, actual notebook cells,
installed assets, module sources, screenshots,
Node invocation input/output, and direct-process/cookie cleanup are separate
strict witnesses. A standard authenticated read-only `kernel_info_request`
queries interpreter identity without executing code or adding a notebook cell.
A deliberate failure after actual cell 1 must retain the
original error and nonzero attachment result while the app and directly owned
processes exit. This does not certify every descendant, global process-memory
accounting or emergency native destruction.

## Reproduce

First build the normal native core/client and install the repository's dev and
Node-host dependencies. With Node 22 on PATH:

```sh
uv run --no-sync python scripts/install_vscode_graph_notebook.py \
  --output /var/tmp/xyg-vscode-cohort
uv venv --python .venv/bin/python /var/tmp/xyg-vscode-server
uv pip install --python /var/tmp/xyg-vscode-server/bin/python \
  notebook==7.5.8 jupyterlab==4.5.11 nbclassic==1.3.3 ipykernel==7.4.0 \
  anywidget==0.11.0 ipywidgets==8.1.9 widgetsnbextension==4.0.16 \
  jupyterlab_widgets==3.0.17 numpy==2.4.6 pillow==13.0.0 pytest==9.2.0
xvfb-run --auto-servernum --server-args='-screen 0 1280x900x24' \
  .venv/bin/python scripts/graph_vscode_notebook_smoke.py \
  --code /var/tmp/xyg-vscode-cohort/application/VSCode-linux-x64/code \
  --extensions /var/tmp/xyg-vscode-cohort/extensions \
  --server-python /var/tmp/xyg-vscode-server/bin/python \
  --output /var/tmp/xyg-vscode-normal
uv run --no-sync python scripts/verify_vscode_graph_notebook_report.py \
  /var/tmp/xyg-vscode-normal
uv run --no-sync pytest -q tests/test_vscode_graph_notebook_report.py
make check-ci
```

Outputs must use new directories, preserving prior failures. To reproduce the
intentional error, use a new output directory and `--fail-after-cell 1`; that
command must exit nonzero. Verify its separate failure/cleanup contract with
`--expect-failure-after-cell 1` on the report verifier. A different native
library path is rejected early because the unchanged notebook fixture requires
this checkout's `target/release/libxyg_core.so`.

The existing Release surfaces `test` job installs the named cohort and runs the
actual notebook/strict verifier in two bounded four-minute steps. The prior
Lab/Notebook7 commands, merge-group trigger and required aggregate stay intact.
Normal pytest and `make check-ci` exercise receipt mutations and CI bypass
controls. No new runner or optional-browser skip is introduced.

## Network and evidence limits

Observed renderer traffic includes allowed host bootstrap endpoints and a
hash-pinned RequireJS response from jsDelivr. Unknown observed requests fail,
including requests during the final layered phase. This is not offline evidence
or an audit of extension-host Node traffic. The exact loaded XYG client is the
same self-contained generated artifact; no CDN dependency is added to XYG.

`checks.json` binds current/historical source, unchanged native/WASM/runtime
artifacts, compiled inputs, actual reports, source snapshots, commands, exits
and logs. `qualification-fixtures.json` is a verified subset used by normal
negative tests. Only the enumerated artifacts are archived. Do not upload
private profiles, Jupyter runtime/connection files, Xauthority or tokens.
Native/WASM code, ABI405, exports, package caps and product policies are
unchanged. Broad parent tests are inherited only over unchanged identities.

Failed attempts remain distinct: the first installer refused HTTP-gzip encoded
VSIX transport; decoding reproduced the exact original pin. The first fixture
archive generator used system Python without Pillow, and its test invocation
failed setup; the corrected project environment is separate. Two installer
metadata mutations initially exposed omitted verifier checks; both now reject.
Formatting/setup errors are preserved. The earlier exploratory VS Code probes
and original startup/Worker failures remain unqualified rather than being
credited as repairs by subsequent passes. The initial color-count-only visual
check was insufficient; it is superseded by the explicit native-center oracle.

## Remaining acceptance

This resolves a bounded named desktop source-checkout frontend proof gap.
Other app/extension versions and platforms, installed XYG distributions,
local-Python-extension kernel discovery, graph-specific box/lasso edge policies,
derived/aggregate/compound notebook routing, selected/annotated exports, the full
notebook size ladder, accessibility, resource/performance and competitor
acceptance remain open. #1015 and milestones 4–7 are not complete. Independent
final review, accepted-main freshness, new-head hosted CI and merge queue are
required before integration; this receipt alone grants no shipping approval.
