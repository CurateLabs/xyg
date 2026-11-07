# Indexed private publication and native binding typing correction

This correction follows lifecycle commit `8cc86ec3` without rewriting earlier
receipts. All ten original-candidate type diagnostics are resolved: the binding's
heterogeneous typed-request mapping is declared as a dictionary, and spatial
and hierarchy source overrides accept the existing internal `_publish` keyword.
The original dictionary values and Rust validation remain unchanged. No checker
rule, admission budget, type-error suppression or runtime validation is weakened.

The override error was also a runtime regression: ordinary public indexed chart
compilation passed `_publish=True` to overrides that rejected the argument.
The retained existing public-chart test fails before this correction. Four new
public composition controls fail before the repair across spatial/hierarchy and
sync/async modes. They now prove that private compilation returns an independent
frame and preserves `current`, while default compilation publishes the new frame.
Scenes and native feature identities remain equal. This grants no new temporal
binding admission to indexed/hierarchy sources, which remain out of scope.

Fresh validation: `uv run ty check` passes, as do 55 existing and new focused
geographic tests. Commands, raw failures/successes and source/artifact bindings
are in `checks.json`. Native Rust and client producers are unchanged and their
artifacts are reused by digest. No browser, WASM, massive-scale or frontend
acceptance is implied. Final current-main integration, independent review,
CI and merge-queue delivery remain pending. #50/#39/M6 remain open.

```sh
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so uv run pytest tests/test_geo_temporal_binding.py tests/test_geo_spatial.py tests/test_geo_hierarchy.py tests/test_geo_retained.py tests/test_geo_retained_components.py tests/test_geo_hierarchy_static_selected.py -q
uv run ty check
uv run pytest tests/test_graphforge_contract_corpus.py tests/test_release_inventory.py -q
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```
