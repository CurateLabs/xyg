# Geographic catalog transport (#49)

The shared Rust processor `geo_layers_protocol::execute` accepts **XYLK v1**
and produces **XYLM v1**. These magics are distinct from graph-layout XYGL/XYGO,
legend XYLG, geographic-column XYGM, compound/chunked XYGC, and Scene XYGS.
The same processor is exposed through C ABI 381 `xyg_geo_catalog_compile` and
WASM ABI 31 `xyg_wasm_geo_catalog_compile`. All integer and floating planes
are explicitly little-endian. No numeric JSON carries authoring or paint data.
The result embeds the ordinary current-version XYGS Scene, consumed by the
existing Rust Scene lowering and browser painter, rather than a second painter.
Product policy, defaults, projection, styles, state precedence, arc sampling,
fill topology, legends/labels and density binning live in `geo_layers.rs`.
See [compiler contract](geo-layer-compiler.md) and [geographic design](geospatial.md).

## XYLK header (128 bytes)

| Offset | Type | Meaning |
|---:|---|---|
|0|4 bytes|XYLK|
|4|u32|1|
|8|u32|layer count, maximum 64|
|12|u32|bit 0 legend present; bit 1 interaction event present; other bits zero|
|16|u32|EPSG 4326 or 3857|
|20|u32|world wrap, exactly 0 or 1|
|24..80|7 f64|center X/Y, zoom, width/height CSS pixels, bearing/pitch degrees|
|80|u32|legend location (0..8, same Rust LegendLocation order)|
|84|u32|legend title UTF-8 bytes, maximum 8192|
|88|f64|legend font size|
|96..128|bytes|reserved zero|

An absent legend requires bytes 80..96 zero. The title follows, padded to an
8-byte boundary with zero bytes. Every subsequent plane has the same padding.
Camera/style numeric fields must be finite; Rust validates their semantic range.
Host wrap values must be actual booleans, not coerced strings or numbers.

An interaction event, when present, follows the padded title as a 64-byte
block before layers. Offsets: operation u32 at 0 (Hover 1, SelectAt 2, Brush 3,
Clear 4, FocusStep 5, FocusFeature 6, SelectFeature 7); selection mode u32 at 4
(Replace 0, Add 1, Toggle 2); signed i32 step delta at 8; reserved zero at 12;
literal layer/feature IDs u64 at 16/24; four finite f64 coordinates at 32..64.
Hover/SelectAt use X/Y and require the other coordinates zero; Brush uses all
four CSS screen bounds. Key operations use the two IDs. All inactive fields
are zero, and unknown operations/modes fail. The initial state comes from
source flags: focus chooses the first valid nonhidden focused key in catalog
layer/source order, expands all repeated-ID rows of that key, and clears other
focus flags. Rust owns picking, hover, brush, selection modes and keyboard walk;
FocusFeature/SelectFeature work for eligible offscreen keys as well.

Each layer has a 384-byte header and eight planes. Layer IDs are literal u64,
unique within a catalog; source feature IDs retain every bit and may repeat.

| Offset | Type | Meaning |
|---:|---|---|
|0|u64|layer ID|
|8|u32|Points 1, Bubbles 2, Routes 3, Arcs 4, Polygons 5, Choropleth 6, Density 7|
|12|u32|presence flags: domain 1, bubble diameters 2, arc 4, density 8, legend label 16, selected patch 32, hovered patch 64, focused patch 128|
|16..64|48 bytes|base style patch|
|64..112|48 bytes|selected patch|
|112..160|48 bytes|hovered patch|
|160..208|48 bytes|focused patch|
|208..224|2 f64|value domain|
|224..240|2 f64|bubble diameter range|
|240|f64|arc bend|
|248|u32|arc steps|
|252,256|2 u32|density columns/rows|
|260..264|bytes|reserved zero|
|264|u64|XYGD descriptor byte length|
|272|u64|feature patch count|
|280|u64|f64 value count|
|288|u64|RGB stop count (maximum 256)|
|296|u64|state byte count|
|304|u64|label count (maximum 128 per layer; compiler caps catalog total)|
|312|u64|legend label UTF-8 bytes (maximum 8192)|
|320|u64|label text blob UTF-8 bytes (maximum 8192)|
|328..384|bytes|reserved zero|

Absent options and inactive state patches require their complete bytes zero.
Unknown flags fail. Plane order is XYGD descriptor; feature patches (48 bytes
per row); values f64; RGB stops (3 bytes per stop); state u8; labels (48 bytes
per label); legend label UTF-8; label text UTF-8. Feature patches, values and
state counts are zero or exactly the source feature count. Source validity and
state are separate; null and hidden source rows remain in metadata and cannot
become visible merely through selection/hover/focus. Numeric null-row values
may be NaN because the Rust compiler reads values only for valid source rows.

A patch is 48 bytes: u32 presence mask at 0 (fill 1, stroke 2, stroke width 4,
diameter 8, opacity 16, symbol 32); symbol u32 at 4 (u8 range); fill/stroke
RGBA8 at 8/12; width/diameter/opacity f64 at 16/24/32; reserved zero at 40..48.
Absent fields are zero, and unknown mask bits fail. Empty base patches select
Rust defaults; empty explicit state patches preserve the base for that state.

