# Combined ABI405 module layout qualification

This continuation starts at independently approved source checkpoint
`ae58f6d8b0fbaff73885b442ed4b926e22dc682a`. Its matching native ABI405 and
WASM38 declarations retain 551 native symbols and 68 Worker exports. The
checkpoint's complete module failed the fixed package caps. Its native mounted
indexed journeys and reviewed source correctness do not supply a shipping pass.

The only retained producer changes are target-specific LLVM inlining threshold
0, compiler names retained through optimization, and deterministic function-name
ordering followed by debug/name stripping in pinned Binaryen132. O2, native O3,
fat LTO, one codegen unit, Rust1.96, dependencies, validators, export union,
renderer, codec bytes, runtime arenas, deadlines and both package caps remain
unchanged. No Rust function body changes or experimental projection/error hints
are retained. The optimizer still consumes the isolated bytes read by packaging.

## Size and attribution

Node22 gzip6 is the packaging measurement; other archive compression is not the
gate. All measurements retain complete native405/WASM38 source and environment
bindings.

| Artifact | Raw bytes | gzip6 bytes | Disposition |
| --- | ---: | ---: | --- |
| Approved source baseline, O2/inline50 | 1,936,761 | 805,269 | over both fixed caps |
| O2/inline0, early stripping | 1,900,190 | 794,290 | gzip still over cap |
| Named O2/inline0, same O3 pass then stripping | 1,903,263 | 796,788 | gzip still over cap |
| Named O2/inline0, function ordering then stripping | 1,897,244 | 784,226 | fitting candidate |
| Selective projection hint plus candidate layout | 1,897,419 | 784,283 | rejected; mixed runtime observations |

Fixed caps are 1,927,168 raw /786,432 gzip6 bytes. The candidate leaves 29,924
raw and 2,206 gzip bytes. The extra error-reporting outline saved zero raw bytes
and grew gzip by one byte; its source was restored. Function ordering saves
6,019 raw /12,562 gzip bytes against the same named compiler output with only
stripping. Named versus early-stripped compiler outputs differ, so these gains
must not be added as if they were independent changes.

## Runtime evidence and limits

The existing ABBA profile harness compares admitted 100-, 10k- and 100k-row
GraphForge composition and geographic Scene/viewport/catalog/interaction
requests. GraphForge composition is not a layout execution benchmark. Complete
initial outputs match for each admitted request; all raw timing samples remain.
The 100k interaction request retains its existing matching resource refusal.
Observed candidate/baseline medians range approximately 1.005–1.135 in this run.
These uncontrolled shared-VM samples include slower cases; no speedup is claimed.
The first invocation omitted the required explicit native path and failed
library discovery. It receives no pass credit; the corrected run passes.

Additional raw-WASM export comparisons cover seven immutable retained glyph/frame
captures, Scene/XYPB/SVG/PNG, and scales1/2. All 56 outputs and every timed
iteration match the explicitly selected native artifact. Timings include API
framing, output copying and assertions; they are not isolated raster timings,
actual browser painting, hardware qualification or competitor evidence.

Normal producer and affected qualification results are recorded in
`checks.json`. The source checkpoint approval is inherited only for
unchanged material. Historical receipts remain byte-identical; the successor
Core binding preserves their original producers. Preparation inventory is not a
final exact-byte freeze.

Independent final-diff review, accepted-main integration, hosted CI and merge
queue remain required. Full #45/#39/#50/#110–113 and milestones4–7 remain open for
scale, resource/default budgets, all-host/accessibility, navigation, comparison
and the other acceptance conditions documented in their authoritative issues.

## Inherited host-gate corrections

The first full Node run passed 1,124 tests but failed two inherited assertions,
with two existing skips. The unsupported-source assertion still expected the
older statement that indexed hosts were pending, although exact indexed hosts
with explicit matching frames are already implemented. The Node and Python
assertions now require the current diagnostic and preserve their error types
and early rejection.

The unchanged browser-global guard also rejected the frozen adapter's local
`window` binding. Destructuring now aliases that public option as `timeWindow`;
property name, validation order, wire arguments and error text remain unchanged.
The guard itself is byte-identical. Six focused Node tests and five Python host
tests pass, followed by the complete corrected Node command. The initial failed
run is retained and is not credited as a pass.

## Normal producer and affected qualification

The normal native, client, WASM and package commands all pass. The packaged
module exactly matches the fitting diagnostic candidate, SHA256
`25ad6dacad480bc508f9fd64aa22eacdb3897111b5afa5ba2c529bd545bf1c03`.
It has ABI38, all68 function exports, zero imports and no name section. Native
ABI405 remains byte-identical to the approved parent, SHA256
`9cc2a1cb109e5c4889e15ff2e75c8602d9ebe6586bb4df5149054c8beafd01d9`.
All Rust source files are parent-exact; only target Cargo configuration changes
among the298 compiled producer inputs.

Fresh full Node validation passes1,126 tests with two existing skips. Actual
Python3.11.17 passes all41 frozen/host cases. Core/inventory/ownership controls
pass42 cases, including real Git CRLF conversion. The API preparation checker
reports matching declarations and four stale generation-time source hashes;
it is not an exact-byte freeze. A capability-check invocation without an
explicit native path selected the oldABI403 build and failed; its preserved
log receives no pass credit. The corrected capability check passes.

The full source foundation passes the default16MiB pointer/camera and trusted
keyboard journeys, all15 retained temporal cases and seven real Worker freezes.
Frozen Scene/XYPB/SVG/HTML/PNG bytes match native; offline ChartView and strict-CSP
Blob Worker PNG recovery/disposal pass. Five-view indexed filtering and the real
32-chart GPU admission/rebuild/context-restoration journey pass; teardown leaves
zero tracked allocations.

An additional real10k primary plus1k peer journey passes at explicit384MiB each.
Complete browser/native/WASM reply replays pass123 pointer,126 keyboard and123
public10k requests. Fresh isolated default1k replays reach11,468,800–11,599,872
WASM linear bytes; the10k primary reaches37,748,736. These measurements exclude
total browser/RSS/GPU accounting and do not imply universal default admission,
reliable two10k completion or contention tolerance.

Sixteen fresh-process CLI compile/instantiate samples are retained separately.
They are neither browser first-paint nor cold filesystem evidence. Shared-VM
measurements establish no startup leadership or competitor win. Broader scale,
resource, accessibility, installed-host and milestone acceptance remains open.

Final local contract validation passes the unchanged workflow validator and all
776 `make check-ci` regression tests. Required commit hooks and Ruff results are
bound separately. Local qualification does not imply hosted CI or queue entry.
