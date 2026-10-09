# Issued overview recovery evidence

This bounded host lifecycle proof adopts existing Rust26–29 nonce/47 receipt
policy. It adds no geometry/temporal decision, ABI signature, quota, memory cap
or compiler profile. Raw nonce0 and domain45/mutations35–36 remain separate.

The pinned paired artifacts come from the normal-merged retirement dependency.
The current Rust/Cargo/toolchain diff against that source is empty. Environment
and source hashes identify the actual files tested, not a historical artifact
from the older allocation foundation. Node runs actual native and wasm32 engines;
Python runs the same native core. Independent reviewer raw controls are retained
when supplied. No output normalization or substituted engine is used by these
host tests.

The new tests exercise exact replay, lost/corrupt allocation/confirmation/cleanup,
retired target0 and historical births, five-view sixteen-handle admission, shared
Data-cap retirement, callback/read settlement, whole-owner recovery singleflight,
closing initial and recovered publication, strict ACK grammar, bounded canonical
inspection, public producer/method/packet decoration and exact domain membership
through retained clone after original/index disposal. Legacy owner tests remain
included. Callback/page storage is caller owned and bounded test fixtures use a
small in-memory store; this is not massive external-storage performance evidence.

Reproduce from this checkout with a current matching native/WASM pair:

```sh
node scripts/gen_geo_overview_hosts.mjs --check
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" XYG_GEO_OVERVIEW_WASM="$PWD/packages/xy-client/dist/xyg-wasm.wasm" node --test packages/xy-node/test/geo-overview-recovery.test.mjs packages/xy-node/test/geo-overview-source.test.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" uv run pytest tests/test_geo_overview_recovery.py tests/test_geo_overview_source.py tests/test_geo_overview_members.py tests/test_geo_frame_leases.py -q
uv run --extra reflex ty check
node js/build.mjs
```

No claim is made for massive interaction, selected overview, source picking,
unknown snapshot6, mutation35/36 recovery, or new notebook/Reflex/VS Code live
routing. Those gates require their separate product paths and evidence.

The actual strict-CSP Chromium proof in `browser-controller.json` uses the fresh
frozen client build and exact WASM pair. Its test-only refresh replaces the
obsolete permanent-poison expectation for a corrupted successful29 response.
It compares the complete original and recovered256-byte receipt before checking
birth confirmation at publication sequence8 precedes exact Data10 sequence0.
Existing old-paint/table, cancellation, ordinary/borrowed pixel, shared-index,
queue-overflow and external/CSP/error assertions remain intact. This exercises
existing browser composition with the recovery adapter; it adds no host/controller
policy or massive-performance claim. The prior expected failure is retained.

`review-negative-controls.json` preserves the independent original failing repro
scripts and available raw logs as base64, including their historical hashes.
The original initial-close stdout was reported by the reviewer but not saved as
a standalone file; that field is explicitly a review observation, not a fabricated
raw execution log. Separate fixed/root/second-review logs retain the actual final
checks. The inspector prevents repeat allocations rather than silently allowing
unbounded copies.
