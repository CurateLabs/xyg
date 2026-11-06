# Temporal submitted-revision snapshot correction

Independent review of `c90fd9a0292d7be2d7d0598123bcd0e2e41be37e` found
that caller mutation of options.revision during Worker reply delivery falsely
rejected a valid Rust commit as stale. Retained before.log.gz reproduces this
through the public packaged coordinator and actual WASM, without forged packets.

The coordinator captures the submitted revision once and uses that scalar for
encoding, admission, highest-request watermark assignment and reply validation.
Caller object mutation cannot change the request's identity after submission.
Existing attempt identity, latest-wins, cancellation, disposal and ambiguity
contracts are unchanged. No ABI, Rust, budget, tolerance or public signature edit.

The existing normal-CI Node publication test delays delivery after actual WASM
execution, mutates the caller's revision, then requires the original committed
frame to return. Duplicate revision remains refused; the next revision succeeds.
An accessor control verifies one revision property read per frame submission.
Twelve focused Node tests pass without skips. The full strict-CSP local-only
Worker foundation harness and asset verifier pass after rebuilding the client.

Reproduce using Node22 with the existing qualified native/WASM artifacts:

```sh
node js/build.mjs
XYG_NATIVE_LIB=/home/ubuntu/.t3/worktrees/xyg/t3-4585b57b/target/release/libxyg_core.so node --test packages/xy-node/test/temporal-graph-publication.test.mjs packages/xy-node/test/temporal-graph.test.mjs
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome node scripts/wasm_foundation_smoke.mjs
uv run python scripts/verify_wasm_assets.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Source/artifact/log bindings below preserve earlier evidence. The client's
production source was rebuilt; native/WASM reuse is by verified digest. The
recorded hook run preceded the final test-only accessor assertion and prose
clarification; the complete final worktree is rechecked before commit.

Independent correction re-review and PR/CI/queue delivery remain required.
#45/M5 remains open for controller/composition, aggregate LOD, frozen exports,
history fixtures, scale, accessibility and broader acceptance. No release or
issue closure is claimed.
