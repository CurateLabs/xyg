# Selected35/36 public mutation adoption

This evidence covers exact native and genuine Worker mutation authority, scoped
latest-dispatch provenance, synchronous JavaScript receipt parsing, State claims,
reader/ACK settlement, and issuer-credit recovery. It is a bounded lifecycle
proof, not a massive-data latency or competitor performance result. Selected19
publication adoption, MemberData cleanup adoption, legacy26–29 rejection
provenance, and selected hierarchy43/44 mutation journals remain separate gates.

Final205-input source-equivalence checks admit the copied native2310768 and
packaged WASM9923f651 pair. `environment.json`, `compiler-inputs.json`, and
`source-sha256.json` identify exact artifacts and source. Browser gzip uses
Node zlib level6. No engine, ABI, renderer, limits, or package cap changed here.

Final results:39 Python tests (11 new),15 Node selected tests (12 new),35
Node legacy tests plus one existing opt-in skip, and45 Node hierarchy tests
in `node-hierarchy.txt`. Root independently ran the11 new Python,
12 new Node, and actual Chromium fixture on the same immutable artifacts.
All browser controls pass with no external requests, CSP violations or page
errors. The old red pixel remains255/0/0/255; literal IDs and time remain u64/i64.

TDD logs preserve real failures: older genuine errors from escaped/nested native
calls, mutable Source context after real35, and genuine Worker resource rejection
incorrectly leaving State busy. Raw-WASM fixture failures were prerequisite
setup conflicts: those arbitrary callbacks have no canonical mutation brand.
Only their prerequisite selected35 authoring now uses direct Rust nonce0 plus
existing drive/prepare helpers; typed33/43/44 assertions and receipts remain.
Initial Worker fixture diagnostics found Source/Index ScopeArc ownership: cleanup
was corrected to close caller-owned original sources/indices after checking that
mutation cleanup did not dispose them. No paint or ownership oracle was weakened.

Reproduce from this worktree after dependencies and browser bundle build:

```sh
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib"
UV_NO_SYNC=1 PYTHONPATH=python uv run pytest tests/test_geo_selected_mutation_hosts.py tests/test_geo_selected.py tests/test_geo_selected_state_nonce.py tests/test_geo_retained.py tests/test_geo_spatial.py -q
node --test packages/xy-node/test/geo-selected-mutation-hosts.test.mjs packages/xy-node/test/geo-selected.test.mjs
node --test packages/xy-node/test/geo-selected-state-nonce.test.mjs packages/xy-node/test/geo-spatial.test.mjs packages/xy-node/test/geoscale.test.mjs packages/xy-node/test/geo-retained.test.mjs
node --test packages/xy-node/test/geo-selected-hierarchy.test.mjs packages/xy-node/test/geo-hierarchy.test.mjs
node scripts/gen_geo_selected_wire.mjs --check
node scripts/gen_geo_overview_hosts.mjs --check
node scripts/gen_geo_overview_wire.mjs --check
XYG_SELECTED_MUTATION_REPORT=geo-selected-mutation-browser.json node scripts/geo_selected_mutation_hosts_smoke.mjs
```

Set `XYG_CHROMIUM` to a locally installed Chrome executable when Playwright's
Chromium is unavailable. Core artifacts must match all recorded compiler inputs;
borrowed binaries are ignored artifacts, not committed source. Historical red
logs are labeled separately from final source-verified proofs. Dependency and
feature hooks/Ruff run before every commit and push.
