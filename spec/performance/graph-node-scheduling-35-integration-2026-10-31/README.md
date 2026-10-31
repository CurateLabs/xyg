# Node #35 and S4 combined-source integration

This receipt combines reviewed Node repair
`32f32199d3472278398c2afdda02b7f4c4ca1b9d` with reviewed S4
`ffeb94d1861aec6aa6ddb7b1b505e93c92358ecc` by normal merge. It also reconciles
the current graph, composition, host and application specifications and API
inventory. Historical receipts remain unchanged. This is local integration
proof, not #35, #36, S5, M4, #108, scale or release acceptance.

## Review and contracts

Whole Node binary/full-index diff versus its original S4 base:
`a981c51f60f0a9730f6d2102e0b6525f81628d08bacf4142eed42d00bae02ba0`.
`m4_s2_final_review` independently approved cancellation/lifecycle and migrated
smoke callers with 31 passing tests and the installed Linux x64 smoke.
`m4_s3_execution_plan` approved membership, source positions, API and evidence
with 42 passing tests and 76 source/receipt/artifact bindings. All four blocking
findings are fixed. The separate S4 PR carries the completed independent
correctness and final policy review for its complete diff. Final combined
review remains required before the Node PR.

Live payloads require one owner per view and await cancellation/disposal.
Static/batch callers explicitly use `graphforgeStaticPayload`. Rust-derived
render membership has separate indexing from full source positions, including
culling, collapsed groups and Aggregate. Complete f64 source snapshots survive
every live graph layout; supplied force positions seed ticks, explicit preset
reuses them, and non-force complete-position reuse stays explicit in the
contract. The API inventory preserves 679 previous gaps and adds six, totaling
685; its preparation-only status is not a release freeze.

## Actual combined checks

`combined-build` rebuilds the native core, client/Worker bundles and real WASM
shipping assets from the combined source. Product Rust/ABI source is unchanged
from reviewed S4. The production WASM matches the exact reviewed module:
1,860,250 raw / 759,008 gzip6 bytes, SHA
`25ee24fdf32ee8355598cff67da44e01556d0bb2914d5cc2d4ab4a3834c1769d`, under
the unchanged S4 1,817/742-KiB limits. Paired production assets verify. No raw
or diagnostic module substitutes for the shipping asset.

- `combined-node-tests`: 138 pass, zero skips, including the 132 affected Node
  cases, five actual native/WASM session replays and the unchanged browser-global
  guard. The official S4 source/generator parameter rename resolves the earlier
  inherited guard failure; no generated declaration or guard is manually altered.
- `combined-contracts`: 673 native ABI checks, production paired assets and
  release inventory matching pass. Native ABI remains 397.
- `two-path-csp`: actual native and browser paths pass the migrated executable
  webview smoke, nonce CSP, cross-origin local assets, Blob Worker and exact
  real-click identities. This uses production shipping WASM, with screenshot
  `webview-csp.png`.
- `functional-paint`: the repaired four-node consumer paints initial and changed
  final geometry, checks real pointer hits against exact tooltip/source UUIDs,
  and pans both views. Initial/final specs, binary payloads, screenshots, source
  and asset hashes are retained in `result.json`. Checkpoint arrival and painted
  frame timestamps remain distinct. ACKs hold presentations for inspection;
  their interval is not scheduler cadence. Full replacement resets viewport.
- `combined-installed-smoke`: a newly built wheel supplies the native package;
  staged facade/platform tarballs and local pinned Koffi tarballs install offline
  into a fresh Linux x64 consumer. The migrated release smoke passes without
  `XYG_NATIVE_LIB`. Wheel and four tarballs are hash-bound, and installed
  GraphForge/controller/worker/scheduler/generated-ABI files equal current
  source. This proves one local platform pairing, not the full release cohort;
  no registry write occurs.

The full S4 strict-CSP foundation is reused only because Rust/WASM, client and
Worker assets are unchanged and hash-bound; its immutable report and six PNGs
are in the S4 package receipt. The fresh combined GraphForge CSP journey above
additionally covers the migrated Node caller. Broader Rust/Python/Node S4 proofs
remain bound to unchanged source; they are not represented as rerun here.

`run.py` is copied unchanged from the S4 receipt, retains exact commands, exits,
raw/gzip logs and timings, and refuses command-name overwrites. `capture.py`
binds source, artifacts, existing receipts and the working merge. Proof runs
before the merge commit, so `artifactCommit:null` and source hashes, rather than
the old HEAD alone, define its provenance. Generated assets stay ignored.
