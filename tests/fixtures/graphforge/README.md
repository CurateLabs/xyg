# GraphForge canonical IPC fixtures

Schema-faithful Arrow IPC files matching GraphForge projection field names
(`node_uuid`, `edge_uuid`, `src_uuid`, `dst_uuid`, `labels`, `relationship_type`,
`provenance_row`). Vendored for CI without a GraphForge runtime dependency.

Regenerate with:

```bash
PYTHONPATH=python uv run python scripts/gen_graphforge_ipc_fixtures.py
```
