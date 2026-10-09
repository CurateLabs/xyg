# Retained frozen export protocol

`geo_snapshot_protocol.rs` exposes trusted immutable SceneData freezing and native
export through XYGJ/XYGW v1. The provenance envelope is [XYGX v2](geo-frozen-export.md).
All numbers are typed little endian fields. There is no JSON, source I/O or host
projection/LOD policy. Registry lock order is snapshot → source or tile → derived ledger;
a borrowed authority callback cannot reenter its source or tile registry.

Requests are exactly256 bytes: magic XYGJ0, version u32@4=1, command u32@8,
zero12..16, handle u64@16, sequence u64@24, budget u64@32, format u32@40,
quality u32@44, scale f64@48, zero56..256. Unused fields must be zero.

| Command | Meaning | Active fields |
| --- | --- | --- |
| 1 | Freeze published SceneData | Data handle, exact nonzero published sequence, budget≤128MiB |
| 2 | Export frozen snapshot | Snapshot handle, budget≤384MiB, format0SVG/1PNG/2PDF/3JPEG/4WebP/5HTML, quality1..100, finite positive scale |
| 3 | Dispose owner after dropping all copies/views | Handle |
| 4 | Freeze immutable mixed TileFrameData | Tile frame handle, exact nonzero epoch, budget≤128MiB |
| 20 | Pure snapshot read | Snapshot handle |
| 21 | Pure artifact companion read | Artifact handle |
| 22 | Pure artifact bytes read | Artifact handle |

Mutation execute requires256 bytes output capacity before touching registry state;
it never uses a size-query mutation. Reply XYGW v1 has kind u32@8=0snapshot/1artifact,
handle u64@16, published sequence u64@24, bytes u64@32, companion bytes u64@40;
artifact format/quality/scale at48/52/56. All other bytes are zero. Dispose replies
carry disposed handle and zero lengths. Maximum16 owners,8 snapshots and8 artifacts.
Candidate failure leaves existing owners unchanged. Source/Data disposal never
invalidates a separately frozen snapshot or exported artifact.

Native status codes: Invalid -1, Limit -9, Stale -10, output capacity -13,
Unsupported -15. WASM without raster rejects export explicitly; it does not
silently omit density images. Snapshot freeze/read remain available.

Pure read length queries allocate nothing and consume no transfer slot. Each
immutable plane permits at most two actual reads. Output-capacity failures consume
no slot. Preflight requires4×plane bytes+256 within the supplied≤384MiB read budget
before copying. Snapshots≤32MiB; artifacts≤64MiB. The durable engine owner retains
its conservative derived reservation through all admitted copies/transfers and is
released only after the host drops their storage and disposes the handle.

Python `_geo_snapshot` and Node `geo-snapshot` are thin packers and lease owners.
`frame.export` returns OwnedGeoArtifact with `bytes` and `snapshot` borrows, explicit
close/aclose/dispose and no destructor. Async cancellation settles every transport
and read before dropping buffers and retiring handles; a remote source requires its
explicit matching snapshot bridge rather than accidentally using local native handles.
Native synchronous export works inside an already running notebook event loop.

Trusted retained painter lowering is a separate `geo_retained_painter` helper:
Datahandle+exact published sequence+opaque GeoTransportPhase authority only. The
phase is acquired before the source callback, serialized by its transport owner,
and retained until painter output/arena is dropped. No bare boolean or claimed
budget can create the permit. It validates the bounded Rust-generated direct
32768/cluster32768/density196608 profile and preflights32×SceneBytes+1MiB against
phase≤128MiB before decode. This covers record/style vectors, grouping scratch,
image clones, painter capacity and fixed layout/tick/header work for that profile.
It does not admit generic host-authored Scenes with arbitrary labels or glyphs.

Reproduce with `cargo test -p xyg-engine --offline geo_snapshot` and
`uv run pytest tests/test_geo_snapshot.py tests/test_geo_retained_components.py -q`.
The independent protocol proof freezes a real published frame, disposes source and
frame, exports all six native formats and verifies paired artifact digests; it also
checks tiny-phase rejection, full-u64/signed-time identity, reserved bytes and read quota.

Command4 uses the distinct tile frame namespace and trusted borrowed tile
receipt/config/key/digest authority. The generated Scene is frozen exactly and
all six native export formats include raster and vector basemap layers plus the
foreground catalog. No-raster WASM retains freeze/read support and returns
Unsupported for static artifact export, including mixed raster Scenes. Tile
painter preparation uses the same opaque serialized transport phase and
32×SceneBytes+1MiB preflight; it admits only the trusted catalog-generated Scene.
Native mixed proof: `uv run pytest tests/test_geo_tiles.py -q`.
