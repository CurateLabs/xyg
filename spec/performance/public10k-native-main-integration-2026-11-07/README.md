# Public 10k graph integration with accepted native geographic main

This normal merge preserves reviewed graph parent
`bea7eab191e6ff54b1999087edf23b3d98695899` (tree-identical to independently
approved `e3ef42819cbb66c461b7903d8fcfe5fbed829abf`) and accepted native
geographic main `43c35f67b95ae4e78e3e96f200a0e6be8642199c` (tree-identical
to approved `1f9e0637e3bc3c7da24fe2ab9034270795d2e18c`).

Three textual conflicts resolve by retaining both attribute pin sets,
regenerating the preparation API inventory through its official checker, and
advancing the Core qualification pointer to additive successor bindings. The
runtime source merge is clean. The explicit Node test list is the exact unique
parent union. Inventory contracts equal accepted main and its 686 gaps equal
the parent union. Historical source, performance and release evidence remains
unchanged. `protection.json` binds all other parent paths to exact Git blobs.

Rust/build and browser producer input identity permits reuse of the reviewed
ABI401 native library and optimized WASM. Native and shipping artifact hashes,
commands, exits and compressed/raw logs are recorded in `checks.json`. Browser
bundles are rebuilt from the merged source before host/browser verification.
No ABI, resource cap, scheduling deadline, tolerance, fixture packet, or policy
changes are introduced. No temporal catalog or frozen-export feature is added.

Reproduce with Node22, Rust1.96, an explicit `XYG_NATIVE_LIB`, supplied Chromium
in `XYG_CHROMIUM` and `XYG_TEST_CHROMIUM`, and a short disk `TMPDIR=/var/tmp`:

```bash
node js/build.mjs
uv run pytest -q tests/test_geo_temporal_binding.py tests/test_temporal_controller.py tests/test_graph_session_python_transport.py tests/test_graph_session_abi.py tests/test_chunked_columns.py tests/test_graphforge_contract_corpus.py tests/test_release_inventory.py
node --test packages/xy-node/test/graph-session-wire.test.mjs packages/xy-node/test/chunked-columns.test.mjs packages/xy-node/test/geo-temporal-binding.test.mjs packages/xy-node/test/temporal-controller.test.mjs
XYG_GRAPH_SESSION_REPORT=target/task-tmp/public10k-native-main/public10k.json node scripts/graph_session_public10k_smoke.mjs
node scripts/graph_session_public10k_replay.mjs target/task-tmp/public10k-native-main/public10k.json
node scripts/wasm_foundation_smoke.mjs
python3 scripts/abi_smoke.py
uv run python scripts/check_release_inventory.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Fresh results and any failed attempts are recorded separately in `checks.json`.
The reviewed parents' costly Rust/admission/mutation proofs remain inherited
only after producer identity checks; they are not freshly executed here.
Required hosted CI and the final independent review still gate queue delivery.

Scope remains one public 10k primary plus one isolated 1k peer, each explicitly
requesting 384 MiB. Trusted camera input is the host button calling
`refreshRender`; it is not canvas dragging. Default16MiB/1k refusal, reliable
two-10k completion under contention, cold start/latency, total process/GPU
memory, larger rendered ladders, notebook/export/accessibility and competitor
qualification remain open. Native geographic snapshots do not establish
mounted notebook/VS Code replacement, indexed/hierarchy automatic binding,
mixed tiles or all-host export acceptance. No issue or milestone closure follows.

## Fresh integration evidence

The affected host batch passes 155 tests on actual CPython3.11.17, with four
Python3.12-only buffer-callback cases skipped on that interpreter. A separate
CPython3.12 run passes all six constructor/command callback cases. All58 focused
Node22 native/WASM tests pass without skips. The Python batch includes all four
required full decoded-image chart/oracle comparisons. All673 ABI controls pass.
A fresh JS build reproduces all seven reviewed native/client/WASM artifact
bindings. The optimized module measures1,927,066raw/786,154Node22gzip6 bytes,
within the unchanged1,927,168/786,432-byte gates.

A fresh actual public10k+1k journey paints60/59 publications, converges both
at step458, and passes trusted unfinished selection, exact host-camera
retention, isolation and disposal. Complete browser/native/WASM XYGR digest
replay passes62 primary and60 peer commands; every primary result retains
10,000 nodes and edges. Its49,741,824-byte linear-memory peak is not process,
GPU, or total resident memory.

Two setup failures are preserved and receive no pass credit. The first host
batch passes154 tests but fails the new successor receipt because it omitted
`manifestSha256` and `originalProducerSha256`; the corrected receipt retains
both unchanged historical producer fields and the complete155-test run passes.
The initial metadata group invokes the capability generator under system
Python without NumPy; using the repository `uv run` environment passes the
complete group. Product code and assertions were unchanged by these repairs.

The full fresh source-distribution foundation passes all16 camera verifier
controls, both scheduling cases and all14 retained temporal browser cases.
Official generated ABI, packaged assets, Python floor, workflow/merge-queue,
ownership, API inventory and capability checks pass. Ownership classifies518
production files.
