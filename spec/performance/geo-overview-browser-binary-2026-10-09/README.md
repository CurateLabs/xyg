# Accepted browser overview binary freeze: small fixture

This records correctness/lifetime evidence, not a latency or massive-data win.
The source baseline is aggregate980 `ae336da2733801ca94071ccb281c7707c8ed6d27`.
No Rust/Cargo/build input changes are part of this browser slice. All199 tracked
compiler-input paths and bytes match the approved membership-protocol artifact
donor, as recorded in `compiler-inputs.json`.

The actual artifact pair is native `be47dff3…` and WASM `66e49864…`; full SHA256
and pinned paths are in `environment.json`. Packaged WASM is1484593 raw bytes,
610671 gzip-level6 bytes. This slice changes browser source only, raises no gate
and does not adopt another build profile. Chrome155.0.8059.40 uses SwiftShader;
Node26.6.0 runs the harness. Reports preserve actual versions and commands.

## Results

* `browser.json`/`browser.txt`: actual public ESM composition and Worker command6,
  strict2432B identity/count prefix, pending update and borrowed-layer pin,
  source/index/controller disposal independence, immutable read and Snapshot
  quotas, local/Rust budget refusal, private captured dispatch, known cleanup
  retry, pending-read close ACK, lost/corrupt confirmation, no blind allocation,
  genuine terminal authority, and foreign producer controls. No external request,
  CSP violation or page error. Ordinary/borrowed old GL cell remains
  `[55,155,255,255]` while mutation confirmation is pending.
* `independent-browser.json`/`.txt`: parent independent source review and actual
  Chrome run pass the recorded controls. `independent-metadata.json` pins the
  unchanged production checkpoint and artifact; this earlier fixture does not
  claim the final additional Worker-disposal output control.
* `controller-regression.json`/`.txt`: unchanged existing public controller
  journey against the same66e artifact, including two-Worker collision,
  queued producer replacement, keyboard/focus/counts, borrowed failure/retry,
  caller-current independence and existing uncertain27/28/29 controls.
* `native-wasm-conformance.json`/`.txt`: separately executes the existing shared
  native/WASM canonical fixture. Scene5301B, painter633B, frozen7733B are byte
  equal across hosts. Its ordinary v2 snapshot1272B hash is identical. Six native
  formats and scriptless offline HTML replay pass. SVG replay `[56,156,255,255]`
  differs by1LSB from GL; no cross-renderer exact-pixel claim. This fixture has
  different temporal source bounds from the public-wrapper fixture; their source
  digests are not claimed equal.

The public wrapper verifies metadata, profile length and Scene32 framing; it does
not implement an independent Scene decoder or compare accepted Scene bytes.
The genuine Rust producer owns canonical Scene validation. Returned bytes are
inert, not live source-feature picking, Rows, query or membership authority.

## Reproduction

```bash
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
# After verifying compiler-input equality, copy the pinned donor66e WASM into
# packages/xy-client/dist/xyg-wasm.wasm (the client build clears dist).
XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  XYG_OVERVIEW_BINARY_REPORT=/tmp/overview-binary.json \
  node scripts/geo_overview_binary_smoke.mjs
XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  XYG_OVERVIEW_CONTROLLER_REPORT=/tmp/overview-controller.json \
  node scripts/geo_overview_controller_smoke.mjs
XYG_NATIVE_LIB=/Users/davidspencer/.t3/worktrees/xyg/t3code-m6-geooverviewmembershipprotocol/target/release/libxyg_core.dylib \
  XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  XYG_OVERVIEW_PAINT_REPORT=/tmp/overview-native-wasm.json \
  node scripts/geo_overview_painter_snapshot_conformance.mjs
```

All six WASM static artifact formats remain Unsupported; `freezeBinary` exports
XYGXv4 only. Temporal/data-space/nonfinal flags3 remain explicit. Durable unknown
allocation recovery, selected overview, final spatial refinement, and massive
interactive/five-view closure remain separate gates. Issue50/39/M6 are not
declared complete by this bounded checkpoint.
