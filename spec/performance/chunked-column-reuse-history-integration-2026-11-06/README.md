# Bounded chunk reuse and frozen-history classification integration

Normal merge parents: cache candidate
`7c5ebc655ba9c8f2cb20037811246da6e01fbcd3` and PR1101 correction
`43b99bebcfa2c1c499d16af815d5109649643296`. The earlier chunk-validation
repair `82fab9c1` is shared ancestry. This integrates the two disjoint changes
without rewriting either producer receipt. Cache product code, its specs and
tests remain byte-identical to the cache parent; naming classification remains
byte-identical to the correction parent. Independent review must cover both
deltas before delivery.

`bindings.json` records the combined source hashes, original receipt bindings
and reused native artifact. Mandatory full-worktree hooks and Ruff checks run
before committing the merge. This integration adds no new runtime behavior or
scale/issue/milestone acceptance claim. #110's public lifecycle, browser/WASM,
remote/spatial and larger-than-RAM evidence and the remaining M7 exits remain
open.
