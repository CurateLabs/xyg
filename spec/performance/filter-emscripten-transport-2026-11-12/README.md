# Emscripten filter transport build correction

PR1122 at `53bc3215` failed hosted job 130864507861 in run 43121658534 while
building the exact Pyodide wheel. The main Rust/Python/JS job and Python 3.11
floor had passed. Emscripten could not compile the C ABI call to
`FilterTierCSession::execute_transport`: that method was incorrectly excluded
from every WASM-family target. The hosted failure remains a failed run.
An exact-source local `cargo check` reproduced E0599 before the correction.

The method now compiles for Emscripten too. Its existing raw XYFC and wrapped
XYFJ bodies, all signatures, ABI405/551 declarations, source availability,
resource limits, budgets and cancellation rules remain unchanged. This enables
the existing in-memory protocol through the C ABI; it does not enable issued
filesystem-backed XYGC sources in Pyodide. Direct-browser WASM38 remains
byte-identical after a fresh source build and packaging.

The exact-wheel Pyodide smoke now copies the frozen in-memory binary corpus
into its VFS and compares all 47 complete raw packets, including capacity/error
responses. A real 70,000-row source also exercises cooperative progress,
advance, stale-token rejection, cancel and subsequent use of the accepted
index. The report requires both the full corpus and a strict cooperative proof;
missing, shortened, false or nonboolean proof fails. Existing min/max, four
Scene/painter comparisons and all 17 unavailable-filesystem stub checks remain.

Fresh qualification includes the corrected Emscripten check, native release
build, an actual non-publishing cp314/Pyodide314 wheel build, and loading that
exact installed wheel in Node22/Pyodide with conformance network access disabled.
Its C ABI405 runs all 47 raw packets and cooperative controls successfully.
The first small native-body unit run used the prior native library and receives
only predecessor-behavior credit; after rebuilding, 17 focused tests pass on
each of actual Python3.11 and 3.12, including required browser callbacks.
All 23 Node filter/density tests and 673 native ABI checks pass.

The initial real Git CRLF checkout control caught missing LF pins for the two
newly hash-bound Python files. Explicit pins accompany this correction; that
failed run remains preserved. The full workflow-control module passes 699
cases with the required topology and strict guards unchanged. Final source
qualification and exact completed commands are recorded in `checks.json`.

The built wheel is
`xyg-0.0.1.dev2967+8e88dceb8-py3-none-pyemscripten_2026_0_wasm32.whl`, SHA256
`af240595c88a3165f8102d442fe708553cb69a4038660a88aa5fda8501c828e9`.
Its version records the reviewed parent; the uncommitted correction used for
this local non-publishing build is bound by the complete source-input manifest.
The Emscripten library SHA256 is
`ba0c8e19ed2fcc9feff65c4752ba6101f88a11b4969e1ccbd5d5060bfaa9722f`.
The new Linux native artifact is
`83014b03cc33ae8058097ba87e460f494c9ec9eb24fc1f74471b9341ecf66025`.

The fresh shipping module equals the module inside the tested wheel:
`d401219f7519006a5ddc222c9dd7b386d5b39fd1ff47d651764e02513cb28e5f`,
1,875,494 raw /785,931 Node22 gzip6 bytes, with 501 gzip bytes spare under
unchanged caps. Python's different zlib output is not used for that cap claim.
All browser client/Worker/inline artifacts remain parent-identical; only the
native library changes identity. No compiler/profile/feature change or
performance improvement is claimed.

The parent benchmark checkpoint `8e88dceb` received independent bounded
approval. Its completed review and source history are preserved here. Its
100M measurements remain historical producer evidence, including the explicit
failure to establish 50 FPS. The later private decoder experiment showed a
microbenchmark improvement but no accepted full-pipeline improvement and a
cached-paint regression; its production edit was discarded before this repair.

`checks.json` records exact commands/exits, source and artifact hashes, the
wheel archive, fresh/inherited boundaries and retained failures. Reproduce the
compile boundary with:

```bash
cargo check -p xyg-core --target wasm32-unknown-emscripten --offline
cargo build --release
uv run --no-sync pytest -q tests/test_pyodide_load_smoke.py tests/test_filter_tier_c.py tests/test_filter_native_callback.py
```

The actual wheel uses the unchanged CI command/environment in
`.github/workflows/ci.yml`, including cibuildwheel4.1.0, Pyodide314.0.0,
`RUSTFLAGS="-C panic=abort"` and the cached Emscripten SDK. The Pyodide runtime
is installed in a private directory, and `scripts/pyodide_load_smoke.py` runs
there with the exact wheel path and explicit Node22 PATH. No wheel is published.
New-head hosted CI, independent final correction review, current-main freshness
and merge-queue acceptance remain required. Whole issues and milestones4–7,
broader host/scale/resource/accessibility/performance and competitor gates
remain open.
