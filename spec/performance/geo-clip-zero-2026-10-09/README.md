# Clipping topology signed-zero regression

The overview painter stress fixture exposed an inherited clipping panic.
RingGraph sorted derived boundary nodes with `total_cmp`, which distinguishes
signed zeros, then welded them with numeric equality, which treats them equally.
A removed positive-zero endpoint failed the later total-order binary lookup.

The four-edge signed-zero regression failed against the original implementation
with the lookup panic. Snapped topology coordinates now normalize zero to
positive zero before insertion. The existing tolerance, canonical f64 source,
winding and other coordinates remain unchanged. All40 viewport and313
geographic Rust tests pass, as does strict all-target Clippy. Independent source
review is green. Logs and frozen source hashes are recorded here.

Reproduce with `cargo test -p xyg-engine geo_viewport::tests`,
`cargo test -p xyg-engine geo_`, and
`cargo clippy -p xyg-engine --all-targets -- -D warnings`.

The original triggering overview fixture uses all256 counts, a4326 camera
center0/0, zoom0,800×600, bearing120, pitch60 and no world wrap. Its actual
overview/native/WASM confirmation belongs to the separate painter/export slice.
No artifact parity or performance win is claimed by this source regression.
