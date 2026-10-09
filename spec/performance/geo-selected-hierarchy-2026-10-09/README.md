# Selected hierarchy closure: bounded native/WASM semantic evidence

Base `4511b501ac76edec26608e81c22f791a377a599e`, branch
`feature/50-geographic-selected-hierarchy`. `environment.json`,
`source-sha256.json` and `source.patch` record the source, build policy and toolchain;
`native-wasm.json` and `raw.jsonl` record actual executed outputs and artifact hashes.
No performance or startup timing claim is made by these functional controls.

The fresh native ABI383 and actual packaged wasm32 ABI33 produce60 identical
normalized semantic packets. The unchanged package policy admits1,458,129 raw
bytes and599,348 gzip bytes below1472KiB/608KiB. No signature or quota changed.
Packet normalization removes only process-owner fields, never IDs, camera/time,
revision, style, Scene, count planes or selected intent. Frozen snapshot bytes
compare without normalization.

The fixture covers Point and MultiPoint, duplicate full-u64 IDs, null geometry,
null interval endpoints, signed-i64 extrema/half-open predicates, both source CRSs
and perspective cameras. Canonical selected Scene, metadata, full XYSE and hit
packets match the paged hierarchy. One empty offscreen/window case separately
asserts expected work telemetry: canonical projection visits1 Point or2
MultiPoint vertices, whereas the hierarchy prunes them and projects0. This
field56 comparison is excluded only from the canonical semantic comparison;
native/WASM packets still compare it byte-for-byte. Original-row packets from
that empty frame retain full IDs/intent and mark time-excluded rows explicitly. An explicit34 link preserves intent/profile
but a different private Scope cannot authorize this root. Unscoped43 returns17
without consuming issued State. Five independent fork lanes share one private
Scope and immutable root; an advancing lane does not advance another's history.
The16-handle saturated transition replaces State→Query→Data without a new slot,
and failed44 publication permits exact retry while old frames remain valid.

At32769 Point or32770 MultiPoint vertices, both cluster and density use two-pass
reduction with canonical byte-identical Scene/full selected counts. Complete
cell membership is paged at4096 rows, checks every original source-row/ID and
deduplicates MultiPoint rows after Source/lane disposal. Original-row paging
includes null/offscreen/time-excluded selection intent; immutable frozen export
captures the full sparse intent/profile/count authority after owner disposal.
None remains XYGZ v1. `legacy-native-wasm.json` records all34 legacy conformance
packets passing, including canonical unselected oracle and reduced membership.
The earlier combined-package report matches33 packet hashes; its second Rows
receipt embeds a process owner affected by the extra scoped-build fixture
allocation. The wire format and semantic fields retain their established
contracts; this is not a native handle-stability claim.

Rust controls separately exercise five distinct Scope/lane/oldData triples:
15 handles→State16→Query16→Data16, with failed44 local budget preserving the
completed query/live ledger and old frames before a successful retry. Admitted
fallback/cancellation consumes State/history; explicit identical-intent reissue
and a newer sequence are required. Pending loans retain exact ACK authority.

Reproduce from the checkout with Node dependencies installed:

```sh
npm ci
npm ci --prefix packages/xy-node
cargo build --release -p xyg-core
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
node js/package-wasm.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
XYG_SELECTED_HIERARCHY_REPORT=/tmp/selected-hierarchy.json \
node scripts/geo_selected_hierarchy_conformance.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
node scripts/geo_hierarchy_conformance.mjs
cargo test -p xyg-engine --lib hierarchy_protocol -- --nocapture
cargo test -p xyg-engine --lib
cargo clippy -p xyg-engine --lib --tests -- -D warnings
```

Linux uses its corresponding `libxyg_core.so`. Native hooks, Ruff and the
ownership audit are required before integration. The bounded fixture does not
prove selected100M/1B interaction latency, five-view GPU/OS memory, browser paint
or public selected hierarchy live-controller support. The existing typed
unselected hierarchy hosts require an explicit selected-frame compatibility
gate until their43/44 orchestration is implemented. Issue50/39 remain open.
