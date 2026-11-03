# Private Python graph-session transport receipt — 2026-11-03

This is append-only local evidence for the P0 internal S6 foundation on
accepted base `030c79062138bb8287df2dc93ab6fdc0ecc8747b`. It is not a public
wrapper, M4/#108 acceptance, browser integration, or performance-leadership
claim. Parent S5 GPU wire/painter changes were absent and were not copied.
The normative boundary is
[graph-session-python-transport.md](../../design/graph-session-python-transport.md).

## Source, environment and native identity

`source.json` records the branch/worktree, accepted native source tree and
SHA-256 of the implementation, tests, protocol, bindings and ownership
records. `environment.json` records actual local tool/runtime versions and
the limited validation environment; no credential environment is captured.
`native.json` records the actual loaded release library's path, size, SHA-256,
ABI 398 and `native` backend, built offline from unchanged accepted Rust.
No generated declaration, ABI version, public API inventory, dependency,
workflow, gate, Rust/WASM source, or existing receipt changed.

This checkout initially lacked the native library and Python/Node installs.
The installed Rust 1.96.0 toolchain built the core with
`/home/ubuntu/.cargo/bin/cargo build --release --offline` (exit 0, fresh build
2m 02s). `uv run --offline` created the project environment from cache.
An initial expanded check had 76 passes and one failure in the existing
Node trace test: `ERR_MODULE_NOT_FOUND` for `koffi`, before any native trace
was emitted. `npm ci --offline --prefix packages/xy-node` installed the
unchanged locked dependencies from cache; all 11 generated-trace tests then
passed. This setup used no registry network and changed no tracked files.

## Results and scope

`commands.json` contains each final command's argv, start time, duration,
return code and raw-output filename. The paired `.txt` / `.txt.gz` files are raw combined
stdout/stderr from the actual runs, including the final full-worktree hooks,
Ruff checks, native build/smoke, generated ABI, and ownership gates.
`probe.json` contains the actual two-node/one-edge fixture's complete render
reply length/hash, exact replay equality and observed native status. This
fixture is a transport correctness probe, not a latency or memory benchmark.

The focused wrapper/raw-ABI suite proves create/render/update, identical
request-buffer identity through sizing/exact copying, real native short
copy refusal with untouched output, retained complete replay, poll delivery,
native refusal atomicity, independent handles, Open alias semantics, bound
owner disposal/unbind, serialized close and future local refusal. Nearby
ABI/generator/tracing/ownership checks supply bounded regression coverage.
No browser harness or hours-long full pytest run was used.

## Reproduction

From the repository root with the locked tools/dependencies already present:

```bash
export UV_OFFLINE=1
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
/home/ubuntu/.cargo/bin/cargo build --release --offline
uv run python -c 'import xyg.kernels as k; from xyg import _native; print(k.BACKEND, _native._lib.xyg_abi_version(), _native._lib._name)'
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

Stage the new owned production file before the ownership gate, whose source
inventory is intentionally tracked-files-only. The final canonical diff
digest is calculated outside this self-referential receipt with
`git diff --full-index --binary 030c79062138bb8287df2dc93ab6fdc0ecc8747b <commit> | sha256sum`.

## Remaining gaps

P1 still requires design for full selection/per-layer identity projection
missing from XYGR and the fast-seed seam. P2+ still requires widget/channel
attachment, session scheduling, keyboard controllers and public notebook
integration. Parent-owned S5 GPU/browser integration, independent review,
integration and eventual publication remain outside this commit. No
acceptance or readiness claim is made for those paths. Module-wide Python
serialization is intentional P0 lifecycle behavior, with no concurrent
throughput claim; native-identical Open calls alias a native lifetime rather
than receiving Python reference-counted ownership.
