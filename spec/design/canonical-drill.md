# Capped canonical scatter drill — ABI 396

This implements the bounded D5 baseline over existing canonical f64 x/y and
paired chunk zone maps. It does not require an ingest sort or a new spatial
artifact. The [LOD serving contract](lod-architecture.md#42-serving-a-viewport)
and dossier §5/§16/§27/§28/§29 remain authoritative.

## Ownership and output contract

`canonical_drill.rs` owns query admission, the existing 200,000 entry / 1.15
hysteresis rule, the existing 80,000,000 candidate-row allowance, paired chunk
pruning, finite inclusive rectangle membership and ascending canonical IDs.
The current floating comparison admits 229,999 rows under hysteresis; tests
compare the boundary directly with `lod_plan::drill_decision`.

The C ABI exposes allocation limits, admission, an area estimate and query.
Python/Node borrow contiguous canonical arrays and map planes, allocate only
the Rust-reported cap, and discard all refused prefixes. Query status is
`complete`, `overflow` or `scan-budget`. Only `complete` supplies an exact
count and valid IDs. The other two supply a null exact count and empty host
ID arrays. IDs currently require a u32-addressable source; larger sources
retain their existing aggregate route.

Preflight considers all O(chunks) metadata before reading any coordinates;
there is no candidate-row expansion or N-u32 allocation. A refusal changes
neither `drill_seq`, subset mapping nor history. Hosts retain the aggregate;
if that also fails to compose, a trace-empty response carries query diagnostics
and preserves the already-painted frame instead of invoking a full-column scan.
`read_bytes` is 16 × logical coordinate rows read, not physical I/O or RSS.
An admitted query can still read up to 80M rows; this cap is not a latency proof.

Only complete unfiltered linear-axis results enter `_drill_points`, before
keyed/spilled density returns. That path preserves global color/size domains,
custom colormaps, categories, direct RGBA alpha, stroke/style, canonical f64
hover, selection translation, recent subset history and append invalidation.
The position-only legacy f32 index remains guarded; channels never use
`_ship_index_points`. Active predicates retain their existing exact filtered
route, and never populate the unfiltered tile store. Static export continues
to use the first-paint tier.

Padding also uses the capped query. Its complete count must fit the entry
budget; failed/skipped ladder rungs are recorded, and `padding.fallback` is
`raw-view` when the original exact window ships. XYDC is validated with the
shared Rust decoder before lazy builds or state changes, even when the reply
is points. The [XYDT contract](density-tile-painter.md) records the browser
mean-color handoff correction; opacity, outgoing texture owners, point-window
cache and disposal retain their existing lifetimes.

## Finite proof and reproduction

Environment used: Linux x86-64, Rust 1.96.0, uv CPython 3.12.15,
NumPy 2.5.1, Node 24.21.0, Playwright 1.61.1 and its Chromium 1248 executable.
These are finite correctness fixtures, with no timing comparison or scale claim.
The [raw local observations and original test logs](../performance/canonical-drill-2026-10-28/README.md)
retain source bindings, environment, encoded/decoded hashes and their limitations.

```bash
export PATH=/home/ubuntu/.cargo/bin:$PATH
mkdir -p target/task-tmp
export TMPDIR="$PWD/target/task-tmp"
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
cargo test --workspace
cargo build --release
python3 scripts/gen_abi_manifest.py --write
node js/build.mjs
npm run build:wasm
uv run python scripts/gen_graphforge_semantic_fixture.py --write
uv run pytest tests/test_canonical_drill_native.py tests/test_canonical_drill_interaction.py tests/test_keyed_colored_drill_browser.py -q
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/canonical-drill.test.mjs
python3 scripts/abi_smoke.py
python3 scripts/verify_ownership.py
```

The ABI bump also regenerates the current GeoColumn, mark, payload, attachment,
chrome, animation, default-style, density, force, palette and tooltip cross-host
goldens through their existing Python fixture writers and Node emitters. Only
their top-level `abi_version` changes from 395 to 396; canonical planes,
metadata bytes, payload values and stable error statuses remain unchanged.
These current fixtures are distinct from immutable historical run receipts.

Raw finite native observations (same Rust ABI through Python and Node):

```json
{
  "f64_endpoints_nan": {
    "status": "complete", "indices": [0, 1, 3], "count": 3,
    "candidate_rows": 4, "candidate_chunks": 2, "rows_read": 4, "read_bytes": 64
  },
  "entry_overflow_240000_rows": {
    "status": "overflow", "indices": [], "count": null,
    "rows_read": 200001, "read_bytes": 3200016, "point_cap": 200000
  },
  "retained_overflow_240000_rows": {
    "status": "overflow", "indices": [], "count": null,
    "rows_read": 230000, "read_bytes": 3680000, "point_cap": 229999
  },
  "sparse_mapped_preflight_only": {
    "status": "scan-budget", "indices": [], "count": null,
    "candidate_rows": 80000001, "candidate_chunks": 1221,
    "rows_read": 0, "read_bytes": 0
  }
}
```

The sparse mapping is metadata-only refusal over a sparse zero-backed file;
it is not an ingested scale benchmark. The 600,000-row sorted-x host fixture
queries `[.20,.22] × [.20,.40]`: exact view count 3,871; two candidate chunks,
131,072 rows / 2,097,152 logical bytes read. Its first padded rung
`[.125,.25] × [0,1]` completes with 75,000 canonical rows, the same two candidate
chunks and reads. The emitted 1,800,000 paint bytes include restored color,
size, RGBA stroke and style channels; the source pointers/store handle persist.

The actual browser endpoint fixture uses 262,144 finite rows with production
thresholds, a forced-spill 256-base pyramid and padding disabled solely to
create distinct cache windows. Each of continuous/custom/categorical/direct
RGBA-alpha lanes produces:

```json
{
  "host_modes": ["density", "points", "points", "density"],
  "point_view_counts": [41882, 41882],
  "wide_query_exact_counts": [null, null],
  "noHandoff": true, "cachePromoted": true, "channelsRetained": true,
  "midAlpha": 0.5, "owned": true, "noGlError": true, "disposed": true
}
```

Before the browser fix, `noHandoff` was false because keyed RGBA tiles were
mistaken for a count-only surface. Afterward actual marks paint, cached windows
promote without a request, density returns, and every tracked GPU object frees.

## Remaining product gap

Unordered 100M source chunks can all overlap even a tiny sparse viewport. This
query then correctly refuses without coordinate reads; it cannot resolve the
rows below 200k. A finer locator retaining canonical row identity is still
required, followed by actual 100M and larger-than-RAM interaction, memory,
payload, lifecycle and competitor evidence. No local 100M run was performed.
This bounded implementation does not close #11/#108 or establish a competitor win.
