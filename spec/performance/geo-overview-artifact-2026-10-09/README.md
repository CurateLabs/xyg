# Geographic overview artifact decision

The exact temporal overview and immutable linked-state foundation require
bounded new packaging limits: **1,408 KiB raw / 576 KiB gzip (level 6)**.
The release compiler and pinned Binaryen 132 O3 profile remain unchanged;
both size gates stay hard failures. This admits functionality and makes no
optimization or runtime speedup claim.

The combined candidate is 1,326,010 raw / 543,366 gzip bytes, SHA-256
452c21d9f5dcb6522a2d3fabfd55e6c5270a6eacda86a07640b5f004d9037285.
The linked-only candidate is 1,278,773 raw / 523,072 gzip; Linux CI measured
525,371 gzip for its preceding exact head, exceeding the old gate by 1,083.
The new limits leave 115,782 raw and 46,458 compressed bytes above the combined
candidate. Future growth must be measured and recorded separately.

Three fresh Chromium process/profile Worker-ready samples are 35.5, 17.4 and
18.7 ms (median 18.7 ms). Each runs actual packaged five-view GL, retained
source/index, full-u64/i64, offline strict CSP, original rows, immutable export,
cancellation/ACK and recovery. The last two also prove extended overview ACK
and mixed-cancel cleanup admission when normal host input capacity is full.
Uncontrolled local load, warm OS file cache and raw loopback HTTP limit these
samples; they exclude main ESM parsing, WAN/cold disk and paired comparisons.

Actual native/WASM overview conformance separately proves exact 256-cell
counts, nullable signed extrema, half-open instant/window semantics, full source
and layer IDs, cross-CRS/pitched ordinary Scene bytes, authenticated read/write
ACKs, typed nonfinal labels, owner disposal, two-copy quotas and source-pick
rejection. It does not establish overview browser paint or massive interactive
latency. Raw source hashes and browser reports are beside this file.

Reproduce from the temporal-overview branch (linked-only branch cannot run the
new overview conformance script):

```sh
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
cargo build --release -p xyg-core
npm ci && npm ci --prefix packages/xy-node
node js/package-wasm.mjs && node js/build.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" node scripts/geo_overview_conformance.mjs
XYG_CHROMIUM="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" node scripts/geo_retained_wasm_smoke.mjs
```

Linux uses `libxyg_core.so` and an installed Chromium path. Required Linux CI
must verify exact-head artifact size; local values do not certify its output.
