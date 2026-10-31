# S4 foundation ABI contract repair

CI run 41245578949, job124668554430 fails on reviewed S4 head
`93cb8570e72d9d21cb48def6679728b10396e3cc`: the geographic frame-lease
conformance script asserts WASM34 while the generated contract and real module
are35. The local `before` command reproduces35!==34. Five current geographic
harnesses copied that old literal. This repairs their expectation using the
committed generated `spec/wasm/abi.json` as the independent authority, with
strict equality retained. The overview harness gains the same check and records
actual loaded native/WASM versions rather than stale389/34 report labels.
Independent review also identified the selected harness's optional report
(native383/WASM33/Scene32/painter15); it now records loaded native/WASM/Scene
versions and the generated painter contract. Historical reports are unchanged.

Only conformance scripts, current specification and this new receipt change.
No production code, generated declarations, tests of payload/ownership/resource
semantics, package gates, compiler, workflow or artifact changes. Earlier
receipts remain immutable. `ci-step.sh` copies the exact complete failing CI
step, selecting this worktree as GITHUB_WORKSPACE; runtime results and final
independent review follow. No M4, release acceptance or publishing claim.


The complete copied CI step passes, including all184 native/WASM host tests
with zero failures, cancellations or skips. The seven emitted CI reports are
retained here. After the review metadata correction, report-enabled selected
and overview conformance reruns pass and record ABI398/35; the selected report
also records Scene34/painter17. This metadata-only correction changes no case
assertion. The earlier step log remains immutable and still contains its old
PASS label; the later focused report proves the corrected label and metadata.

The production module is the same independently reviewed shipping artifact
`27835ac2610b53ffb79af2a2db1510547fe8be334cad0eebf06b347986bd9099`.
No rebuild or package-budget adjustment is needed for harness-only changes.
Final hook/review pins are recorded with the PR update.
