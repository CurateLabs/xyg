import assert from "node:assert/strict";
import test from "node:test";

import {
  GEO_CRS,
  GEO_GEOMETRY,
  GeoNativeError,
  geoColumnFree,
  geoColumnMeta,
  geoColumnMetadata,
  geoColumnNew,
  geoColumnPlaneLens,
  geoColumnRead,
  geoDescriptorFromGeoArrow,
} from "../src/index.js";

test("geoColumnNew point round-trip", () => {
  const handle = geoColumnNew({
    geometry: GEO_GEOMETRY.point,
    crs: GEO_CRS.epsg4326,
    xy: [-104.9903, 39.7392],
    validity: [1],
    featureIds: [42],
  });
  try {
    const meta = geoColumnMeta(handle);
    assert.equal(meta.length, 1);
    assert.equal(meta.vertexCount, 1);
    assert.equal(meta.geometry, GEO_GEOMETRY.point);
    assert.equal(meta.crs, GEO_CRS.epsg4326);
  } finally {
    assert.equal(geoColumnFree(handle), true);
    assert.equal(geoColumnFree(handle), false);
  }
});

test("geoColumnNew rejects unsupported CRS without leaking values", () => {
  assert.throws(
    () =>
      geoColumnNew({
        geometry: GEO_GEOMETRY.point,
        crs: 9999,
        xy: [0, 0],
        validity: [1],
      }),
    (error) =>
      error instanceof GeoNativeError &&
      error.nativeCode === -2 &&
      !String(error.message).includes("9999"),
  );
});

// ---------------------------------------------------------------------------
// Read-back, canonical metadata, GeoArrow descriptor helper, adversarial inputs
// (#47 A5/A7). Layout of the XYGM v1 header: crates/xyg-engine/src/geo.rs.
// ---------------------------------------------------------------------------

const SHELL = [0, 0, 10, 0, 10, 10, 0, 10, 0, 0];
const HOLE = [2, 2, 2, 4, 4, 4, 4, 2, 2, 2];
const SECOND = [20, 20, 30, 20, 30, 30, 20, 30, 20, 20];

const meta = (name, crs = "EPSG:4326") =>
  [name, JSON.stringify({ crs, crs_type: "authority_code" })];

function arrowInput(name, rest, crs) {
  const [extensionName, extensionMetadata] = meta(name, crs);
  return { extensionName, extensionMetadata, ...rest };
}

function withColumn(descriptor, fn) {
  const handle = geoColumnNew(descriptor);
  try {
    return fn(handle);
  } finally {
    assert.equal(geoColumnFree(handle), true);
  }
}

function xygmHeader(doc) {
  const view = new DataView(doc.buffer, doc.byteOffset, doc.byteLength);
  return {
    magic: String.fromCharCode(...doc.slice(0, 4)),
    version: view.getUint32(4, true),
    geometry: view.getUint32(8, true),
    crs: view.getUint32(12, true),
    features: view.getBigUint64(16, true),
    vertices: view.getBigUint64(24, true),
    nulls: view.getBigUint64(32, true),
    rings: view.getBigUint64(64, true),
  };
}

test("polygon with a hole reads back exactly with recorded orientation", () => {
  const descriptor = geoDescriptorFromGeoArrow(
    arrowInput("geoarrow.polygon", {
      x: [...SHELL, ...HOLE].filter((_, i) => i % 2 === 0),
      y: [...SHELL, ...HOLE].filter((_, i) => i % 2 === 1),
      offsets: [[0, 2], [0, 5, 10]],
      featureIds: [901n],
    }),
  );
  withColumn(descriptor, (handle) => {
    const planes = geoColumnRead(handle);
    assert.deepEqual(Array.from(planes.xy), [...SHELL, ...HOLE]);
    assert.deepEqual(Array.from(planes.validity), [1]);
    assert.deepEqual(Array.from(planes.featureIds), [901n]);
    assert.deepEqual(Array.from(planes.offsets0), [0, 2]);
    assert.deepEqual(Array.from(planes.offsets1), [0, 5, 10]);
    assert.equal(planes.offsets2.length, 0);
    assert.deepEqual(Array.from(planes.orientations), [1, 2]);
    assert.deepEqual(geoColumnPlaneLens(handle), {
      xy: 20, validity: 1, featureIds: 1, offsets0: 2, offsets1: 3, offsets2: 0, orientations: 2,
    });
  });
});

