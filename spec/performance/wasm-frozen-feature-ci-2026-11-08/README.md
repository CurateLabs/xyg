# Shared frozen-PNG feature guard repair

Bounded CI/publication correction at reviewed parent
`f1c074a974aac13a8d2a35f8a046a7111f2dcfa9`. No runtime source, ABI, optimizer,
package cap, renderer, source budget or scheduling policy changes. Independent
review of this correction and fresh hosted CI/queue acceptance remain pending.
All issue and milestones 4–7 acceptance limits remain open.

## Reproduced hosted failure

PR1116's `Packaged WASM assets (single producer)` job
[128603863688](https://github.com/CurateLabs/xyg/actions/runs/42438961171/job/128603863688)
compiled the browser adapter, then failed before packaging with
`direct-browser xyg-wasm unexpectedly enables native PNG`. Dependent test jobs
were skipped and receive no pass credit. The old gate rejected any PNG package.
It predates the implemented, documented shared `frozen-raster` capability.
The existing browser contract explicitly disables full engine `raster` while
retaining shared Rust PNG; it does not require PNG's absence.

Both `ci.yml` and `publish.yaml` now retain the resolved normal dependency graph
with exact Cargo package/feature facts and `--color never`.
`scripts/check_wasm_features.py` requires local workspace adapter/engine sources,
the engine's exact `frozen-raster` feature set and pinned vendored PNG0.18.1
without extra features. It rejects full native `raster`/`default`, unexpected
engine/adapter features, `xyg-core`, missing/duplicate/unbound packages and
malformed evidence. PNG's own compression dependencies are allowed. This is a
resolved feature-policy check, not a blanket dependency-name exemption.

The workflow verifier requires the complete unconditional build, tree and check
commands. Conditional, commented, removed, masked, echo-only and wrong-input
checks are rejected. Explicit plain text is required: a real Cargo run with
`CARGO_TERM_COLOR=always` emits ANSI even under the custom tree format; overriding
it with `--color never` produces valid deterministic evidence. Omission of that
flag is rejected in both workflows. Existing single-producer/consumer,
merge-group, aggregate, artifact, export, ABI and size gates remain unchanged.

## Evidence and qualification

The real default Cargo graph passes. Enabling `xyg-engine/raster` through Cargo
produces a real graph rejected by the new checker. Fifteen bounded feature tests
cover legitimate shared PNG and malformed/unbound/native feature controls.
Fourteen workflow mutations exercise failure propagation in both producers.
The final `make check-ci` command passes all 793 tests; seven final Core/actual
Git-CRLF checks, scoped typing and mandatory full-worktree hooks/Ruff pass.
The feature tests join the existing `make check-ci` target; no new job or duplicate
gate is introduced.

The ordinary raw wasm32 build and `npm run build:wasm` succeed. The fresh compiler
artifact is byte-identical to the reviewed parent compiler, and all eleven
runtime artifact records remain unchanged after packaging. The module remains
**1,897,547 raw /784,435 Node22 gzip6 bytes**, within fixed
**1,927,168 /786,432** caps, with **68 function exports**, zero imports,
ABI405/WASM38. Parent runtime/browser/PNG behavior is inherited after exact
source/artifact identity, not claimed as a fresh broad runtime test here.

`checks.json` records final command outcomes, source/artifact hashes and raw/log
archives. `current-bindings.json` advances the exact parent history; predecessor
snapshots are exact Git-parent bytes. The original hosted failure remains a
failure. One manual mutation helper initially lacked its script import path;
that setup failure remains archived. An initial local contract run was stopped
before completion after the real colored-Cargo experiment identified the need
for explicit color suppression; it receives no pass credit. The final command
and its result are retained separately.

## Reproduction

Use the pinned Rust1.96, Node22, existing locked dev dependencies and disk TMPDIR:

```sh
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
cargo tree -p xyg-wasm --target wasm32-unknown-unknown --edges normal --prefix none \
  --format '{p}|{f}' --color never > wasm-tree.txt
uv run --no-sync python scripts/check_wasm_features.py wasm-tree.txt
npm run build:wasm
TMPDIR=/var/tmp uv run --no-sync make check-ci
uv run --no-sync pytest -q tests/test_graphforge_contract_corpus.py
uv run --no-sync --with pre-commit pre-commit run --all-files
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
```

No hosted pass, issue completion, performance improvement, total-memory bound,
new platform qualification, shipping or queue acceptance is established by this
local correction. Parent unexplained installed-server and graph contention
failures remain unresolved; this correction does not address their mechanisms.
