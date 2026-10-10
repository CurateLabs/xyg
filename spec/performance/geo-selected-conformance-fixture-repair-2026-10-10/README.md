# Selected raw conformance fixture repair

Base5909dc17f106fd1a7aef431e015f364eadc67d05. The old script attempted public
35/36 adoption through arbitrary raw WASM callbacks after public adoption began
requiring genuine captured dispatch. Scope cleanup masked that original fixture
error with ResourceLimit. The verbatim baseline failure is in `red.txt`.

The repaired fixture identifies only its raw WASM bridges in a private WeakSet.
Native controls still call real public `State.begin`. Raw35/36 use exact nonce0
Rust authoring, with existing canonical drive/prepare helpers. No fake transport
brand or product Frame is fabricated. A private consumed-State cleanup set is
updated only after strict actual Rust success/handle/sequence/reserved validation;
it prevents a stale fixture State owner from disposing a replaced Query/Data.
Actual raw35 State absence and raw36 IndexedQuery phase are asserted.

All original packet goldens, literal IDs/time, State rejection, selected counts,
five-view16-handle/8-Data pressure, explicit engine parking, row continuation,
failed-page recovery, cancellation settlement/ACK, alpha direct/cluster/density,
and two actual colliding WASM instances remain enforced. `native-wasm.json` and
`native-wasm.txt` are the complete repaired run. No product or CI change was made.

```sh
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
XYG_SELECTED_REPORT=/tmp/selected.json node scripts/geo_selected_conformance.mjs
```

All205 compiler inputs matched the immutable donor before copying. NativeSHA256
2310768d02d25b56579c3da358cc243f63629798a49cb7e652308d76c5c9d8f0;
WASMSHA2569923f65166ef898582f2fecd8b8864aaa8dc87a4ed6b6db49de84c4c4aae508d.
This is a fixture compatibility repair, not new M6 performance or completion evidence.
