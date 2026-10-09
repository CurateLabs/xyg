# Owned temporal overview integration

This checkpoint normally merges recovery981 `be43986d`, binary982 `060eebd5`,
and membership983 `555f1dd6` on public composition980 `b4d9f786`.
The integrated source hashes and raw controls are recorded here.
`client-build.json` preserves the complete verbatim build log as base64 with its
SHA256, including ANSI escapes and trailing whitespace.

All199 tracked compiler inputs are byte-identical to the reviewed recovery981
donor. The explicit native artifact is66c1a0b0404b0e32ea54a42e5e83b45611e4dd179f3aa45a6b4081fe9198ba12;
WASM227b582d0923f88349c5f188aada376828685d7cae10e36087443404dc81b388.
Unchanged raw1,496,127/gzip6 613,427 caps pass. The local editable-build native
artifact is not used as a substitute for this pinned pair.

Actual integrated controls pass:27 Node native/WASM domain-owner cases and full
four-page XYOM byte comparison,24 overview-owner cases,21 Python owner/member
cases, six allocation-recovery packets, actual strict-CSP accepted-frame binary
freeze, ordinary/borrowed public controller,216 workflow tests, generator checks,
client build and CI contract verification. Controller raw proof predates only
membership registrations; the final binary journey includes all three parents.
No external requests or CSP violations occurred in the browser journeys.

The existing paired test lanes now run the public membership suite; the existing
Direct browser foundation artifact retains its complete XYOM comparison report,
raw recovery report and accepted-frame binary browser report. No new job or
massive benchmark gate was introduced. Node exposes the member module through
its package subpath and includes it in the existing default test command.

The accepted-frame freeze validates2432 metadata bytes and the Scene32 header;
Rust owns full Scene compilation/import validation. Browser static formats remain
Unsupported. Public allocation owners still use nonce0 in this checkpoint;
unknown26–29/45 and snapshot6 guards remain, and durable host adoption is the
next separate slice. Native live-host overview presentation, final spatial
refinement, mixed linked playback and massive/competitor evidence remain open.

Reproduce after the standard native/WASM build, npm installs and client build:

```sh
node scripts/gen_geo_overview_hosts.mjs --check
XYG_GEO_OVERVIEW_WASM=packages/xy-client/dist/xyg-wasm.wasm node --test packages/xy-node/test/geo-overview-source.test.mjs packages/xy-node/test/geo-overview-members.test.mjs
uv run pytest tests/test_geo_overview_source.py tests/test_geo_overview_members.py -q
node scripts/geo_allocation_recovery_conformance.mjs
node scripts/geo_overview_binary_smoke.mjs
node scripts/geo_overview_controller_smoke.mjs
uv run pytest tests/test_verify_ci_workflow.py -q
make check-ci
```

Set `XYG_NATIVE_LIB` to the explicit native build and `XYG_CHROMIUM` to the
available system Chromium when needed. The raw JSON pins the actual Node and
Chrome versions; these are correctness and ownership controls, not timing wins.
