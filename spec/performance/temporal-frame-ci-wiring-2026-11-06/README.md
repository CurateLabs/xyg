# Temporal publication regression CI wiring correction

Independent review of `cd46f5dc036346344496a1d9b8c416b98d6c0e82`
confirmed that the two new actual-wasm32 regressions were absent from the
explicit Node package test list. Add the file beside the existing temporal
graph tests in `packages/xy-node/package.json`. The existing CI Node host
suite and `make check-graph` invoke that same npm test command. No workflow,
production code, test assertions, dependency or budget changes are introduced.

The original output-publication production diff and its producer receipts stay
unchanged. This correction does not independently repeat broader suites or
qualify whole #45/#50/M5/M6 acceptance. `checks.json` records exact selected
source/artifact hashes, discovery control, explicit native/wasm32 regression
execution, environment, and compressed/raw output hashes. The system Python
record in the original receipt is distinct from its uv test runtime; the latter
is 3.12.15 as independently verified.

Verification:

```sh
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/temporal-graph-publication.test.mjs
uv run python scripts/verify_ci_workflow.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Source hashes describe canonical producing bytes. Historical receipt files,
current-source compatibility bindings, packaged assets and their limits remain
unchanged. Remote current-head CI remains parent-owned.
