# Frozen source/camera and CPU paint consistency

Additive correction against `360526be4e303b8615f6d5e22c4001b8db0e6b07`.
The original review topology/finite-position correction remains preserved. A
further independent probe found that changing a finite retained source y from0
to1 was accepted although camera [1,1,60,60,240,180,1] projected it to61 while
retained paint stayed60. Rechecksumming is not sufficient cross-plane validation.

The Rust live painter and frozen importer now share `Camera::project`. Each
retained CPU paint-node center must bitwise equal its source render position
under the captured camera. The canonical multiply/add order is preserved;
DPR remains backing-resolution metadata and does not scale CSS coordinates.
No host projection, tolerance, ABI version402, signature or cap changes.

Against the previous native artifact, four newly added finite-position/camera
mutants fail their expected-refusal assertions while all20 prior malformed
publication cases remain rejected. The positive DPR-only mutation retains its
bytes. Historical receipts and the old native artifact are immutable. This
check remains part of acquisition/codec validation; it does not establish actual
frozen HTML/PNG/SVG output, a normal Scene lowering or public WASM freeze.


Fresh validation passes17 temporal/frozen and152 interaction Rust tests,79
Python freeze/temporal/session/Core tests,12 Node freeze/native-WASM wire cases,
strict workspace/all-target Clippy and all673 ABI checks. Generated declarations
remain544 symbols atABI402. The complete browser foundation passes16 camera
controls, two bounded scheduling cases and all14 retained temporal cases against
the freshly rebuilt shipping module. No whole-suite or scale claim is made.

Native artifact SHA256 is
`2319014d30fca29856cee73c773744de7474c62c95b9308f1caec851350525cf`.
WASM SHA256 is
`4fc0a9a6960b22d741ac2b1fee6c62277283ce1ea1da850acd18a7df7c6da94f`:
1,927,003raw /786,268Node22gzip6 bytes under unchanged1882/768-KiB limits.
The client index remains byte-identical to the prior producer. The old native
proof and current tests are distinct producers, bound explicitly inchecks.json.

Reproduction with Node22/Rust1.96, explicitselectednative and Chromium:

```bash
cargo test -p xyg-engine temporal_graph
cargo test -p xyg-engine graphforge::interaction
cargo build -p xyg-core --release
npm run build:wasm
node js/build.mjs
uv run pytest tests/test_temporal_graph_frozen.py tests/test_temporal_graph_native.py tests/test_graph_session_python_transport.py tests/test_graphforge_contract_corpus.py -q
node --test packages/xy-node/test/temporal-graph-frozen.test.mjs packages/xy-node/test/graph-session-wire.test.mjs
cargo clippy --workspace --all-targets -- -D warnings
uv run python scripts/abi_smoke.py
uv run python scripts/gen_abi_manifest.py --check
uv run python scripts/verify_wasm_assets.py
node scripts/wasm_foundation_smoke.mjs
```

The current binding advances both correction histories without modifying their
bytes. Final independent review must cover the topology and camera repairs
against the originally reviewed checkpoint. The shared projector introduces no
alternative layout, style resolution or renderer. Public full-format export and
WASM snapshot attachment remain subsequent implementation requirements.


The normative budget wording now distinguishes the384MiB per-operation admission
envelope from whole-process memory. Caller-owned snapshots accumulate across
operations, and the256-handle cap does not enforce a global byte budget. Full
CPU/source/WASM accounting remains #111 work; no new global-memory proof or waiver
is claimed by this codec correction.
