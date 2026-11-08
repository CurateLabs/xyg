# Browser-native modern CSS color bridge

Base: `af83f14c8cfbc05034076ba8378e4e56e91f0b37`.
Actual application evidence retained false fallback warnings for detached
construction. A separate connected-browser probe found the substantive defect:
valid `oklch()` and `color-mix()` computed values remain modern functions, while
the bridge only decoded computed rgb/rgba. Marks, tokens and ancestor backdrops
therefore used fallback colors despite the dossier §36 contract.

The existing browser theme bridge now asks the browser to convert non-rgb
computed colors through one private1×1 Canvas2D pixel per document into sRGB
RGBA8. It does not implement color-space mathematics or a second chart renderer.
Legacy computed rgb/rgba keeps its existing float alpha. Invalid literal
assignments warn and retain the supplied fallback; computed nonfinite channels
cannot become uniforms. Detached roots keep their existing stale-theme lifecycle
and heal on connection without falsely warning that valid input is malformed.
Native authoring validation, static export limitations and Rust policy remain.
No native/WASM ABI, feature, compiler, resource cap or scheduling change is made.

## Executed contract

`scripts/css_color_bridge_smoke.mjs` uses public composition/native-built binary
fixtures in `tests/fixtures/css_color_bridge.json` and the normal shipped client.
The ordinary full source foundation invokes it unconditionally; staged-package
and explicitly focused density runs retain their declared scope.

- Twelve modern mark inputs, including Lab/LCH/OKLab/OKLCH, sRGB/P3/linear color,
  mixed colors, missing components and transparency, match independent browser
  RGBA8 conversion and complete same-surface literal-control canvas bytes.
- Three ancestor backdrops match every byte of the1024-byte GPU palette lookup
  against an independent arithmetic oracle. At least100 fully opaque painted
  pixels must consume the expected dimmed color. Literal and modern lookup
  textures must match; comparisons never substitute only CPU paint metadata.
- Legacy alpha0.55 remains exact. Sentinel-valued colors, invalid literal
  diagnostics, one-pixel reuse, automatic CSS-variable updates, detached
  connection recovery and zero remaining chart DOM owners are asserted.
- Instrumented color changes upload no source geometry buffers. This is a small
  fixture check, not massive-scale frame-rate or total-memory qualification.
- The exact new harness rejects the hash-bound old client at the first modern
  mark-color assertion. Before/after captures use the same authored point.

The initial attempt to compare arbitrary-color circular edges found four
one-channel-level differing bytes. Repeated draws with **unchanged input and the
same lookup texture** reproduce them. The mark tests preserve complete exact
same-surface comparisons; backdrop tests establish complete exact GPU color
planes and opaque painted interiors, with full-frame hashes and repeated-frame
differences retained. They do not claim whole-image antialiasing/frame stability
for categorical dimming. No existing assertion, tolerance, deadline or cap is
weakened; that renderer qualification remains open.

## Reproduction

Use Node22, the installed Chromium, this checkout's explicit native405 library,
matching generated client/WASM artifacts and `TMPDIR=/var/tmp`.

```bash
node js/build.mjs
XYG_CHROMIUM=/path/to/chromium XYG_COLOR_REPORT=/path/to/report.json \
  XYG_COLOR_CAPTURE=/path/to/after.png node scripts/css_color_bridge_smoke.mjs
XYG_CHROMIUM=/path/to/chromium XYG_NATIVE_LIB=/path/to/libxyg_core.so \
  node scripts/wasm_foundation_smoke.mjs
```

`XYG_COLOR_CLIENT` selects an explicit client only for regression controls. The
normal foundation fixes it to its own current distribution. Supplying the
archived old client must fail, rather than silently using new assets. Browser
absence is a launch failure; none of these required cases is conditionally
skipped. Fixture generation uses the public Python composition API and native
`figure().build_payload()`; its exact producer script and input/output hashes
are retained with the evidence.

## Calibration and remaining qualification

[Plotly's documented template surface](https://plotly.com/python/templates/)
sets figure layout/data defaults; [Matplotlib's documented color inputs](https://matplotlib.org/stable/tutorials/colors/colors.html)
include literal colors and normalized tuples. This change addresses XYG's
separate runtime browser-CSS bridge. The attempted local Python input calibration
found neither comparison package in the borrowed environment, so no runtime
cross-library render, timing or superiority result is credited.

Only the recorded Chromium/SwiftShader environment is freshly qualified here.
Browser-only functions do not gain native/headless CSS-cascade, effective-theme
snapshot, HDR or wide-gamut output support. Conversion uses SDR sRGB RGBA8;
legacy RGB alpha precision is preserved separately. One pixel plus browser
context/object overhead is not a global Canvas2D/driver memory budget proof.
The intended60fps/100M-row/dashboard theme targets and broader hosts,
accessibility, massive/competitor acceptance, CI/queue and milestones4–7 remain
open. Earlier startup, Worker and antialiasing failures are not fixed by this
color conversion. Independent final review is still required.
