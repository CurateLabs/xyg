# Bounded local chart snapshots, 2026-11-07

This is a committed implementation/proof candidate for part of #110. It does
not close #110, #109, #113 or milestones 4–7, and has no independent review or
delivery approval. No GitHub mutation or publication was performed.

The branch preserves original `74195403ccd18c760e3d20a18f024daab95d711a` and
normally merges accepted main `80e841542462eaf5509ac90e1f17a80cae974164` as
`0dae0d55`. Full hooks and both Ruff checks passed before the merge commit.
The two merge conflicts retained accepted-main review history and inventory
provenance. Accepted main already contains chunk-cache source SHA256
`2f14fee24e6bab44f7b82403c64ad391baf7b551188585814d05f8db51ab58cc`;
no separate dependency merge was needed. Old receipts and generators are retained.

`ChunkedColumns.chart` now composes stored overview or exact viewport snapshots
on Python/Node through the ordinary chart renderer. Rust owns complete canonical
admission, page selection, cancellation, physical identity and cache policy.
ABI 400 adds the native transport; declarations were generated, not hand edited.
See the [scope/resource contract](../../design/tier3-phase4-roadmap.md#bounded-local-chart-snapshots-110-continuation).

The 512-row fixture is only 9,432 bytes. Four Python headless rendered snapshots
match the full-scan oracle pixel-for-pixel with nonblank output. First viewport
reads 3,072 canonical bytes, pan reads only 1,024 additional bytes, deep zoom reads
zero. `report.json` records physical IDs, provenance, exact pixel hashes and
elapsed durations **including two renders**, not time-to-first-paint thresholds.
Python peak RSS excludes Chromium/GPU and includes the bounded full-scan oracle.
The HTML captures are losslessly gzip-compressed; PNG and oracle pairs are retained.
Node proves composition, canonical IDs, reuse, rejection and disposal; it has no
new rendered browser or WASM proof. No new competitor performance result is claimed.

Reproduction from this checkout (use the actual explicit tool paths recorded in
`environment.json`):

```bash
export CARGO_BUILD_JOBS=2
export PATH=/home/ubuntu/.cargo/bin:/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
cargo test --workspace
cargo clippy --all-targets -- -D warnings
cargo build --release
export XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so
npm ci --prefix packages/xy-node
node js/build.mjs
XYG_TEST_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome uv run pytest tests/test_chunked_columns.py -q
node --test packages/xy-node/test/chunked-columns.test.mjs
uv run python scripts/chunked_chart_evidence.py --output target/chunked-chart-reproduction --chromium /home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
uv run python scripts/gen_abi_manifest.py --check
uv run python scripts/verify_ownership.py
uv run python scripts/check_release_inventory.py
uv run ty check
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Project tests use Python 3.12.15; system Python is 3.14 (see environment manifest).
Raw logs retain the initial type-check failure (two undeclared metadata attributes)
and its corrected green result. Pillow emits four deprecation warnings in the
headless proof; these do not change pixel comparison or test outcomes. Client
build succeeds with its existing import.meta/IIFE warning. Inventory retains its
685 explicit preparation/classification gaps; these are not waived or closed.

Remaining acceptance includes automatic viewport gesture/channel publication,
stale reply handling across that bridge, real larger-than-RAM artifacts with total
RSS/GPU/WASM/latency/first-paint budgets, the full scale and competitor ladder,
direct browser/WASM and remote orchestration if supported, unordered spatial
localization, and the other #109/#113 workstreams. Caller-retained snapshots are
additional memory. Existing row-pick indices remain local to each snapshot;
applications map through the attached canonical source IDs. This is deliberately
not a claim of stable browser selection state across live frame replacement.


Final validation: `cargo test --workspace` passes 1,992 tests, zero failures;
Clippy passes with warnings denied. Focused tests pass 19 Rust, 11 Python and
7 Node tests, with zero failures/skips. ABI smoke, ABI generation check,
ownership (516 production files), inventory comparison and `ty check` pass.
`final/` contains a fresh proof after the final native rebuild and metadata
declarations; root captures retain the earlier run. `producer-inputs.json`
binds final source and generated client/native artifact bytes by SHA256.
The local native artifact stays at its recorded target path, not in Git.
No final native WASM module was built; browser/WASM functionality and shipping
size caps remain unqualified by this change, and no cap was changed.

Raw logs are losslessly gzip-compressed. An initial diff whitespace check rejected
trailing whitespace/EOF lines in raw tool logs; compression preserves those exact
bytes while allowing the canonical source diff whitespace check to pass.
