# Public 10k attachment admission candidate

This receipt concerns memory correctness and admission under the existing explicit
384 MiB arena per view. It makes no competitive performance claim. The required
1k/10k/100k/1M rendered ladder, Python notebook delivery, #35/#36/#1015 and M4
remain separate acceptance work. The hosted 100M hardware guard is unchanged.

The normative ownership derivation is in `spec/design/graph-interaction.md`,
“S4 review repair: admission and owner transitions”. Only document ingress is
removed from the event-reference expansion allowance. The full existing document,
expanded TextList labels, repeated derived IDs, arbitrary UTF-8 escaping,
compounds, layout, route, old/new publication, GPU and capped-grid envelopes
remain reserved before allocation. Open retains two serialized ingress caches;
Update retains its old caches while reserving the new one. Both use six times
the incoming document bytes (two existing three-times-cache allowances).
Non-document ingress keeps 128 times actual bytes. External arena capacity,
old output capacity and foreign owner retention remain additive.

`historical-refusals.json` is copied byte-for-byte from the reviewed producer's
`target/task-tmp/scheduling-after.json` in `/home/ubuntu/.t3/worktrees/xyg/t3-41a17c25`.
It preserves default-16-MiB 1k and explicit-384-MiB 10k initialization failures.
It is historical evidence, not a current-source result. The first two package
attempts also remain as failures: 1,927,246 raw bytes exceeded the unchanged
1,927,168-byte cap. A compiler hint produced no saving and was removed.

The native diagnostic uses an isolated integration-test executable with a
counting System allocator. It counts requested allocation sizes, including Vec
capacity, realloc changes and simultaneously live candidate/result allocations.
Its baseline excludes already-created document/request input storage; the caller
passes the input length as external staging. Logs report exact document/request
length, retained envelope, live requested bytes and peak, plus output length.
This is neither allocator-internal overhead nor RSS/VRAM/browser-process memory,
and the sample is not used as a general admission bound. The existing envelope
is the bound. A refused render must preserve its opening reply and sequence;
the same request then succeeds after restoring the arena.

The new browser harness copies the existing progressive **test fixture** with an
explicit 0.01 camera scale to include the initial 10k source graph. The qualified
scenario pairs that 10k primary with a 1k peer (the existing 0.25 camera),
each at explicit 384 MiB. It retains full convergence as a gate. It uses the
public attachment, shipping Worker, unchanged automatic continuation and renderer.
No response is held and no layout callback is installed. Host-button camera and
trusted pointer/keyboard actions execute while unfinished. Identity lookup uses
instance IDs even after reversing fixture storage order. The parent-owned smoke,
fixture and controller source are unchanged relative to the merged reviewed proof.

The replay tool compares SHA-256 of complete browser XYGR replies with fresh
native/WASM replies to the exact captured commands. WASM linear memory cannot
shrink, so its final byteLength includes intra-call growth throughout replay;
it excludes JS, browser processes and GPU storage. Browser CDP heap metrics are
supporting observations, not total memory. Screenshots capture canvas paint.

Reproduction (from the repository root; Node 22 and Rust 1.96):

```sh
export CARGO_BUILD_JOBS=2
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
cargo build -p xyg-core --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
cargo test -p xyg-engine --test graph_session_memory -- --nocapture
cargo test -p xyg-engine graphforge::interaction
node --test packages/xy-node/test/graph-session-wire.test.mjs
XYG_GRAPH_SESSION_REPORT=target/task-tmp/public10k.json node scripts/graph_session_public10k_smoke.mjs
node scripts/graph_session_public10k_replay.mjs target/task-tmp/public10k.json
UV_NO_SYNC=1 uv run --python 3.12.15 pytest -q tests/test_graph_session_python_transport.py tests/test_graph_session_abi.py
```

Final observed results and digest bindings are recorded alongside this receipt.
Cold means a fresh browser process; a repeat run warms filesystem/artifact caches
but also launches a fresh browser. Neither is a controlled cold-machine timing.

