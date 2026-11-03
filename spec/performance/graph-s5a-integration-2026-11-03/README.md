# S5a integration onto accepted M4 foundations

This receipt records a normal merge of independently reviewed S5a child
`629101e0e750dadb68bab2750d4c5e87191789cd` onto accepted main
`030c79062138bb8287df2dc93ab6fdc0ecc8747b` (merged #1083 and #1084).
It does not complete S5b, #35, #36, #934, #1015, M4, #108, or publication.

## Integration controls

The five Rust product/test deltas are exactly the reviewed child deltas against
its `1044cdf2175d57dbed2c5088f747f812a982dc08` base. The Node replay source equals
the reviewed child plus accepted main's unchanged standalone-temporal regression.
All unrelated accepted-main source, generated native ABI 398 declarations,
fixture metadata, Node scheduling/cache work, temporal arena repair and strict
WASM-manifest harness checks are retained. Historical squash-ancestry conflicts
were resolved by preserving accepted main and applying only S5a changes.
The browser specification retains both the accepted S4 notes and additive S5a
notes; the S4 status now records its actual merge. No history was rewritten.
`integration-control.json` verifies all 2,831 accepted-main performance files
against their Git blobs. The old child receipt is retained unchanged.

## Proof status

Fresh native and client builds pass. The real production producer under the
old hard gates fails at 764,063 gzip6 bytes (limit 759,808). The separately
labelled production-optimizer measurement is 1,872,541 raw / 764,063 gzip6,
11,933 / 4,255 over the old limits. All six actual native/diagnostic-WASM replay
tests pass with zero skips, including accepted-main standalone-temporal staging.
No diagnostic asset is substituted for production packaging.

The later, separately reviewed [package decision](../graph-s5a-package-budget-2026-11-03/README.md)
retains the required functionality with minimal next-KiB hard limits and real
production/paired-asset/full-foundation proof. Historical child measurements
continue to describe their own source; no old receipt is rewritten.

Fresh focused verification passes: 125 Rust interaction tests, 67 native core
tests, 73 WASM adapter tests plus five integration tests, 42 Python
session/generator/ownership tests, 673 native ABI checks, current official
native/WASM declarations and all-target warnings-denied Clippy. Ownership
classifies 502 production paths. The first Python invocation named a nonexistent
ownership test file and collected no tests; its command failure is retained,
then corrected to the actual test_verify_ownership.py without assertion changes.

`run.py` selects Node 22.23.4, Rust 1.96.0 and cached Chromium 156; command JSON
retains exact argv, exit status, timing, raw-log hashes and deterministic gzip
logs. Each command name is append-only. Artifact provenance remains uncommitted
until captured explicitly; `artifactCommit: null` must be preserved for such
proof. Compiler, profile, optimizer, ABI/export contracts and resource admission
are unchanged by this integration.
