# Notebook canonical identity batch order

Correction of independently reviewed cfd2da004ff14b1d8ce8039aeb0062d148b32b4d.
Review found that concatenating native-sorted batches could change global callback
order and repeat identities across batch boundaries. The preserved before run
fails all four new cases (999/1000/1001/2100 descending UUIDs with mixed node and
edge identities), including the actual selection callback.

The adapter now merges native-sorted runs using only Rust-emitted reference
keys and removes identical keys across batches. Persisted node/edge UUID bytes
remain kind-qualified. Derived keys retain exact optional result-id bytes, layer,
path and order; reply-local string pool offsets cannot influence global order.
Native resolution, identity equivalence and per-layer provenance remain Rust's.
No new identity joins or authored UUID matching is performed in Python. Keys
are private transport metadata and do not appear in public callback records.

The four boundary cases compare complete callback and UUID-selection records
with one admitted native request. Input repeats across batches and same UUIDs
on nodes/edges must retain exactly the unique native records. A derived case
compares single-input batches with one native request across differently ordered
result IDs. Initial fixtures used non-admitted result IDs, conflicting similarity
channels, and an untyped Cypher path; Rust correctly rejected them. The final
fixture uses admitted similarity and random-walk algorithm layers. Earlier
attempts remain separate, without weakening validation. Existing 10001/40000 resource/selection/ACK controls remain unchanged.

Fresh checks and source/artifact/log bindings are recorded in checks.json. The
current Core binding receipt advances append-only and retains all historical
producer receipts. Native, JS and WASM artifacts are reused by verified digest.
The retained small notebook capture belongs to the earlier Python producer; it
is not a fresh capture of the order correction. Fresh native/transport controls
cover the changed batch behavior, without a new notebook or scale claim.

Reproduce using explicit existing native and project environment:

```sh
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" uv run pytest tests/test_graph_widget.py tests/test_graph_session_python_transport.py tests/test_graph_notebook_report.py tests/test_graphforge_contract_corpus.py -q
uv run ty check
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Independent correction review, current-head CI and merge queue remain required.
Typed identity still has the unchanged native envelope; full #1015/#35/#36/M4
acceptance, geometric UUID sets/highlights, complete pointer/frontend/export
journeys, accessibility and the rendered 1k–1M ladder remain open.
