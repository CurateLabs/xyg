# Issued temporal-overview sources

Dossier §17, §27–29 and §34. This is the typed ownership and existing geographic
composition adapter for the [overview protocol](geo-temporal-overview-protocol.md)
and [trusted painter/snapshot](geo-overview-painter-snapshot.md). It introduces no
host geometry, temporal filtering, palette, tier, layout or feature policy.

`GeoOverviewIndex.from_frame(seed, retained_source, budget=..., max_vertices=...,
read_chunk=..., read_page=..., write_page=...)` builds an issued immutable index.
The Node/browser spelling is `GeoOverviewIndex.fromFrame(seed, {bridge, budget,
maxVertices, readChunk, readPage, writePage})`. The caller supplies authenticated
storage callbacks. The seed must have private issuer provenance; modifying a
public owner handle, query or selection annotation cannot grant another owner.
Selected seeds, including empty intent, are unsupported before command 27.
The async Python spelling is `from_frame_async`; synchronous native operation
works inside an already-running notebook asyncio loop without `asyncio.run`.

An index accepts independent explicit snapshots through `update(query,
sequence=...)` / `update(query, {sequence, signal})`. A complete query specifies
camera, source digest/generation, layer, all five revisions, signed time,
`reduced_kind=0`, `max_cells=0`, `previous_direct=False` and
`max_projected_vertices=0`. Rust returns temporal-exact counts on its fixed
16×16 **data-domain** grid. Counts measure vertices, including MultiPoint
vertices, and are explicitly nonfinal spatial output. Cell ordinals are not
source feature IDs. Exact original-row domain membership uses the separate issued member adapter.
There is no source pick, Rows, selection or screen refinement authority.

The only chart-building surface remains `geo_chart(geo_layer('density',
source=index, layer_id=..., query=query, sequence=...), camera=query['camera'])`.
It accepts one overview density layer and exactly query/sequence properties.
The camera/layer must match the query exactly; the chart budget is an upper
ceiling over the index's explicit processor budget. Authored styles, events,
legends, mixed layers and tile sessions are rejected. Python `compile` and
`compile_async` return an owned overview frame; Node uses the existing async
`compileRetained` owned-frame method. Ordinary point/catalog behavior is
unchanged. `to_image(..., frame=frame)` / `toImage(..., {frame})` require the
same privately issued index and exact query, and return an owned artifact.

Each frame owns one immutable Data handle and its native packet read. `retain`
(command 26) creates independent ownership with the existing two-read quota;
it survives index, source and original-frame disposal. Native `export` freezes
command 6 and supports PNG, JPEG, WebP, SVG, PDF and inert offline HTML with the
full nonfinal XYOF receipt. Python static `show` / `_repr_html_` exports that HTML.
Callers drop borrowed packet/Scene/count views before explicit close/dispose.
Frames do not borrow an index handle for retention/export. Browser paint uses
only the trusted private Data painter path, with an exact Worker-issued bridge.

All mutable public fields are decorations. Internal index and frame registries
capture issuer, numeric authority, sequence and encoded snapshot before dispatch.
The shared TypeScript owner retains 256 source-header bytes and a 2304-byte
immutable frame header/count receipt; internal getters return bounded copies.
Runtime private fields and captured canonical methods prevent public method
edits from redirecting nested publication or cleanup. A Worker may transfer a
wire request; private canonical snapshots are never sent as transfer buffers.

Resolved transport promises do not prove settlement. Supply, cancellation,
read/write ACK and disposal require exact code-0 receipts with the issued
handle/sequence. Rejected cleanup remains retryable and drops views before the
first attempt. A private pending ticket survives failed ACK; exact retry, or
validated cancellation followed by terminal code 9 without a loan, confirms
release. Deferred query admission settles before disposal, so no handle-zero
cleanup is sent. An index blocks new queries once closing starts. The recovery adoption proof admits five Queries beside five indices, five old
Data owners and one retained seed (sixteen handles). Opt-in command29 replaces
its known Query handle with Data. Each accepted replacement retires its
corresponding old Data before later publication, preserving the combined eight
Data cap. This proves handle admission and atomic ownership, not five-view
browser latency. The existing
128 MiB processor, 384 MiB derived, 16 total handles, eight sessions and eight
Data owners remain unchanged; storage retained by callbacks is external storage
and is not claimed as part of the engine ledger.

## Durable allocation ownership

Automatically issued overview owners now use the private bounded allocation
attempt described in [overview recovery](geo-overview-recovery-hosts.md).
Commands26–29 carry private per-issuer nonces; exact replay recovers a lost
allocation receipt and command47 confirms its birth before another nonce may
be issued. Public recovery methods settle the complete drive/read continuation,
not only the allocation ACK. Cancellation and disposal retain the guard until
callbacks, exact ticket ACKs, Data disposal and birth release settle. Raw nonce0
packets retain their legacy behavior.

This bounded slice does **not** complete #39. Subsequent layers cover
[Snapshot-local6/7 recovery](geo-overview-binary.md),
[selected35/36 mutation hosts](geo-selected-mutation-hosts.md),
[domain45 recovery](geo-overview-members-recovery.md), and
[native live overview routing](geo-native-overview-hosts.md).
Public19 and hierarchy43/44 adoption, lost MemberData10 cleanup, feature
refinement and massive end-to-end interaction remain separate gates.

## Reproduction

Build the current native core and packaged WASM/client, then run:

```sh
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" uv run pytest tests/test_geo_overview_source.py tests/test_geo_overview.py tests/test_check_typing.py -q
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" XYG_GEO_OVERVIEW_WASM="$PWD/packages/xy-client/dist/xyg-wasm.wasm" node --test packages/xy-node/test/geo-overview-source.test.mjs
node scripts/gen_geo_overview_hosts.mjs
```

The generator derives Node framing, owner implementation and declarations from
canonical TypeScript while preserving the native-only geoscale suffix. Node
native export adds only command-6 artifact ownership, not count/geometry policy.


Issued frames now provide bounded exact original-row domain membership through
[the typed membership adapters](geo-overview-members-hosts.md). The counts remain
spatially nonfinal; this does not grant camera picking or selected overview
membership, and unknown45 allocation recovery remains open.
