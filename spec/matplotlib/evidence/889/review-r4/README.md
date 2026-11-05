# PR #1096 review corrections

Greptile reviewed immutable `8d59d2270db316fe9274e723324d6804f5c053b0` and
requested changes in three threads: hidden axes showed decorations after null
tickers; Python/Node annotation coordinates returned different diagnostics;
compatibility prose named the wrong label strategy.

Before repair, all eight new native SVG tests failed for x/y, axis-off/Axis
visibility and NullFormatter/NullLocator. The independently authored Node
registry program rejected a nonnumeric x with the old message while Python
used the stable XYG prefix; that failed output is preserved too.

The adapter now preserves pre-existing `none` over label-only `off` for either
null ticker, including when independent minors are promoted. Tests compare
actual hidden-axis SVG decoration groups with the same hidden control and
inspect final compiled strategy. Python/Node numeric literal checks now use
matching stable coordinate diagnostics for nonnumeric/nonfinite values. Four
Rust registry cases pin exact x/y messages, generated from Rust and instantiated
independently in both hosts. No ABI/signature, painter, rendering tolerance or
resource gate changes. The only Rust change is rejection registry entries.

Compatibility prose and host-parity contracts now match null ticker behavior
and hidden-axis precedence. Existing historical review receipts are preserved.
Final commands, outcomes and hash bindings are recorded alongside this file.

Validation: required pyplot 1196 passed / 163 skipped / 26 qualified xfails;
make check-host-parity green with 1097 tests; focused pyplot/export/native-style
167 passed / 3 skipped / 4 qualified xfailed; typecheck passed; Rust registry
4 tests passed; standalone Node Scene 131 passed / 1 skipped.

The first standalone Node invocation omitted XYG_NATIVE_LIB and failed library
lookup; the log is retained. With the explicit development library, three old
annotation-message assertions failed (one coordinate message and two earlier
style-message changes). These now assert exact stable messages; the complete
Node Scene module passes. Those assertion-only changes followed the required
Python/host gate runs and affect no production source. Historical failure logs
are preserved. No full browser suite or new WASM build was needed for host
validation/adapter and registry-only Rust changes; packaged artifacts retain
their approved optimized binding. The generated mark-fixture side effect was
archived and restored. Fresh independent review and current-head CI remain
required before merge.
