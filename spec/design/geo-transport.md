# Retained geographic WASM transport

Retained source, tile and snapshot commands require an explicit
`xyg_wasm_geo_transport_acquire(instance)` handshake before a browser adapter
copies authoring buffers or accepts ownership of its geographic FIFO. Legacy
geographic catalog and ordinary Scene workers use separate instances.

The private, noncloneable Rust `GeoTransportLease` reserves exactly 160 MiB in
the shared 384 MiB tile/derived ledger, including its 1 MiB cache metadata. This
credit covers the host FIFO and synchronous framing temporaries together (32 MiB), and one complete 128 MiB WASM phase. Source construction reserves three manifest lengths plus 8,192 bytes before copying; it drops the manifest and releases that credit synchronously before handing the framed request into the FIFO. Failed construction releases the temporary reservation. An admitted Worker queues requests synchronously, so concurrent factories cannot hide private manifest copies outside the shared credit.
Together with the separately enforced shared 128 MiB source/processor ledger,
the retained product path admits at most 512 MiB across these domains. Existing
SceneData reservations conservatively account their retained copies as well.
Different owners compete for the same process/instance ledger; a third 160 MiB
transport cannot coexist with two existing transports. Failure releases its
candidate metadata reservation. Disposal releases the credit after the
instance's arena, output and active jobs have been dropped; adapters must first
settle the FIFO and release their CPU copies.

Acquisition requires settled asynchronous WASM jobs. It drops prior arena,
output and temporal caches before reserving credit. The instance's effective
arena budget then stays at most 128 MiB, while its original declaration remains
charged to the separate WASM instance registry. Smaller declarations retain
their smaller effective budget. Acquisition is idempotent. Raw retained exports
also acquire as a compatibility fallback, but callers relying on that fallback
cannot claim admission before they allocate host request buffers.

The opaque `GeoTransportPhase` borrows the persistent owner and holds an
exclusive phase mutex. Its budget cannot exceed 128 MiB. Trusted frame painter
preparation accepts an immutable SceneData handle and exact publication sequence;
Rust verifies its generated point/density profile and admits
`32 * SceneBytes + 1 MiB` before decoding or lowering through the shared Scene
painter. It neither consumes a SceneData ownership read nor accepts arbitrary
host Scene bytes. The result includes the actual record/style counts.

Every ordinary product lane rejects retained-mode instances before execution,
including Scene decode/compile, temporal/temporal graph, graph, GraphForge,
aggregate, compound, dashboard, ticks and legacy geographic ingress. Read-only
diagnostics, palette, arena staging and cancel/dispose remain available. This prevents an arbitrary authored Scene decode from
escaping the admitted phase. Ordinary legacy workers retain their existing
behavior; mixing their arbitrary Scene ingress into a retained instance is
unsupported. Retained exported reads subtract the previously accepted output
capacity and staged request bytes from the phase budget and preserve that output
on failure.

`cargo test -p xyg-wasm --test geo_transport_budget` proves real shared credit,
failed acquisition cleanup, idempotence, effective caps, rejected raw Scene
input, disposal and recovery in an exclusive process.
`cargo test -p xyg-wasm --test geo_scale_budget` separately proves the declared
384 MiB instance ceiling and immutable two-transfer read semantics.

The512 MiB contract accounts admitted live retained CPU storage across the Rust
engine and owning Worker module. It excludes OS RSS, WASM linear-memory pages
retained by the allocator, GPU storage, DOM and caller-owned canonical app data.
It is not a512 MiB process-RSS promise. Ordinary chart workers are separate and
keep their existing policy.
