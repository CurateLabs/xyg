# PR1104 preserved Rust test transcript classification

Hosted Rust/Python/JS job128159731244 at caeffd14 failed its naming scan on
the frozen chunk-reuse Rust stdout receipt. The crate-relative unit-test entry
was interpreted as a legacy ABI path because the complete stdout occupies one
JSON line. Later upload errors reflect absent files after that early stop;
downstream skipped tests receive no pass credit. The failure also applies to
the subsequent keyed-lookup head and needs this additional correction.

The transcript stays byte-identical. The existing fail-closed frozen-evidence
map adds exactly its path and canonical UTF-8/LF SHA-256, with a name/comment
that covers both the two earlier issue snapshots and this test transcript.
Mutation or copy/rename restores every ordinary check. Existing newline reading
semantics are unchanged. No directory, extension or future evidence is exempted.
The existing matrix of exact-path/content and real newline controls now includes
all three fixed receipts. An isolated pre-fix check reports exactly one error;
the complete corrected naming module passes 155 tests, including the real
repository scan. Full-worktree hooks and Ruff passed.

Preserved path: spec/performance/chunked-column-reuse-2026-11-06/rust-tests.json
Canonical SHA256: ab1fd6dd588c7022eda421e672d88d90ec0ee53a26402120f3258833362cb3eb

Reproduce:

```sh
uv run pytest tests/test_stale_names.py -q
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The Rust cache/native artifact are unchanged from independently approved
d86875e284cf82e817114de9e894a85c3ca6cbd8. That approval covers lookup/LRU;
this naming correction requires its own independent review and fresh CI. No
whole #110/M7, larger-than-RAM, browser/WASM, accelerated100M or release claim.
