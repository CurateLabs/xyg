# PR #1065 density tile review follow-up

This is updated **source browser and bounded Node proof**, based on
`12eb6ff8`, for the two
[Greptile findings](https://github.com/CurateLabs/xyg/pull/1065#issuecomment-6357259973).
It does not requalify the prior wheel, npm packages or release candidate.
The parent directory's original browser/provenance files and the old
packaged Reflex reports retain their original hashes and historical scope.

The client now compares returned dimensions with the existing finite
16–4096 host boundary. A canvas wider than 4096 continues to accept capped
paint replies. Before pruning textures, it checks every current/shown/fading
frame by texture object identity. If Rust omits any source tile, the client
immediately completes that fade, clears outgoing aliases and removes
incomplete cached frames. Rust still owns retention and byte budgets.

[Raw browser results](browser.json) preserve the previous count/mean-color
proof and add actual resizes through `renderStandalone`:

- A 4924-pixel request accepts a 4096-wide reply, then pan continues updating.
  Cached/fetch-all pixels match exactly: 86,403 nonblank density pixels for
  counts and 87,813 for means. Oversized 4097 and mismatched 4095 reply widths,
  and NaN/Infinity requested dimensions, allocate nothing and preserve pixels.
- A nine-tile L0 source starts a real L1 fade. A 560→400 resize leaves L1
  unchanged while Rust prunes three outgoing L0 tiles. A further resize
  serves L2 and prunes two immediate-previous L1 tiles. Both fades complete
  immediately, every remaining frame references live textures, and mid-fade
  pixels match a completed fetch-all oracle with zero differences.
- Ordinary fully retained adjacent fades still draw both levels. Prior
  malformed/stale, physical mean-color/legend, cache reuse and disposal
  assertions remain active. Resize comparisons complete only count exposure
  to isolate fade ownership; each capture has nonzero density ink and SHA256.

The Node density adapter now uses existing Rust-backed `screenShape` before
calling the bounded low-level painter, and separates raw XYDC from structured
inventory options. Its [focused 15-test suite](node-tests.log) covers large, tiny and fractional
viewports, non-finite refusals, malformed controls, and exact bounded-frame
parity; the low-level helper continues refusing oversized direct calls.

[The wide-viewport failure](red-wide-viewport.log) and
[active-fade failure](red-active-fade.log) were reproduced before their fixes.
They are intermediate diagnostics, not final artifact acceptance; their
intermediate bundle/harness hashes were not separately retained.
[Final provenance](provenance.json) records exact current source, harness and
artifact hashes, commands, scope and limitations. [The build log](client-build.log)
retains typechecking, shader lint and bundle production. Native ABI395,
native library, worker and compute-WASM bytes are unchanged. The ESM and
standalone painter hashes changed, so old artifact reports cannot qualify
the new client.

The coordinator also ran the original unmodified
[full WASM foundation](xyg-1065-review-foundation.json) on this final client
and retained its six screenshots and [log](xyg-1065-review-foundation.log).
[The bounded Node benchmark](node-bounded.json) and
[coordinator validation provenance](validation-provenance.json) bind those
checks to the same producer hashes. These are source/structural checks; no
100M latency or complete release host-matrix acceptance is claimed.

Reproduce the focused proof after building native and client assets:

```bash
node js/build.mjs
python3 scripts/verify_wasm_assets.py
python3 scripts/density_tile_smoke.py /path/to/chromium
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" \
  node --test packages/xy-node/test/pyramid.test.mjs
```
