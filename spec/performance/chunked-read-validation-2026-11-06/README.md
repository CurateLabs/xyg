# XYGC fetched-detail validation and stale-empty cancellation (#110)

Candidate based on accepted main `c3152d97bdb3a1efd61686b21d84385ee0f8de9e`,
merged normally as `12706a9d` (identical tree). Branch
`t3/m7-spill-chunked-filter`. This is a bounded implementation candidate,
not acceptance of #110, #11/#5, #109 or the M7 milestone. Independent review
and parent delivery remain required.

## Finding and behavior

The existing local ordered XYGC reader admitted structurally valid metadata
but trusted fetched detail bytes. Finite out-of-map values, changed extrema,
and an interior x-order violation could silently publish altered rows.
Both paged and nonpaged reads now validate each fetched slab against its
admitted finite extrema and ordering before publishing. Existing corrupt-artifact
error code 2 passes through the unchanged Python/Node ABI. Validation takes
constant scratch space and a linear pass over fetched bytes, with no extra I/O.
The nonpaged reader also checks generation before publishing, including an empty
or fully y-pruned result. Whole-call/page errors discard gathered rows.

This is structural validation, not authentication: same-length edits preserving
extrema/order, skipped chunks and overview/detail consistency are not checked.
Sources must be immutable while open; mutation in tests injects failures and
does not promise concurrent-writer support. No ABI signatures, file versions,
resource budgets, numerical tolerances, tier policy or hardware guards changed.

## Focused evidence and commands

`before.log.gz` retains the actual pre-fix Rust run: 11 passed and the two new
regressions failed. `after.log.gz` retains all 13 passing chunked-column tests.
Host tests exercise already-open file mutation and stale empty queries; existing
full-scan, overview, nonfinite and pull-backpressure oracles remain active.
All sources/artifacts, environment and raw-log hashes are in `manifest.json`.

```bash
cargo test -p xyg-engine chunked_columns -- --test-threads=1
cargo build --release
uv run pytest tests/test_chunked_columns.py -q
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so node --test packages/xy-node/test/chunked-columns.test.mjs
node js/build.mjs
uv run pytest tests/test_graphforge_contract_corpus.py -k 'survives_windows_checkout or compatibility_declaration or ci_rebuilds' -q
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

No timing/scale win, hardware renderer, browser journey, or larger-than-RAM
claim follows from these fixtures. The generated native/client files are ignored
and not committed. Historical producer receipts and current Graphforge binding
bytes are unchanged; its focused CRLF/source-binding checks pass.
Optional workspace `cargo fmt --all --check` exposes existing formatting drift
outside this slice; the full failed output is retained. File-scoped rustfmt of
the changed Rust module passes; unrelated source formatting was preserved.

## First remaining exit and next contract

Read-only live issue/dependency inspection confirms #10 and the native #8/#9
foundations are closed; #11 blocks #5. Existing main receipts already prove
bounded negatives, host parity, 100M memmap/kernel latency, software-browser
pixels and hosted comparison structure. They must not be rerun as new proof.
The first spill exit still needs accepted-main accelerated 100M owned-allocation
and normal-RAF evidence under the unchanged hardware guard. Retained run
40639793475 failed renderer admission before allocation; software runs cannot
satisfy it. This environment supplies no accepted hardware execution and no
workflow dispatch was performed (parent owns external mutations).

Reuse `.github/workflows/ceiling-benchmark.yml` with the existing
`colored-browser-hardware` manual mode and retain its successful raw
receipt when real matching hardware is available; keep normalized competitive
and remaining headline requirements explicit. For #110 the next independent
contract is bounded canonical chunk reuse with stable source/view provenance
and generation-safe eviction; remote/range formats, WASM-compatible orchestration
and an actual larger-than-RAM first-paint/navigation journey remain unproven.
#111 shared-context budgets, #112 indexed linked views and #113 integrated
acceptance remain open. No issue or milestone closure is claimed.
