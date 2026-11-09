# Selected hierarchy temporal remount sequence floor

Base: `d7019c6cafccfa9693ae095ab2e51e6f2f8fe873`.
A real public Node temporal host failed after cancelling a prepared selected
hierarchy replacement and releasing/reopening the browser mount. The lane had
consumed sequence 21, accepted paint still named 20, and XYHT advertised the
original retained source's sequence 2. The fresh browser reused 21; Rust correctly
rejected the different query as stale. The failed run and its secondary cleanup
error remain recorded.

Python and Node live hosts now retain the highest structurally valid desired
sequence alongside their camera/time revision floors. This bounded authoring
highwater survives mount release and candidate abort. Cursor/range XYHT packets
advertise its maximum with the original source counter. Rust query admission,
exact replay and ownership rules are unchanged; the accepted frame and caller's
source publication do not advance merely because a preparation was attempted.
No Rust, native ABI, WASM, browser renderer, resource cap, default, deadline or
serialization format changes.

The regression uses actual selected hierarchy queries, abort, remount and a
subsequent native preparation above the advertised floor. Python and Node compare
the complete 56-byte cursor/range packets with shared golden bytes. Malformed
camera framing carrying a maximum-u64 sequence cannot poison the sequence
floor before the valid native operation. The small
unit transport completion only clears a synthetic control token; it does not
qualify visual acknowledgement. The separate strict-CSP Chromium journey uses
real HTTP/native/ChartView Prepare/CAS/RetireACK and release acknowledgements.
Every observed accepted publication retains privately issued hierarchy authority
and complete selected u64 intent, including empty frames.

`XYG_GEO_HIERARCHY=1 node tests/browser/geo_mounted_temporal_test.mjs` runs the
new two-row finite-interval hierarchy fixture through the existing browser
journey. It covers exact picking, pointer/keyboard camera composition, held reply
supersession, i64 extrema, half-open range membership, storage failure retaining
paint, drain failure/retry, binding disposal, remount, independent caller frames,
controller destruction and final native cleanup. The existing CI native-host
step invokes it unconditionally without changing its 5-minute timeout. Canonical,
aggregate and indexed modes retain their existing assertions.

The old Python temporal framing fails both final cursor/range regressions. The
old Node temporal framing, isolated through an otherwise identical native host,
reproduces the stale-query browser failure. Failed diagnostic paths and the
BigInt report-serialization error are retained separately from successful product
runs. Earlier exploratory notebook evidence at 7cfd used a separately started
Jupyter server and does not qualify this source or repair cold startup.

`checks.json` records exact commands, artifacts, sources, predecessor bytes,
results and evidence scopes. The 324 compiled/configuration/optimizer inputs and
eight archived native/WASM/browser artifacts remain base-exact; their combined
runtime qualification is inherited only over unchanged bytes. This host framing
repair is freshly tested and does not inherit an unearned product approval.
The module remains 1,895,719 raw /786,385 Node22 gzip6 bytes, with 47 gzip bytes below
the unchanged cap. No compiler rebuild or 72 GB scan was performed.

Remaining: independent final correction review, current-main freshness, hosted
CI and mandatory queue; actual hierarchy VS Code/Jupyter remount qualification,
five simultaneous automatic bindings, mixed tiles, global budgets, broader
accessibility/scale/competitor acceptance and all issue/milestone closure.
Earlier server startup, timer-order and disposed-Worker failures remain
unresolved. This fixes the reproduced sequence reuse, not every stale-handle or
host reliability failure. No remote action has been taken for this candidate.
