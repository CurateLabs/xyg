# PR1113 UPDATE admission boundary regression

Correction against reviewed integration `8275fc9f87ed55071e66472a703fe3671dd53e8a`
addresses Greptile thread `PRRT_kwDOTxX6Es60zBBW`. Production code, ABI,
resource caps and shipping artifacts are unchanged. The new committed Rust test
calculates the normative replacement envelope independently of `admit`, including
retained ownership, non-document ingress, 6× document ingress, the complete new
document envelope, external retention and the extra Owned-state item.

The exact limit is 3,526,208 bytes. One byte below it refuses and preserves the
entire old reply, render revision, publication and work; retrying the same
sequence at the exact limit installs the new coordinates and supports identical
cached reply delivery. The complete interaction module passes 153 tests.
Two temporary production mutations are negative controls: removing the document
discount rejects exact-limit success; omitting replacement ownership incorrectly
accepts the one-under request. Both fail this test. The original production file
was restored byte-for-byte before the final successful interaction run.

Additional qualification: 33 Core/provenance/inventory tests including actual Git
CRLF conversion, full-worktree hooks, Ruff check and Ruff format check pass.
Commands and canonical LF source/archive/raw hashes are in `bindings.json`.
Earlier evidence is unchanged. This test uses the current selected Rust 1.96
compiler; no native/WASM rebuild or new browser capture is required for this
coverage-only change. It adds no performance, default-arena, larger-ladder,
frontend/export/accessibility, issue or milestone acceptance claim. Independent
final correction review and new-head hosted CI/merge queue remain required.
