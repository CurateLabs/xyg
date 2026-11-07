# PR1106 async temporal observer rejection

Correction of approved candidate `f4052f326c70bb0bb9abb36a5dbb093585621c06`.
Greptile comment 4497908168 identified discarded rejected observer promises.
The retained pre-fix actual-browser run fails with `async state observer rejection bypassed onError`.
The old producer receipts remain unchanged. The before fixture is preserved;
its only difference from the final fixture is the final report proof flag.

The snapshot observer is still invoked synchronously after Rust publication.
Its returned promise is caught without awaiting it. Synchronous exceptions,
rejected promises, and errors from the application error observer are isolated.
No command, Rust policy, geometry, ABI, budget or public signature changes.
The official API inventory generator refreshes only generation provenance and
the modified source hash; contracts/classifications and 685 gaps remain unchanged.

The existing normal-CI retained geographic browser smoke now installs synchronous
throwing, asynchronously rejecting, unresolved-promise and ordinary observers.
Two real Worker cursor commands complete in order before the unresolved promise
is released. Both error kinds reach onError twice; that async handler itself
rejects, and no unhandled rejection escapes. The required report flag proves the
checks executed. The complete strict-CSP offline geographic smoke passes, including
the inherited five small views and automatic temporal binding. This is a bounded
correctness proof, not a performance or full five-view temporal qualification.

Reproduce with Node 22 and the bound existing native/WASM artifacts:

```sh
node js/build.mjs
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome node scripts/geo_retained_wasm_smoke.mjs
uv run python scripts/check_release_inventory.py --write
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" uv run pytest tests/test_geo_retained.py tests/test_graphforge_contract_corpus.py tests/test_release_inventory.py -q
uv run python scripts/check_release_inventory.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Fresh verification: actual packaged browser smoke passed; 39 focused Python
tests passed with no skips; client build/typecheck, inventory and mandatory
full-worktree hooks/Ruff checks passed. Artifacts were rebuilt only for the
TypeScript client; native/WASM bytes equal the approved baseline. Source,
artifact, environment and raw/compressed log bindings are in checks.json.

Independent correction review, fresh CI and merge queue remain required.
#50/#39/M6 remain open: native-host binding, mixed tiles, complete frozen
attributed exports, all-host/accessibility, massive-scale, five-view temporal
and competitor qualification are outside this correction.
