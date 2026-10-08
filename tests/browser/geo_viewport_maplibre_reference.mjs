#!/usr/bin/env node
// Independent flat-ground camera oracle: local MapLibre 6.13.0, native Rust,
// and the real wasm32 artifact. No MapLibre product dependency or network tiles.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { chromium } from "playwright";
const root = fileURLToPath(new URL("../../", import.meta.url));
const dist = process.env.XYG_MAPLIBRE_DIST;
if (!dist)
  throw Error("Supply local MapLibre 6.13.0 dist with XYG_MAPLIBRE_DIST");
assert.equal(
  JSON.parse(await readFile(join(dist, "../package.json"), "utf8")).version,
  "6.13.0",
);
const server = createServer(async (req, res) => {
  const pathname = new URL(req.url, "http://localhost").pathname;
  if (pathname === "/") {
    res.setHeader("Content-Type", "text/html");
    res.end(
      '<!doctype html><link rel="icon" href="data:,"><div id="map" style="position:absolute;left:0;top:0"></div>',
    );
    return;
  }
  if (
    ![
      "/maplibre-gl.mjs",
      "/maplibre-gl-shared.mjs",
      "/maplibre-gl-worker.mjs",
    ].includes(pathname)
  ) {
    res.writeHead(404).end();
    return;
  }
  res.setHeader("Content-Type", "text/javascript");
  res.end(await readFile(join(dist, pathname.slice(1))));
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const { instance } = await WebAssembly.instantiate(
  await readFile(
    process.env.XYG_WASM_ARTIFACT ??
      join(root, "target/wasm32-unknown-unknown/release/xyg_wasm.wasm"),
  ),
  {},
);
const x = instance.exports,
  h = x.xyg_wasm_instance_new(64 << 20);
let sequence = 0;
function request(c, op, args = []) {
  const b = new ArrayBuffer(128),
    v = new DataView(b);
  new Uint8Array(b).set([88, 89, 86, 67]);
  for (const [at, n] of [
    [4, 1],
    [8, op],
    [12, 4326],
    [16, 1],
  ])
    v.setUint32(at, n, true);
  [...c.center, c.zoom, c.width, c.height, c.bearing, c.pitch].forEach((n, i) =>
    v.setFloat64(24 + 8 * i, n, true),
  );
  args.forEach((n, i) => v.setFloat64(80 + 8 * i, n, true));
  return b;
}
function execute(c, op, args = []) {
  const b = request(c, op, args),
    n = spawnSync(join(root, "target/debug/geo_viewport_conformance"), [], {
      input: Buffer.from(b),
      maxBuffer: 1 << 20,
    });
  assert.equal(n.status, 0, n.stderr.toString());
  assert.equal(x.xyg_wasm_arena_resize(h, b.byteLength), 0);
  new Uint8Array(
    x.memory.buffer,
    x.xyg_wasm_arena_ptr(h) >>> 0,
    b.byteLength,
  ).set(new Uint8Array(b));
  assert.equal(
    x.xyg_wasm_geo_viewport_execute(h, ++sequence, 0, b.byteLength),
    0,
  );
  const w = new Uint8Array(
      x.memory.buffer,
      x.xyg_wasm_output_ptr(h) >>> 0,
      x.xyg_wasm_output_len(h),
    ).slice(),
    nv = new DataView(
      n.stdout.buffer,
      n.stdout.byteOffset,
      n.stdout.byteLength,
    ),
    wv = new DataView(w.buffer);
  for (let at = 24; at < 96; at += 8)
    assert.ok(
      Math.abs(nv.getFloat64(at, true) - wv.getFloat64(at, true)) <= 1e-6,
      `native/WASM field ${at}`,
    );
  assert.equal(nv.getUint32(168, true), wv.getUint32(168, true));
  for (let at = 184; at < 216; at += 8)
    assert.ok(
      Math.abs(nv.getFloat64(at, true) - wv.getFloat64(at, true)) <= 1e-9,
      `native/WASM footprint ${at}`,
    );
  const result = [nv.getFloat64(80, true), nv.getFloat64(88, true)];
  result.bounds = nv.getUint32(168, true)
    ? [184, 192, 200, 208].map((at) => nv.getFloat64(at, true))
    : null;
  result.camera = {
    ...c,
    center: [nv.getFloat64(24, true), nv.getFloat64(32, true)],
    zoom: nv.getFloat64(40, true),
    width: nv.getFloat64(48, true),
    height: nv.getFloat64(56, true),
    bearing: nv.getFloat64(64, true),
    pitch: nv.getFloat64(72, true),
  };
  return result;
}
const cases = [
  {
    center: [0, 0],
    zoom: 2,
    width: 800,
    height: 600,
    bearing: 0,
    pitch: 0,
    points: [
      [0, 0],
      [10, 5],
      [-10, -5],
    ],
  },
  {
    center: [12, 35],
    zoom: 4,
    width: 800,
    height: 600,
    bearing: 37,
    pitch: 30,
    points: [
      [12, 35],
      [14, 36],
      [10, 34],
    ],
  },
  {
    center: [-73, 40],
    zoom: 7,
    width: 1024,
    height: 768,
    bearing: 73,
    pitch: 60,
    points: [
      [-73, 40],
      [-72.9, 40.1],
      [-73.1, 39.9],
    ],
  },
  {
    center: [179, 10],
    zoom: 4,
    width: 960,
    height: 540,
    bearing: -25,
    pitch: 45,
    points: [
      [179, 10],
      [-179, 10],
    ],
    referencePoints: [
      [179, 10],
      [181, 10],
    ],
  },
  {
    center: [0, 85.0511287798066],
    zoom: 4,
    width: 800,
    height: 600,
    bearing: 0,
    pitch: 30,
    points: [
      [0, 85.0511287798066],
      [1, 85],
    ],
  },
  {
    center: [0, 0],
    zoom: 24,
    width: 800,
    height: 600,
    bearing: 17,
    pitch: 45,
    points: [
      [0, 0],
      [1e-7, 0],
      [0, 1e-7],
    ],
  },
];
let browser,
  projections = 0,
  inverses = 0,
  transitions = 0,
  maxError = 0;
try {
  browser = await chromium.launch({
    executablePath: process.env.XYG_CHROMIUM ?? process.env.CHROMIUM,
    args: [
      "--use-gl=swiftshader",
      "--enable-unsafe-swiftshader",
      "--ignore-gpu-blocklist",
    ],
  });
  const page = await browser.newPage({
    viewport: { width: 1200, height: 900 },
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  const refs = await page.evaluate(async (cases) => {
    const { Map } = await import("/maplibre-gl.mjs"),
      out = [];
    for (const c of cases) {
      const el = document.getElementById("map");
      el.style.width = c.width + "px";
      el.style.height = c.height + "px";
      const map = new Map({
        container: el,
        style: { version: 8, sources: {}, layers: [] },
        center: c.center,
        zoom: c.zoom,
        bearing: c.bearing,
        pitch: c.pitch,
        minZoom: 0,
        maxZoom: 24,
        maxPitch: 60,
        renderWorldCopies: true,
        attributionControl: false,
        interactive: false,
      });
      await new Promise((r) => map.once("load", r));
      const actualCamera = {
        ...c,
        center: map.getCenter().toArray(),
        zoom: map.getZoom(),
      };
      const points = (c.referencePoints ?? c.points).map((p) =>
        ((p) => [p.x, p.y])(map.project(p)),
      );
      const pixels = [
        [c.width / 2, c.height / 2],
        [c.width * 0.25, c.height * 0.25],
        [c.width * 0.75, c.height * 0.75],
      ];
      const inverse = pixels.map((p) => map.unproject(p).toArray());
      const corners = [
        [0, 0],
        [c.width, 0],
        [c.width, c.height],
        [0, c.height],
      ].map((p) => map.unproject(p).toArray());
      const bounds = map.getBounds().toArray();
      el.style.width = c.width + 100 + "px";
      el.style.height = c.height + 60 + "px";
      map.resize();
      map.setPitch(40);
      map.setBearing(31);
      const updated = (c.referencePoints ?? c.points).map((p) =>
        ((p) => [p.x, p.y])(map.project(p)),
      );
      const updatedCamera = {
        ...actualCamera,
        width: c.width + 100,
        height: c.height + 60,
        center: map.getCenter().toArray(),
        zoom: map.getZoom(),
        pitch: map.getPitch(),
        bearing: map.getBearing(),
      };
      out.push({
        actualCamera,
        updatedCamera,
        points,
        pixels,
        inverse,
        corners,
        bounds,
        updated,
      });
      map.remove();
    }
    return out;
  }, cases);
  function compare(actual, expected, tolerance, label, longitude = false) {
    for (let i = 0; i < 2; i++) {
      const reference =
        longitude && i === 1
          ? Math.max(-85.0511287798066, Math.min(85.0511287798066, expected[i]))
          : expected[i];
      const delta = actual[i] - reference;
      const error = Math.abs(
        longitude && i === 0 ? delta - 360 * Math.round(delta / 360) : delta,
      );
      maxError = Math.max(maxError, error);
      assert.ok(
        error <= tolerance,
        `${label}: ${actual} != ${expected}; error ${error}`,
      );
    }
  }
  for (let k = 0; k < cases.length; k++) {
    const r = refs[k],
      c = r.actualCamera;
    for (let i = 0; i < c.points.length; i++) {
      compare(
        execute(c, 1, c.points[i]),
        r.points[i],
        1e-6,
        `project case ${k}`,
      );
      projections++;
    }
    for (let i = 0; i < r.pixels.length; i++) {
      compare(
        execute(c, 2, r.pixels[i]),
        r.inverse[i],
        1e-9,
        `inverse case ${k}`,
        true,
      );
      inverses++;
    }
    const corners = [
      [0, 0],
      [c.width, 0],
      [c.width, c.height],
      [0, c.height],
    ].map((p) => execute(c, 2, p));
    for (let i = 0; i < 4; i++)
      compare(corners[i], r.corners[i], 1e-9, `bounds corner ${k}`, true);
    // Verify the resize/pitch/bearing commands before comparing the next frame.
    let updated = execute(c, 5, [c.width + 100, c.height + 60]).camera;
    updated = execute(updated, 7, [40]).camera;
    updated = execute(updated, 6, [31]).camera;
    // MapLibre may constrain its centre near the pole after a size change. The
    // shell sends its actual snapshot; Rust's certified source latitude clamps
    // at the Mercator limit and returns canonical wrapped longitudes.
    updated = execute(updated, 8, r.updatedCamera.center).camera;
    for (const key of ["zoom", "width", "height", "bearing", "pitch"])
      assert.ok(
        Math.abs(updated[key] - r.updatedCamera[key]) < 1e-9,
        `transition snapshot ${key}`,
      );
    const frameBounds = execute(c, 0).bounds;
    assert.ok(frameBounds, "Rust camera footprint is published in XYVR");
    compare(
      frameBounds.slice(0, 2),
      r.bounds[0],
      1e-9,
      `getBounds southwest ${k}`,
      true,
    );
    compare(
      frameBounds.slice(2, 4),
      r.bounds[1],
      1e-9,
      `getBounds northeast ${k}`,
      true,
    );
    for (let i = 0; i < c.points.length; i++) {
      compare(
        execute(updated, 1, c.points[i]),
        r.updated[i],
        1e-6,
        `updated case ${k}`,
      );
      transitions++;
    }
  }
  console.log(
    JSON.stringify({
      reference:
        "MapLibre 6.13.0 flat ground, default FOV, zero terrain/padding/roll",
      projections,
      inverses,
      transitions,
      boundsCorners: cases.length * 4,
      cameraBounds: cases.length,
      maxError,
    }),
  );
} finally {
  x.xyg_wasm_instance_dispose(h);
  await browser?.close();
  await new Promise((r) => server.close(r));
}
