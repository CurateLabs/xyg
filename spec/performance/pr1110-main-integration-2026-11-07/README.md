# PR1110 integration with accepted main

This append-only successor integrates accepted main
`084b3c1b7c393e135476aab9610bf8334767b2ac` and final PR1110 source
`6c81d68e93378429c4549442b8700091e22e128d` with a two-parent merge.
The only textual merge conflict was the generated API inventory, resolved by
`uv run python scripts/check_release_inventory.py --write`. Both integrations,
CI commands, specifications and historical evidence remain present. Current Core
bindings point to this successor; additional LF rules protect the newly bound
main evidence in a real Git CRLF checkout. Historical bindings are unchanged.

The actual JupyterLab/IPython/anywidget/Chromium journey runs against the combined
source, selects the hash-verified ABI401 native library, delivers the final
pointer callback and passes the exact CI report-verifier invocation. This is
fresh execution, distinct from the earlier hosted-report replay. Compressed raw
logs, reports and original PNG captures are bound in checks.json. Both notebook
executions are retained. No ACK hold, sleep, tolerance, report-field injection,
ABI rollback or verifier/gate relaxation was introduced.

All 244 tracked Rust/Cargo inputs match the native producer before copying its
verified library. The separately verified raw WASM producer has identical
Rust/Cargo inputs; the existing packaging producer reproduces shipping WASM
SHA256 7bce0525a9688ae051ef0f13d9f55da1a1e9fef08b2449993673e8811aada3a1.
An initial setup attempt supplied already optimized WASM to the packaging
producer, optimizing it twice. That local attempt is retained; the corrected
raw input reproduces the required artifact. Browser bundles are built from the
final combined source and are generated, ignored files.

The first affected Python run exposed absent LF rules for newly bound main
files; the corrected real Git CRLF control passes. The full Node suite retained
1062 passes, two skips and one worker-lifecycle assertion failure (expected pack
record). Its isolated unchanged test passes. The timeout scenario has a 500 ms
wall budget and can retire before packing under contention; no budget or test
was changed. These failures remain in the raw evidence rather than being
reclassified as a fully green original run. See checks.json for every command,
exit, source and artifact hash and subsequent scoped results.

No source producer checkout was edited. No push, PR write, watch, publication,
issue closure or milestone acceptance was performed. Independent parent review
of the complete combined diff, including the verifier correction, remains
pending. Broader #110/#109/#113/M7 and whole milestones remain open.

Final focused controls: 163 Python passes with five skips (four Python 3.12
buffer-callback cases and the separately exercised optional browser case),
59 notebook tests, 58 Core/ABI-transition controls including real CRLF checkout,
37 affected Node controls including the complete worker-layout module,
six browser-transport controls, 673 native ABI smoke assertions and one explicit
chunked-chart Chromium render. The authoritative generated ABI declarations,
capability matrix and regenerated API inventory are current. Both fresh
notebook journeys and both exact CI verifier calls passed. The final journey
progressed from step 9 to 300, with final pointer callbacks increasing 1 to 2.

All 12,538 pre-existing performance/release evidence and fixture files are
byte-identical to the source parent (the regenerated API inventory is the
explicit exception). Runtime sources under Python, Rust, browser TypeScript,
Node hosts, the CI workflow and the notebook verifier are byte-identical to
6c81d68; accepted main contributes its tests/specification/evidence. Final
full-worktree hooks, Ruff lint and Ruff format checks pass.

`make check-ci` passed the workflow/merge-queue invariant checker and all 772
contract tests. Final full-worktree hooks and Ruff checks are required again
before the integration commit. Prior failed/interrupted attempts remain retained;
this receipt makes no claim of a green full Node suite or full Python suite.
