# Bounded public43 admission recovery

Python and the shared TypeScript/mechanically generated Node owner now adopt the
existing43 exact-request journal. An authentic producer reply and47 Confirm
precede Query I/O. Canonical authoring metadata remains nonce0. Unknown accepted
admission keeps the same issued operation; exact recovery does not restore State.

The proof covers9 focused Python tests,18 Node tests,61 broader Python tests,
77 broader Node tests and actual Chrome155 offline/CSP Worker execution. The
Worker controls inject lost/corrupt successful43 replies, corrupt Confirm,
twelve microtask mutation timings, a colliding foreign Worker State, cancelled
borrowed-page settlement and lost Query10. The last case deliberately stays
guarded. It is not a physical-absence classifier. Raw callback WASM bridges are
explicitly untrusted for typed admission; their negative control keeps State
consumed and the operation uncertain. Native Point/MultiPoint, reduced complete
membership, five lanes, Rows and frozen-output controls remain covered.

All206 compiler inputs match the pinned donor. No Rust, ABI, quota, compiler
profile or package cap changed. The84 complete authenticated raw engine packets
are byte-identical to the committed opt-in oracle; the comparison normalizes
nothing. The oracle remains in
[the engine evidence](../geo-hierarchy-recovery-2026-10-10/README.md). The full
packet report is hash-linked in `engine-packet-comparison.json`; its original
bytes are already committed there. The old nonce0 engine controls are unchanged.

`environment.json` pins the exact borrowed native and WASM paths/hashes. Raw WASM
is1505822 bytes; gzip level6/mtime0 is618706 bytes under unchanged1507328/622592
caps. Browser test entry bundling is test-only and shares one genuine private
module graph. Generated client bundles remain ignored. Source hashes include
production, fixture, generator and focused tests; review reports are retained
alongside writer results. `legacy-native-mode-red.txt` records the broader test
that caught async-from-native lane cleanup awaiting synchronous bytes; captured
native functions now run via the owning async mode, with issuer identity None
preserved. The original failure is retained rather than relabeled green.

Reproduce from the repository root with dependencies installed:

```sh
export XYG_NATIVE_LIB=/absolute/path/to/verified/libxyg_core.dylib
export XYG_HIERARCHY_WASM=/absolute/path/to/verified/xyg-wasm.wasm
uv run pytest tests/test_geo_hierarchy.py tests/test_geo_selected_hierarchy.py tests/test_geo_selected.py tests/test_geo_selected_publication_hosts.py tests/test_geo_overview_recovery.py tests/test_geo_hierarchy_static_selected.py -q
node --test packages/xy-node/test/geo-hierarchy.test.mjs packages/xy-node/test/geo-selected-hierarchy.test.mjs packages/xy-node/test/geo-selected.test.mjs packages/xy-node/test/geo-selected-publication-hosts.test.mjs packages/xy-node/test/geo-overview-recovery.test.mjs
node scripts/gen_geo_hierarchy_node.mjs --check
node scripts/gen_geo_selected_wire.mjs --check
node scripts/gen_geo_overview_hosts.mjs --check
node js/build.mjs
cp "$XYG_HIERARCHY_WASM" packages/xy-client/dist/xyg-wasm.wasm
XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' XYG_HIERARCHY_ADMISSION_REPORT=/tmp/hierarchy43-worker.json node scripts/geo_hierarchy_admission_hosts_smoke.mjs
XYG_SELECTED_HIERARCHY_WASM="$XYG_HIERARCHY_WASM" XYG_HIERARCHY_RECOVERY_PACKETS=/tmp/hierarchy-engine-packets.json node scripts/geo_hierarchy_recovery_conformance.mjs
```

Public44 retains its separate legacy uncertainty guard and generic-kind fallback
debt. Lost Query10, massive latency, broad linked-view interaction and browser
static hierarchy adoption are not completed by this proof. No new framework,
selection algorithm or geometry policy lives in these hosts.