The separate two-10k diagnostic capture completed once and has a complete
native/WASM replay, but several repeats timed out near steps 380–457. Those
failures remain recorded and reliable concurrent two-10k completion is **not**
qualified. The qualified 10k+1k scenario is the requested actual 10k attachment
plus an isolated peer; it is not represented as two concurrent 10k qualification.
The parent-owned 1k proof and all existing gates remain unchanged.

The initial new recorder expanded 819,200 canvas bytes into JS arrays twice per
publication and retained over 400 MB of historical reply copies. Its final
version reads canvas bytes once per paint, uses those same bytes for counts and
hashes, and hashes historical complete XYGR replies asynchronously before
releasing diagnostic copies. It retains the current reply for pointer lookup.
No response delivery is delayed, no ACK is held, and no layout callback is used.
`cleanupMs` includes evidence digest settlement as well as disposal; it is not
an isolated product disposal-latency measurement. Raw payload totals are sums
of complete request/reply bytes, not peak residency.

Initial invocation of the new Node resource test before packaging failed with
ENOENT for the not-yet-produced WASM asset (`node-resource.log.gz`); final normal
wire tests run against the packaged artifact and pass. No failed historical
result is reclassified as a success.

Qualified cold/cache-warm results (fresh browser processes, SwiftShader):

| Primary 10k metric | Cold | Cache-warm |
|---|---:|---:|
| first paint including worker startup | 548.7 ms | 557.2 ms |
| first-to-settled publication | 18,273.7 ms | 18,308.4 ms |
| largest publication gap | 575.8 ms | 592.9 ms |
| largest host heartbeat gap | 539.0 ms | 536.9 ms |
| painted publications | 60 | 60 |
| final Rust steps | 458 | 458 |

Both runs preserve trusted unfinished exact node selection, camera translation
from 320 to 332 with later continuation continuity, empty peer selection and
unchanged peer camera, zero held replies/errors, and complete disposal. Every
primary publication replay retains **10,000 nodes and 10,000 edges**, with no
geometry aggregation/drop to admit it. These cadence observations are not an
interaction-latency target win. The complete decoded primary reply traffic is
217,871,136 / 217,871,280 bytes across the run, not resident/payload-per-frame
size. `results.json` reports both views and memory/payload scope is above.

The qualified full-sequence replay observes a 49,741,824-byte real WASM linear
peak; the bounded normal-CI test observes 42,401,792 bytes. The native requested
allocation ledger peaks at 39,103,392 bytes for Open/Render/10-step continuation,
versus a 382,843,208-byte retained admission envelope after the step. These are
separate scopes; no sum or browser-total-memory claim is made.

Final focused checks: 152 Rust interaction tests; the isolated allocation-ledger
regression; eight existing normal native/WASM wire module tests including the new
10k resource regression; 38 Python native transport/ABI tests; shipping client
build, native/WASM release builds, package size/version/hash verification; two
qualified public browser journeys and full native/WASM reply replays. All pass.
The shipping module is 1,927,066 raw / 786,154 Node-22 gzip6 bytes, leaving
102 / 278 bytes under unchanged 1,882 / 768 KiB caps. ABI, compiler/profile,
optimizer flags, routes, caps, tolerances and wall deadlines are unchanged.

The first warm attempt crashed before fixture startup with Chrome profile/cache
write failures in quota-limited tmpfs `/tmp`; its log is retained. The successful
repeat uses `TMPDIR=$PWD/target/task-tmp/tmp` on the disk-backed worktree. Nothing
was deleted from other workspaces. Reproduction should export that TMPDIR before
commands needing temporary storage. No gate or timeout was changed to recover.

`bindings.json` records source, generated artifact, raw receipt/log/screenshot
hashes, environment and exact commands. Candidate commit/diff identities are
reported in the local handoff after committing (avoiding a self-referential
commit hash in this receipt). Parent owns independent review, PR/CI/queue work.

Raw logs are retained byte-for-byte in deterministic gzip archives (`*.log.gz`);
use `gzip -dc` to inspect them. Artifact bindings include decompressed hashes.
