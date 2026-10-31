# Node review follow-up on native ABI 398

Append-only follow-up to the original Node scheduling and integration receipts.
Base is `ef0870774edacd4fcffceddeb10e9dd469ad0989`, the normal merge of S4 CI
repair `7c02d3df0e769e945ae171f90906f9b17acfc65f`. Prior receipts are immutable.

Greptile comments 4433364950 and 4433364956 identify a stale synchronous API
recipe and unnecessary full GraphData materialization on collapsed edge picks.
The recipe now uses one GraphForgeLayoutController per view, awaits the live
payload, resolves picks from that payload, explicitly requests preset position
reuse, and awaits owner disposal. Batch/export callers use the static API.

Edge picks build one source-edge identity index per immutable composition,
reusing the existing persisted/derived ID formatter. They copy no node names,
types, text/value columns. The regression traps unrelated attribute reads and
checks one index construction across live and static collapsed picks, including
derived edges and exact result provenance. Identity policy remains unchanged;
the retained map is O(source edges), without a constant-memory claim.

Two missing Node scheduling shell paths use the existing node-host ownership
policy and bounded human ledger. Native ABI 398 and production WASM are inherited
from the S4 repair; the API inventory retains 685 explicit preparation gaps.
This is no #35/#36/M4/#108 acceptance or publication claim. Verification and
independent final review follow below.


Verification: actual native/client/WASM build passes unchanged package gates;
49 focused GraphForge/actual session replay tests pass, zero skips. ABI smoke
passes 673 checks, paired assets verify, all 500 ownership paths classify, and
the preparation inventory verifies. Fresh offline Linux x64 wheel/four-tarball
installation passes at ABI398. The bounded four-node browser journey passes
exact pointer UUID, initial/final paint and pan checks, retaining specs, buffers
and screenshots. These are functional observations, not performance thresholds.
The complete strict-CSP S4 foundation is reused only by exact unchanged Rust,
WASM, worker and paired-client asset hashes.

The first focused run started while the package producer was still running:
its log explicitly binds the old `25ee24fd` module and fails the new standalone
regression (48 pass/1 fail). No assertion or product change followed; the
post-build run binds `27835ac2` and passes all49. Both logs remain. Full Node
baseline harness repair is independently owned in the S4 follow-up and will be
merged and verified before whole-package acceptance. Full-worktree hooks and
Ruff check/format pass. Final independent review remains pending.
