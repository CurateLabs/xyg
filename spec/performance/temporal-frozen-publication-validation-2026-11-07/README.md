# Retained frozen-publication validation correction

Correction against independently reviewed native freeze checkpoint
`9479cff7fc4237b6b4ef158613e6bb5a18758714` addresses the retained publication
import finding. The original binary producer and all earlier receipts remain
unchanged. New immutable source/artifact/log bindings identify this correction.
No ABI signature, version402, cap, tolerance, rendering or export policy changes.

Rust now validates finite matching source-position planes, render endpoint
bounds, source/render membership correspondence, exact CSR offset shape,
nonempty sorted member slices, node inverse-map equality, unique represented
source edges and endpoint mapping, and visual/emphasis plane lengths before
retaining imported bytes. This rejects rechecksummed malformed publications,
rather than relying on the checksum or independent paint/GPU plane validation.
The helper accepts legitimate aggregate membership and parallel source edges;
it does not require one source entity per rendered mark or change LOD policy.

Independent-standard-library rechecksumming tests reproduce20 failures against
the historical native ABI402 library SHA256
`9b11f9c760085c1ab95226c3ef88aa9eadb8e7292fe26822393acd6d0cb4afd0`.
The original four review cases are included. The first setup used several
incorrectly shortened arrays and recorded18 failures plus2 already-rejected
inputs; the corrected exact-shape run records20 failures. Neither run is a pass.
`regression-producer.py.gz` preserves the exact Python source for that latter
run before formatting, with the historical library retained by the prior receipt.

Fresh correction checks pass17 Rust temporal tests,67 Python freeze/temporal/
session controls and4 Node freeze cases, including all20 rechecksummed imports
through both native hosts. Strict all-target workspace Clippy exposed the prior
checkpoint's frozen-publication helper after its test module; its unchanged
function definition is moved ahead of the tests. A transient dangling doc comment
during this move caused a second failed compile; it is corrected. Final strict
Clippy passes without lint suppression. Failure logs retain their actual status.

This is an acquisition/codec repair. Normal Scene lowering, embedded provenance
recovery and actual HTML/PNG/SVG exports, public WASM freeze attachment, and full
#45/M5/milestones4–7 acceptance remain open. New native/WASM/client builds are
required and bound to the final correction sources; no historical artifact is
relabeled as its producer. Final independent re-review and delivery remain pending.


After the placement-only correction, a fresh rebuild again passes the complete
native freeze module and current Core/LF/CRLF bindings (31 tests), official ABI
checker (544 symbols, ABI402), all673 ABI smoke controls and4 Node cases. The
existing session FFI controls pass. Shipping assets are rebuilt and verified
under the unchanged caps. No lint bypass or assertion relaxation is added.

Reproduce with Rust1.96, Node22, explicit `XYG_NATIVE_LIB`, project uv tooling,
and a short disk TMPDIR:

```bash
cargo test -p xyg-engine temporal_graph
cargo test -p xyg-core graphforge_session_ffi
cargo build -p xyg-core --release
uv run pytest tests/test_temporal_graph_frozen.py tests/test_temporal_graph_native.py tests/test_graph_session_python_transport.py -q
node --test packages/xy-node/test/temporal-graph-frozen.test.mjs
cargo clippy --workspace --all-targets -- -D warnings
npm run build:wasm
node js/build.mjs
uv run pytest tests/test_temporal_graph_frozen.py tests/test_graphforge_contract_corpus.py -q
uv run python scripts/gen_abi_manifest.py --check
uv run python scripts/abi_smoke.py
uv run python scripts/verify_wasm_assets.py
```

`checks.json` binds raw/archived logs, the regression producer snapshot,
current/historical source hashes, final Rust producer inputs and runtime artifacts.
The archived native library preserves the final artifact for read-only review.
The original checkpoint and its old failed-import acceptance remain historically
inspectable. Rendered frozen-format qualification remains subsequent work.
