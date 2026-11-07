# Native viewport refinement candidate — 2026-11-07

Base: ae58f6d8b0fbaff73885b442ed4b926e22dc682a. Candidate for independent
parent review; no shipping, #110 closure or milestones 4–7 completion claim.

The public Python `ChunkedColumns.chart().widget()` and Node
`ChunkedColumns.chart().liveHost(send)` feed the existing browser `render` model.
Real Chromium wheel gestures leave the 2,048-point overview unchanged when
viewport dispatch is disabled, then cause native detail reads when enabled.
Both hosts return IDs equal to an independent full-scan predicate over the exact
browser ranges; replacement retains those ranges. Real keyboard exploration
reaches host pick callbacks with exact source IDs and f64 coordinates. PNGs are
captures, not pixel-oracle qualification. Python's small native regression also
covers latest intent, independent chart handles, source caller closure, selection
IDs, warm cache zero reads, budget/truncated detail failure retention, close while
queued, and reentrant transport close. Node's regression covers asynchronous Koffi,
exact picks and range selection, stale pick refusal, warm reuse and drain-before-free.

The browser harness implements the actual anywidget model contract; it does not
start Jupyter or VS Code. Its local test carrier uses base64 solely to cross the
Playwright/stdio evidence seam. Product payloads remain binary. All artifact rows
are physically written: 8,192 paired rows = 131,072 canonical bytes, plus metadata
and bounded overview. This is far below the machine's physical RAM. No larger-than-
RAM, RSS ceiling, latency target or cross-library performance win is claimed.

`bindings.json` binds source files, fresh native and generated paint artifacts,
Python/Node/toolchain, captures and raw fixture/report files. Native core was built
in this checkout with `cargo build --release -p xyg-core`; no Rust signatures or
policy changed. No combined WASM artifact was installed or qualified. All existing
caps, features, guards and compiler flags remain unchanged.

Reproduce from this checkout (Node points to Node 22; Chrome is the explicit
Chromium executable listed in bindings):

```bash
export TMPDIR=/var/tmp
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:/home/ubuntu/.cargo/bin:$PATH
export PYTHONPATH=$PWD/python:$PWD/tests
export XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so
export XYG_NODE=$(command -v node)
export XYG_TEST_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
uv sync --group dev
npm ci
npm ci --prefix packages/xy-node
cargo build --release -p xyg-core
node js/build.mjs
uv run pytest tests/test_chunked_live.py -q
node --test packages/xy-node/test/chunked-live.test.mjs
uv run pytest tests/test_channel.py tests/test_widget.py tests/test_public_api.py tests/test_release_inventory.py tests/test_chunked_columns.py -q
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Final focused proof: 4 Python lifecycle/browser cases passed (including Python
and Node real-browser variants); Node native lifecycle case passed. Related
Python regressions: 96 passed, one optional browser snapshot case skipped in that
run without browser configuration. Full pytest was not run (multi-hour browser
suite). Normal test collection discovers these tests; no additional CI gate was
introduced. The browser case honors `XY_REQUIRE_BROWSER=1` and the existing
`XYG_TEST_CHROMIUM` convention.

Development failures are retained in `logs/`: the first source-ID insertion was
in the wrong projection helper; a page-cap cache expectation was wrong; the initial
Python environment lacked Playwright; `crypto.randomUUID` was unavailable in the
harness context; one run started before native linking finished; Python Playwright
1.61.1 does not exist (1.61.0 is locked instead); a test-only Node stdio bridge
initially kept stdin open and its run was interrupted; a keyboard locator matched
three canvases; event-based pick qualification timed out and was replaced with
actual host callback receipts; an attempted callback mutation encountered the
frozen callbacks dataclass; and the initial larger fixture exceeded XYGC's 2,048
stored-overview cap. No timeout or product budget was increased. The final fixture
has a valid 2,048-point overview. Read-only inspection failures and tool syntax
errors caused no mutations.

Remaining acceptance is normative in
[the viewport contract](../../design/chunked-native-viewport.md): installed
notebooks/VS Code, adversarial cross-loop/remount/rebind and stale/partial matrices,
full pixel oracles, complete process/GPU accounting, source IDs beyond 2^53 in
large-backed causal fixtures, remote/direct-browser WASM, and larger-than-RAM
resource/latency/fetch/export/cross-host comparisons. Parent independent review
must resolve findings before this candidate is delivered onward.

A final diagnostic assertion incorrectly required every accepted gesture frame to
perform physical I/O. Coalesced/superseded reads can warm the native cache before
the accepted generation runs. Final proof checks actual Rust candidate metadata
and exact full-scan rows, and records its actual physical read counters, including
zero; it does not infer physical reads from row count. No cold-fetch latency or
complete cancelled-work accounting is established by this candidate.

The final browser run also exposed a retained hover target referencing a retired
GPU trace during replacement (`null._fcId`). Replacement now clears that target
before deleting its buffers and invalidates the pick sequence. The browser
regression performs another wheel replacement after an actual keyboard pick and
requires no page errors.
