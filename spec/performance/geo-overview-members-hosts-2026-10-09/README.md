# Bounded issued overview membership host proof

`node-native-wasm.txt` contains27 passing actual native/WASM tests;
`python.txt` contains14 passing actual native Python tests. `packets.json` records
complete four-page XYOMv1 outputs from each engine, normalizing only the process
owner field16..24. Literal original rows0/4/5/9 have matching vertex counts2/1/2/1;
MultiPoint duplicate IDs do not merge distinct physical rows. These packets match
byte for byte. `legacy-node.txt` / `legacy-python.txt` record the earlier49/36
combined owner/membership/typing tests before two additional disposal controls.

`source-sha256.json` captures197 compiler inputs plus owned host/test sources.
Every compiler input was byte-compared with the paired artifact producer;
`environment.json` records zero differences, exact artifact SHA256 and donor
ancestry. Client typecheck/build passed. No Rust rebuild or compiler/quota change
belongs to this host-only slice. Evidence is bounded correctness/ownership proof,
not performance measurements or complete M6 acceptance.

Reproduce from this checkout with the exact donor383/33 artifact pair:

```sh
node scripts/gen_geo_overview_hosts.mjs --check
node js/build.mjs
# Build refreshes dist; restore the paired packaged WASM before the test.
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib \
XYG_GEO_OVERVIEW_WASM=$PWD/packages/xy-client/dist/xyg-wasm.wasm \
XYG_GEO_MEMBERS_REPORT=$PWD/spec/performance/geo-overview-members-hosts-2026-10-09/packets.json \
node --test packages/xy-node/test/geo-overview-members.test.mjs
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib \
uv run pytest tests/test_geo_overview_members.py -q
```

The full signed predicate cases cover All, Instant(MIN/0/10/MAX), and
Window[MIN,0)/[10,MAX). Tests include null geometry, producer disposal before
continuation, repeated cancellation before reader settlement, rejected and lost
successful ACK, eight-Data pressure/retry, known46 conversion probes, uncertain45
poison, mutable callback framing, immutable canonical records, bounded inspection
copy, strict malformed terminal receipts and dispose during publication.

Unknown allocating45 confirmation remains explicitly unresolved in this adapter;
it never guesses a numeric owner or blindly reallocates. Rust45 opt-in recovery
is a later dependency. Membership is temporally exact/data-space and spatially
nonfinal, with no camera pick or selected overview authority. Caller-retained
inspection copies/raw protocol reads are application-owned. Public companion UI,
massive interactive latency and complete M6 journeys remain acceptance gates.
