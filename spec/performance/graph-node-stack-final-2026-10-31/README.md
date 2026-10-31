# Final Node/S4 stack verification

This new receipt records the normal merge of S4 head
`93cb8570e72d9d21cb48def6679728b10396e3cc` into reviewed Node follow-up
`c1a277dfa094568697f42217cdd6fa65fd0f23b0`. The merge has no conflicts; the
shared current API status changes are identical. Only S4's three test-harness
repairs and its append-only evidence are new relative to the Node follow-up.
Product/native/client/WASM sources and generated production assets are unchanged.

Earlier receipts stay immutable, including the original S4 failed full Node
run and the Node follow-up's in-flight old-module failure. Fresh checks below
verify the combined source; unchanged installed/package/browser proof is reused
only through exact source/artifact hashes. This is not S5, #35/#36, M4, #108,
release-freeze or registry acceptance. Remaining acceptance precedes publishing.


Fresh combined full Node suite: **1,507 passed, zero failed/cancelled, two
existing skips** out of 1,509 tests. Native ABI smoke passes 673 checks; all500
production ownership paths classify; official generated declarations are current
at 537 symbols / ABI398; paired assets and API inventory pass. Root product and
asset hashes are unchanged from the reviewed Node follow-up and S4 shipping
proof. Full-worktree hooks and Ruff checks pass; final independent commit review follows.
