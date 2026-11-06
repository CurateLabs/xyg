# R3 Core rc.7 and graph notebook integration

This is a normal merge of accepted main
`57a171bbc18e8380e8ac238a22e3a9d3bf15b1b8` into widget candidate
`d3ed3b2083c023ee09d7c0443797a3e2c2d29a04`, in the exclusively owned
`/home/ubuntu/.t3/worktrees/xyg/t3-56fb3ea2` worktree on
`t3/graph-widget-progressive-layout`. Both parents and all prior receipts are
preserved. The Core worker checkout `t3-c566baa0` was read only.
No branch history rewrite, child agents, GitHub mutation, push, PR or watch.

## Combined source identity

The only textual merge conflict was the host-parity append. Both the rc.7
qualification and R2 notebook sections are retained. The workflow retains the
rc.7 immutable source pin, default/rc.5/rc.7 corpus synchronization and bounded
notebook step; merge_group and Release surfaces semantics are unchanged. The
API table retains exact rc.7 qualification alongside the notebook contract.
No notebook/runtime source, ABI, cap, timeout, optimizer or tolerance is changed.

The inherited checkout-repair binding correctly fails against the newly combined
API/host-parity bytes (`inherited-binding-failure.log`). Its historical bytes
are not rewritten. `current-bindings.json` now binds the actual combined sources,
including the current provenance test, attributes, workflow, workflow verifier
and this README. Every new current-bound text file is explicitly LF-pinned.
The actual Git autocrlf regression derives coverage from that entire binding,
plus the historical bindings and original generator snapshot; an unpinned
control still converts to CRLF. No assertion is skipped or weakened.

Historical original producer and generation/default/checkout-repair snapshots
remain authoritative for their own producing revisions, manifest and 112 IPC
bytes. The current binding anchors those historical files without claiming that
the combined sources produced the historical IPC. Capture HEAD is the widget
parent, not the uncommitted merge tree. Final merge HEAD and canonical accepted-
main diff hash are reported in the handoff; this is not review/CI acceptance.

## Validation and artifacts

Raw command/status/log and source/artifact evidence is recorded beside this
README. The Core ledger change is one test-only rc.7 corpus invocation. Runtime
Rust/WASM and widget/client source bytes are unchanged from their qualified
parents. The existing native library and Core-qualified WASM bytes are reused
only after exact digest checks; no runtime rebuild or new artifact qualification
is claimed. Generated artifacts stay ignored and are not committed.

Fresh validation passed 177 Core/release tests with cached Dunamai and zero
skips, 144 notebook/channel/controller/gate checks, and 66 Node/native/WASM
composition tests with zero skips. All three source-corpus syncs and packaged
WASM verification passed. The focused Rust corpus test passed and the native
ABI smoke passed 673 checks. The final notebook report has no browser page
errors. Runtime/client build inputs are unchanged from R2, so no new JS build
or broad runtime Rust/WASM rebuild was required. Fresh validation covers the Core corpus/provenance and real Git checkout
filters, release contracts with cached Dunamai and zero optional-test skips,
native/Node/WASM Core composition, the existing CI verifier and focused guards,
widget/channel/controller/view-state checks, and the real bounded notebook
journey on the combined sources. The notebook retains R2's five-node fixture:
trusted unfinished-layout keyboard/navigation, presentation/legend, callbacks,
Python row selection, independent widgets, final pointer verification and
cleanup. It proves no 1k/10k/100k/1M rung, frontend matrix or complete UUID API.
Full worktree hooks/Ruff run before the merge commit; their output is captured
under ignored target first so logging cannot itself modify tracked hook inputs.

## Reproduction

Use the repository's Rust/Node toolchains and the existing project environment.
Use an owned bare Core source-object store containing the pins from all three
provenance files. The read-only Core worker mirror held rc.7 only; the older
pins were fetched read-only into `target/graph-r3/core-source.git` without a new
contributor checkout or any change to that completed worktree. Core artifacts may be copied from a qualified checkout only after
checking its recorded digests; otherwise run the normal native/WASM producers.

```
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:/home/ubuntu/.cargo/bin:$PATH
git init --bare target/graph-r3/core-source.git
# Fetch each exact commit from tests/fixtures/graphforge/{core,core/0.6.0-rc.5,core/0.6.0-rc.7}/provenance.json:
git --git-dir target/graph-r3/core-source.git fetch --no-tags https://github.com/CurateLabs/graphforge c2b782cd833d54aa14bb097b69bd23f3c2a93a9b
git --git-dir target/graph-r3/core-source.git fetch --no-tags https://github.com/CurateLabs/graphforge aaa573f446bbed5b8d7577c9a9824ddd6664e840
git --git-dir target/graph-r3/core-source.git fetch --no-tags https://github.com/CurateLabs/graphforge f871a2a1c2a397d8d74dfabcede611f3b5e5f906
uv run --offline --with dunamai pytest -q tests/test_graphforge_contract_corpus.py tests/test_graphforge.py tests/test_release_version.py tests/test_check_release_version.py tests/test_verify_release_cohort.py
python3 scripts/sync_graphforge_contract_corpus.py --core-repo target/graph-r3/core-source.git
python3 scripts/sync_graphforge_contract_corpus.py --core-repo target/graph-r3/core-source.git --output tests/fixtures/graphforge/core/0.6.0-rc.5
python3 scripts/sync_graphforge_contract_corpus.py --core-repo target/graph-r3/core-source.git --output tests/fixtures/graphforge/core/0.6.0-rc.7
cargo test -p xyg-engine graphforge::ledger::tests::pinned_core -- --nocapture
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/graphforge.test.mjs packages/xy-node/test/graphforge-wasm-parity.test.mjs
uv run pytest -q tests/test_graph_widget.py tests/test_widget.py tests/test_channel.py tests/test_view_state.py tests/test_graph_layout_controller.py tests/test_graph_notebook_report.py tests/test_release_surface_gate.py
python3 scripts/verify_ci_workflow.py
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome XYG_GRAPH_NOTEBOOK_REPORT=target/graph-r3/notebook.json node scripts/graph_notebook_progressive_smoke.mjs
.venv/bin/python scripts/verify_graph_notebook_report.py target/graph-r3/notebook.json
uv run ty check
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The bindings are captured after all bound text is final and formatted. A future
legitimate change to a current-bound file requires a new current binding receipt,
not edits to this historical receipt or the original producer evidence.

## Limits and ownership

This integration adds no #1015 feature. Full typed UUID/per-layer callbacks,
UUID-origin selection, UUID box/lasso sets, selected/annotated export parity,
Notebook 7/VS Code qualification, Aggregate selection persistence and the
required rendered size ladder remain open as recorded in R2. Core rc.7 Linux
qualification is preserved, not promoted to an installed release cohort or
complete platform/consumer acceptance. Parent owns independent full-product-
diff review, PR, remote CI and merge queue. No issue/release closure is claimed.
