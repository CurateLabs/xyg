# Reflex retirement and replacement coverage (#1063)

## Retired framework contracts

The removed `python/reflex_xy/`, `examples/reflex/`, `tests/reflex_adapter/`,
`tests/reflex_geo_*_app/`, `scripts/reflex_ws_smoke.py`, and the five
Reflex-named geographic launch/transport scripts implemented support that no
longer exists. Their computed vars, registry/token lifecycle, plugin linking,
JSX wrappers, socket.io attachment cap, connection/session affinity, state
rebuild races and reconnect contracts retire with the implementation.

Wrapper source-text assertions in `test_example_apps.py`,
`test_tailwind_root_customization.py`, `test_wasm_tick_host_assets.py`, and lazy
adapter imports in `test_import.py` retire. `Chart.reflex_components` and its
API/type inventory entries retire; generic `chrome_components` stays covered.

## Preserved shared proof

- `tests/test_channel.py` preserves transport-neutral validation, exact pick,
  canonical box/lasso selection, semantic rows, clear, callback ordering and
  request identity. Widget/channel tests preserve the Python callback path.
- `tests/test_geo_host.py` retains bounded immutable identity and frozen
  camera; only registry/inline assertions were removed. Native live host,
  hierarchy and overview tests retain exact u64/i64 identities, thread
  settlement, staged ownership, failed hydration, ACK recovery and release.
- `tests/browser/geo_{live,live_hierarchy,native_overview}_host_test.mjs`
  retains Node/browser binary RPC, five mounts, camera/time edits, trusted
  keyboard navigation, native buffer lifetime and recovery. Notebook and
  VS Code journeys remain independent proof for their supported transports.
- `scripts/app_lifecycle_smoke.py` is the renamed FastAPI gallery smoke:
  resize, visibility, WebGL loss/restore, DOM slots and iframe paint remain.
- `scripts/append_stream_smoke.py`, Node `stream.test.mjs`, and generic
  payload-rehome tests retain tail-only uploads, prefix identity, pixel
  equivalence, coalesced refinement and DPR/range rebuilds.
- Tailwind/core customization and `tests/test_shared_glhost.py` retain
  shared-painter behavior. The historical internal GPU registry symbol remains
  stable; it is neither a framework import nor an adapter support promise.
- `scripts/wasm_html_ticks_smoke.mjs` and
  `tests/test_wasm_tick_host_assets.py` retain local worker/WASM URL admission,
  strict CSP and missing-asset failure proof outside the deleted JSX wrapper.

## New consumer proof

- `tests/test_streamlit_consumer.py`: four deterministic public chart families,
  actual Streamlit AppTest reruns, one iframe, SVG/PNG export and bounded inputs.
- `scripts/consumer_apps_smoke.py` and `.mjs`: real running Streamlit and Node
  apps, screenshots/pixel assertions, Streamlit rerun, Node trusted DOM brush,
  replacement/disposal/remount, SVG response, bounded request rejection,
  Rust WASM tick admission, and fail-closed missing-WASM behavior. The Python
  app runs without Node on PATH; the Node app runs without Python on PATH.
- `tests/test_dependencies.py`, `test_xyg_package_identity.py`,
  `test_verify_wheel.py` and `test_verify_sdist.py` reject the retired namespace,
  dependencies/extra and shipped files while retaining base/native diagnostics.
- `tests/test_verify_ci_workflow.py` rejects missing, skipped, softened or
  commented consumer gates and missing retained browser evidence.

## Integration with #1065

Main's new packaged Reflex application, `packaged_reflex_ticks_*` runners and
socket adapter assertions retire with the adapter. Its framework-free
`standalone_export.py` moves to `tests/fixtures/packaged_density_export.py`.
The required installed consumer gate now runs that fixture with the installed
wheel and the retained `packaged_density_export_browser.mjs`, preserving both
missing/corrupt inline-WASM HTML cases. Generic density tile/channel, Node,
WASM, spill, lifecycle and recovery checks remain, including binary XYDC
attachment forwarding in `test_density_tile_frames.py`. The release inventory
retains its public-surface guard and experimental Python classification while
removing the retired namespace and regenerating its snapshot through its tool.

The Streamlit iframe is a snapshot with browser-local interactions. It does
not replace the live Python callback, incremental append or geographic lease
transport. Those shared contracts stay in the tests named above; unsupported
Reflex-specific transport paths retire explicitly. Full release matrix and
GraphForge-specific Streamlit qualification remain with #54 and #1016.
