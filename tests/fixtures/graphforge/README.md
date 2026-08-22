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
```
