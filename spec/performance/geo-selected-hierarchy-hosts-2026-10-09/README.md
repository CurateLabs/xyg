# Selected hierarchy typed host proof

This evidence exercises Python native and mechanically generated Node/shared
TypeScript hierarchy adapters against the fresh source-equivalent native383 and
packaged wasm32 ABI33 artifacts pinned in `environment.json`. The host tree has
no Rust diff from engine90149. Static43 matching is the separately reviewed
compatibility commit88fc691. `node-tests.txt` records61 targeted tests, including24
new typed tests; `python-tests.txt` records40 targeted tests, including five new
typed tests and the independent raw static compatibility test.

`parity.json` records six native/WASM pairs of complete direct Point/MultiPoint
Scene, original Rows and frozen selected snapshot packets. Only process-local
owner16..24 and, for Rows, continuation owner80..88 are normalized. Full source,
camera, signed time, fullu64 IDs, selection contents and provenance remain exact.
The direct Scene also equals canonical selected35/11 bytes after owner/sequence
fields32 are excluded from that *separate* oracle comparison. Reduced fixtures
compare complete remaining bytes to canonical selected output and page all32769
Point rows or16385 two-vertex MultiPoint rows once, preserving source order after
source/index disposal. These are functional controls, not timing benchmarks.

The suite verifies five independent camera/time lanes, the existing16-handle
limit, foreign issued State and producer rejection across two real WASM modules
with colliding handles, callback mutation, read/ACK cancellation, failed cleanup
retry, definite43 rejection preserving State, ambiguous43 ownership, failed44
Query confirmation, lost/corrupt successful44 without replay, late abort+rejected
Data cleanup, and pre-aborted operation recovery. Python additionally checks
parser traceback storage is gone before command10 and initiates cleanup while a
borrowed callback/ACK remain gated. Actual native composition static mounting
retains a marked selected43 frame independently of the caller and source.

Reproduce using the pinned artifact paths (or build paired artifacts from the
recorded engine source using the ordinary repository build). Set
`XYG_NATIVE_LIB` to the native library; set `XYG_HIERARCHY_WASM` to the pinned
WASM. The default test WASM path is module-relative packaged storage.

```sh
node scripts/gen_geo_selected_wire.mjs --check
node scripts/gen_geo_hierarchy_node.mjs --check
npx tsc --noEmit -p js/tsconfig.json
npx tsc --noEmit --strict --module NodeNext --moduleResolution NodeNext --target ES2022 packages/xy-node/src/geo-hierarchy.d.ts
XYG_SELECTED_HIERARCHY_HOST_REPORT=spec/performance/geo-selected-hierarchy-hosts-2026-10-09/parity.json node --test packages/xy-node/test/geo-selected-hierarchy.test.mjs packages/xy-node/test/geo-hierarchy.test.mjs packages/xy-node/test/geo-selected.test.mjs packages/xy-node/test/geo-indexed-host.test.mjs packages/xy-node/test/geo-live-host.test.mjs
UV_NO_SYNC=1 PYTHONPATH=python uv run pytest tests/test_geo_selected_hierarchy.py tests/test_geo_hierarchy.py tests/test_geo_selected.py tests/test_geo_indexed_host.py tests/test_geo_live_host.py tests/test_geo_hierarchy_static_selected.py -q
```

No geometry, selection join or tier policy is added to hosts. The immutable page
store and its copies are explicit caller-owned bounded storage. Native host
mounting requires a native producer bridge; a WASM bridge does not authorize a
native host mount. Browser live routing, massive selected latency and1B scale
remain separate gates. Package and native/WASM CI register the new dual-artifact
suite only after fresh paired artifacts exist. Compiler settings and size caps
are unchanged.
