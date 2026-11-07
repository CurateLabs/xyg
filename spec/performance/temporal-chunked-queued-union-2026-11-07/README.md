# Queued temporal and chunked candidate integration

This local merge combines reviewed PR1110 at
`2cb7f0a13ec0af3a00b9dcfd2b104a2c579b7ac9` and reviewed PR1111 at
`181967e1c8ede618555fb0bc45ba09b5424cba9d`. Both have green required PR checks
and are queued against accepted main `084b3c1b7c393e135476aab9610bf8334767b2ac`.
Their queue state does not establish accepted-main ancestry for this local tree.

The merge preserves both product paths. Attributes retain both receipt pin sets,
Core current qualification advances to the combined sources while preserving
both historical binding chains, and the preparation inventory is regenerated
with the official generator. Earlier receipts remain immutable. Native Rust
production inputs match the reviewed PR1110 producer; combined browser sources
require a fresh client build. Every reused binary must match its producer hash.

This receipt records combined qualification as it is executed. Parent independent
review, accepted-main freshness and new-head CI/queue remain required for delivery.
Broader issue and milestone acceptance requirements remain open.

Fresh combined checks pass with the explicit ABI401 producer native library.
The focused Python batch passes130 tests with one browser test initially skipped;
the explicit Chromium run of that rendered-navigation test then passes its four
complete image/oracle comparisons. Sixteen actual native/WASM wire/publication
tests pass. The full foundation passes camera/scheduling and fourteen retained
temporal cases. Client build, packaged assets, full hooks and Ruff checks pass.
Parent protection verifies15,511 staged Git identities. The local T3 AGENTS.md
overlay differs from its indexed file and is kept outside the committed changes.
