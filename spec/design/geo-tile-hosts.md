# Native mixed tile hosts

`GeoTileSource` and `GeoTileSession` are data/session types, exported lazily by
Python `xyg` and from the Node root. `geo_chart`/`geoChart` remains the sole chart
builder. Hosts pack typed XYGT requests and consume Rust's exact read tickets;
they do not select tiles, project geometry, infer a provider or choose LOD.

Every source explicitly supplies generation, layer/style revisions, kind, zoom
and payload/geometry limits, locator, attribution and local/network location.
Optional signed time windows are i64 (Python integer/Node bigint). Identity fields
are full u64, never JavaScript numbers. Raster payloads are canonical raw RGBA;
vector payloads are validated XYGD. Compressed provider images are not implicitly
decoded. An optional `http_tile_loader`/`httpTileLoader` only fetches an explicitly
configured attributed HTTP(S) receipt and bounds response storage before copying.
Its callback receives the authenticated Rust-issued locator, XYZ and limits.

Python's native reader and target stage are synchronous and work within a running
notebook event loop. Node readers/stages are asynchronous and receive an AbortSignal.
Cancellation waits for outstanding I/O/staging to settle before dropping buffers
and acknowledging the read ticket. The Rust-issued primitive capacity limit is privately captured before calling
the reader, so mutating a callback receipt cannot widen authority. Authorized
logical length and backing capacity are checked separately; a tiny view of an oversized allocation is rejected.
Readers must release their own retained callback buffers before resolving.

`prepare` returns an owned immutable candidate Frame without committing live
state. `update` requires an explicit target stage and commits only after it succeeds.
A rejected stage, read or style revision preserves the previously committed Frame.
Python holds operation admission through stage and commit, rejecting callback
reentry and session close. Node closes new-operation admission synchronously when
disposal starts, then settles existing I/O before retiring the owner.
Source/session disposal leaves independently owned Frames usable. Drop all borrowed
`frame.data` views before `close`/`dispose`; artifacts likewise own their `bytes`
and paired `snapshot` until explicit retirement. There are no finalizers.

Native composition accepts `tile_session`, `tile_vector_styles`, `tile_image_id`
(Python), or `tileSession`, `tileVectorStyles`, `tileImageId` (Node). Foreground
layers use the existing geographic catalog. Tile and retained point-source modes
require separate explicit frames. Python `.compile()` and Node `.compileTiles()`
stage a native frozen SVG before commit and return the owned Frame. A remote Node
session uses its explicit `session.update(..., stage)` target instead. The chart
budget must cover the session's explicit ≤128MiB processor budget and remain
≤384MiB; it never overrides the source's resource limits.

`chart.to_image(..., frame=frame)` / `chart.toImage(...,{frame})` requires a Frame
from that session with exact camera and catalog/style authoring binding. It returns
an owned artifact, including immutable paired provenance. `frame.export` also works
after session disposal. SVG, PNG, PDF, JPEG, WebP and static offline HTML preserve
all mixed basemap and foreground Scene records, attributions and raw raster pixels.
HTML has a static CSP and no scripts or network dependencies. Native artifacts are
accountable to [XYGX v2](geo-frozen-export.md) and [XYGJ](geo-snapshot-protocol.md).
No-raster WASM can freeze/read but explicitly rejects static artifact export.

Repeated exports of the same Frame are byte deterministic. Independent hosts
compare exact Scene/config/key/payload stamps and pixels; private cache handle/epoch
in the exact receipt is transport context and is not rewritten in snapshots.
Tile time keys preserve signed source windows, but global mixed camera/time
revisions and shared foreground signed-time filtering remain an explicit #50 gate.
This native bridge does not claim completion of browser mixed export or all-scale
multi-layer temporal composition.

Reproduce: `uv run pytest tests/test_geo_tiles.py tests/test_check_typing.py -q`.
The real native/Node proof checks six formats, frozen raster pixels and attribution,
full-u64 revisions/feature IDs, same-Frame determinism, target/style failure recovery,
old Frame lifetime, unauthorized backing capacity and unsettled-read cancellation.
