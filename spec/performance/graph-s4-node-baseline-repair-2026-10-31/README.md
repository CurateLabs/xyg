# Node baseline test-harness repair

This append-only receipt is based on
`7c02d3df0e769e945ae171f90906f9b17acfc65f`. Its broad Node run recorded
1,477 passes, six failures, ten cancellations and two existing skips in
`../graph-s4-ci-repair-2026-10-31/full-node.txt.gz`. That record is unchanged.
Only three existing test files and this new receipt change here. Production,
generators, assertions in ABI/ownership gates, ABI versions, budgets and
shipping assets remain unchanged. This establishes no M4, S5 or release
acceptance; independent final review belongs to the parent.

## Before proof and cause

The preserved pre-S4 checkout is
`80af7df777562605b7ce0bea240c3538a7ebfca7`, with native ABI 396 library
SHA-256 `cef2c70e0d1e0e2f5d26ab8e7e0b5b3a519abe324d549bd56c5a39eafa3fa0ea`.
Its original `graph-s3-review-repair-2026-10-31/results.json` binds that binary.
`pre-s4-before` reproduces all six exact assertion failures with that original
binary and its matching host declarations. `pre-s4-hierarchy` additionally
reproduces four failures and ten cancellations in the complete hierarchy file.
Neither run changes the preserved checkout or replaces any assets.

Twelve relevant test/product files were byte-identical between that checkout
and the untouched repair base; `evidence.json` records each hash. The geography
fixture uses the native bridge, so this before proof needs no WASM substitution.

Hierarchy owners deliberately capture bound transport functions when created
(`geo-hierarchy.js`, `geo-hierarchy-wire.js`). The tests replaced
`bridge.execute` afterward, so operations 43/44 bypassed their counters and
fault hooks. The publication barrier was never reached; its pending test
cancelled the ten subsequent cases. The repair installs stable forwarding
functions before owner construction and changes private test targets later.
The real native entry point is restored before the public host's identity
check, and no production check is altered. Target setters also cover later
captures. Real operations still execute through the existing native bridge.

The formerly cancelled close-during-26 case also replaced a cleanup callable
after an authentic retained owner captured it. It now retains the real native
26/read barrier and wraps that genuinely issued owner's public `dispose`
method to refuse once. Assertions prove exact retained-owner identity, a new
native handle, one initial refusal, later retry, disposed data and lane reuse.
This proves host retry ownership; it does not claim a native disposal failure.

The geometry expectations were stale relative to existing authority:

- `constantMarkColor` ignores a string `color_ch` and takes the style/default
  fallback, matching Python `_scene_observations._constant_color` and Rust
  `scene_constant_color_admit`. Tests retain invalid object-channel rejection
  and add an explicit style fallback distinct from the ignored string.
- Rust admitted per-item scatter `size` in ABI 386 / PR #1031
  (`126733f655aa83532254060b3501968c292bd6cb`). The test now includes `size`
  among allowed names, retaining symbol/unknown rejection and checking exact
  spelling with rejected `SIZE` and leading-space variants. See dossier §29
  and `host-parity.md`'s scatter size contract.

## Results and boundaries

`focused-pass` runs both affected files: **212 passed**, zero failed,
cancelled or skipped. Actual 43/44 counters, lost 33/43/44 replies, uncertain
33/43 cleanup, post-publication cancellation, real anchor retention and six
canonical/indexed/hierarchy lost/corrupt allocation cases all execute.
Lost-reply assertions explicitly require the injector to have run.

`full-node` runs every `packages/xy-node/test/*.test.mjs` file under actual
Node 22.23.4 with concurrency four: **1,493 passed, zero failed, zero cancelled,
two existing skips** out of 1,495 cases. The packet-storage identity-failure
case and heatmap fill-opacity (#889) remain explicitly skipped by their existing
tests; neither is changed or counted as a pass here.

Three intermediate repair runs remain visible: `focused-after` exposed the
native entry-point identity guard when a wrapper remained installed;
`focused-native-identity` exposed the unreachable old anchor-disposal hook;
`focused-final` rejected an overstrict new disposal-call count. Cleanup is
idempotent and the host may retry more than once, so the final test requires
at least one retry plus actual disposed data. No failing log was overwritten.

The runner retains exact argv, exits, elapsed wall time, raw logs and gzip/hash
pairs. `evidence.json` binds the final three test sources, preserved binaries,
unchanged product controls and raw results. Native ABI remains 398 and the
existing production WASM is untouched. No compiler build, package operation,
remote mutation, publication or budget change is part of this repair.

## Reproduction

Select the recorded Node 22 binary and this checkout's existing native build:

```bash
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
node --test --test-concurrency=1 packages/xy-node/test/geo-live-hierarchy-host.test.mjs packages/xy-node/test/geom.test.mjs
node --test --test-concurrency=4 packages/xy-node/test/*.test.mjs
```

`run.py NEW-NAME COMMAND ...` captures a fresh reproduction and refuses an
existing command name. The exact original before commands and explicit
pre-S4 library path are retained in their command JSON files. Full repository
hooks and Ruff results are retained before the narrow commit. Final commit
and complete canonical diff hash are reported in the parent handoff to avoid
a self-referential receipt.
