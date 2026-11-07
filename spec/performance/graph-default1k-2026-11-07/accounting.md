# Capacity inventory for the plain phase plan

This is a capacity upper bound, not a fit to the allocation observations. It
applies only after the Rust document allowlist, persisted/no-loop/undirected
facts and runtime budget/owner/state eligibility checks. Unsupported operations
use the unchanged complete general plan. All cardinality products/sums in the
admission plan are checked before candidate cloning. CSR entry admission happens
before its allocation; its offsets cannot exceed the unchanged1048576-entry cap.

The scalar unit below is8bytes even on wasm32. Growable Vec capacities are
bounded at twice the produced row count; small initial capacities, table headers,
alignment and fixed minima are covered by the fixed98304source and131072output
reserves. Immutable old publication capacities are separately counted using each
actual Vec capacity and element size. Sharing the grid never removes that old
owner from the envelope.

| Future work | Inventory bound |
|---|---|
| node paint/styles | two NodePaint rows and four ResolvedGraphStyle rows per source node; includes capacity growth and source/resolved/output style coexistence |
| node hierarchy numeric work |32scalar slots/node: direct-parent options, representatives, visibility/compound/depth/bounds, forest/order/transition/mask work; no actual compound frame path is eligible |
| node render numeric work |32scalar slots/node: active indices and compact/masked coordinates, cluster identity scratch, output coordinates, built/final membership, counts/offsets/cursors/members/focus, flags, visual/emphasis and encoding scratch |
| node layout/query scratch |16scalar slots/node: force arrays' temporary work, CoSE seed/component/query work; retained/cloned force and source positions are in48D; grid minima fit fixed overhead |
| edge paint/styles |two EdgePiece rows and four pairs of ResolvedGraphStyle/SemanticPaintLayers per source edge |
| straight route work |three slots/edge for each of five coordinate/index columns plus EDGE_ENDS_STRIDE end facts, even though eligible geometry emits at most one shaft |
| edge maps/membership |48scalar slots/edge: routing HashMap at most four buckets/edge with16-byte key/24-byte Vec/one control byte (164bytes), up to32bytes/edge of bundle Vec capacity, rank/size8bytes, leaving180bytes/edge for endpoint/kept/aggregate-slot/CSR/flag arrays and sorting; no clustered edge-dedup map is eligible |
| pick builder |primitive storage belongs to numeric row work; old grid counted by capacity; new CSR at most4Qbytes plus two4097-u32 offset/cursor arrays; Q=min((n+m)*4096,1048576) |
| CPU/GPU serialized node |at most208bytes/node: f64 positions, source flags, source/render membership and offsets, visual/emphasis, CPU center/style and GPU coordinates/style/state |
| CPU/GPU serialized edge |at most336bytes/edge: endpoints and membership/offsets, source flags, visual/emphasis, CPU style/piece index/14-f64 geometry, GPU shaft coordinates/attributes/index/flags/style/state; no head/frame columns |
| fixed serialized output |131072bytes: section tables/names/alignment and fixed facts, at most200companion rows/candidates/ring entries; neutral persisted rows have no variable labels/derived IDs and at most96text bytes/row |
| builder/final copies |three times the complete serialized upper bound: growable section payloads (at most twice payload length) and exact final output; temporary numeric/paint encoding columns are in row work |
| state and output identities |the existing1024/item and128/text bounds on actual state are retained outside and inside the owner lock; actual prior outcome capacity and pending refs are separately charged; point/focused select admits one future source item; region/bulk/coordination/replacement use the general plan |
| cache and host |three times each actual opening/Open-reply/last-request/last-reply byte length; request128(A-D)+6D, actual external staging/output/foreign-owner capacity; unchanged |

For source ownership the unchanged48D bound covers old/new UUID vectors and maps,
edge identity tuples, source/style/label headers, parent/collapse planes, positions,
retained CoSE arrays and decoding copies. Eligible input alone contains at least
16n+53m bytes, giving768n+2544m bytes plus metadata. Maps use at most four buckets
per row including control bytes; source vectors and their speculative clones
remain below that allowance. State trees and serialized caches are additional.

The Rust tier code labels viewport edge omission EdgeSample even with no stride
sampling. Eligibility requires source counts within both budgets. Thus there is
no clustering and sample_edges keeps the whole eligible edge list. Complete
replay additionally joins every visible edge back to canonical endpoints and
requires all and only edges with two visible source nodes, with singleton edge
membership. There is no paint-count requirement for offscreen canonical nodes.

The independent exact OPEN/RENDER boundary tests calculate this recipe outside
the admission helper. Whole UPDATE tests independently retain both general
source/publication envelopes and actual old caches/state, reject one byte below
and at limits with either replacement/old source omitted, then accept exact and
replay cached bytes. The old3526208UPDATE regression is unchanged. The native
allocation ledger checks default16MiB progress and full-shaft authored geometry,
refusal/retry/update/disposal. Isolated actual WASM replay records its separate
linear-memory high water. These observations validate the bounded journeys; they
are not a proof of process/GPU/RSS or arbitrary16MiB graph admissibility.

The complete preceding RenderOutput is immutable Arc-owned as well: speculative
session clones share its rows and grid until a fresh candidate publication is
built. The actual preceding publication remains fully charged once; no deep
clone of its row vectors is hidden in the new-work reserve. Only the admitted
candidate installs the new Arc after serialization succeeds. The test-only
revision-exhaustion helper uses Arc::make_mut to construct its synthetic boundary.
