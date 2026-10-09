# Selected host conformance checkpoint

`conformance.json` records actual native383 and packaged wasm32 ABI33 execution
against engine source head `b583f6ab9`. The host codecs and fixture were pending
integration at capture; their exact source hashes are recorded separately. The
native and WASM artifacts were borrowed from the matching linked-state worktree
only after the engine/core/Cargo/config diff against that head was verified empty.

Run from this host slice after building matching artifacts:

```sh
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib \
XYG_SELECTED_REPORT=spec/performance/geo-selected-hosts-2026-10-09/conformance.json \
node scripts/geo_selected_conformance.mjs
```

`XYG_SELECTED_WASM` optionally selects the packaged artifact explicitly. The
fixture verifies exact native/WASM selected Scene and original-row packet bytes,
normalizing only process owner handles and the explicitly different indexed
publication sequence. It exercises full-u64 IDs, signed-minimum time, complete
XYSE intent, canonical/indexed owner replacement, private Rows continuation,
existing five-view16-handle/8-Data pressure, explicit engine parking, failed-page
recovery, outstanding-read cancellation settlement, cross-instance colliding
handles and effective selected-alpha picking for direct, cluster and density.

The report is correctness and ownership evidence. It does not establish massive
interactive latency, selected browser controller or selected notebook/Reflex/
VSCode journeys. Selected frozen exports remain explicitly Unsupported until
complete selected authority is represented in the frozen format.
