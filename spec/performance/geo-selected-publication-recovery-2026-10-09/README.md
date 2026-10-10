# Selected indexed publication recovery evidence

This bounded engine proof covers selected command19 with nonzero nonce, exact
304-byte Style48 request replay, and private Data retirement. It changes no
geometry, selection, style precedence, host product policy, ABI or quota. Public
19 adoption, hierarchy44 recovery and massive interaction readiness remain open.

`native-wasm.json` retains twelve complete normalized packets for direct and
reduced nullable-time MultiPoint fixtures. Six nonce-zero packets match the
pinned prior33a61 native/WASM pair through `legacy-baseline.json`. The unchanged
35/36 script also reproduces all twelve previous packets byte-for-byte; its
current report is `prior-mutation-current.json`, with the prior report committed
in the preceding mutation evidence folder. Literal checks preserve duplicate
u64MAX IDs, annotation-shaped IDs, >2^53 IDs, original rows, null geometry,
i64MIN filtering, offscreen rows, selected counts and full Scene bytes.

Normalization changes only process-local packet owner16..24 AFTER matching the
actual requested Source/Query/Rows handle and publication sequence. Rows80..88
remains untouched and is independently validated. No camera/time/style/state,
count, source, footer, Scene, or remaining metadata bytes are masked.

Actual native and WASM controls check exact19 replay after Query replacement,
changed-style/47 sequence rejection, independent36 retirement, lost original19
receipt replay and lost10 retirement via47, five indexed views at16 handles,
failed19 budget preserving completed Query, original Source/Index disposal before
Rows, and bounded cancellation/read ACK. Focused Rust controls additionally
check held36 birth saturation and release,8 Data capacity, exact local budget
and one-byte-under, retained26 Data after original disposal, and a newer Scope
State plus large nonce33 receipt. Complete Scope credits also apply to opt-in
35/36; nonce0 keeps its previous resource policy and all output controls.

All1484 engine tests, seven publication tests, ten prior mutation tests, strict
workspace Clippy and hooks/Ruff pass. `tdd-before.txt` records two failing tests
before implementation; the independent log contains the actual seven passing
library tests (unmatched binary test targets run zero tests). No performance,
competitor speedup or massive-data latency claim follows from this journal.

Artifact paths/hashes, exact raw/gzip6mtime0 sizes and unchanged caps are in
`environment.json`. The201-path compiler manifest includes the newly staged
cfg-test file. Production and test/spec/script hashes are separately pinned.
The four-copy request allowances cover retained authority plus new canonical
copies before allocation; there is no extra pool or quota expansion.

Reproduce from this checkout:

```bash
cargo test -p xyg-engine selected_publication --lib
cargo test -p xyg-engine --lib
cargo clippy --workspace --all-targets -- -D warnings
cargo build -p xyg-core --release
cargo build -p xyg-wasm --target wasm32-unknown-unknown --release
npm ci && npm ci --prefix packages/xy-node
node js/build.mjs
node js/package-wasm.mjs target/wasm32-unknown-unknown/release/xyg_wasm.wasm
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib \
XYG_SELECTED_PUBLICATION_WASM=$PWD/packages/xy-client/dist/xyg-wasm.wasm \
XYG_SELECTED_PUBLICATION_BASELINE=spec/performance/geo-selected-publication-recovery-2026-10-09/legacy-baseline.json \
node scripts/geo_selected_publication_recovery_conformance.mjs
```

To regenerate the old baseline use the exact older artifact paths/hashes from
`legacy-baseline.json`, set `XYG_SELECTED_PUBLICATION_LEGACY_ONLY=1` and
`XYG_SELECTED_PUBLICATION_REPORT=/tmp/baseline.json`. Missing explicitly supplied
artifacts fail the script. It uses existing shared encoders/drivers and raw
framing solely in tests; hosts do not implement geometry, LOD or selection.
