# Generation-safe overview charts and required rendered CI proof

This correction preserves candidate `d56069f8c4cff1d7ffa5f9109694193e215c29f7` and its original receipts. Independent review found that overview chart requests bypassed generation cancellation and that the exact rendered comparisons were skipped by normal CI.

Rust now admits overview chart reads against the monotonic generation watermark, checks it again after bounded overview construction, and checks once more after copying C outputs before returning success. On refusal hosts discard every output. Success generation provenance comes from Rust, without host-stamping an older overview as accepted. The existing static `overview()` metadata API remains generation-independent. New ABI 401 entry `xyg_chunked_columns_chart_overview` preserves all earlier signatures; declarations are regenerated with the official generator. Emscripten refuses local-file operations.

Engine regression covers rejection before admission and supersession after bounded copying for both populated and empty overviews. Python and Node real-native tests reject older overview generations, accept the current generation with zero detail I/O, reject it after a newer cancellation watermark, and preserve static metadata access. Both host regressions fail before the repair.

The normal Python CI step exports its existing installed Playwright browser path as `XYG_TEST_CHROMIUM`. The four unmasked image/oracle comparisons now execute in the full pytest command. If a required browser is absent, the test fails instead of skipping. Workflow negative controls forbid removing the browser alias or required-browser setting, preserving the merge-group gate. A retained missing-browser run is an expected failure, not pass evidence.

Fresh focused engine, host, ABI, CI, rendered, type and metadata results and exact source/artifact/log bindings are recorded in `checks.json`. Earlier 1,992 workspace tests remain historical evidence; this successor does not claim to have repeated every prior suite. Rendered snapshots use the ordinary compiler/painter and the same full-scan pixel oracle. Native/WASM/client builds and packaging are recorded separately; caps and ownership remain unchanged.

This is a programmatic snapshot feature. Automatic gesture refinement, larger-than-RAM resource/latency proof, browser/WASM file orchestration, remote/spatial sources and complete #110/#109/#113/M7 acceptance remain open. Independent final review, PR/CI and queue delivery are pending. No publication or milestone closure is claimed.
