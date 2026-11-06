# PR1107 frameAndLayout revision capture

Greptile comment4498138609 identified repeated reads of options.revision in
frameAndLayout: the width guard and frame submission could observe different
getter values, admitting a frame outside the layout revision width. The previous
independent approval at823db2ca covered frame capture; this is a subsequent
entry-point correction requiring its own re-review.

frameAndLayout now captures the revision once, verifies that scalar is a nonzero
u32 bigint, and passes the exact captured value in an explicit frame-options
object. It never spreads or re-reads the original revision property. Existing
attempt guarding, cancellation and Rust publication behavior are unchanged.

The existing normal-CI getter regression now exercises both entry points. It
executes actual WASM for frame creation/delivery, then uses a deterministic
layout-task stub to inspect the coordinator's frame/layout revision. Its getter
returns an in-width value on two reads and an out-of-width value afterward.
The retained pre-fix run observes three reads and fails; the correction requires
one read and exact matching frame/layout revisions. This stub is not evidence
of real CoSE performance. The complete actual-Worker strict-CSP foundation
harness separately passes, including its existing real frame/layout lifecycle.

Twelve focused Node tests pass without skips. The rebuilt client/typecheck,
asset verifier, full strict-CSP foundation and full-worktree hooks/Ruff pass.
Native/WASM artifacts, caps, ABI and Rust sources are unchanged. Earlier
receipts remain byte-identical; checks.json binds source/artifact/raw/gzip logs.

Reproduce with Node22, explicit existing native and packaged WASM:

```sh
node js/build.mjs
XYG_NATIVE_LIB=/home/ubuntu/.t3/worktrees/xyg/t3-4585b57b/target/release/libxyg_core.so node --test packages/xy-node/test/temporal-graph-publication.test.mjs packages/xy-node/test/temporal-graph.test.mjs
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome node scripts/wasm_foundation_smoke.mjs
uv run python scripts/verify_wasm_assets.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Independent correction review, fresh CI and queue acceptance remain required.
#45/M5 controller/composition, aggregate LOD, frozen exports, history, scale
and accessibility acceptance remain open. No publication or closure claim.
