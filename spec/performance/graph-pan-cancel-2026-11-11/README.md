# Canvas pan cancellation and desktop input diagnostics

Parent: `8f7ef9e55819f380128cce7bd4955596352459db`. This bounded
correction finishes the last committed canvas pan when the browser sends
`pointercancel`. It emits one terminal view event with the same interaction
identity. Later capture loss, release and buttonless movement do not repeat
completion or resume the gesture. Unfinished selections retain their existing
rollback behavior.

The parametrized real-client capture probe fails on the original client for
pointer cancellation while its capture-loss variant passes. The corrected
client passes both variants, including last-view equality and duplicate-release
checks. The complete view-state/security subset passes 69 tests.

## Hosted failure and limits

PR #1122's ordinary checks passed, but merge-group run 42937750028 failed in the
actual VS Code Jupyter graph-region journey. The group commit
`35d6d086a08dd8ade0ee24cb6da38ded980999d9` has exactly the reviewed
`ad848266a6bde2971ab3d146f6c8f398e7dcc00c` tree. Its artifact records four
`pan_drag` updates for interaction 7 and no terminal event, then the unchanged
10-second wait fails. Earlier box/lasso and refusal assertions passed; the
native owner was released during failure cleanup. Later missing-evidence upload
failures are downstream consequences. The queue removed the PR; it did not merge.

**The hosted artifact lacks pointer cancellation/release diagnostics, so the
hosted cause remains unconfirmed.** A local unchanged actual-application journey
passes. A private instrumented journey also passes and records normal trusted
release/capture-loss events. Neither establishes a reliability repair. An early
control selected a mismatching installed cohort and failed its admission guard;
an initial diagnostic installed too early and collected no pointer records.
Both setup failures remain preserved without product-pass credit.

The shared region fixture now records at most 128 pointer/capture/native-drag
records, with canvas identity/connectivity, bounds and hit-test tags. Failure
reports retain these records. It records no notebook content or profile secrets,
and changes no pointer input, geometry, assertion, resource cap or timeout.
The corrected actual VS Code journey passes its original strict verifier and
captures 26 trusted pointer/capture records from one connected canvas.

`checks.json` binds exact source, predecessor snapshots, runtime artifacts,
commands and compressed evidence. Historical receipts remain unchanged. Rust,
ABI, exports, compiler/optimizer configuration and the native/WASM binaries
remain parent-exact; generated clients are rebuilt and packaged normally.
The module remains 1,884,503 raw / 786,337 Node22 gzip6 bytes, only 95 bytes below
the unchanged gzip cap. No performance, all-host, global-memory, massive-data,
shipping, issue or milestone completion claim follows.

## Reproduce

Use Node22, disk TMPDIR, explicit checkout/native selection and the pinned
Chromium. Do not synchronize a borrowed environment.

```bash
node js/build.mjs
node js/package-wasm.mjs
uv run --no-sync pytest -q tests/test_view_state_client.py tests/test_static_client_security.py
node scripts/wasm_foundation_smoke.mjs
xvfb-run --auto-servernum --server-args='-screen 0 1280x900x24' .venv/bin/python scripts/graph_vscode_notebook_smoke.py --regions --code <pinned-code> --extensions <pinned-extensions> --server-python <installed-server-python> --output <new-private-output>
.venv/bin/python scripts/verify_vscode_graph_regions_report.py <new-private-output>
```

Independent final-diff review, accepted-main freshness, required hosted checks
and merge-queue acceptance remain necessary. The unresolved 100k notebook peer
deadline, earlier GPU/context/startup failures, broader milestone criteria and
competitor qualification remain open.
