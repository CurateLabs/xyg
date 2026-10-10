# Public selected19 publication: bounded lifecycle evidence

This unmerged adapter checkpoint builds on frozen selected35/36 PR996. It uses
an unchanged, source-verified205-input Rust/native/WASM core. `environment.json`
pins the immutable donor paths and hashes; `compiler-inputs.json` lists every
compared compiler/build input. `source-hashes.json` identifies the exact dirty
host source/test/spec checkpoint that produced the reports. This is lifecycle
and correctness evidence, without latency, massive-data or milestone claims.

`node-tests.txt` has10 new native controls; `python-tests.txt` has9 native
controls. Final broader runs have72 Node and37 Python passes. Controls cover
lost19 and Confirm, actual read23 failure and its two-read quota, lost successful
Data10, lost Forget, whole-flight close/repeated cancellation, concurrent Frame hook singleflight,
failed-hook retry, immutable
original producer/budget,20 sequential publications at unchanged16-live banks,
independent retained Rows/hierarchy/Frozen authority, and private issuer forgery.
The changed Style48 binding control verifies genuine SourceStale nonadmission
followed by publication from the same complete Query with its original style.

`browser.json` / `browser.log` are actual Chromium155, two real WASM Workers,
offline strict CSP and the genuine constructor-issued transport. Lost/corrupt19,
corrupt Confirm, read retry and12 queued-microtask receipt schedules preserve
exact source/sequence/fullu64/i64 authority. The Rust-owned selected Scene paints
opaque green; the retained old accepted Scene paints opaque red. Twenty
additional sequential publications reclaim the bounded host/engine banks. The
two Workers have colliding numeric handles; foreign private-State claims are
covered by the prior35/36 checkpoint, rather than claimed as a new19 negative.

`frame-hook-red.json` is a reproduced production defect: simultaneous Frame
close calls invoked a gated hook twice. The subclass now shares one shielded
task across retirement and hooks; actual native cancellation and hook-retry
controls pass. Root browser and second reviewer Node reports independently
verify the unchanged JavaScript/Worker source; final Python proof includes the
subclass repair.

The two `*-oracle-red.json` logs preserve errors in the additional test oracle,
not production red/green evidence. Preparing an incomplete Query produced genuine
native-1, which remains uncertain; a changed Style48 binding produced genuine
native-10, rather than the incorrectly assumed-9. The final test drives first,
checks the actual-10 contract, then publishes successfully. No rejection
classifier was broadened to accommodate either mistaken expectation.

Reproduce from this worktree after installing its pinned toolchain:

```sh
export XYG_NATIVE_LIB=/tmp/xyg-m6-durable-frozen-artifacts/9923f65166ef898582f2fecd8b8864aaa8dc87a4ed6b6db49de84c4c4aae508d/libxyg_core.dylib
node --test packages/xy-node/test/geo-selected-publication-hosts.test.mjs
UV_NO_SYNC=1 PYTHONPATH=python uv run pytest tests/test_geo_selected_publication_hosts.py -q
node scripts/gen_geo_selected_wire.mjs --check
node scripts/gen_geo_overview_hosts.mjs --check
node scripts/gen_geo_hierarchy_node.mjs --check
node js/build.mjs
cp /tmp/xyg-m6-durable-frozen-artifacts/9923f65166ef898582f2fecd8b8864aaa8dc87a4ed6b6db49de84c4c4aae508d/xyg-wasm.wasm packages/xy-client/dist/xyg-wasm.wasm
XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' XYG_SELECTED_PUBLICATION_REPORT=/tmp/selected19.json node scripts/geo_selected_publication_hosts_smoke.mjs
```

Use the local approved Chromium path where appropriate. Genuine native/Worker
outcome scopes grant adoption; arbitrary raw callbacks do not become producers.
Hierarchy43/44 host journal adoption, MemberData10 retirement and complete
massive-data/multiple-view evidence remain separate gates. Tracker closure is
not proof of those gates.
