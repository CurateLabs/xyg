# Selected hierarchy43/44 recovery foundation

Engine-only opt-in nonce recovery using the existing fixed bank. Public hierarchy
owners still need adoption before lost43/44 can be called recovered there. No
massive interaction, linked mounted-view, performance improvement or1B claim.

`environment.json` pins the fresh native/WASM pair, original baseline pair, build
profile, unchanged package caps and exact compression level. `compiler-inputs.json`
hashes206 tracked compiler/config/packaging inputs including the new cfg(test)
module. `source-sha256.json` pins this slice and its unchanged canonical raw fixture.

Six new tests and20 existing hierarchy tests pass. Full safe-engine1500 tests,
strict workspace/all-targets/all-features Clippy, package validation and full
worktree hooks/Ruff pass. The original TDD red rejected nonzero43 as InvalidFrame;
the intermediate fallback test failure selected the frontier before work, so the
corrected work case uses a smaller source instead of weakening the assertion.

The test-only wrapper instruments the existing raw42–44 conformance fixture. It
adds64 actual native/WASM43/44 exact replay, changed-byte rejection and idempotent
Confirm controls; retires logical Query births separately from Data; and uses
exact private ticket ACKs throughout. Rust owns all traversal/selection/Scene
policy. Existing literal controls cover Point/MultiPoint, full-u64 duplicate/null
IDs, signed-i64 time, five lanes, direct/cluster/density selected counts, complete
paged cell membership, original rows and frozen authority after owner disposal.

The three `*-packets.json.gz` files retain all84 complete native Data packets per
run. Owning creation receipt/request and publication sequence are asserted before
recording. Baseline versus current nonce0, and baseline versus current opt-in,
match every original byte and handle, with **no normalization**. The unchanged
canonical fixture separately compares native/WASM outputs using its documented
process-local owner normalization; it does not mask source rows, IDs, selection,
time, Scene, camera/revisions, counters or payload content. Pair reports expose
that canonical fixture's hash; the wrapper's own hash is separately pinned.

Raw JSON is compressed with gzip9/mtime0 for storage only. Package gate values use
gzip6/mtime0. Native/WASM binaries and generated bundles are not committed.

```sh
cargo test -p xyg-engine hierarchy_protocol_tests --lib
cargo test -p xyg-engine --lib
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo build -p xyg-core --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib \
  XYG_HIERARCHY_RECOVERY_PACKETS=/tmp/optin-packets.json \
  XYG_SELECTED_HIERARCHY_REPORT=/tmp/optin-pair.json \
  node scripts/geo_hierarchy_recovery_conformance.mjs
# Repeat with XYG_HIERARCHY_RECOVERY_LEGACY_ONLY=1 for nonce0.
# For the original baseline additionally set XYG_NATIVE_LIB and
# XYG_SELECTED_HIERARCHY_WASM to environment.json's baseline paths.
```

```python
import gzip, json
from pathlib import Path
read = lambda n: json.loads(gzip.decompress(Path(n).read_bytes()))["packets"]
assert read("baseline-packets.json.gz") == read("current-legacy-packets.json.gz")
assert read("baseline-packets.json.gz") == read("optin-packets.json.gz")
```

Unknown replies are engine-replayable only when clients opt in and settle47;
nonce0 retains its existing uncertainty gates. Failed/read-pending Query loans
remain live until exact ACK even when their journal birth is retired. Retirement
never disposes a lane, Source or independently owned later Data.
