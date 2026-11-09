# Hosted naming, Python-floor and successor discovery repair

Base: `3548164e2c803f11b9ee07cb03f6e37ace66930c`. This follow-up changes CI,
naming validation and provenance only. Runtime sources, generated clients,
compiled inputs and shipping artifacts remain base-exact. Whole milestones 4–7
remain open.

Hosted run `42660045065` at PR1116 head `bc040379` failed. The main job's
naming check reported upstream vendor entrypoints and incidental `strings`
output as retired product identities. The Python 3.11 job failed collection
because its isolated installation omitted PyYAML, which workflow tests import.
Neither failure is recast as a pass. Missing downstream artifacts followed the
failed main gate. A separate local inspection found the immutable parent-union
Node discovery assertion also needed the already-qualified five-view test.

The naming checker now recognizes only complete upstream entrypoint tokens,
exact relative vendor fields, and one exact-path/content historical diagnostic.
Other occurrences, lookalike paths, root ABI references and changed/copied
historical diagnostics still fail. No vendor directory or evidence directory
is excluded; historical evidence and upstream files are unchanged. The floor
installs the test parser explicitly. The Node guard retains its original
parent union plus the qualified geographic lifecycle test without duplicates.

Fresh commands and their original logs are bound in `checks.json`. They include
focused naming/workflow tests, actual Python 3.11 collection, the stdlib workflow
validator, and Core's real LF/CRLF checkout proof. The seven final naming
regressions fail against the archived parent checker. An initial focused run
had two incorrectly compact JSON test fixtures; the final fixtures use the
actual upstream digest manifest's standalone field shape. The first clean
floor-environment attempt omitted the package's NumPy runtime dependency and
failed loading conftest; installing that existing runtime dependency allowed
the three guard tests to run. No product dependency or test skip was added.
The first Core run detected an unpinned new contributor-contract source; its
LF attribute was added before rerunning the actual checkout proof.

The preceding temporal binding received independent exact-commit approval:
`3548164e`, review SHA256
`241106342be49a75f4243414861bf87b4b70cd61d7f018f22edd949dd4a98a61`.
Its fresh reviewer evidence comprises the six-family browser proof, 42 complete
painter and 42 RGBA comparisons, 44 focused tests and independent lifecycle/lane
controls. That review does not cover this later CI delta. Its full foundation,
build and hook results remain inherited receipt evidence here; no new runtime
rebuild or broad browser qualification is claimed.

Final-delta independent review, final-head hosted CI, current-main freshness and
merge-queue acceptance remain required. There is no shipping, issue or milestone
closure claim. The unchanged module remains 1,895,754 raw /786,405 Node22 gzip6
bytes, leaving 27 bytes under the unchanged gzip cap.
