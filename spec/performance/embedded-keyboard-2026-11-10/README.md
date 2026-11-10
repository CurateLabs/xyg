# Embedded keyboard coordinates and event ownership

Parent: `15053cd5345373337d6070bd3902268c8fa8110f`.

Two shared-client defects were reproduced while exercising a real VS Code
Jupyter notebook. An exact-value reply reused a keyboard readout's old viewport
coordinates after its output moved. Enter/Space also reused that cache. Separately,
handled plot keys prevented the default but continued bubbling; the installed
VS Code host forwarded Enter into its cell-edit command and expanded the input.

The client now projects the focused point against the current canvas rectangle
for keyboard exact replies and activation. Pointer-owned replies keep their
physical viewport coordinates. Traversal reuses the same projection helper and
retains its finite/polar-culling and edge-clamp behavior. Handled traversal,
enabled activation and dismissal keys stop propagation. Disabled activation,
unhandled keys and Tab retain host behavior. Sequence invalidation, transition
suppression and the single keyboard live announcement remain enforced.

The existing required `scripts/browser_conformance.mjs` tests ancestor movement
before an exact reply, another movement before Enter, and physical pointer
ownership after another movement. It compares both public click events and
transport messages. Actual keyboard input checks that handled keys stay local,
while `q` and Tab bubble and Tab moves focus. Existing semantic, stale-response,
transition, toolbar, reduced-motion, layout and pixel checks remain intact.
No CI command, browser requirement, timing ceiling or pixel tolerance is relaxed.

Reproduction after the normal client build:

```sh
node js/build.mjs
XY_CONFORMANCE_HEADFUL=1 LIBGL_ALWAYS_SOFTWARE=1 MOZ_WEBRENDER=1 \
  WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1 \
  xvfb-run --auto-servernum --server-args='-screen 0 1280x720x24' \
  node scripts/browser_conformance.mjs --browsers=chromium,firefox
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" TMPDIR=/var/tmp \
  uv run --no-sync pytest -q tests/test_accessibility_contract.py \
  tests/test_view_state.py tests/test_channel.py tests/test_graphforge_contract_corpus.py
```

`checks.json` binds source history, exact runtime artifacts, commands, actual
exits and archived outputs. The ESM and IIFE clients were rebuilt normally.
Native/WASM code, ABI, exports, compiled inputs, worker and package limits remain
unchanged. Earlier qualification is inherited only for unchanged identities;
these runs establish no speed, massive-data or total-memory improvement.

The final assertions reject the exact parent client, the intermediate
coordinate-only client, and a current-client counterfactual that removes only
activation rebasing. Chromium and headful Firefox pass. Local headless Firefox
failed WebGL2 admission; WebKit could not launch because system libraries are
missing. Those attempts remain failed and receive no local pass credit. The first expanded
contract run also failed the real CRLF checkout because the newly bound
accessibility test lacked an LF pin; that pin and a hook formatting change are
now included. The failed run is preserved separately. Required
hosted cross-browser checks remain necessary.

The existing strict JupyterLab 4.6.5 routed-identity journey passes with the new
client. Its initial unconfigured invocation lacked a Jupyter executable and
failed; the explicit existing environment rerun is bound separately.

## Actual VS Code diagnostic, with qualification still pending

The private normal-GUI prototype completed the unchanged ten-cell public fixture
in VS Code 1.103.2, Jupyter extension 2025.7.0, Python 3.11.17 and anywidget
0.11.0. It observed first/intermediate/final paint, trusted unfinished keys,
pointer and wheel, five canonical edge callbacks, delivered GPU UUID masks,
layer/result/row identity, public Node parity and disposal. Read-only CDP
inspection bound the actual isolated ChartView module bytes to the built ESM;
it neither enabled shared contexts nor changed the renderer/prototype. Real
workbench screenshots were used, not discardable-framebuffer readback.

This is supporting diagnosis, not a newly qualified frontend cohort. The normal
strict notebook verifier intentionally rejects its unsupported frontend schema.
A committed reusable VS Code notebook driver and strict host-specific verifier
remain necessary. The host fetched supporting bootstrap resources (including
RequireJS from jsDelivr); no offline or zero-external-traffic claim is made.
Only public kernel/server-selection APIs were used, without the Python extension.
NbClassic 1.3.3 served unmodified installed widget scripts with byte checks.
Private authentication tokens, kernel connection files, profiles and X cookies
are excluded from evidence archives.

Earlier prototype failures remain failed: selector/kernel admission mistakes,
unauthenticated XSRF refusal, missing Notebook7-only widget assets, test-mode
modal refusal, incorrect frame/coordinate adapters, black discarded-framebuffer
readback, shared-context inspection on isolated views, and a partial request-file
write. The successful prototype uses atomic request/reply renames and exact new
graph-instance targeting. It establishes no blanket startup/Worker reliability
repair. Host-source inspection, screenshots and logs are individually bound;
none substitutes for the missing reusable host qualification.

#1015 and milestones 4–7 remain open. Newer Notebook7, full VS Code qualification,
graph-specific brush/edge policies, derived/aggregate/compound notebook routing,
selected exports, full notebook scale ladder, accessibility, platforms, resource
budgets and competitor/performance acceptance remain outstanding. This correction
requires independent final-diff review, current-main freshness, hosted checks and
the repository merge queue before integration.
