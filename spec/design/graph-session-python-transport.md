# Private Python native graph-session transport

Status: **P0 internal S6 foundation for #1015 / #36 only**. This does not
establish acceptance for #108, M4, a public Python session wrapper, notebooks,
or the browser painter. The authoritative protocol remains
[graph-interaction.md §3](graph-interaction.md#3-abi--wasm); native ABI
398 and its generated declarations are unchanged.

## Boundary and ownership

`python/xyg/_graph_session.py` provides `GraphSession` only by explicit import
from this private module. `xyg` does not export it. Construction forwards an
XYGF document, a complete XYGI Open request, and the caller's unsigned-u64
instance/group scalars to the already registered
`_native._lib.xyg_graphforge_session_create`. Python neither allocates nor
infers graph identity. Rust validates the document, opening request, matching
identities, admission, layout, selection, geometry, revisions and operation
sequence. `_native` retains its existing required-library and ABI checks;
there is no Python or NumPy algorithm fallback.

The wrapper's methods map directly to registered generated ABI functions:

| Private method | Existing native export |
| --- | --- |
| constructor | `xyg_graphforge_session_create` |
| `update(request)` | `xyg_graphforge_session_update` |
| `render(request)` | `xyg_graphforge_session_render` |
| `interact(request)` | `xyg_graphforge_session_interact` |
| `poll_event(request)` | `xyg_graphforge_session_poll_event` |
| `bind_temporal(request)` | `xyg_graphforge_session_bind_temporal` |
| `unbind_temporal(request)` | `xyg_graphforge_session_bind_temporal` |
| `coordinate_deliver(request)` | `xyg_graphforge_coordinate_deliver` |
| `close()` / context exit | `xyg_graphforge_session_destroy` |

Unbind takes the caller's complete Bind request containing `temporal.u64[0]`.
It is an opaque forwarding convenience: Python does not inspect or enforce
the operation or temporal section. The caller supplies all requests, stamps
and sequences. Every successful command returns the complete native XYGR as
immutable `bytes`. No production encoder, parser, selection dictionary,
provenance heuristic, trace-index inference, renderer, or alternate
`layout_render` path is added. Importing the module does not import widgets,
channel attachment, graph-layout scheduling or keyboard controllers. It uses
the existing `_native` module, which itself imports NumPy; this is not a
dependency-free native loader claim.

## Host buffer contract and exact retries

Inputs accept `bytes`, `bytearray`, or a live, one-dimensional,
C-contiguous, one-byte-item `memoryview`. Non-byte typed views,
multidimensional/strided/released views and non-buffer values fail before
FFI. Buffer lengths must fit both Python's host allocation index and C
`size_t`. Instance/group scalars must support integer indexing, exclude
booleans, and fit unsigned u64 without truncation. Zero identities, empty
buffers, wire schema and all Rust product limits remain Rust validation.
Type/bounds exceptions have fixed, value-free messages.

Constructor identity normalization and document/opening snapshots run before
acquiring the lifecycle lock. Integer-indexing scalars can execute caller code
in `__index__`; supported buffer subclasses can likewise execute Python buffer
callbacks. Neither callback may run under the non-reentrant lifecycle lock.
Commands first check local closure under the lock, release it to snapshot the
request, then reacquire it and recheck the handle before any FFI. Thus initially
closed wrappers still refuse before input conversion, and a callback or another
thread closing the wrapper during conversion cannot leave a usable stale
handle. Native alias revocation continues to be validated by Rust as Unbound.

Each input is snapshotted once into a private ctypes u8 allocation. A command
holds that same allocation, byte length, native handle and request bytes
throughout its query and copy retries. Python never consumes, increments or
rewrites `op_seq`, even after refusal. The first call uses null output and
capacity zero. On native Capacity (-5) with a strictly larger required length,
the wrapper allocates exactly that length and calls the same export again.
Further growing Capacity results follow the same rule; a non-growing
Capacity is surfaced rather than looping. This accommodates native poll's
non-consuming sizing calls without imposing a guessed output ceiling or
host-side protocol state. A length beyond host allocation bounds fails
locally; successful output lengths must fit the allocated capacity.

Rust alone retains complete replies and decides byte-identical replay,
failed-command atomicity, poll consumption and stale/bound-owner behavior.
A host allocation failure after a successful native sizing call can leave
the operation applied; callers may retry the identical bytes. Python does
not roll back or recompile. The wrapper makes one input snapshot and copies
the complete native output into immutable Python bytes; it is not zero-copy.
The ctypes output allocation and returned bytes coexist during that copy.
It retains no graph buffers or result cache after return (dossier §27/§29).

## Serialized lifecycle and failures

One module-level lock serializes native handle creation, complete
query/copy transactions and close calls, including calls on different Python
wrappers. This intentionally conservative P0 boundary prevents a close or
another operation from intervening between sizing and exact copying. It
also covers byte-identical Open retries, which Rust may resolve to the same
native handle. No identity or graph-state registry is maintained in Python.
Independent native handles retain independent graph state and lifetimes;
this foundation makes no concurrent throughput claim. Direct raw-ABI or
other-language callers are outside the Python lock; native locking and
validation remain authoritative.

Native Open retry semantics are preserved: wrappers opened with identical
active-instance bytes alias the same native lifetime. Closing either revokes
that handle; the other observes native Unbound (-10). A conflicting Open is
rejected by Rust. This is not Python reference-counted shared ownership.
Use explicit `close()` or a context manager; no finalizer or background work
is installed. Close waits for an in-progress transaction. Successful destroy
or already-Unbound destroy marks the local wrapper closed. Repeated close
is a no-op. Every subsequent command/context entry fails consistently with
`GraphSessionError("graph session is closed")`, `status=None`, before buffer
validation or native access. Other destroy failures remain observable and
leave the wrapper available for an explicit close retry.

`GraphSessionStatus` names the existing codes 0 through -11; it adds no
protocol status. Native refusals raise the private `GraphSessionError` with
the unchanged numeric `.status` and the fixed message
`native graph session request failed`. Messages contain no request bytes,
labels, identities, stamps, coordinates or derived values. Local lifecycle
and impossible-output failures also use this private error with
`status=None`; invalid input types/bounds use `TypeError`/`ValueError`.
No XYGR status parser or error reply synthesis exists in Python. A bound
owner disposed in Rust remains observable as -10, including on replay; a
caller-authored unbind request can recover as the native contract permits.

## Proof and explicit remaining work

`tests/test_graph_session_python_transport.py` exercises the actual native
398 library: create/render/update; retained complete bytes across
query/short/exact/replay; mutable-input snapshot identity; poll delivery;
stale, wrong-instance/group, malformed and conflicting replay refusals;
unchanged sequence/cache after refusal; independent lifetimes; native Open
aliasing; bound-owner disposal and unbind recovery; deterministic threaded
close ordering; repeated close; input boundaries and private import isolation.
Bounded subprocess regressions also exercise indexable constructor scalars and
supported buffer callbacks that close/open/render other native sessions, plus
closure during command conversion. Timeout kills and reaps a regressed child,
so a deadlock cannot strand a thread holding the parent test process's lock.
The existing raw ctypes proof remains in `tests/test_graph_session_abi.py`.
The original append-only local receipt is
[graph-python-session-transport-2026-11-03](../performance/graph-python-session-transport-2026-11-03/README.md).
The independent-review reentrancy repair has a separate append-only
[repair receipt](../performance/graph-python-session-transport-reentrancy-repair-2026-11-03/README.md).

P1 design is still needed for full selection/per-layer identity projection
missing from XYGR and the fast-seed seam. P2+ still owns widgets, channel and
session attachment, scheduling, keyboard control and public notebook
integration. S5 GPU wire/painter/browser work belongs to the parent. This
foundation does not prove performance leadership, chart breadth, complete
selection projection, or publication readiness; it changes no capability or
competitor acceptance claim, ABI/WASM/source policy, package gate, workflow,
dependency, generated API inventory, or public API.
