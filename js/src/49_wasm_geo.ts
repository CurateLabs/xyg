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
  return encodeGeoPlanes(input, 0);
}

function encodeGeoPlanes(input: XygGeoDescriptor, prefix: number): ArrayBuffer {
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
  if (!Number.isSafeInteger(length) || length + prefix > 256 * 1024 * 1024) throw new RangeError("geographic descriptor exceeds transport budget");
  const out = new ArrayBuffer(prefix + length), bytes = new Uint8Array(out, prefix), view = new DataView(out, prefix);
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


export interface XygFrozenGeoScene {
  crs?: number;
  centerX: number;
  centerY: number;
  zoom: number;
  width: number;
  height: number;
  bearing?: number;
  pitch?: number;
  worldWrap?: boolean;
  diameter?: number;
  strokeWidth?: number;
  fillRgba?: Uint8Array;
  strokeRgba?: Uint8Array;
}

/** Frames an authoring camera/style snapshot; Rust owns all admission/lowering. */
export function encodeWasmGeoSceneRequest(input: XygGeoDescriptor, camera: XygFrozenGeoScene): ArrayBuffer {
  const result = encodeGeoPlanes(input, 128), bytes = new Uint8Array(result), view = new DataView(result);
  bytes.set([88, 89, 71, 80]); view.setUint32(4, 1, true); view.setUint32(8, 128, true);
  let flags = camera.worldWrap ? 1 : 0;
  for (const [plane, offset, flag] of [[camera.fillRgba, 96, 2], [camera.strokeRgba, 100, 4]] as const) {
    if (plane != null) {
      if (!(plane instanceof Uint8Array) || plane.length !== 4) throw new TypeError("Scene paints must be four RGBA8 bytes");
      bytes.set(plane, offset); flags |= flag;
    }
  }
  const crs = camera.crs ?? input.crs;
  if (!Number.isInteger(crs) || crs < 0 || crs > 0xffffffff) throw new RangeError("camera CRS must be u32");
  view.setUint32(12, flags, true); view.setUint32(16, crs, true);
  [camera.centerX, camera.centerY, camera.zoom, camera.width, camera.height, camera.bearing ?? 0, camera.pitch ?? 0, camera.diameter ?? NaN, camera.strokeWidth ?? NaN]
    .forEach((value, i) => view.setFloat64(24 + i * 8, value, true));
  view.setBigUint64(104, BigInt(result.byteLength - 128), true);
  return result;
}
