/**
 * GeoArrow-shaped buffers → `geoColumnNew` descriptor (#47).
 *
 * Arrow-free by design: Node hosts decode Arrow/Parquet however they like and
 * hand this helper the already-decoded GeoArrow planes (child coordinate
 * arrays, list offsets, optional validity, optional feature identity) plus the
 * extension name and extension-metadata JSON. It mirrors the Python adapter
 * (`python/xyg/_geoarrow.py`) decision for decision — same CRS parser, same
 * "null points contribute no vertex" packing, same stable error codes — and
 * leaves every geometric validation (finite, ranges, offsets, rings, holes,
 * limits) to Rust. No Arrow dependency, no row expansion.
 */
import { GEO_CRS, GEO_GEOMETRY, GeoNativeError } from "./abi.js";

const EXTENSION_TO_GEOMETRY = Object.freeze({
  "geoarrow.point": GEO_GEOMETRY.point,
  "geoarrow.linestring": GEO_GEOMETRY.linestring,
  "geoarrow.polygon": GEO_GEOMETRY.polygon,
  "geoarrow.multipoint": GEO_GEOMETRY.multipoint,
  "geoarrow.multilinestring": GEO_GEOMETRY.multilinestring,
  "geoarrow.multipolygon": GEO_GEOMETRY.multipolygon,
});

const CRS_RE = /^EPSG:(\d+)$/;
const U64_MAX = (1n << 64n) - 1n;

function geometryKind(extensionName) {
  if (typeof extensionName !== "string") throw new GeoNativeError(-3);
  const kind = Object.hasOwn(EXTENSION_TO_GEOMETRY, extensionName)
    ? EXTENSION_TO_GEOMETRY[extensionName]
    : undefined;
  if (kind === undefined) throw new GeoNativeError(-3);
  return kind;
}

/** Parse the GeoArrow extension-metadata JSON into a certified EPSG code. */
function parseCrs(extensionMetadata) {
  if (typeof extensionMetadata !== "string" || extensionMetadata.length === 0) {
    throw new GeoNativeError(-2);
  }
  let payload;
  try {
    payload = JSON.parse(extensionMetadata);
  } catch {
    throw new GeoNativeError(-1);
  }
  const crs = payload !== null && typeof payload === "object" ? payload.crs : undefined;
  if (typeof crs !== "string") throw new GeoNativeError(-2);
  const match = CRS_RE.exec(crs.trim());
  if (match === null) throw new GeoNativeError(-2);
  const code = Number(match[1]);
  if (code !== GEO_CRS.epsg4326 && code !== GEO_CRS.epsg3857) throw new GeoNativeError(-2);
  return code;
}

function asF64(values) {
  if (values instanceof Float64Array) return values;
  if (values == null) throw new GeoNativeError(-1);
  return Float64Array.from(values, Number);
}

function asU32(values) {
  if (values instanceof Uint32Array) return values;
  if (values == null) throw new GeoNativeError(-1);
  for (const value of values) {
    if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) {
      throw new GeoNativeError(-4);
    }
  }
  return Uint32Array.from(values);
}

function asValidity(validity, count) {
  if (validity == null) return new Uint8Array(count).fill(1);
  const out = new Uint8Array(validity.length);
  for (let i = 0; i < validity.length; i += 1) {
    const flag = validity[i];
    if (flag === true || flag === 1) out[i] = 1;
    else if (flag === false || flag === 0) out[i] = 0;
    else throw new GeoNativeError(-1);
  }
  return out;
}

function asFeatureIds(featureIds, count) {
  if (featureIds == null) return null;
  if (featureIds.length !== count) throw new GeoNativeError(-1);
  const out = new BigUint64Array(count);
  for (let i = 0; i < count; i += 1) {
    const item = featureIds[i];
    let value;
    if (typeof item === "bigint") value = item;
    else if (Number.isSafeInteger(item)) value = BigInt(item);
    else throw new GeoNativeError(-1);
    if (value < 0n || value > U64_MAX) throw new GeoNativeError(-1);
    out[i] = value;
  }
  return out;
}

function interleave(x, y) {
  if (x.length !== y.length) throw new GeoNativeError(-1);
  const xy = new Float64Array(x.length * 2);
  for (let i = 0; i < x.length; i += 1) {
    xy[2 * i] = x[i];
    xy[2 * i + 1] = y[i];
  }
  return xy;
}

/**
 * Build a `geoColumnNew` descriptor from decoded GeoArrow planes.
 *
 * @param {object} input
 * @param {string} input.extensionName `ARROW:extension:name`, e.g. `geoarrow.polygon`.
 * @param {string} input.extensionMetadata `ARROW:extension:metadata` JSON text.
 * @param {ArrayLike<number>} input.x x coordinate plane. For `geoarrow.point` this is one
 *   value per feature (null slots hold arbitrary values); for nested kinds it is the flat
 *   vertex plane.
 * @param {ArrayLike<number>} input.y y coordinate plane, same length as `x`.
 * @param {ArrayLike<number | boolean> | null} [input.validity] per-feature validity;
 *   omitted means every feature is present.
 * @param {ArrayLike<number>[]} [input.offsets] list offsets, outermost level first
 *   (`[o0]`, `[o0, o1]` or `[o0, o1, o2]`). Required for every kind but point.
 * @param {ArrayLike<number | bigint> | null} [input.featureIds] producer feature identity
 *   forwarded to Rust unchanged; length must equal the feature count.
 * @returns {{ geometry: number, crs: number, xy: Float64Array, validity: Uint8Array,
 *   featureIds: BigUint64Array | null, offsets0: Uint32Array | null,
 *   offsets1: Uint32Array | null, offsets2: Uint32Array | null }}
 */
export function geoDescriptorFromGeoArrow({
  extensionName,
  extensionMetadata,
  x,
  y,
  validity = null,
  offsets = [],
  featureIds = null,
}) {
  const geometry = geometryKind(extensionName);
  const crs = parseCrs(extensionMetadata);
  const depth = [0, 0, 1, 2, 1, 2, 3][geometry];
  if (!Array.isArray(offsets) || offsets.length !== depth) throw new GeoNativeError(-3);
  const xs = asF64(x);
  const ys = asF64(y);
  if (xs.length !== ys.length) throw new GeoNativeError(-1);

  if (geometry === GEO_GEOMETRY.point) {
    const flags = asValidity(validity, xs.length);
    if (flags.length !== xs.length) throw new GeoNativeError(-1);
    // Null points contribute no vertex: pack only present rows.
    let present = 0;
    for (let i = 0; i < flags.length; i += 1) present += flags[i];
    const xy = new Float64Array(present * 2);
    for (let i = 0, w = 0; i < flags.length; i += 1) {
      if (flags[i] === 1) {
        xy[w] = xs[i];
        xy[w + 1] = ys[i];
        w += 2;
      }
    }
    return {
      geometry,
      crs,
      xy,
      validity: flags,
      featureIds: asFeatureIds(featureIds, flags.length),
      offsets0: null,
      offsets1: null,
      offsets2: null,
    };
  }

  const planes = Array.from(offsets ?? [], asU32);
  if (planes.length === 0 || planes[0].length === 0) throw new GeoNativeError(-3);
  const count = planes[0].length - 1;
  const flags = asValidity(validity, count);
  if (flags.length !== count) throw new GeoNativeError(-1);
  return {
    geometry,
    crs,
    xy: interleave(xs, ys),
    validity: flags,
    featureIds: asFeatureIds(featureIds, count),
    offsets0: planes[0] ?? null,
    offsets1: planes[1] ?? null,
    offsets2: planes[2] ?? null,
  };
}