test("multipolygon with holes across two polygons reads back exactly", () => {
  const flat = [...SHELL, ...HOLE, ...SECOND];
  withColumn(
    geoDescriptorFromGeoArrow(
      arrowInput("geoarrow.multipolygon", {
        x: flat.filter((_, i) => i % 2 === 0),
        y: flat.filter((_, i) => i % 2 === 1),
        offsets: [[0, 1, 2], [0, 2, 3], [0, 5, 10, 15]],
      }),
    ),
    (handle) => {
      const planes = geoColumnRead(handle);
      assert.deepEqual(Array.from(planes.xy), flat);
      assert.deepEqual(Array.from(planes.offsets2), [0, 5, 10, 15]);
      assert.deepEqual(Array.from(planes.featureIds), [0n, 1n]);
      assert.deepEqual(Array.from(planes.orientations), [1, 2, 1]);
    },
  );
});

test("read-back preserves f64 bit patterns", () => {
  const xy = [-104.99030000000001, 39.739199999999997, -0, 0.1 + 0.2];
  withColumn(
    {
      geometry: GEO_GEOMETRY.multipoint,
      crs: GEO_CRS.epsg4326,
      xy,
      validity: [1],
      offsets0: [0, 2],
    },
    (handle) => {
      const got = geoColumnRead(handle).xy;
      assert.deepEqual(
        Array.from(new BigUint64Array(got.buffer, got.byteOffset, got.length)),
        Array.from(new BigUint64Array(Float64Array.from(xy).buffer)),
      );
    },
  );
});

test("canonical metadata is an XYGM v1 document and is deterministic", () => {
  const make = () => ({
    geometry: GEO_GEOMETRY.polygon,
    crs: GEO_CRS.epsg4326,
    xy: [...SHELL, ...HOLE],
    validity: [1],
    offsets0: [0, 2],
    offsets1: [0, 5, 10],
  });
  const a = geoColumnNew(make());
  const b = geoColumnNew(make());
  try {
    const doc = geoColumnMetadata(a);
    assert.ok(doc instanceof Uint8Array);
    assert.equal(doc.length % 8, 0);
    assert.deepEqual(xygmHeader(doc), {
      magic: "XYGM",
      version: 1,
      geometry: GEO_GEOMETRY.polygon,
      crs: 4326,
      features: 1n,
      vertices: 10n,
      nulls: 0n,
      rings: 2n,
    });
    assert.deepEqual(Buffer.from(geoColumnMetadata(b)), Buffer.from(doc));
    assert.ok(Buffer.from(doc).includes("geoarrow.polygon"));
  } finally {
    geoColumnFree(a);
    geoColumnFree(b);
  }
});

test("stale handles raise the stable -10 on every read path", () => {
  const handle = geoColumnNew({
    geometry: GEO_GEOMETRY.point,
    crs: GEO_CRS.epsg4326,
    xy: [0, 0],
    validity: [1],
  });
  geoColumnFree(handle);
  for (const call of [geoColumnMetadata, geoColumnPlaneLens, geoColumnRead]) {
    assert.throws(
      () => call(handle),
      (error) => error instanceof GeoNativeError && error.nativeCode === -10,
    );
  }
});

