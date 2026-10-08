# Caller-owned WebGL2 geographic surfaces

This is the optional shell seam for issue #49. A geographic Scene is compiled
and prepared in Rust before reaching this seam. XYG reuses the ordinary
`ChartView` mark buffers, programs, vertex arrays, and point-pick pass. It does
not create a second geographic renderer or lower geometry in TypeScript.

## API and ownership

`createMapLibreGeoLayer({id, prepared, onCameraEvent?})` returns a structural
MapLibre custom layer (`type: "custom"`, `renderingMode: "2d"`). The application
supplies its own map object to `map.addLayer(layer)`. `prepared` is the existing
`XygWasmScenePaint` result of the Rust worker's `prepareScene` operation.

- `onAdd(map, gl)` uploads existing painter buffers into the supplied WebGL2
  context. It must belong to `map.getCanvas()`.
- `render(gl, options)` paints only when the map schedules a frame. It paints
  into the incoming draw framebuffer without clearing its color/depth/stencil.
- `setPrepared(prepared)` replaces the Scene transactionally and requests a
  map repaint. Failed validation/upload retains the previous Scene.
- `pick(cssX, cssY)` uses the existing direct-point pick framebuffer and returns
  the full Rust source identity as `bigint`, or `null`. Polygon/line policy
  interaction is not provided by this point-pick method.
- `onRemove()` releases XYG resources and listeners; it permits later re-add.
  `dispose()` also makes the handle unusable. Neither loses the owner's context.
- `onCameraEvent(event)` forwards the map's `move` event to the application.
  The application prepares a replacement through the Rust camera seam. This
  seam does not derive camera matrices, reproject features, or schedule draws.

The Rust viewport dimensions must match the drawing buffer through a uniform
pixel ratio, allowing one device pixel of CSS size rounding. An owner resize
suppresses stale paint/picks until a matching replacement is prepared.
The Scene must use a full viewport and GL marks without DOM
decorations; labels, legends, colorbars, annotations, or padded chart layouts
are explicitly rejected. Separate geographic decoration/interaction and camera
policy remain requirements of #49/#48. This shell alone does not close them.

The internal DOM stays detached and provides existing mark bookkeeping only.
No displayed overlay canvas, second WebGL context, resize observer, chart
gestures, independent animation frame, or context-governor registration is
created for a borrowed surface. Only the owner may resize or lose its canvas.

## State contract

Construction, replacement, color paint, picking, and live-context destruction
are enclosed in `withExternalGLState`. The guard normalizes required painter
state and restores it in `finally`, including separate draw/read framebuffer
bindings, program, vertex array and its element binding, array/pack/unpack
buffers, viewport/scissor, blend functions/equations/color, color/depth write
masks, clear color, pixel-store settings, affected texture/sampler units,
active texture, generic attribute values, and affected capability enables.
Pointer layouts/divisors reside in XYG-owned vertex arrays. An active transform
feedback operation is rejected before any mutation.

Context loss invalidates the view and makes picking return `null`. The owner
decides whether restoration is allowed; XYG does not prevent the loss event or
call `loseContext`/`restoreContext`. If still mounted, restoration rehydrates
the retained prepared Scene. Removal while lost releases bookkeeping/listeners
without attempting to recover a foreign namespace.

On borrowed surfaces, resolved Rust RGBA is converted directly to hex input so
the existing painter does not require an attached CSS resolver. Ordinary
attached hydration retains its CSS RGBA representation. Explicit painter
opacity is one because alpha is already resolved in Rust; this alpha contract
also applies to ordinary attached Scene hydration.

The integration follows the official [MapLibre GL JS v6.13.0 custom-layer
source contract](https://github.com/maplibre/maplibre-gl-js/blob/v6.13.0/src/style/style_layer/custom_style_layer.ts):
`render(gl, options)` receives the owner context and render inputs. The shell
provides no general state defaults beyond its documented blend/depth contract;
XYG supplies and restores the remaining state it needs.

## Reproduction and bounded evidence

The product never imports MapLibre or fetches a CDN. The test supplies the
official npm package, pinned to 6.13.0, from an isolated local directory. Keep
its BSD-3-Clause `LICENSE.txt` with any redistributed fixture. The test package
is not part of the default bundle or dependency manifest.

```sh
npm ci
node js/build.mjs
npm run build:wasm
mkdir -p /tmp/xyg-maplibre613
npm pack maplibre-gl@6.13.0 --pack-destination /tmp/xyg-maplibre613
tar -xzf /tmp/xyg-maplibre613/maplibre-gl-6.13.0.tgz -C /tmp/xyg-maplibre613
XYG_MAPLIBRE_DIST=/tmp/xyg-maplibre613/package/dist \
  XYG_CHROMIUM=/path/to/chromium node tests/browser/external_gl_test.mjs
```

`external_gl_test.mjs` builds the test entry from source in a temporary directory
without changing the product export entry. It serves only local ESM/worker/WASM
assets under strict CSP (`worker-src 'self'`, no blob/eval/CDN). The real Chromium
WebGL2 probe asserts hostile owner state survives construction, paint, picks,
replacement, upload failures, callback exceptions, teardown and owner context
restoration. Failed uploads leave no allocated XYG objects. Separate foreign
draw/read/default targets prove XYG paints the supplied target and preserves
basemap pixels. An actual MapLibre blank green map proves its scheduling,
same-context mark paint, source picks and removal without network map assets.

The generic alpha regression proof compares opaque red `[255,0,0,255]` and
half-alpha red premultiplied `[128,0,0,128]`; the inherited omitted-opacity
scatter default produced `[204,0,0,204]` and `[102,0,0,102]` respectively.

The local MapLibre package's ESM main is 1,079,357 raw bytes (286,225 gzip), its
worker 508,314 raw (144,092 gzip), and its shared module empty. These costs are
borne by applications choosing MapLibre; XYG adds none of them to its bundle.
This is ownership/correctness evidence, not a geographic scale/performance
benchmark, pitched-camera proof, or polygon interaction/decoration proof.
