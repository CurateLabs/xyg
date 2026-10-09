# Combined public temporal overview integration

The actual reviewed typed owner55d3715, browser controller0210e1 and domain-membership protocol9f8f2707 are normal-merge parents of source checkpointef7fd4193. Package and CI registration extend the existing jobs and artifact; no new release gate, pool or dependency is introduced.

All197 tracked Rust/Cargo/.cargo/vendor/build inputs are byte-identical to the domain protocol artifact producer. `artifact-inputs.json` records every hash. Matching borrowed native SHA256be47dff3ae3b40fc24387b8b8a2d245c492b94c772a325e872696a0571e507da and WASM66e49864b39d1e8fda9d0144a4a229b13bcbdfbc452b697c20f6ce60c6ab0820 are used for the actual combined checks. WASM raw1,484,593 bytes/gzip6 610,671 bytes stays below existing caps.

## Evidence

- `python.txt`:15 overview owner/codec/composition tests pass.
- `node.txt`:24 actual native/WASM typed-owner and immutable native export cases pass.
- `browser.json`:actual Chromium155, ordinary/borrowed pixels55/155/255/255, producer identity/colliding Workers, captured dispatch, queued-origin validation, exact counts,32-row companion, ownership/ACK/disposal/cancellation and old-paint controls pass. No external requests, CSP violations or page errors.
- `client-build.txt`:the combined TypeScript client build passes. ANSI color and trailing whitespace were removed from stored build output only.
-216 workflow verification tests and `make check-ci` pass; ownership audit classifies466 production paths. Generator `--check` is nonmutating.

## Reproduce

Build the release native core and direct WASM artifact from these compiler inputs, install root and Node dependencies, then:

```sh
node js/build.mjs
node scripts/gen_geo_overview_hosts.mjs --check
XYG_GEO_OVERVIEW_WASM="$PWD/packages/xy-client/dist/xyg-wasm.wasm" node --test packages/xy-node/test/geo-overview-source.test.mjs
uv run --no-sync pytest tests/test_geo_overview_source.py tests/test_geo_overview.py tests/test_geo_components.py -q
XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node scripts/geo_overview_controller_smoke.mjs
uv run --no-sync pytest tests/test_verify_ci_workflow.py -q
make check-ci
```

Set `XYG_NATIVE_LIB` to the matching explicit native artifact for Node/Python. Raw logs preserve the actual run environment; `source-sha256.json` pins the integration inputs.

## Limits

This is bounded public temporal-domain overview evidence. Counts are spatially nonfinal. Public domain-membership adapters, accepted-frame browser export, native live-host overview routing, uncertain allocation recovery, concurrent five-overview replacement and massive/competitor latency remain open. This does not close#50,#39 or M6.