test("geoDescriptorFromGeoArrow covers all six kinds including nulls", () => {
  const ingest = (input) =>
    withColumn(geoDescriptorFromGeoArrow(input), (handle) => ({
      meta: geoColumnMeta(handle),
      planes: geoColumnRead(handle),
    }));

  // Point: null slot holds garbage and contributes no vertex.
  const point = ingest(
    arrowInput("geoarrow.point", {
      x: [Number.NaN, -104, Number.NaN, -105],
      y: [Number.NaN, 39, Number.NaN, 40],
      validity: [0, 1, 0, 1],
      featureIds: [5, 6, 7, 8],
    }),
  );
  assert.equal(point.meta.geometry, GEO_GEOMETRY.point);
  assert.deepEqual(Array.from(point.planes.xy), [-104, 39, -105, 40]);
  assert.deepEqual(Array.from(point.planes.validity), [0, 1, 0, 1]);
  assert.deepEqual(Array.from(point.planes.featureIds), [5n, 6n, 7n, 8n]);

  const line = ingest(
    arrowInput("geoarrow.linestring", {
      x: [0, 1, 5, 6],
      y: [0, 1, 5, 6],
      validity: [1, 0, 1],
      offsets: [[0, 2, 2, 4]],
    }),
  );
  assert.deepEqual(Array.from(line.planes.offsets0), [0, 2, 2, 4]);
  assert.deepEqual(Array.from(line.planes.validity), [1, 0, 1]);

  const multipoint = ingest(
    arrowInput("geoarrow.multipoint", { x: [0, 1, 2], y: [0, 1, 2], offsets: [[0, 2, 3]] }),
  );
  assert.deepEqual(Array.from(multipoint.planes.xy), [0, 0, 1, 1, 2, 2]);

  const multiline = ingest(
    arrowInput("geoarrow.multilinestring", {
      x: [0, 1, 2, 3],
      y: [0, 1, 2, 3],
      offsets: [[0, 2], [0, 2, 4]],
    }),
  );
  assert.deepEqual(Array.from(multiline.planes.offsets1), [0, 2, 4]);
  assert.equal(multiline.planes.orientations.length, 0);

  const polygon = ingest(
    arrowInput("geoarrow.polygon", {
      x: [0, 10, 10, 0, 0],
      y: [0, 0, 10, 10, 0],
      validity: [1, 0],
      offsets: [[0, 1, 1], [0, 5]],
    }),
  );
  assert.deepEqual(Array.from(polygon.planes.validity), [1, 0]);
  assert.deepEqual(Array.from(polygon.planes.orientations), [1]);

  const multipolygon = ingest(
    arrowInput(
      "geoarrow.multipolygon",
      {
        x: [0, 10, 10, 0, 0],
        y: [0, 0, 10, 10, 0],
        offsets: [[0, 1], [0, 1], [0, 5]],
      },
      "EPSG:3857",
    ),
  );
  assert.equal(multipolygon.meta.crs, GEO_CRS.epsg3857);
});

test("geoDescriptorFromGeoArrow mirrors the Python CRS and kind errors", () => {
  const base = { x: [0], y: [0] };
  const code = (input) => {
    try {
      geoDescriptorFromGeoArrow({ ...base, ...input });
    } catch (error) {
      assert.ok(error instanceof GeoNativeError);
      assert.ok(!String(error.message).includes("9999"));
      return error.nativeCode;
    }
    return 0;
  };
  const [name] = meta("geoarrow.point");
  assert.equal(code({ extensionName: name, extensionMetadata: undefined }), -2);
  assert.equal(code({ extensionName: name, extensionMetadata: "" }), -2);
  assert.equal(code({ extensionName: name, extensionMetadata: "{not json" }), -1);
  assert.equal(code({ extensionName: name, extensionMetadata: "{}" }), -2);
  assert.equal(code({ extensionName: name, extensionMetadata: '{"crs":"OGC:CRS84"}' }), -2);
  assert.equal(code({ extensionName: name, extensionMetadata: '{"crs":"EPSG:9999"}' }), -2);
  assert.equal(code({ extensionName: name, extensionMetadata: '{"crs":4326}' }), -2);
  assert.equal(code({ extensionName: "geoarrow.vendor_point", extensionMetadata: meta(name)[1] }), -3);
  assert.equal(code({ extensionName: "__proto__", extensionMetadata: meta(name)[1] }), -3);
  assert.equal(code({ extensionName: name, extensionMetadata: meta(name)[1], x: [0, 1] }), -1);
  assert.equal(code({ extensionName: name, extensionMetadata: meta(name)[1], featureIds: [1, 2] }), -1);
  assert.equal(code({ extensionName: name, extensionMetadata: meta(name)[1], featureIds: [-1] }), -1);
  assert.equal(code({ extensionName: name, extensionMetadata: meta(name)[1], validity: [2] }), -1);
  assert.equal(code({ extensionName: name, extensionMetadata: meta(name)[1] }), 0);
  assert.equal(
    code({ extensionName: "geoarrow.linestring", extensionMetadata: meta(name)[1], offsets: [] }),
    -3,
  );
});

