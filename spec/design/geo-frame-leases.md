# Immutable geographic frame leases

This bounded #50 ownership slice adds an independent owner of an existing trusted
retained point SceneData. It does not change projection, time filtering, LOD,
selection, index storage, the public chart builder, or massive interaction gates.
It supplies the ownership seam required for later explicit mounting of a
precompiled indexed frame without consuming the caller's frame.

## Trusted command 26

`XYGQ` v1 command 26 is exactly 256 bytes, without payload. Handle at byte 16 is
an existing immutable **SceneData** capability, sequence at byte 24 is its exact
publication sequence, and the existing query budget at bytes 32–63 is explicit.
All other command-specific fields are zero. Source/query, auxiliary, RowsData,
unknown and disposed handles cannot confer SceneData authority. A stale sequence
fails before allocating or publishing a duplicate. No host-authored Scene or
provenance bytes are accepted, and this command never advances a source query.

The fixed reply gives a new independent Data handle at byte 16, the unchanged
publication sequence at byte 24, exact packet length at byte 32 and the input
SceneData handle at byte 40. The new packet's process-local owner at byte 16 is
that input SceneData handle, so ordinary preparation identity checks apply even
when the original query session no longer exists. **Only those eight owner
bytes differ** from the input packet. Camera, signed time, revisions, literal
IDs, full-source semantic identity, grid counts, Scene and metadata are identical.
Process-local handles are not source IDs or durable provenance.

## Admission and lifetime

Private immutable source/result/style authority is an `Arc` shared by the
original and duplicates. Its single existing source/query lease remains held
until the last authority owner drops; source, index and query disposal cannot
invalidate it. The original authority allocation includes Arc control storage.
No canonical source/result vectors are copied for this operation.

Before allocating packet storage, Rust admits four packet lengths plus one
Entry and 256 bytes of fixed overhead under the existing shared 384 MiB derived
ledger and the caller's processor ceiling (at most 128 MiB). This covers the
new stored packet, its independently permitted two actual transfer reads and
native read scratch. Arc retain is allocation-free. Registry limits remain
16 total handles and eight Data handles. Rejected budget/handle/sequence or
capacity admission leaves every existing owner and query unchanged.

Command 23 applies its usual two-read quota independently to each duplicate;
length discovery is pure and does not spend a read. Explicit Data disposal
releases that packet's charge. A consumer must drop all its derived views,
painters and owned transfer copies before disposal. Disposal of one frame
cannot revoke a different retained owner. This does not extend ledger claims
to framework IPC, frontend processes, GPU storage or OS RSS.

## Thin host methods

Python `frame.retain()` returns a new owned frame for a synchronous native owner;
`await frame.retain_async()` supports an asynchronous bridge and also synchronous
owners inside an already-running notebook loop. Node `await frame.retain()`
returns the matching owned frame. These methods copy only small private host
framing metadata and attach the original authenticated source reader to the new
owner's pick, exact membership, full-source rows, spatial-index build and export
methods. They never replace `source.current`, close the caller's frame or query
an index. Async Python cancellation settles any outstanding command/read,
drops unreturned views, then explicitly disposes the newly created Data owner.

The shared TypeScript `prepareGeoSceneData` accepts command 26 without a style
payload; style comes exclusively from trusted immutable authority. This internal
framing seam does not add another chart-building surface or mount integration.

## Evidence and remaining integration

Focused Rust tests cover direct/reduced exact packet identity, independent copy
quotas, source/original disposal, full-source rows, wrong authority, stale sequence,
malformed payload, small budget, eight-Data pressure and repeated clone/dispose.
Native Python four tests and Node four tests pass, covering running-loop use,
indexed frames after query/index/source disposal, picking, rows, SVG export,
pressure/read-error recovery and settled asynchronous duplicate cancellation. The real
native383/WASM33 conformance runner passes direct and 40,000-vertex reduced
frames: exact packet equality after normalizing only bytes16–23, full-u64
identities, picking, full-source rows, independent copy quotas and exact reduced
membership (two original rows rather than 40,000 vertices). Their frozen XYGX
snapshots also match exactly; all six native formats export after original/source
disposal, while no-raster WASM explicitly returns Unsupported for artifact export.

Reproduce using fresh current artifacts:

```sh
cargo test -p xyg-engine geo_scale_protocol --lib
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" PYTHONPATH=python:tests uv run pytest tests/test_geo_frame_leases.py -q
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" node --test packages/xy-node/test/geo-frame-leases.test.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" node scripts/geo_frame_leases_conformance.mjs
```

The last command accepts `XYG_FRAME_LEASE_WASM` for an explicitly selected real
wasm32 artifact; it does not package or waive the artifact size gate. Explicit `GeoChart.host(frame=...)` integration and its real
notebook/Reflex/VS Code journey are subsequent work; this document does not claim
that those hosts already accept indexed sources.

The initial local cmd26 checkpoint artifact is 1,277,035 raw bytes and 522,210 bytes
with Node `gzipSync` defaults, below the unchanged 1,310,720 / 524,288-byte
gates. SHA-256: `312c41122d6d61c38eece8e6fbf0691ba8d45e7562d2ee4f49e3b82b2ad31ed4`.
This uses the existing O3/inline100/Binaryen132 profile; package signatures
remain native383/WASM33. The packaged artifact passed the conformance command
above, not just the unoptimized compiler output.

CI on Linux measured that checkpoint at 524,462 gzip bytes, 174 bytes above
the unchanged 524,288-byte gate. Data-slot admission is now one shared cold
function for all five Data producers, with inlining disabled for that function
only. The release optimizer profile and quotas are unchanged. The revised local
artifact is 1,276,353 raw / 522,046 Node-default gzip bytes, SHA-256
`06403229aa9ff7df71f4527aef97c52a58bc6cd093879e374a4c8bd8e7cee4f8`.
Fresh native and packaged-WASM conformance and all23 protocol tests pass.
Linux exact-head CI remains the platform size decision; the local result alone
does not establish that gate. No runtime speedup is claimed.
