# Installed supported-consumer qualification: bounded #886 slice

Passed locally on 2026-10-24 against parent product commit
`d611d7e98faf6ef6fa68634b18980f358ddc4542`. The wheel/native/client artifacts
were built from that product state; this change adds qualification fixtures,
browser assertions and specification/evidence only. Exact harness hashes are
in `consumer-apps-smoke.json` under `qualification_source_sha256`, alongside
the parent commit and installed wheel/npm archive hashes. No product paths,
comparison/spill harnesses, graph features or workflows changed.

The live amended [#886](https://github.com/CurateLabs/xyg/issues/886) body is
retained in `issue-886.json`. Support follows
[#1063](https://github.com/CurateLabs/xyg/issues/1063), with tick semantics from
[#869](https://github.com/CurateLabs/xyg/issues/869) and
[`application-consumers.md`](../../design/application-consumers.md).

## Proof and output contract

`consumer-apps-smoke.json` is the complete schema-1 installed gate receipt.
`packaged-consumers.json` holds its nine added browser cases:

- Installed Python hosted public HTML and installed Node/vanilla TypeScript:
  secondary Cartesian `x/y/y2` Rust caches and degree-polar angular/radial
  `x/y` caches, nonempty Rust-formatted labels and colored plot pixels.
- Both hosts: HTTP-404 tick module rejection, and HTTP-200 four-byte module
  rejection by real `WebAssembly.compile`. The latter's SHA-256 is
  `054edec1d0211f624fed0cbca9d4f9400b0e491c43742af2c5b0abebf0c990d8`.
  These failures preserve chart paint but paint no synthetic ticks, expose
  `XYG_WASM_INIT_FAILED` and terminate the failed Worker. HTTP error bodies
  are deliberately not read after Worker termination; status is retained.
- One actual Node native split-density payload on the public kernel-less
  `ChartView` boundary: native `XYG_WASM_SOURCE_UNSUPPORTED` reason/trace IDs,
  ordinary live viewport scheduling, exact original grid/texture identity,
  zero replacement uploads or density attachment, one tick Worker only,
  colored distinct zoom pixels and exact home ranges. Observed maximum zoom
  channel delta was 255; restored home delta was 0 (allowed maximum 1).
- Every added case: explicit paired assets under CSP, allowlisted same-origin
  requests, zero CSP violations/page errors, released GL/context/texture,
  listener/frame cleanup, terminated Workers, zero object URLs and late events.

`density-export.json` retains the two existing installed public Python
file-export optional-inline-module cases. Their unavailable/failed-refinement
contract preserves the overview and is separate from tick admission failure.
The complete gate also passed the existing real Node/Streamlit application
journeys and all six mandatory installed Streamlit AppTests (zero skips).
The focused `test_wasm_tick_host_assets.py` run passed all ten tests.

Runtime: Chromium `156.0.8078.4` (explicit repository binary), Node `v24.21.0`,
Python `3.12.15`, Streamlit `1.66.1`, Koffi `3.1.4`. SwiftShader launch arguments
are retained in the JSON. The wheel and npm consumer imports resolve inside
fresh installs, with native/Python/Node development overrides removed. The
Python HTTP and Streamlit hosts run without Node on PATH; Node hosts run
without Python. Installation may fetch locked dependencies; browser requests
remain local and allowlisted.

`consumer-run-final.txt` is raw successful stdout/stderr, ending in the same
JSON as the complete report. Host logs, installed AppTest JUnit/stdout,
screenshots and compressed raw Node spec/buffer planes are retained here.
`SHA256SUMS` covers these evidence files. Generated browser bundles, wheel/npm
archives and HTML documents are not committed. The exact wheel remains at
`target/consumer-wheels/xyg-0.0.1.dev2885+d611d7e9-py3-none-linux_x86_64.whl`;
compressed generated public HTML and sidecars remain under the ignored
`consumer-apps-smoke/` output. Their hashes are in the report. The gate's
temporary clean environments/npm archives are removed after completion.

## Reproduction

After repository native/client/WASM setup, the exact proof command was:

```bash
mkdir -p target/task-tmp
TMPDIR=$PWD/target/task-tmp uv run python scripts/consumer_apps_smoke.py \
  --wheel target/consumer-wheels/xyg-0.0.1.dev2885+d611d7e9-py3-none-linux_x86_64.whl \
  --chromium /home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
```

Omit `--wheel` to build a fresh candidate rather than reuse the recorded wheel.
The runner finds Cargo under `~/.cargo/bin` when needed. The setup used:

```bash
TMPDIR=$PWD/target/task-tmp uv sync --group dev
TMPDIR=$PWD/target/task-tmp npm ci
PATH=$HOME/.cargo/bin:$PATH TMPDIR=$PWD/target/task-tmp cargo build --release
PATH=$HOME/.cargo/bin:$PATH TMPDIR=$PWD/target/task-tmp \
  cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
TMPDIR=$PWD/target/task-tmp node js/build.mjs
TMPDIR=$PWD/target/task-tmp node js/package-wasm.mjs
PATH=$HOME/.cargo/bin:$PATH TMPDIR=$PWD/target/task-tmp XYG_REQUIRE_WASM=1 \
  uv build --wheel --out-dir target/consumer-wheels
TMPDIR=$PWD/target/task-tmp uv run pytest tests/test_wasm_tick_host_assets.py -q
TMPDIR=$PWD/target/task-tmp uv run --with pre-commit pre-commit run --all-files
TMPDIR=$PWD/target/task-tmp uv run ruff check .
TMPDIR=$PWD/target/task-tmp uv run ruff format --check .
```

## Scope remaining

This is a bounded correctness slice, with no blocker to its local proof. It
does not establish every unsupported density source family or the entire
secondary/polar/family/provenance configuration space. The Node split fixture
uses the public `ChartView` boundary; it does not claim the packed vanilla app
implements a split transport. Streamlit remains a snapshot iframe without
Python callback/streaming or automatic Worker discovery. Missing/corrupt
inline-density behavior is reused once rather than repeated on every host.

Final-candidate artifact cohort reuse, independent final-diff review and the
remaining #108/#886 acceptance disposition belong to the parent/release work.
No large benchmark, hosted dispatch, publication, GitHub mutation, PR, push,
issue closure, #54 qualification or release acceptance was performed or claimed.
