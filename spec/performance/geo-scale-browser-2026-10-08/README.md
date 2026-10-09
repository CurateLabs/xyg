# Retained geographic browser evidence, 2026-10-08

These three local runs exercise the packaged ABI 33 candidate. They are
implementation evidence; integration and milestone completion remain separate
gates. Raw observations are in [sample-1.json](sample-1.json),
[sample-2.json](sample-2.json), and [sample-3.json](sample-3.json).

## Artifact, environment, and startup

All runs use the same 1,230,703-byte WASM artifact, SHA-256
`b4ef252d2acb7ab0c916cd8e91d966bb3e7c1b1b64d2ec79887bce47cfdf2f72`.
Release packaging measures gzip level 6 at 502,593 bytes; this harness also
records level 9 at 501,997 bytes. Sample 1 predates the explicit gzip-level
fields, but its 501,997-byte value is the same level 9 measurement. The release
limits are 1.25 MiB raw and 512 KiB gzip; see
[browser-wasm.md](../../design/browser-wasm.md).

The host is an Apple M4, 10 logical CPUs, 32 GiB RAM, Darwin arm64, Node
26.6.0, and Chrome 155.0.8059.40, with device pixel ratio 1. Chrome's reported
Mac Intel user agent is browser emulation, not the host architecture.

Worker-construction-to-ready times were 28.3, 25.9, and 34.7 ms; the median is
28.3 ms. Each run starts a fresh browser process and profile. Requests use raw
loopback HTTP without compression, the OS file cache is warm, and main ESM
bundle parsing is outside this interval. Concurrent development load was not
controlled. These observations establish local startup samples, not cold disk
or WAN behavior, a paired compiler comparison, a latency percentile, or a
competitor performance claim. UTC records fall on October 9; the folder date
is the October 8 local execution date.

## Verified behavior

The fixture uses the actual packaged Worker and Rust chunk/manifest/source
protocol. It checks full u64 IDs and i64 time values, two concurrent builder
lifecycles, a bounded FIFO with rejection before input detachment, and five
actual GL-painted charts sharing one Worker and one WebGL2 context. Each view
contains 101 source rows and presents an opaque red center pixel. CPU picks
return the exact full-width ID. Source table pages contain 50, 50, and 1 rows.

It also verifies stale-query cancellation, unsettled read callback ownership
before acknowledgement, failed-read preservation of the old frame, subsequent
recovery, real context loss/restoration, failed initialization cleanup,
dispose during a pending read, and queued Worker shutdown with no remaining
pending requests. Bounded companion DOM cleanup is asserted.

The 32,769-row aggregate case verifies Rust membership reduction and two
paged membership reads, exact member IDs, opaque cursor validation, and
immutable-frame hit identity. That case uses a minimal borrowed-layer stub;
it is membership evidence, not an aggregate GPU paint measurement. The five
direct views above use actual ChartView painting.

A test-only TypeScript module loads the current private parser without adding
public exports. Forty-seven mutations of actual SceneData, membership, and
hit receipts are rejected, including framing, source geometry/CRS, time
windows, provenance bounds, cursors, and reserved bytes. Frozen source export
uses the actual snapshot Worker route: repeated XYGX reads are byte-identical
and preserve Scene 32, camera, time, generation, and full IDs. WASM raster
export explicitly returns UnsupportedExport; no WASM PNG claim is made.

All samples report no external requests and no CSP violations under
`default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self';
connect-src 'self'; style-src 'unsafe-inline'; object-src 'none'; base-uri
'none'`. The test serves only its page/modules and local packaged client,
Worker, and WASM. It uses no CDN or MapLibre runtime dependency.

Sample 3 is the final guard regression. It additionally checks ordinary
temporal-graph, GraphForge, and annotation calls while retained transport
admission is pending and after admission: each rejects before synchronous
buffer copies or detachment. Samples 1 and 2 preceded that final host guard.

## Persistent buffer accounting

Each of the six measured 101-row direct frames (the original plus five shared
views) has an 11,976-byte SceneData packet and a 5,212-byte Painter, represented
by two distinct typed backing buffers totaling 17,188 bytes. A conservative
original Rust packet plus two allowed transfer copies and one persistent
Painter totals 41,140 bytes, below the Rust per-frame charge of 111,616 bytes
(`1024 * 101 + 8192`). ChartView consumes packed planes as views and adds no
geometry or style typed-buffer expansion on this path. Old and new frames
hold independent leases; persistent Painter storage is not attributed to a
reusable staging phase.

For the current geographic tile primitive profile, the separate source review
of `geo_tile_protocol.rs` and the browser packed mark builders bounds three
receipt copies plus Painter at at most `6.5 * receipt + fixed overhead`, below
the `7 * total + 65536 + semantic` lease. The receipt includes canonical Scene
and column planes. Packed triangles, segments, and raster RGBA use direct
views; isolated scatter is the worst case at 112 derived bytes per 32-byte
Scene record. This is a contract/accounting review, not a measured public
browser tile-controller test. Generic hexbin fan expansion and authored glyph
expansion are outside that trusted geographic profile.

The 512 MiB policy covers live product-owned Rust and raw typed binary
buffers within one shared engine/Worker module. It excludes OS RSS, committed
WASM linear-memory high water, general JavaScript object heap, DOM/canvas
backing stores, GPU memory, and application-owned inputs. Separate browser
Workers have separate module budgets. These small browser cases do not prove
100M-row browser painting or massive-data interaction latency. Actual native
scale measurements are in [the native evidence folder](../geo-scale-2026-10-08/README.md).

## Reproduction and validation

From the repository root, build/package the current client and ABI 33 WASM
using the repository's documented build commands, then run:

```bash
XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
XYG_GEO_RETAINED_REPORT='spec/performance/geo-scale-browser-2026-10-08/reproduction.json' \
node scripts/geo_retained_wasm_smoke.mjs
node scripts/geo_source_parser_smoke.mjs
node --check scripts/geo_retained_wasm_smoke.mjs
node --check scripts/geo_source_parser_smoke.mjs
node --check tests/browser/geo_retained_page.mjs
```

The retained smoke and all syntax checks passed. The separate native parser
smoke rejects 20 mutations against an actual native source receipt, retaining
full u64/i64 values. Browser success is published after teardown, including
Worker disposal; final reports show `pending: 0`.
