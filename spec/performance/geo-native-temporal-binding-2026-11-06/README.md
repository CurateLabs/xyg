# Native temporal/geographic binding candidate

Prepared isolated branch `t3/native-temporal-geo-binding`. Original branch tip
`74195403`; fetched accepted main `9a75c4c00588eef20fdbf5c97952bb2d8f46beb4`
and independently approved browser candidate
`b9b59a60103fe9729da1b552700d82f0c81caf1f` are preserved by ordinary merges
`5e7142a1` and `06f2e1d0`. No producer checkout was changed. No GitHub mutations,
publication, workflow or worktree creation. Human commit identity is DavidSpencer
<1526975+DecisionNerd@users.noreply.github.com>.

The native binding uses the public retained composition and existing native
session, Rust-authored Scene, independent frame duplication, membership and
export/host paths. The normative contract and remaining mounted-renderer and
indexed/mixed-source limitations are in `spec/design/geo-retained-hosts.md`.
The new Python and Node tests use actual native sessions. They cover initial
cursor/range snapshots, selection-only no query, camera/time supersession during
an unsettled read, failure preserving the accepted picture and provenance,
full u64 IDs and signed time extrema, public SVG export, native host adapter
construction, independently surviving old snapshots, observer reentrancy and
async rejection, controller disposal with pending work, concurrent independent
Python source owners, and exact native aggregate membership.

The resource lines in the raw logs report 2-row and 32,769-row fixtures. Python
records process peak RSS (including interpreter, NumPy, pytest and earlier tests),
not isolated engine memory. Node reports instantaneous process memory including
V8 and native allocations. Elapsed times include fixture creation/compilation as
specified by each test; they are single local observations, not percentiles,
comparative throughput or large-scale acceptance. Raw chunk/packet sizes are
reported. No 100M allocation or five-view temporal/competitor claim is made.

`current-bindings.json` advances the previous Core current-source receipt without
rewriting it. Prior receipt hashes and original generator/IPC receipts remain
unchanged. `historical/` retains exact pre-change HEAD snapshots for affected
previously bound inputs. The existing provenance test exercises real Git CRLF
checkout conversion, including an unpinned control, against the new current
receipt. Native Rust, ABI, WASM exports, budgets, tolerances and dependencies are
unchanged. The freshly built/package-validated module stays under the unchanged
1882 KiB raw / 768 KiB Node22 gzip6 gates. Artifact hashes and gzip counts are in
`checks.json`. The browser run is an inherited retained path regression; native
snapshot integration is established by the native public tests, not claimed as
a new automatic mounted-browser journey.

Reproduce from this checkout (Node 22.23.4 and Rust 1.96.0):

```sh
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:/home/ubuntu/.cargo/bin:$PATH
export CARGO_BUILD_JOBS=2
cargo build --release
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
uv run pytest tests/test_geo_temporal_binding.py tests/test_geo_retained.py tests/test_geo_retained_components.py tests/test_temporal_controller.py -q -s
node --test packages/xy-node/test/geo-temporal-binding.test.mjs packages/xy-node/test/temporal-controller.test.mjs packages/xy-node/test/geo-host.test.mjs packages/xy-node/test/geo-live-host.test.mjs
cargo test -p xyg-engine temporal --lib
node js/build.mjs
npm run build:wasm
node scripts/geo_frame_leases_conformance.mjs
node scripts/geo_overview_membership_engine_conformance.mjs
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome node scripts/geo_retained_wasm_smoke.mjs
python3 scripts/check_release_inventory.py
python3 scripts/verify_ownership.py
uv run pytest tests/test_graphforge_contract_corpus.py -q
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Normal CI discovers the Python tests; the new Node file is explicitly listed in
`packages/xy-node/package.json`. Parent independent final review, PR/CI and merge
queue are required. #50/#39/M6 and broader M5/#108 remain open for mixed tiles,
complete frozen attributed exports, all-host/accessibility and massive/five-view/
competitor acceptance. This candidate also leaves automatic replacement of an
already mounted native renderer to the existing XYGH CAS/ACK integration.
