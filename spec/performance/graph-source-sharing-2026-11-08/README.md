# Immutable graph source ownership — incomplete larger-rung work

This candidate does **not** complete the requested public 100k/1M render and
scheduling rungs of #35/#36 or original milestones 4–7. It removes a concrete
source-copy cost from transactional GraphSession cloning. It does not replace
render acceptance with an engine checkpoint, alter fixtures/cameras, reduce
canonical populations, lower reservations, raise budgets, or change force,
LOD, pick, opacity or scheduling policy.

Identity maps, labels, hierarchy, parent validity, canonical edge endpoints,
edge ordinals and static source styles share immutable Arc allocations.
Positions, collapsed flags, force vectors and interaction state remain private.
The preceding publication and CSR retain their existing shared ownership.
The allocator ledger and pointer-identity regression run in existing normal
engine tests. OPEN candidate clones request 1,360 bytes for 1k unpositioned
nodes, 17,360 bytes with authored positions and 10,360 bytes for 10k nodes.
These measurements include requested Rust heap only, not allocator overhead,
RSS, WASM linear memory, page heap or GPU ownership.

The unchanged 48D source and publication-work admission envelopes still refuse
100k first render: retained 372,738,496 + work 377,420,296 + request/external =
757,098,696 estimated bytes versus the fixed 402,653,184-byte cap. Actual OPEN
requested-heap peak is 44,458,626 bytes. The 1M diagnostic refuses OPEN before
source materialization (1,088 requested bytes). Neither diagnostic establishes
render feasibility or impossibility. A complete per-class capacity and phase
proof, source/force/publication/serialization ownership changes as needed,
typed-load ingress certification, real useful paint, full native/WASM replies,
trusted pointer/Tab interaction, later progress, independent peers, camera
preservation, cancellation and disposal remain required for the larger rungs.

Fresh tests, failures, artifacts, environment, captures and source inputs are
bound in `current-bindings.json` and `run.json`; raw logs are append-only gzip
files beside this receipt. Local artifact/capture paths in the run are within
this isolated checkout's `target/task-tmp/graph-source-sharing`. Historical
Core receipts are referenced without rewriting them. No live GitHub read was
performed under the no-remote instruction; the existing local issue receipts
were read as historical context.

Reproduction (Rust and Node binaries must be on PATH; no network required after
cached dependency installation):

```sh
TMPDIR=/var/tmp cargo test --workspace
TMPDIR=/var/tmp cargo build --release
TMPDIR=/var/tmp cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
TMPDIR=/var/tmp node js/package-wasm.mjs
python3 scripts/verify_wasm_assets.py
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so python3 scripts/abi_smoke.py
cargo test -p xyg-engine --test graph_session_memory -- --nocapture
```

The initial workspace failure is a /tmp quota error. The controller-wide smoke
fails on an undefined legacy shared-WebGL-host registry. Public10k under
concurrent test load paints 44/42 frames, then both instances hit the unchanged
scheduler watchdog (345/321 steps). Those raw failures remain failures; default1k
success does not repair the 10k reliability observation. The first foundation
attempt lacks the Node koffi dependency; subsequent validation installs it
from the offline cache. Original remaining acceptance, all required hosts,
accessibility, performance/competitor evidence and issue closure remain open.
