import assert from "node:assert/strict";
import test from "node:test";

import {
  GEO_CRS,
  GEO_GEOMETRY,
  GeoNativeError,
  geoColumnFree,
  geoColumnMeta,
  geoColumnNew,
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
