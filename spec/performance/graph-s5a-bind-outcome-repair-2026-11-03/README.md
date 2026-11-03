# S5a binding outcome repair

Greptile finding [4460032516](https://github.com/CurateLabs/xyg/pull/1085#discussion_r4460032516)
identifies a real contract mismatch at reviewed commit
`5840b4790660d8bafa59e9b5308b450c51f55713`: binding paints the adopted temporal
selection, while its default `OpOutcome` reports zero selected elements.

## Reproduction and narrow fix

The new Rust regression fails on the original implementation: expected
`outcome.u32 = [1,0,2,0]` for an owner with one node and one edge selected,
but receives `[1,0,0,0]`. The actual native/production-WASM regression also fails
when unbinding and then adopting an owner that retains one selected node.
Both failures and exact argv/raw logs are retained here.

The fix constructs `OpOutcome.selected` from the already borrowed destination
state under the existing temporal world lock, before speculative publication.
It adds no lock acquisition, state mutation, selection reducer, event, request
field, ABI/export or package/runtime-budget change. The existing false
`state_changed`, empty changed refs and absent disclosure remain unchanged;
binding adopts ownership without mutating the owner's interaction state.
Unbind retains its fresh empty Owned selection and zero count. All existing
stamps, resource checks, candidate rollback and complete cached retries remain.

The Rust regression covers initial nonempty bind, same-owner rebind, exact
retry bytes, a different nonempty owner, unchanged old-owner selection, and
unbind with preserved destination selection. The actual native/WASM replay
covers empty bind, nonempty adoption after detach, same-owner and post-frame
rebind, capacity/retry bytes and the existing stale/disposed-owner controls.

## Verification status

126 Rust interaction tests, nine native session tests, two WASM session adapter
tests, the Python ABI session proof, 673 native ABI smoke checks, generated
native/WASM declarations and all-target warnings-denied Clippy pass after
repair. The native release core is rebuilt from the repaired source.

Real production packaging and paired assets pass under unchanged
1,829/747-KiB gates. The new module measures 1,872,568 raw / 764,079 gzip6 bytes,
27 / 16 bytes above the original S5a artifact, leaving 328 / 849 bytes.
Optimized SHA-256 is
`862a04c4053dc32f2757a35e8a39d79e837ea276ab0b2a14cd380bfbfb89b820`;
gzip6 SHA-256 is
`f73768daa491f1bd12dd25ce7adf2c2ed4355ac8aab05d1d840cb1062c5d4a66`.
The actual native/production-WASM replay and package-contract suite passes all
13 tests, zero skips, with diagnosticModule false. The original full strict-CSP
foundation passes against production source-dist assets with six screenshots,
zero external requests and artifactCommit null. No diagnostic module substitutes
for those assets. Eight compiler/package/optimizer/ABI input files remain
byte-identical to the original S5a commit (package-controls.json).

Only API inventory base provenance and the browser-spec source digest change;
declarations and all 685 explicit acceptance/classification gaps are unchanged.
Final independent review and full-worktree hooks/Ruff checks pass; committed CI remains pending. Historical S5a receipts
remain immutable and describe their original source/artifact. This correction
establishes no S5b/S6/S7, graph scale, M4/#108 or publication acceptance.

## Final independent review

`s5a_final_review` approved the seven-path nonreceipt diff against the original
S5a commit, SHA-256
`b6fa29aa52d08e3d4743f5f1fa198c45dd4a2a251cd51873fb44df51f1774c91`.
It verified exact source/artifact/raw-log hashes, all 13 real replay/package
passes, six byte-identical browser screenshots and all 3,063 historical receipt
files unchanged. No blocker remains for this correction. Full-worktree hooks,
Ruff lint and format pass (930 Python files). Final evidence retains the
uncommitted-source artifactCommit null; CI must qualify the resulting commit.
