# Accepted browser overview binary freeze

The existing `XygGeographicChart.fromOverview` controller exposes
`freezeBinary({budgetBytes?, signal?})`. It freezes the exact privately accepted
immutable Data owner and publication sequence using snapshot command6. It never
requeries the index. Rust owns XYGXv4, its inert XYOF domain counts, Scene32 and
all source/camera/time/revision checks. Dossier §17/§27/§28/§29/§34 applies.

```ts
await chart.ready;
const frozen = await chart.freezeBinary();
const bytes = frozen.bytes; // Borrow; drop application references before ACK.
// Persist/export these inert binary bytes using application-owned I/O.
await frozen.dispose();
```

`GeoOverviewFrozenBinary` has readonly `kind: 'xygx-v4'`, `sequence`, `closed`
and a borrowed `bytes` view. Its constructor requires a module-private capability.
The controller return type is public; no second chart builder or renderer is
introduced. Repeated bytes access returns the same view and consumes no extra
Rust read slot. Application copies or retained borrowed views remain application
owned and must be dropped before disposal ACK. Mutating a borrowed byte array
cannot alter the private accepted identity or create live query authority.

## Producer and binary validation

The genuine Worker constructor issues a private frozen snapshot bridge using the
same captured transport/queue/post/ready chain as its source bridge. A foreign
Worker, colliding numeric handle, public method replacement or changed backing
Worker cannot retag this producer. The backing Worker is checked after queue/ready
waits before posting. The actual native termination method is captured at
construction; setting a public `disposed` decoration or replacing `.terminate`
cannot grant terminal authority.

The fixed256B XYGW command6 receipt must have exact version/kind/sequence/length,
a positive owner and zero reserved/companion fields. One pure command20 read then
validates its exact length and all2432 bytes of the XYGXv4 fixed prefix against
the private2304B accepted XYOV authority, including all256 exact-u64 counts.
Scene magic/version must be Scene32. Maximum Scene757920B and binary760352B are
the existing Rust overview profile. Import policy remains Rust-owned; this
mechanical framing check adds no projection, time predicate, palette or LOD rule.

## Pin, publication and failure lifetime

A freeze synchronously reserves4096B from the existing host FIFO credit and pins
the accepted Data before its first await. The mutation barrier is independent
of the update chain. Candidate computation may proceed, but paint/table/borrowed
handoff and retirement of the pinned frame wait until command6 settles. This
avoids update/close cycles. Ordinary and borrowed views keep their accepted paint
and companion while mutation confirmation is pending. Borrowed callbacks retain
their admission-time captured identity and existing atomic handoff contract.

A valid receipt transfers ownership to an independent known Snapshot, releases
the Data pin and framing credit, then starts its immutable read. A definitive
Rust rejection (`XYG_GEO_INVALID_ARGUMENT`, `XYG_GEO_RESOURCE_LIMIT`,
`XYG_GEO_STALE_HANDLE`, or `XYG_GEO_SNAPSHOT_UNSUPPORTED_EXPORT`) releases the pin
without changing accepted paint. Pre-abort performs no allocation. Cancellation
after known allocation settles any pending read, drops internal packet/header
references, then sends exact command3 disposal. Failed known cleanup coalesces
only while pending and is explicitly retryable; new allocation waits for it.

A lost or malformed command6 confirmation creates an uncertain guard. The guard
keeps the accepted Data and4096B pin credit, blocks another freeze/new allocation/
publication/disposal, and reports `GeoOverviewBinaryUncertainAllocation`. It never
guesses a Snapshot handle, retries allocation or treats the failure as absence.
Only genuine termination of the issuing Worker permits local teardown; Rust's
entire issuing module is then gone. Durable allocation recovery remains a gate.

Closing aborts outstanding work, settles the freeze read and exact cleanup before
destroying controller-owned consumers. A known returned Snapshot remains caller
owned and readable after Source/Index/Controller disposal. Its immutable bytes
also survive Worker termination until caller disposal. The application owns its
external source/page store, Worker and any retained output copies.

## Resource and format scope

No cap or pool increases. Snapshot command6 reserves its persistent Rust credit
before allocation: `8 * binary_length + 65536 + 8MiB` compile scratch, at most
14536960B for the bounded profile. This credit is distinct from the existing
16MiB Data/painter/ChartView lease, host4096B framing credit and128MiB transport
phase. The existing8 Snapshot/16 total Snapshot-or-Artifact handles and two
lifetime immutable read slots remain authoritative; pure length probes consume
none. The128MiB source/384MiB derived ledger retains its per-WASM-module live
owned CPU scope, excluding OS RSS, committed linear memory, GPU/DOM and arbitrary
application input/output copies.

This public API exports **binary only**. WASM SVG, PNG, PDF, JPEG, WebP and HTML
artifact command2 all return Unsupported. Native six-format export and scriptless
offline HTML remain separately proven by the existing snapshot seam; the browser
does not add a renderer. Ordinary v2 and selected v3 formats are unchanged.
Flags3 remain temporal-exact, data-space and nonfinal; domain0..255 never becomes
a source feature ID or GeoLodKey. Selected overview, final spatial refinement,
durable unknown-allocation recovery and massive interactive claims remain open.

## Executable proof

`node scripts/geo_overview_binary_smoke.mjs` runs the actual packaged Worker under
offline strict CSP, including pending update and borrowed handoff, exact old
time/counts, eight-owner and two-read limits, budget failure, captured dispatch,
cleanup retry, pending-read close, lost/corrupt confirmation and terminal/foreign
issuer controls. `geo_overview_painter_snapshot_conformance.mjs` independently
retains native/WASM binary/painter parity, six native formats and offline replay.
Raw artifacts, compiler-input equality and reproduction commands are recorded in
[the evidence folder](../performance/geo-overview-browser-binary-2026-10-09/README.md).
