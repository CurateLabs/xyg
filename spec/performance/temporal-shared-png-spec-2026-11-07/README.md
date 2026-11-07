# Shared PNG current specification correction

Parent d660cfdd326dd4ff3b8b0f56ce4bd2c3619f6644 received an independent complete
371-path review with one remaining P2: the current WASM36 profile still described
the previous over-cap PNG refusal as current behavior. The review found no P1
product defect and freshly exercised module/offline Blob Worker PNG, fourteen
exact current/prior-native PNGs, recovery and lifecycle controls.

The normative browser-WASM paragraph now identifies that refusal as historical
and links the unchanged shared-PNG continuation. It states the same qualified
1,886,125 raw / 784,655 Node22 gzip6 bytes under unchanged caps and preserves the
future combined-module and whole-issue limits. Runtime code, fixtures, generated
artifacts, compiler settings and all earlier receipts are unchanged.

A successor Core binding records the new specification and pointer. Existing
Core/provenance/real-CRLF checks and mandatory full-worktree hooks/Ruff are run
against this correction; exact commands, exits and source/artifact identities
are in checks.json. No rebuild or new browser capture is claimed. Completed
independent correction review and later integration/CI/queue remain required.
No #45/M5/milestone completion or global process-budget claim is made.
