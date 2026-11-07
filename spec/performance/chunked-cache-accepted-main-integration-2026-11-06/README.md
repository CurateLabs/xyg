# PR1104 accepted-main integration

The ordinary merge joins reviewed candidate `4c3c15f` and accepted main
`9a75c4c0`. Main exactly matches the reviewed, already-included `43b99beb`
parent tree. The nine ancestry conflicts retain the reviewed union; the resolved
product tree equals `4c3c15f` in full. This directory is the only additive change.

`receipt.json` binds every pre-existing tracked source/evidence file, the fresh
native artifact, environment, checks and losslessly compressed transcripts.
Historical receipts, original Rust JSON and issue snapshots remain intact.
The fresh native artifact matches the reviewed SHA-256 and size exactly.

Final full-index binary diffs and delivery commit/tree identity are emitted to
`target/cache-integration-delivery/` after the commit, avoiding a self-referential
commit hash. Their hashes are reported in the local handoff. The parent handles
independent integration review, push, PR1104 CI and merge queue.

This bounded proof does not close #110, M7, larger-than-RAM, browser/WASM, 100M,
full-host coverage, #111, #112 or #113. No shipping budget or gate changes.