test("hole outside shell, degenerate parts, and non-empty nulls fail with stable codes", () => {
  const expectCode = (input, status) =>
    assert.throws(
      () => geoColumnNew(geoDescriptorFromGeoArrow(input)),
      (error) =>
        error instanceof GeoNativeError &&
        error.nativeCode === status &&
        error.message === new GeoNativeError(status).message,
    );
  const flat = [...SHELL, ...SECOND];
  expectCode(
    arrowInput("geoarrow.polygon", {
      x: flat.filter((_, i) => i % 2 === 0),
      y: flat.filter((_, i) => i % 2 === 1),
      offsets: [[0, 2], [0, 5, 10]],
    }),
    -11,
  );
  expectCode(
    arrowInput("geoarrow.linestring", { x: [1], y: [1], offsets: [[0, 1]] }),
    -12,
  );
  expectCode(
    arrowInput("geoarrow.polygon", {
      x: [0, 1, 2, 0],
      y: [0, 1, 2, 0],
      offsets: [[0, 1], [0, 4]],
    }),
    -12,
  );
  expectCode(
    arrowInput("geoarrow.linestring", {
      x: [0, 1],
      y: [0, 1],
      validity: [0],
      offsets: [[0, 2]],
    }),
    -14,
  );
});

test("adversarial descriptors fail with stable codes and publish no handle", () => {
  const probe = () =>
    geoColumnNew({ geometry: GEO_GEOMETRY.point, crs: GEO_CRS.epsg4326, xy: [0, 0], validity: [1] });
  const cases = [
    // Offsets claim 2**31 / u32::MAX vertices while only two exist: no allocation attempt.
    [-4, { geometry: GEO_GEOMETRY.linestring, xy: [0, 0, 1, 1], validity: [1], offsets0: [0, 2 ** 31] }],
    [-4, { geometry: GEO_GEOMETRY.linestring, xy: [0, 0, 1, 1], validity: [1], offsets0: [0, 2 ** 32 - 1] }],
    // Non-monotonic offsets.
    [-4, { geometry: GEO_GEOMETRY.multipoint, xy: [0, 0, 1, 1], validity: [1, 1], offsets0: [0, 2, 1] }],
    // Depth mismatch: a point column must not carry offsets; a polygon needs its ring plane.
    [-3, { geometry: GEO_GEOMETRY.point, xy: [0, 0], validity: [1], offsets0: [0, 1] }],
    [-3, { geometry: GEO_GEOMETRY.polygon, xy: SHELL, validity: [1], offsets0: [0, 1] }],
    // Validity flag outside {0, 1}.
    [-1, { geometry: GEO_GEOMETRY.point, xy: [0, 0], validity: [2] }],
    // Non-finite and out-of-range coordinates (typed arrays reach Rust unfiltered).
    [-6, { geometry: GEO_GEOMETRY.point, xy: Float64Array.of(Number.NaN, 0), validity: [1] }],
    [
      -6,
      { geometry: GEO_GEOMETRY.point, xy: Float64Array.of(Number.POSITIVE_INFINITY, 0), validity: [1] },
    ],
    [-7, { geometry: GEO_GEOMETRY.point, xy: [181, 0], validity: [1] }],
    // Unsupported CRS.
    [-2, { geometry: GEO_GEOMETRY.point, xy: [0, 0], validity: [1], crs: 9999 }],
  ];
  for (const [status, partial] of cases) {
    const before = probe();
    try {
      assert.throws(
        () => geoColumnNew({ crs: GEO_CRS.epsg4326, ...partial }),
        (error) => error instanceof GeoNativeError && error.nativeCode === status,
        `expected ${status} for ${JSON.stringify(partial)}`,
      );
      const after = probe();
      // Handles come from a monotonic counter: a rejected descriptor publishes none.
      assert.equal(BigInt(after), BigInt(before) + 1n);
      geoColumnFree(after);
    } finally {
      geoColumnFree(before);
    }
  }
});

test("host wrapper rejects feature id length mismatch before FFI", () => {
  assert.throws(
    () =>
      geoColumnNew({
        geometry: GEO_GEOMETRY.point,
        crs: GEO_CRS.epsg4326,
        xy: [0, 0],
        validity: [1],
        featureIds: [1, 2],
      }),
    RangeError,
  );
});

test("GeoArrow offsets reject narrowing and excess planes", () => {
  for (const end of [4294967298, -4294967294, 2.5, Number.NaN]) {
    assert.throws(
      () => geoDescriptorFromGeoArrow(arrowInput("geoarrow.linestring", { x: [0, 1], y: [0, 1], offsets: [[0, end]] })),
      (error) => error instanceof GeoNativeError && error.nativeCode === -4,
    );
  }
  assert.throws(
    () => geoDescriptorFromGeoArrow(arrowInput("geoarrow.linestring", { x: [0, 1], y: [0, 1], offsets: [[0, 2], [], [], [0, 999]] })),
    (error) => error instanceof GeoNativeError && error.nativeCode === -3,
  );
});
