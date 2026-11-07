# Notebook UUID-selection report correction

Independent final review of `1caae2a69497754be5829254e3edd1e2aea0cb2e`
found that all three retained identity notebook captures selected a node plus
an edge while the existing CI verifier still required one selected row. This
correction preserves those captures unchanged and records their verifier
failures. It changes only notebook proof, verification and provenance metadata;
all identity transport and widget production code remains unchanged.

The notebook now prints the two requested UUIDs and their Rust composition
identity records. The smoke records that kernel output as `uuidSelection` and
waits for delivery of the corresponding two-row browser selection. The verifier
requires a distinct canonical UUID pair, ordered node/edge identity records
matching those UUIDs, and an integer browser count of exactly two. Typed callback
reports without their UUID request metadata fail closed. Older row-selection
reports retain their original one-row contract; the retained PR1100 capture
continues to pass. Wrong/missing/duplicated identity requests and wrong counts
are covered by negative tests.

This proves request identity plus browser delivery cardinality, not independently
measured exact geometric UUID sets or every highlighted pixel. Those requirements,
aggregate/compound highlights, full pointer journeys, other frontends, exports,
accessibility and rendered scale ladders remain open. No tolerance, budget, ABI
or release restriction changes.

`current-bindings.json` records current raw source bytes while preserving the
complete historical binding chain, including the ownership-correction snapshot.
All historical reports, screenshots, failures and native/JS artifact receipts
remain unchanged. Fresh capture, environment, source/artifact hashes, and
compressed/raw check logs are recorded adjacent to this file. New text is pinned
to LF; gzip and screenshots remain binary.

Reproduction:

```sh
uv run pytest tests/test_graph_notebook_report.py tests/test_graph_widget.py tests/test_graphforge_contract_corpus.py -q
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome XYG_GRAPH_NOTEBOOK_REPORT="$PWD/target/task-tmp/identity/report-repair.json" node scripts/graph_notebook_progressive_smoke.mjs
uv run python scripts/verify_graph_notebook_report.py target/task-tmp/identity/report-repair.json
uv run python scripts/verify_ownership.py
uv run python scripts/verify_ci_workflow.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```
