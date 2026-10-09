# Combined input and typed ownership checkpoint

This checkpoint joins the reviewed pointer implementation, selected-overview
rejection guard and explicit selected hierarchy typed hosts with actual main.
`environment.json` and `source-sha256.json` identify the frozen source and actual
paired native/WASM/client artifacts. This is a new checkpoint; the parent
standalone reports remain their original measurements.

The Node and Python suites passed58 and43 tests. Raw conformance passed60
selected and34 ordinary hierarchy cases, with native/actual WASM byte parity.
The six-format snapshot probe passed with strict offline HTML. Actual Chrome155
passed the27-preparation trusted-input fixture and the existing five-view
recovery fixture. Type checking and generated-wire, ownership and CI checks
passed. Independent merge review verified every parent test registration and
explicit actual-WASM path, plus unchanged reviewed production implementations.

Reproduce the parent commands in `../README.md`, with the packaged WASM at
`packages/xy-client/dist/xyg-wasm.wasm`, then run the selected and ordinary
hierarchy conformance scripts and `geo_selected_snapshot_conformance.mjs`.
Node tests: `geo-overview-selected`, `geo-selected-hierarchy`, `geo-hierarchy`
and `geo-live-host`. Python tests: selected hierarchy, static selected hierarchy,
overview selected, ordinary hierarchy, live host, overview and host suites.
Set `XYG_GEO_OVERVIEW_WASM` explicitly for the paired overview tests.

The separate selected hierarchy live route remains under repair after a real
lost State-allocation reply exposed uncertain ownership. It is not included
here. This checkpoint establishes no massive latency, overview final paint,
domain membership or competitor performance win. M6 and issues50/39 stay open.
