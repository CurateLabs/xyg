# Temporal Scene slice arguments

Base: `5e42af822c32798c9238bcbd3b3e3ce22808964a`.

`temporal_scene::paint` already receives borrowed slices. Pass eight of these
slices directly to `SceneBatch::new_with_chrome_literal_ids`, removing redundant
borrows identified by strict workspace Clippy. The function signatures, data,
styles, admission, outputs and public contracts do not change. Freshly built
arrays remain borrowed.

The earlier strict-Clippy failure remains recorded in the preceding
[admission receipt](../graph-temporal-owner-charge-2026-11-08/README.md).
This successor records a fresh passing `cargo clippy --workspace --all-targets
-- -D warnings`, followed by official native release and WASM package builds.
All nine compiler/runtime artifacts are byte-identical to the reviewed base,
including the native library, raw compiler WASM, optimized module, manifest,
workers and clients. Runtime qualification is inherited only over that verified
equality; no new browser or massive-data execution is claimed here.

The module remains 1,895,754 raw / 786,405 Node22 gzip6 bytes, with 27 gzip bytes
spare under unchanged caps. The separate combined graph integration still needs
its own matching package qualification. This mechanical lint correction does
not establish complete memory accounting, hosted checks, queue acceptance,
shipping or milestones 4–7 completion.

`checks.json` binds raw/compressed logs, the artifact equality comparison,
compiled inputs and successor source history. Reproduce with Rust 1.96 and
Node 22.23.4, explicit matching native artifacts and disk `TMPDIR=/var/tmp`:

```bash
cargo clippy --workspace --all-targets -- -D warnings
cargo build --release
npm run build:wasm
uv run --no-sync pytest -q tests/test_graphforge_contract_corpus.py
```
