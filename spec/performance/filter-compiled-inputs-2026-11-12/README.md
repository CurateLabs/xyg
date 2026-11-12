# Complete compiled-input provenance, 2026-11-12

Parent: `54467773b9ed0c09c2af6efc45f779d6b8928c75`.

An independent private copied-input rebuild exposed an inherited omission from
the 327-entry compiled-input manifest: `crates/xyg-engine/src/index_slots.rs`
and `crates/xyg-engine/src/graphforge/interaction/wire_packet.rs` were absent.
Both modules were already tracked in Git and in the complete current-source
bindings. Neither module changed in the single-color optimization. The earlier
compiled-input list was therefore incomplete; its entry count is not proof of
an exhaustive producer input set. Earlier receipts remain byte-identical.

This successor records all 329 inputs and requires every tracked Rust source
under `crates/` and `vendor/` to appear in the manifest with its exact digest.
The original copied-input build failed with missing-module errors (exit 101).
Adding the two source-identical files enables the unmodified private build;
`checks.json` records the command, exit, artifact digest and comparison with
the already qualified native library. The complete input copy uses the same
workspace feature union, release configuration and locked dependencies, without
changing Root sources or shipping artifacts.

The completeness regression also retains all predecessor bindings and source
archives. It rejects a manifest with either module missing. Core qualification
uses actual Git LF/CRLF checkout conversion; this is not a synthetic line-ending
replacement. The new successor has 65 historical parent manifests.

No product, wire, ABI, compiler, build-profile, package-cap, native, WASM, client
or Worker bytes change in this correction. The shipping module remains
1,875,559 raw / 785,836 Node22 gzip6 bytes (596 gzip bytes spare). The exact
single-color implementation, paired CodSpeed results and their limits remain
in the [parent receipt](../filter-single-color-2026-11-12/README.md).

The pending review of the earlier candidate was cancelled after this gap was
found; it supplies no approval. One new independent review must cover the full
single-color change and this correction before delivery. Current-head hosted
checks and the required merge queue remain necessary. This does not establish
whole #112 or milestones 4–7 acceptance. The private channel-rounding probe is
separate exploratory work and supplies no performance or shipping qualification.
