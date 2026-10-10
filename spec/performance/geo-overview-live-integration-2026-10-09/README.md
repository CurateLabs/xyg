# Reviewed live overview integration

Normal ancestry includes the reviewed public recovery, membership recovery and
native host parents in `environment.json`. No Rust, ABI, quota, native/WASM
artifact or product policy changes in this integration. All 199 compiler inputs
match the retirement donor, and both artifact hashes are checked before use.

The combined source passes 136 Node native/WASM tests, 79 Python tests and 216
workflow cases. The actual strict-CSP browser proof covers the existing shared
Rust painter, nonfinal temporal counts, pending and failed replacements, exact
CAS/retirement, focus, lost-commit recovery and producer disposal. Per-parent
notebook, production Reflex and VS Code receipts are linked from the capability
matrix; they are bounded functional evidence, not performance measurements.

The two obsolete host-Unsupported assertions now verify independent host
retention and caller survival after host close. Six native export assertions
and all other failure controls remain. New tests and the native host browser
report are registered in the existing CI lanes and artifact, without a new job.

```sh
node js/build.mjs
XYG_NATIVE_LIB=/absolute/path/to/libxyg_core.dylib XYG_GEO_OVERVIEW_WASM=/absolute/path/to/xyg-wasm.wasm node --test packages/xy-node/test/geo-overview-source.test.mjs packages/xy-node/test/geo-overview-recovery.test.mjs packages/xy-node/test/geo-overview-members.test.mjs packages/xy-node/test/geo-overview-members-recovery.test.mjs packages/xy-node/test/geo-native-overview-host.test.mjs packages/xy-node/test/geo-host.test.mjs packages/xy-node/test/geo-live-host.test.mjs
XYG_NATIVE_LIB=/absolute/path/to/libxyg_core.dylib uv run --no-sync pytest tests/test_geo_overview_source.py tests/test_geo_overview_recovery.py tests/test_geo_overview_members.py tests/test_geo_overview_members_recovery.py tests/test_geo_native_overview_host.py tests/test_geo_host.py tests/test_geo_live_host.py -q
XYG_NATIVE_LIB=/absolute/path/to/libxyg_core.dylib XYG_CHROMIUM=/absolute/path/to/Chrome XYG_GEO_NATIVE_OVERVIEW_REPORT=/tmp/overview-browser.json node tests/browser/geo_native_overview_host_test.mjs
uv run --no-sync pytest tests/test_verify_ci_workflow.py -q
make check-ci
```

The first workflow test invocation named a nonexistent plural filename and ran
no tests; the corrected command above produced the preserved 216-case result.
Default overview show remains static. Lost MemberData10,35/36 public mutation,
unknown snapshot allocation, final spatial refinement, linked-view automation,
massive five-view/phase measurements and competitor evidence remain separate
M6 gates. This aggregate does not close #39 or the milestone.
