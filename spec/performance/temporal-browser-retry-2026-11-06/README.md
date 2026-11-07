# Public temporal graph frame retry

## Candidate and scope

This bounded #45 repair changes the existing public browser coordinator and
its existing Node publication and browser foundation tests. It preserves Rust
visibility, UUID identity, CoSE, work budgets, ABI, and package size limits.
The live issue acceptance criteria are retained in `issue-45.json`.

The starting checkout was `74195403`. Normal no-commit merges incorporated
accepted main `c3152d97bdb3a1efd61686b21d84385ee0f8de9e` as `e45a27a3`, then
reviewed publication/CI wiring `ec58124ff083da650c2f35bd5ec2f3b53f4902c2`
from the parent's publication branch as `d22a6713af30ef13665d8b2bdbf7c0de5b3c4861`.
Both merges ran full-worktree hooks, Ruff check and Ruff format check before
commit. Their raw logs are `main-hooks.log.gz` and `stack-hooks.log.gz`.
The accepted-main versions resolved the scheduling spec and generated release
inventory conflicts. This candidate remains stacked on the publication fix.

## Reproduction and contract

`before-node.log.gz` fails after an invalid input reserves revision 1. The next
valid submission is refused before reaching WASM. `before-browser.log.gz` fails
on retry after a genuine packaged-WASM resource rejection through the public
coordinator and real Worker. Both were captured before the coordinator edit.

The coordinator now validates before changing transport state. It retains the
highest requested revision, reserves each attempt separately, and releases only
the current failed attempt. Duplicate in-flight and successfully returned
revisions remain stale. Superseded lower revisions remain stale even after a
newer failure. Late older errors cannot release a newer reservation. Layout
callbacks and results are guarded by attempt identity and disposal.

`frameAndLayout` prevalidates its u32 revision width. Layout failure after a
valid returned frame consumes that frame revision. A transport retry cannot
promise rollback when Rust may already have committed before delivery failed.
Rust output-admission rejection itself leaves the applied revision unchanged.

The actual WASM fixture binds 4,096 nodes and 80 edges valid from cursor 10.
Its fixed 70,128-byte arena admits creation. Cursor 10 requires 72,336 output
bytes and fails with the existing resource error. Retrying revision 1 at cursor
0 returns 69,776 bytes with 4,096 visible nodes and zero visible edges under
the same cap. This is correctness evidence without a performance comparison.

## Verification and reproduction

Use Node 22.23.4 from
`/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin`
on PATH. Set `XYG_NATIVE_LIB` to the native path in `environment.json`.

```bash
node js/build.mjs
node --test packages/xy-node/test/temporal-graph-publication.test.mjs packages/xy-node/test/temporal-graph.test.mjs
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome node scripts/wasm_foundation_smoke.mjs
uv run python scripts/verify_wasm_assets.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

`node-final.log.gz` records 10 passing tests. The later `node-complete.log.gz`
records 11 passing tests including failed-supersession callback suppression. They cover input and actual output
rejection/retry, successful stale and duplicate in-flight requests, concurrent
supersession, late failures, malformed input preserving active layout,
prevalidated layout width, consumed frames after layout failure, and disposal.
`browser-final.log.gz` and `browser-final.json` record the full strict-CSP foundation
pass, including the real Worker retry and existing frame/layout membership,
rapid requests, progressive layout supersession and disposal goldens.
The Node test is included in the existing `npm test --prefix packages/xy-node`
command by the reviewed stack. The browser test runs in the existing full
foundation CI command. No workflow was added.

Earlier and final build/test reports remain separate, with generated failure
screenshots retained. The final source and artifact hashes are in
`environment.json` and `browser-final.json`. These are working-tree receipts
based on the stacked base, rather than claims that the base contains this edit.

The producer is `/home/ubuntu/.t3/worktrees/xyg/t3-4585b57b`, head `ec58124f`.
All 243 tracked Rust/Cargo/toolchain source files match it byte-for-byte.
The reused native SHA-256 is
`02f0edf9c79ae1408821c197981b37ebe8f5746a4e1a8df4f8a3ccf468f6519e`.
The unchanged optimized WASM SHA-256 is
`7bce0525a9688ae051ef0f13d9f55da1a1e9fef08b2449993673e8811aada3a1`.
`node-size.json` measures the actual Node 22 gzip size. The raw module is
1,927,032 bytes with 136 bytes headroom under 1,882 KiB. Node 22
gzip6 measures 786,115 bytes with 317 bytes headroom under 768 KiB. Generated artifacts
remain ignored. The producer workspace was read only.

## Remaining acceptance

This candidate requires parent independent review and PR/CI/merge-queue delivery.
#45 remains open for automatic controller/composition attachment, full GraphForge
history fixtures, aggregate LOD membership, rendered frozen HTML/PNG/SVG
provenance, and large/massive playback, accessibility and parity evidence.
It establishes no M4, M6, M7, release or competitive performance completion.