A label is 48 bytes: feature index u32 at 0; anchor u32 at 4; font size f64 at
8; source-coordinate X/Y f64 at 16/24; RGBA8 at 32; reserved zero at 36; text
offset/length u32 at 40/44. Each referenced range must fit the blob and be
independently valid UTF-8. Anchor and source-row admission remain Rust-owned.

## XYLM header and planes

| Offset | Type | Meaning |
|---:|---|---|
|0|4 bytes|XYLM|
|4|u32|1|
|8,12|2 u32|normalized CRS and wrap|
|16..72|7 f64|normalized camera, same field order as XYLK|
|72|u64|XYGS Scene bytes|
|80|u64|layer count|
|88|u64|style owner count|
|96|u32|focus present, exactly 0 or 1|
|100..104|bytes|reserved zero|
|104,112|2 u64|focus layer/feature IDs; zero when absent|
|120|u64|interaction hit count|

Bytes 8..72 are the exact normalized camera rebuild key. Independently derived
floating-point cameras obey the existing native/WASM projection tolerance;
identical frozen snapshots have identical key bytes. Body: ordinary XYGS
bytes, then u32 style owners (layer index, or u32::MAX for a separator), then
one 128-byte layer header followed by its planes. Every plane is padded with
zeros to 8 bytes. No trailing bytes are accepted.

| Layer offset | Type | Meaning |
|---:|---|---|
|0,8|u64,u32|literal layer ID and kind|
|12|u32|bounds present 1, density present 2|
|16..24|8 bytes|canonical source metadata digest|
|24,32|2 u64|source feature count, visible source-row index count|
|40,44|2 u32|density columns/rows|
|48,56|2 u64|density cell count, membership count|
|64|u32|dropped channels: diameter 1, symbol 2, stroke 4 (density only)|
|68..72|bytes|reserved zero|
|72..104|4 f64|visible CSS screen bounds; zero when absent|
|104..128|bytes|reserved zero|

Layer planes: source feature IDs u64; source validity u8; authored state u8;
visible source-row indices u32. Density additionally has cell counts u32,
CSR offsets u32 (cell count + 1), and source-row indices u32. Counts record point vertices; each CSR segment deduplicates source-row indices. Segment length is at most the cell count, and a cell is empty exactly when its membership segment is empty. Offsets start at zero and end at membership count. Grid rows
are top-to-bottom CSS order. Members retain source order and retain source row
identity even when literal IDs repeat. Interaction union for repeated IDs is
within a layer; `(layer ID, literal feature ID)` disambiguates layers. Source
buffers remain canonical and untouched. Metadata and Scene are derived caches.

After all layer planes, each interaction hit has a 24-byte header containing
literal layer ID, feature ID and source-row index count (three u64), followed
by that many u32 indices padded to 8 bytes. Hits refer to the preserved source
planes. Compile-only responses have canonical normalized focus and no hits; interaction responses carry
the updated authored state planes and a newly compiled Scene. Metadata-only
Rust focus normalization applies on every compile; if it changes state flags,
the Scene is rebuilt to keep styling and metadata consistent. Normalization
state clones are released before output framing allocation. Input buffers
remain untouched and errors publish no partial Scene/state.

## Admission, lifecycle and adapters

Budget maximum is 384 MiB and minimum 64 KiB. Existing individual XYGD columns
remain bounded by 256 MiB. All framing, count multiplication, exact lengths,
reserved bytes, padding, labels, and source plane ranges are checked before
allocating decoded source/options. At most 64 small borrowed frame descriptors
are allocated during scanning; no source-sized allocation precedes admission.
Transport reserves `3*request_bytes+32768`, then gives the compiler half the
remaining budget for compilation or one quarter for interaction. Interaction
compiles an immutable baseline, admits the Rust index into that same quarter
budget (including baseline/decoded Scene/row index/grid/state/hits), applies
the event, drops index/baseline, and recompiles updated state. One quarter is
reserved for retained interaction results during final output encoding. The preflight includes retained feature/text/density metadata
and conservative clipping/arc scratch before source decoding. Result framing
requires twice its byte length to fit the remaining reserve, covering coexistence
with the compiled Scene and metadata. The native size query computes the same
bounded processor twice in sequence, with no persistent cache. Host framing
and ctypes may make bounded request copies; the reserve includes these copies.

C rejects excessive lengths before constructing any pointer slice. All failures
leave output bytes and output length untouched; insufficient capacity is -13.
A null output with capacity zero is the ordinary size query. Native errors are
the stable GeoError codes. The oracle reads at most budget+1 stdin bytes.

The worker `geo.catalog` lane shares all geo/compile/graph/aggregate sequence
admission. Nonzero u32 sequence is required, queued work is rechecked before
cancelling/staging, stale/zero work cannot destroy newer work, cancellation and
disposal release staging/output, and valid current work supersedes active lanes.
Proxy transfer failures remove pending entries and throw typed
XYG_WASM_INVALID_ARGUMENT. Thin Python/Node/TypeScript adapters frame typed
planes and validate exact output lengths; none owns geographic product math.
