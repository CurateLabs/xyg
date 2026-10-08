/** Thin typed-plane framing for Rust GeoColumn ingestion (XYGD v1). */
export interface XygGeoDescriptor {
  geometry: number;
  crs: number;
  xy: Float64Array;
  validity: Uint8Array;
  featureIds?: BigUint64Array | null;
  offsets0?: Uint32Array;
  offsets1?: Uint32Array;
  offsets2?: Uint32Array;
}

/** Copies source buffers once; no CRS, geometry, or topology policy lives here. */
export function encodeWasmGeoDescriptor(input: XygGeoDescriptor): ArrayBuffer {
  if (!(input.xy instanceof Float64Array) || !(input.validity instanceof Uint8Array)
      || input.xy.length % 2 || (input.featureIds != null && !(input.featureIds instanceof BigUint64Array))) {
    throw new TypeError("geographic source planes must be typed arrays");
  }
  if (input.featureIds != null && input.featureIds.length !== input.validity.length) throw new RangeError("identity plane length must match validity");
  const offsets = [input.offsets0, input.offsets1, input.offsets2].map(p => p ?? new Uint32Array());
  if (offsets.some(p => !(p instanceof Uint32Array))) throw new TypeError("offset planes must be Uint32Array");
  for (const value of [input.geometry, input.crs]) if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) throw new RangeError("geometry and CRS codes must be u32");
  const planes = [input.xy, input.validity, input.featureIds ?? new BigUint64Array(), ...offsets];
  const padded = (n: number) => Math.ceil(n / 8) * 8;
  const length = planes.reduce((n, p) => n + padded(p.byteLength), 64);
  if (!Number.isSafeInteger(length) || length > 256 * 1024 * 1024) throw new RangeError("geographic descriptor exceeds transport budget");
  const out = new ArrayBuffer(length), bytes = new Uint8Array(out), view = new DataView(out);
  bytes.set([88, 89, 71, 68]);
  view.setUint32(4, 1, true); view.setUint32(8, input.geometry, true); view.setUint32(12, input.crs, true);
  view.setUint32(16, input.featureIds == null ? 0 : 1, true);
  [input.validity.length, input.xy.length / 2, ...offsets.map(p => p.length)].forEach((n, i) => view.setBigUint64(24 + i * 8, BigInt(n), true));
  let cursor = 64;
  // Explicit little-endian writes avoid platform/alignment-dependent typed casts.
  for (let i = 0; i < planes.length; i += 1) {
    const plane = planes[i];
    for (let j = 0; j < plane.length; j += 1) {
      if (i === 0) view.setFloat64(cursor + j * 8, Number(plane[j]), true);
      else if (i === 1) view.setUint8(cursor + j, Number(plane[j]));
      else if (i === 2) view.setBigUint64(cursor + j * 8, BigInt(plane[j]), true);
      else view.setUint32(cursor + j * 4, Number(plane[j]), true);
    }
    cursor += padded(plane.byteLength);
  }
  return out;
}
