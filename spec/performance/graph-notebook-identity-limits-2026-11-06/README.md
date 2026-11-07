# Notebook identity admission and selection batching repair

Greptile review of PR1103 head `2c8349ed` identified two regressions: the extra
GraphSession rejected a previously supported 40,000-node Figure frame, and
SelectRefs rejected a 10,001-element callback before its reply reached the view.
Both reproduced against the selected real native library before editing, with
statuses -4 and -8 respectively. Prior captures and failed attempts remain
unchanged; raw before/after evidence is retained here.

Identity adapters now open a native session only when needed. Callback-time
identity preparation is attempted off-loop during compilation; an expected
resource refusal cannot reject the ordinary Figure frame. No initial identity
session render is requested. Derived companion replies update the adapter's
private revision. Callback identity refusal is explicit as
`graphforge_error="XYG_GRAPH_IDENTITY_RESOURCE_LIMIT"` with an empty typed list,
while the ordinary row/full Selection, reply and later frames still work.
Explicit UUID-command failure occurs before applying masks. No native limit,
ABI, renderer, layout kernel, tolerance or resource envelope changes.

Ref/UUID requests contain at most 1,000 inputs and replace private scratch
selection per batch. Complete callback projections remain ordered and explicit
UUID masks apply after all batches resolve. Source/render joins cache the
existing Rust member plane's inverse rather than rescanning all rows per input;
this preserves existing one-to-one refusal and adds no identity or LOD policy.
Metadata/host output cost remains unqualified at scale.

Focused tests cover real 40k frame compilation with/without identity callbacks,
10,001 full identities and UUID masks, 40k explicit metadata refusal, and actual
callback/reply/next-frame progress. These are bounded regression fixtures, not
the required rendered 1k–1M ladder or full geometric/front-end/export acceptance.
A fresh ordinary JupyterLab capture verifies the small full notebook journey
with the repaired producer. All original identity, ownership and report receipts
remain immutable. Current bindings and compressed/raw logs are appended here.

Reproduction:

```sh
uv run pytest tests/test_graph_widget.py tests/test_graph_session_python_transport.py tests/test_graph_notebook_report.py tests/test_graphforge_contract_corpus.py -q
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome XYG_GRAPH_NOTEBOOK_REPORT="$PWD/target/task-tmp/identity-limits/notebook.json" node scripts/graph_notebook_progressive_smoke.mjs
uv run python scripts/verify_graph_notebook_report.py target/task-tmp/identity-limits/notebook.json
uv run python scripts/check_release_inventory.py
uv run ty check
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```
