# GraphForge canonical IPC fixtures

Schema-faithful Arrow IPC files matching GraphForge projection field names
(`node_uuid`, `edge_uuid`, `src_uuid`, `dst_uuid`, `labels`, `relationship_type`,
`provenance_row`). Vendored for CI without a GraphForge runtime dependency.
`tests/test_graphforge_scene.py` also runs this canonical topology through the
configured Rust CoSE seam twice, proving seeded identity and exact pin behavior.

`semantic_compound.json` is the inspectable GraphForge semantic evidence
fixture. It covers every closed semantic plane, selection/pinning, transitive
parents, collapse, an internal edge, a remapped boundary edge, and a visible
self-loop. Exact light/dark Scene, browser-painter, SVG, raster-command, and PNG
hashes are generated only from Rust-owned canonical Scene output.

Regenerate with:

```bash
PYTHONPATH=python uv run python scripts/gen_graphforge_ipc_fixtures.py
cargo build --release -p xyg-core
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" uv run python scripts/gen_graphforge_semantic_fixture.py --write
```

Omit `--write` in the second command to verify the committed semantic hashes.

## Scene32 / XYPB15 contract refresh (#945)

`scene32_refresh.json` retains the previous Scene31/XYPB14 digests as contract
evidence, separate from performance measurements. With native ABI381:

- all 99 GraphForge request digests and 98 document digests are unchanged;
- the render document changes only its `scene.version` value and the version
  word in its embedded canonical Scene;
- light/dark semantic Scene bytes change only their version word, while SVG,
  raster-command, and PNG bytes are unchanged;
- the semantic browser painter now contains derived kind8 marker batching
  with Rust-packed per-instance style planes, so its change includes payload
  layout rather than just version words; and
- public hexbin count/mean/sum and heatmap Scene digests change only their
  version word. Their current canonical authoring is checked against both
  current digests and the retained Scene31 digests.

The tests restore the old version words and require the exact previous SHA-256
values, proving these bounded claims. They do not admit old product input.
Historical hosted and local benchmark artifacts retain their original output
digests, timings, memory, and size measurements. This refresh supplies no new
performance measurement and does not imply a benchmark rerun or improvement.

```bash
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" uv run python scripts/gen_graphforge_cross_host.py
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" uv run python scripts/gen_graphforge_semantic_fixture.py --write
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" uv run pytest tests/test_graphforge.py tests/test_graphforge_semantic_evidence.py tests/test_m2_wave_b_evidence.py -q
```
