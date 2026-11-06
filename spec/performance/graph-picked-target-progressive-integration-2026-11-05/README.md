# Picked-target and accepted progressive-browser integration

This normal merge retains reviewed picked-target head `945b3ec13a3d78e7e99d9476889ed5d2b6dc8dc6`
and accepted main `c818fac4f1522eccc0e5532beb77ff0ba7719842` (#1098).
The only textual conflicts were the browser specification and generated release
inventory. Both specification additions are retained; the inventory is refreshed
with `uv run python scripts/check_release_inventory.py --write`. The combined
wire-test module retains both existing picked-target tests and the accepted
continuation/progress test. No hand-authored product resolution was required.

All prior performance receipts remain byte-identical. `protection.json` records
Git-blob comparison counts and verifies that product sources follow the exact
union of reviewed picked-target source and accepted main changes. No Rust source
changed from the prior reviewed candidate, so its native and optimized WASM
artifacts are retained. Browser bundles are rebuilt from the combined sources.
`artifacts.json` records current artifact hashes; prior receipt hashes describe
historical client builds rather than this combined build.

Each fresh command has a command JSON and losslessly compressed raw log (`logs.json` binds both hashes), recorded by the unchanged
`../graph-picked-target-main-integration-2026-11-05/run.py` with
`XYG_ATTACHMENT_RECEIPT` set to this directory. The browser runs use actual
packaged Worker/WASM, no diagnostic session-module override, and Playwright
Chromium. `progressive.json` covers the bounded progressive controls including
unfinished nonzero companion paging; `legacy.json` covers legacy journeys.
Wire/migration, package contracts, official inventory validation, whole-worktree
hooks and Ruff are recorded separately. Results are limited to commands with
exit zero; historical broader suites are not represented as fresh reruns here.

The 1882/768-KiB picked-target caps and existing 16/384-MiB arenas remain unchanged.
No public hover integration, full rendered scale ladder, notebook integration,
#35/#36/M4/#108 acceptance, selected release cohort, or publication follows.
The retained 1k evidence and its interaction limits remain historical and scoped.
Independent final integration review, fresh remote CI and merge-queue acceptance
are required before landing this merge. No prior receipt is rewritten.
