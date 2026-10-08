// Python ↔ Node GeoColumn parity (xyg#47, AC2): every case in
// tests/fixtures/geo_cross_host.json (authored by the Python host from real
// pyarrow GeoArrow arrays, packages/xy-node/test/fixtures/write_geo_cross_host_fixtures.py)
// is rebuilt here from its decoded GeoArrow planes with `geoDescriptorFromGeoArrow`.
// Node must reach the same descriptor, retain the same f64 bits, return the same
// planes from Rust, and emit byte-identical canonical `XYGM` v1 metadata. Error
// cases must return the pinned stable status and publish no handle.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import test from "node:test";

import {
  GEO_CRS,
  GEO_GEOMETRY,
  GeoNativeError,
  abiVersion,
  geoColumnFree,
  geoColumnMetadata,
  geoColumnNew,
  geoColumnRead,
  geoDescriptorFromGeoArrow,
} from "../src/index.js";

const golden = JSON.parse(
  fs.readFileSync(new URL("../../../tests/fixtures/geo_cross_host.json", import.meta.url), "utf8"),
);

const KIND = {
  "geoarrow.point": GEO_GEOMETRY.point,
  "geoarrow.linestring": GEO_GEOMETRY.linestring,
  "geoarrow.polygon": GEO_GEOMETRY.polygon,
  "geoarrow.multipoint": GEO_GEOMETRY.multipoint,
  "geoarrow.multilinestring": GEO_GEOMETRY.multilinestring,
  "geoarrow.multipolygon": GEO_GEOMETRY.multipolygon,
};

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");

/** 16-hex-digit big-endian IEEE-754 images → Float64Array (bit-exact, NaN safe). */
function f64(bitStrings) {
  const words = new BigUint64Array(bitStrings.length);
  bitStrings.forEach((hex, i) => {
    words[i] = BigInt(`0x${hex}`);
  });
  return new Float64Array(words.buffer);
}

/** Bit images of a Float64Array, for exact comparison (NaN and -0 included). */
function bitsOf(values) {
  const words = new BigUint64Array(values.buffer, values.byteOffset, values.length);
  return Array.from(words, (w) => w.toString(16).padStart(16, "0"));
}

const u64 = (strings) => BigUint64Array.from(strings, BigInt);

function arrowInput(c) {
  const a = c.arrow;
  return {
    extensionName: c.extension_name,
    extensionMetadata: c.extension_metadata,
    x: f64(a.x),
    y: f64(a.y),
    validity: a.validity,
    offsets: a.offsets,
    featureIds: a.feature_ids === null ? null : u64(a.feature_ids),
  };
}

function expectedDescriptor(c) {
  const d = c.descriptor;
  return {
    geometry: KIND[c.extension_name],
    crs: Number(JSON.parse(c.extension_metadata).crs.split(":")[1]),
    xy: d.xy,
    validity: d.validity,
    featureIds: d.feature_ids,
    offsets0: d.offsets0,
    offsets1: d.offsets1,
    offsets2: d.offsets2,
  };
}

function describe(desc) {
  const plane = (p) => (p === null ? null : Array.from(p));
  return {
    geometry: desc.geometry,
    crs: desc.crs,
    xy: bitsOf(desc.xy),
    validity: Array.from(desc.validity),
    featureIds: desc.featureIds === null ? null : Array.from(desc.featureIds, String),
    offsets0: plane(desc.offsets0),
    offsets1: plane(desc.offsets1),
    offsets2: plane(desc.offsets2),
  };
}

test("golden matches this build's ABI version and covers every kind", () => {
  assert.equal(golden.schema, "xyg.geo-cross-host/v1");
  assert.equal(Number(golden.abi_version), abiVersion());
  const ok = golden.cases.filter((c) => c.status === 0);
  assert.deepEqual(new Set(ok.map((c) => c.extension_name)), new Set(Object.keys(KIND)));
  assert.ok(golden.cases.some((c) => c.status === -11));
  assert.ok(ok.some((c) => c.read_back.orientations.includes(2)));
});

for (const c of golden.cases.filter((entry) => entry.status === 0)) {
  test(`Node reproduces the Python descriptor, read-back and XYGM bytes: ${c.name}`, () => {
    const desc = geoDescriptorFromGeoArrow(arrowInput(c));
    const want = expectedDescriptor(c);
    assert.deepEqual(describe(desc), want);

    const handle = geoColumnNew(desc);
    try {
      const planes = geoColumnRead(handle);
      assert.deepEqual(bitsOf(planes.xy), c.read_back.xy);
      assert.deepEqual(Array.from(planes.validity), c.read_back.validity);
      assert.deepEqual(Array.from(planes.featureIds, String), c.read_back.feature_ids);
      assert.deepEqual(Array.from(planes.offsets0), c.read_back.offsets0);
      assert.deepEqual(Array.from(planes.offsets1), c.read_back.offsets1);
      assert.deepEqual(Array.from(planes.offsets2), c.read_back.offsets2);
      assert.deepEqual(Array.from(planes.orientations), c.read_back.orientations);

      const metadata = geoColumnMetadata(handle);
      assert.equal(metadata.length, c.metadata_len);
      assert.equal(Buffer.from(metadata).toString("hex"), c.metadata_hex);
      assert.equal(sha256(metadata), c.metadata_sha256);
    } finally {
      assert.equal(geoColumnFree(handle), true);
    }
  });
}

for (const c of golden.cases.filter((entry) => entry.status !== 0)) {
  test(`Node returns the pinned stable status and publishes nothing: ${c.name}`, () => {
    const probe = () =>
      geoColumnNew({ geometry: GEO_GEOMETRY.point, crs: GEO_CRS.epsg4326, xy: [0, 0], validity: [1] });
    const before = probe();
    try {
      assert.throws(
        () => geoColumnNew(geoDescriptorFromGeoArrow(arrowInput(c))),
        (error) => error instanceof GeoNativeError && error.nativeCode === c.status,
      );
      const after = probe();
      // Monotonic handle counter: the failed ingest consumed no handle.
      assert.equal(BigInt(after), BigInt(before) + 1n);
      geoColumnFree(after);
    } finally {
      geoColumnFree(before);
    }
  });
}
