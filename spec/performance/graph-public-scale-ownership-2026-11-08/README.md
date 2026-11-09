# Public graph scale ownership and interaction rung

This candidate advances the real public 100k and 1M render/interaction rungs of
#35/#36, following the incomplete immutable-source checkpoint
`2f9e60d79c3fd76f4297de1e6ec25bb048c91b1d`. It preserves that commit and all prior
receipts. It does not merge Root's later GPU/navigation/dense candidates.
Full M4, other required hosts, accessibility, performance and competitor
acceptance, issue closure, independent review and integration remain open.

The browser default is 16 MiB; the explicit maximum is 384 MiB
(402,653,184 bytes). Native405/551 declarations and WASM38/68 exports remain
unchanged. The normal compiler/optimizer, features, package caps, LOD, force,
pick, scheduling intervals and watchdog are preserved. The existing generated
browser chunk preference is eight; the Rust API still admits ten on small
sources. Rust's separately versioned optional admission fact admits two at
1M nodes plus 1M edges under the unchanged four-million-work ceiling.

## Ownership proof

The normative [phase/class specification](../../design/graph-interaction.md#plain-retained-graph-phase-admission-default-arena)
describes the closed borrowed schema certificate, checked OPEN phase maxima,
source/index/force Arc owners, mutable integration planes, publication/CSR,
pick and paint scratch, packet arena, lossless retry cache and external output
loans. General and unsupported schemas retain their conservative envelope.
UPDATE still reserves whole old plus whole new and preserves the exact
3,526,207 refusal / 3,526,208 success and retry boundary.

The manual requested-allocation ledger exercises complete Wire execution, not
an isolated engine render. Inputs/fixture construction are outside its baseline;
their lengths are still charged as external staging. The second ledger also
owns and charges a full caller output buffer during the uncached force command.

| Neutral ring source | First render requested peak | Force command peak, Wire | Force command peak with caller output | Preflight including caller output |
| --- | ---: | ---: | ---: | ---: |
| 100k nodes + 100k edges | 87,557,574 | 156,981,018 | 192,592,682 | See raw ledger |
| 1M nodes + 1M edges | 266,629,384 | 372,154,060 | 396,758,012 | 400,020,004 |

Complete public interaction traces, including every uncached full caller output
loan, peak at **192,593,698** bytes for 100k and **397,232,796** for 1M.
Both traces release all session/caller owners after disposal; the isolated
default peer peaks at 8,761,546 requested bytes.

The one-million-source retained owner vector after first render is
`[98304,48777216,30000000,16000000,58000000,32799780,24055440,24723520,1024]`:
fixed metadata, canonical identity/index, source auxiliary planes, positions,
force, publication/CSR/paint/pick, packets, encoded replies and reducer/event
state. Its sum is 234,455,284. Each class is capacity charged. Native allocator
tests independently check source clones, state B-tree node widths and growth,
pick B-tree widths, converged default1k input, disposal and failure atomicity.
The three-step 1M command rejects six million work units before force cloning;
the visibility-validation allocation is separately measured in the raw ledger.

WASM linear memory, native requested heap, page heap, RSS and GPU storage are
distinct scopes. The full replay measures linear memory high water, including
allocator memory retained after frees; it is not a 384 MiB linear-memory or RSS
claim. The final 100k/1M WASM linear high waters are respectively
229,507,072 and 430,309,376 bytes. Page CDP metrics and shared GPU storage accounting are retained in the
public reports. Opaque driver memory and process RSS are not measured here.

## Public presentation and complete reply proof

Both primary views use the existing public fixture/harness and the normal
shipping module, with an independent 1k peer at the unchanged default. The
canonical input is an undirected persisted UUID ring with no labels, loops or
derived edges. No input is reduced. The disclosed public camera is
`[150/N,150/N,320,160,640,320,1]`, producing a roughly 300-pixel picture rather
than clipping the graph away or overlaying a tiny point. Source coordinates
come from the existing Rust progressive layout. The peer's first paint is
also useful; its later physical contraction is ordinary force convergence.

The runs record real Tab entry, trusted arrow/Enter input while unfinished,
trusted pointer selection, camera changes, every subsequent camera publication,
later Rust progress, independent peer state, cancellation/disposal and no late
presentation. They never hold, reorder or pace production replies, pause force
or extend watchdogs. One bounded latest-input mailbox admits input while a
force command is outstanding; it frames only after that reply publishes.
Bounded normal foundation tests cover replacement, stale/malformed facts,
trusted keys and disposal of queued intent. Pending temporal updates reject
queued input; further trusted key/pointer input sends no graph command and
retains its native default without producing a terminal busy failure.

Every captured command is reconstructed on fresh native and actual shipping
WASM sessions. Full XYGR lengths and SHA256 bytes must equal the browser reply,
including first uncached native calls with full output capacity, capacity
queries, short buffers and cached retries. The replay validates complete
canonical flags, unique CSR node memberships, exact canonical edge endpoint
joins, all and only LOD-retained edge membership, neutral opacity, literal UUIDs,
canonical indices and pick forms. At 1M, three-step work and stale commands must
fail without changing the preceding cached bytes. Closed/disposed handles are
rejected. This provides complete reconstruction independently of the browser.

100k uses Direct: all 100k nodes and edges are published. Picking explicitly
reports degradation under the unchanged primitive/grid limits; exact source
node picks retain reverse paint order. It does not promise all-edge picking.
1M naturally uses Aggregate: all one million source nodes belong to CSR groups;
only inter-cluster source edges remain in the rendered edge memberships. Picks
return aggregate membership with an empty source-ref plane, preserving the
existing zero placeholder rather than inventing a canonical source identity.
The reports retain actual group counts for every publication.

## Reproduction and evidence

`run.json` binds all sources, builds, artifacts, environment, raw logs and
captures, and distinguishes fresh checks from inherited evidence.
`current-bindings.json` is an append-only successor of the immutable-source and
original temporal-line bindings. Historical receipts are not rewritten.
Compressed evidence retains raw SHA256/length bindings; all text uses LF.
The optimized module is retained as a deterministic gzip artifact, separately
from the Node producer's gzip6 package-cap measurement.

Use Node22, the explicitly named Chromium, `TMPDIR=/var/tmp`, this checkout's
native library and `PYTHONPATH`; borrowed Python environments require
`uv --no-sync`. Normal producer commands are `cargo build --release`,
`cargo build -p xyg-wasm --release --target wasm32-unknown-unknown`,
`node js/build.mjs` and `node js/package-wasm.mjs`. Producer flags remain the
pinned wasmO2 / inline-threshold0 / stripnone followed by Binaryen132 O3 /
reorder-functions-by-name / stripdebug pipeline.

Run `scripts/graph_session_public_scale_smoke.mjs` with `XYG_GRAPH_SCALE=100000`
or `1000000`, `XYG_GRAPH_SESSION_REPORT`, and `XYG_CHROMIUM`. Replay its report
with `scripts/graph_session_public_scale_replay.mjs`. The manual allocator
sources and exact compile commands are retained beside the raw logs. Expensive
larger rungs remain manual/scheduled under #108; CI allocates neither 100M nor
1B sources. Normal foundation/Release surfaces carry bounded structural and
ownership regressions.

All raw failures remain evidence: initial 100k input starvation and watchdogs,
the run overlapping package optimization, fixture assertions corrected for an
authored button and trusted-key observation, replay typed-array/placeholder
oracle mistakes, the default1k global-envelope refusal, package-size trials,
and the first foundation invocation selecting the wrong default browser.
A later manual run exposed a harness array-tail assumption when Worker startup
order reversed. Primary lookup now uses its exact instance identity; no reply
ordering or transport pacing is imposed.
Passing reruns do not establish a general contention or watchdog reliability
repair. The historical 10k contention failure and broad registry failure also
remain in the predecessor receipt; the broad harness registry name is corrected
to the actual v2 owner. The previously labeled same-ABI fixture is ABI35 and now
asserts explicit incompatibility with ABI38; current-runtime missing/malformed
facts still fail closed. Full required-host acceptance remains open wherever it
was not actually executed.

Manual trace reproduction uses `python trace_inputs.py REPORT.json OUTPUT.trace`,
then `rustc --edition=2021 -O wire-trace.rs --extern xyg_engine=target/release/deps/libxyg_engine-c08e762ddb3a6e01.rlib -L dependency=target/release/deps -o /var/tmp/wire-trace`
and `/var/tmp/wire-trace OUTPUT.trace` from a fresh matching native build.
The rlib and diagnostic executable hashes are bound in `run.json`.
