# Private graph-session input reentrancy repair — 2026-11-03

Append-only repair evidence for the independently reviewed implementation
`346256a1c4386bb4f2c3b05e54e9d489afd1ee87`, whose parent/accepted native base
is `030c79062138bb8287df2dc93ab6fdc0ecc8747b`. The
[original receipt](../graph-python-session-transport-2026-11-03/README.md)
remains unchanged. This repair is still only the private P0 S6 foundation;
it makes no M4/#108, public notebook, browser, or publication acceptance claim.

## Finding and narrow repair

The reviewed constructor held the module's non-reentrant lock while
`operator.index` normalized supported identity scalars. A valid `__index__`
that closed another GraphSession deadlocked before outer create reached FFI.
The audit also found the same issue in command input conversion: on Python
3.12+, supported bytes/bytearray subclasses can execute `__buffer__` inside
`memoryview(data)` and re-enter another session's lifecycle.

Constructor scalar normalization and both document/opening snapshots now
finish outside the lock. Commands check closure under the lock, snapshot
outside it, then reacquire the lock and recheck the handle before forwarding.
An input callback closing the command's own wrapper therefore gets the same
private closed error (`status=None`); no handle captured before conversion is
used afterward. The non-reentrant lock is preserved. Native creation and the
entire query/exact-copy/close transaction, including alias behavior, remain
serialized. No Rust/product policy, request bytes, sequence, native ABI,
generated binding, dependency, ownership classification, or public API changes.

The normative contract update is in
[graph-session-python-transport.md](../../design/graph-session-python-transport.md).

## Before/after proof

`baseline-index-reentrancy.{json,txt}` records the new indexable-instance
regression on unmodified reviewed production code: the child times out after
8 seconds. `baseline-buffer-reentrancy.{json,txt}` records the supported
command-bytearray callback producing the same bounded timeout. These are
expected failing baseline proofs; subprocess timeout kills and reaps the
child rather than leaving a thread holding the pytest process's module lock.
The baseline runs used the added tests before the production repair. Their
raw tracebacks include the exact subprocess reproduction code.

The final tests use actual native ABI 398 for both identity scalar fields,
both constructor byte-buffer inputs, command buffer reentry into other
sessions, and a command buffer callback closing its own target. Each callback
closes a session, opens/renders/closes another native session, and verifies
that the outer operation or closed refusal completes correctly. Python buffer
callback cases explicitly skip on Python <3.12; scalar cases run on every
supported Python version. Each subprocess has an 8-second timeout and is
killed/reaped on regression. Existing retained-byte, native status, alias,
independent-handle, bound-owner, and close-race proofs are preserved.

`commands.json` records the final checks with exact argv, return codes,
durations and raw `.txt` / `.txt.gz` outputs. `source.json` hashes the final
implementation/tests/specification and confirms the original receipt and
native source were unchanged. `environment.json` and `native.json` record
the actual local interpreter/tools and loaded ABI/hash. No fallback or mock
native core is used. This is correctness evidence, not a performance claim.

## Reproduction and remaining scope

With the existing locked dependencies and release core present, from the
repository root:

```bash
export UV_OFFLINE=1
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
uv run pytest tests/test_graph_session_python_transport.py tests/test_graph_session_abi.py -q
uv run pytest tests/test_graph_session_python_transport.py tests/test_graph_session_abi.py tests/test_abi_parity.py tests/test_generated_abi_trace.py tests/test_verify_ownership.py tests/test_audit_python_host_core.py -q
uv run python scripts/abi_smoke.py
uv run python scripts/gen_abi_manifest.py --check
uv run python scripts/verify_ownership.py
uv run python scripts/audit_python_host_core.py
uv run ty check python/xyg/_graph_session.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

To reproduce the red baseline in a disposable checkout, combine the final
test file with the reviewed commit's unmodified production module, then use
the exact `-k` commands in the two baseline JSON records. Each expected
timeout remains bounded to 8 seconds. Baseline evidence must not be mistaken
for a failed final check.

P1 selection/per-layer identity projection and fast-seed design, P2+
widget/channel attachment, scheduling, keyboard/public notebook integration,
and parent S5/browser work remain outstanding. The parent owns renewed
independent review and integration; no remote PR/push/issue action occurs.
The final canonical `git diff --full-index --binary <repair-base> <commit>`
SHA-256 is reported separately to avoid a self-referential receipt.
