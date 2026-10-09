# Hierarchy host adapter functional evidence

The shared typed hierarchy driver and mechanically erased Node codec consumed
actual native ABI383 and packaged wasm32 ABI33. `native-wasm.json` records36
packet hashes forming18 exact native/WASM pairs: direct Scene/Rows, two reduced
Scenes and all14 membership pages. Member packets normalize only process-local
owner bytes16..24 and their redundant owner80..88. Camera/time/key/cursor/count,
original source ordinals and full-u64 records remain exact. Scene buffers compare
without normalization and also match the ordinary canonical Rust source oracle.

`node-tests.txt`:36 tests passed, including21 hierarchy tests and existing flat
index, retained-frame and public static host regressions. `python-tests.txt`:41
tests passed, including12 hierarchy tests. Reduced fixtures contain32769 valid
Point rows or16385 valid MultiPoint rows with two vertices per row, duplicate
u64MAX IDs, null rows and a valid empty MultiPoint. Complete4096-row pages yield
all source ordinals once after source/hierarchy/query disposal. Signed-i64MIN
identity is checked on ordinary frames. No host geometry/count policy is added.

Negative controls cover backing capacity and callback ticket mutation, failed
writes/read recovery, cancelled reads and durable writes that must settle before
exact private ACK, cancelled terminal replies that cannot publish, local budgets,
explicit work fallback, selected v2 authority returning UnsupportedSelected,
strict reserved reply fields, old-frame lifetime and authentic retained-frame
provenance. Two actual WASM modules with colliding numeric Data handles cannot
cross producer authority. Rejected native/WASM cleanup can be retried without
restoring disposed views, and Python weak producer records do not pin source/frame
cycles. Explicit Python/Node public static mounts retain a distinct lease
before caller/source/index disposal. Hierarchy live routing is not implemented;
private WeakSet markers distinguish these frames and their clones from canonical
mutable SourceSession authority. Static authoring matching normalizes only
command/source handle, not the snapshot bytes or claimed execution history.

Reproduce from a native/WASM build of protocol commit166d08a14 (all Rust crates
are unchanged in this host slice), or equivalent integrated code:

```sh
uv sync --extra reflex --group dev --no-install-project
npm ci
npm ci --prefix packages/xy-node
node scripts/gen_geo_hierarchy_node.mjs --check
npx tsc -p js/tsconfig.json --noEmit
npx tsc --strict --noEmit --target es2022 --module nodenext --moduleResolution nodenext packages/xy-node/test/geo-hierarchy-types.ts
XYG_NATIVE_LIB=/absolute/path/libxyg_core.dylib XYG_HIERARCHY_WASM=/absolute/path/xyg-wasm.wasm XYG_HIERARCHY_HOST_REPORT=spec/performance/geo-hierarchy-hosts-2026-10-09/native-wasm.json node --test packages/xy-node/test/geo-hierarchy.test.mjs packages/xy-node/test/geo-spatial.test.mjs packages/xy-node/test/geo-frame-leases.test.mjs packages/xy-node/test/geo-indexed-host.test.mjs packages/xy-node/test/geo-host.test.mjs
PYTHONPATH=python XYG_NATIVE_LIB=/absolute/path/libxyg_core.dylib uv run --no-sync pytest tests/test_geo_hierarchy.py tests/test_geo_retained.py tests/test_geo_spatial.py tests/test_geo_frame_leases.py tests/test_geo_host.py tests/test_geo_indexed_host.py -q
```

`environment.json` pins the exact native/WASM hashes and host source hashes.
The recorded native and WASM artifact paths identify the borrowed protocol-tree
build used for these tests. The gzip field uses Python gzip level9 with mtime0;
it is an environment measurement, not the release packager level6 gate.
The earlier protocol artifact passed its unchanged package gate; this host slice
makes no claim about a subsequently combined release artifact. The Map/dict
fixture store and canonical input are explicitly caller-owned small test data,
not bounded massive storage evidence. No browser framebuffer, GPU latency,
selected hierarchy, massive host latency,1B runtime or competitor-win claim is
made. Those remain separate #50 gates.
