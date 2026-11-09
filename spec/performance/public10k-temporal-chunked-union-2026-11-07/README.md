# Reviewed 10k graph and queued temporal/chunked integration

Normal history-preserving merge of reviewed graph head
`08ce02217e8fc032a775aab5fff48195e74b4d66` and reviewed/queued temporal plus
chunked head `fc096e61f3069496c6cae5719e361ec4336180e8`. Accepted main at
preparation remains `ae104cf35316e10e56e345c225acef2604e487a1`; queue acceptance
is not presumed. This integrates the complete 10k ingress ownership correction
and exact UPDATE boundary regression with retained temporal controller behavior,
generation-aware chunked chart snapshots, generated native ABI401 declarations
and preserved fixture packets.

The only textual source conflict is the existing native/WASM wire module. Both
complete tests are retained: 10k document admission and retained temporal history.
The API preparation inventory is regenerated through its official checker.
Current qualification uses additive successor bindings and LF pins, retaining all
historical source and receipt identities. Rust native/WASM and browser client
artifacts are built from the combined source before host checks.

No source policy, ABI signature, resource cap, timing deadline, tolerance or gate
is relaxed. This is functional integration, not default-arena, two-10k,
contention/latency,100k/1M,frontend/export/accessibility,competitor or fullmilestone
acceptance. All broader #35/#36/#1015/#110/#109/#113 requirements remain open.


Fresh combined validation passes 153 Rust interaction tests and the allocation
ledger regression; 18 Node native/WASM wire and chunked controls; 53 Python host
checks with one explicit browser skip, followed by the required rendered test
passing all four full decoded image/oracle comparisons; and 33 Core/inventory
controls including actual Git LF/CRLF conversion. The first attempt at the
explicit render command named a nonexistent test and ran zero tests; its exit4
log is retained and is not credited. The corrected existing test passes.

A fresh public10k+1k browser journey paints60/59 advancing publications and both
converge at step458, with trusted unfinished selection, exact host-camera
retention, isolation and cleanup. Complete browser/native/WASM reply replay
passes63 primary and60 peer commands while every primary publication retains
10,000 nodes and edges. The full source-dist foundation also passes16 camera
controls, two bounded scheduling cases and all14 retained temporal cases.
Both Workers explicitly request384MiB. No contention or latency win is claimed.

Reproduction uses Node22, Rust1.96, an explicit combined native library,
`XYG_CHROMIUM` and a short disk-backed TMPDIR:

```bash
cargo build --release
npm run build:wasm
node js/build.mjs
cargo test -p xyg-engine graphforge::interaction
cargo test -p xyg-engine --test graph_session_memory
node --test packages/xy-node/test/graph-session-wire.test.mjs packages/xy-node/test/chunked-columns.test.mjs
uv run pytest tests/test_graph_session_python_transport.py tests/test_graph_session_abi.py tests/test_chunked_columns.py -q
XYG_TEST_CHROMIUM="$XYG_CHROMIUM" uv run pytest tests/test_chunked_columns.py::test_rendered_chart_snapshot_navigation -q
XYG_GRAPH_SESSION_REPORT=target/task-tmp/public10k-union/public10k.json node scripts/graph_session_public10k_smoke.mjs
node scripts/graph_session_public10k_replay.mjs target/task-tmp/public10k-union/public10k.json
node scripts/wasm_foundation_smoke.mjs
```

The source bindings and artifact digests identify combined producer bytes; the
pre-commit HEAD field still names08ce and does not name the combined producer.
Historical packets and failed runs retain their original bytes and status.


Strict workspace all-target Clippy and all673 ABI smoke controls pass; generated
ABI401 declarations, packaged assets and workflow/merge-queue validation pass.
The new native library is6137240 bytes, SHA256
`b93f21b8f19799897566a5447279f0a79729b7814c0391db302cd31a050a31bd`.
ShippingWASM matches reviewed10k artifact
`06938b014a74528eb95a279971cb884b41a9dbcb094d3530a49a633ffd1e9792`:
1,927,066raw /786,154Node22gzip6 bytes, within unchanged caps. The protection
manifest covers15,617 parent paths outside five explicit merge/binding changes.
