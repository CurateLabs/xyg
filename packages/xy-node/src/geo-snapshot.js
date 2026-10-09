/** Typed frozen-frame export bridge. Rust owns immutable provenance and rendering. */
const HEADER = 256,
  MAX = 64 << 20,
  BUDGET = 384 << 20;
const formats = { svg: 0, png: 1, pdf: 2, jpeg: 3, webp: 4, html: 5 };
export class GeoSnapshotError extends Error {
  constructor(status) {
    super(
      {
        [-1]: "XYG_GEO_SNAPSHOT_INVALID",
        [-9]: "XYG_GEO_SNAPSHOT_LIMIT",
        [-10]: "XYG_GEO_SNAPSHOT_STALE",
        [-13]: "XYG_GEO_SNAPSHOT_OUTPUT_CAPACITY",
        [-15]: "XYG_GEO_SNAPSHOT_UNSUPPORTED",
      }[status] ?? "XYG_GEO_SNAPSHOT_ERROR",
    );
    this.status = status;
    this.code = this.message;
  }
}
function uint(n) {
  if (typeof n !== "bigint" || n < 0n || n > 0xffffffffffffffffn)
    throw new TypeError("expected u64 bigint");
  return n;
}
function budget(n) {
  if (!Number.isSafeInteger(n) || n < HEADER || n > BUDGET)
    throw new RangeError("invalid snapshot budget");
  return n;
}
export function encodeGeoSnapshotRequest(
  command,
  handle,
  {
    sequence = 0n,
    budget: limit = 0,
    format = "png",
    scale = 1,
    quality = 90,
  } = {},
) {
  if (
    !Number.isInteger(command) ||
    ![1, 2, 3, 4, 5, 6, 20, 21, 22].includes(command) ||
    !Number.isSafeInteger(limit) ||
    limit < 0 ||
    limit > BUDGET ||
    (![1, 4, 5, 6].includes(command) && sequence !== 0n) ||
    (![1, 2, 4, 5, 6].includes(command) && limit !== 0)
  )
    throw new TypeError("field does not belong to snapshot command");
  if (command === 2 && typeof scale !== "number")
    throw new TypeError("expected numeric f64 scale");
  const b = new ArrayBuffer(HEADER),
    v = new DataView(b);
  new Uint8Array(b).set([88, 89, 71, 74]);
  v.setUint32(4, 1, true);
  v.setUint32(8, command, true);
  v.setBigUint64(16, uint(handle), true);
  v.setBigUint64(24, uint(sequence), true);
  v.setBigUint64(32, BigInt(limit), true);
  if (command === 2) {
    if (
      !Object.hasOwn(formats, format) ||
      !Number.isInteger(quality) ||
      quality < 0 ||
      quality > 0xffffffff
    )
      throw new TypeError("invalid export framing");
    v.setUint32(40, formats[format], true);
    v.setUint32(44, quality, true);
    v.setFloat64(48, scale, true);
  }
  return b;
}
export function decodeGeoSnapshotReply(packet) {
  if (!(packet instanceof ArrayBuffer) || packet.byteLength !== HEADER)
    throw new TypeError("invalid snapshot reply");
  const b = new Uint8Array(packet),
    v = new DataView(packet),
    kind = v.getUint32(8, true),
    handle = v.getBigUint64(16, true),
    length = v.getBigUint64(32, true),
    companion = v.getBigUint64(40, true);
  if (
    String.fromCharCode(...b.subarray(0, 4)) !== "XYGW" ||
    v.getUint32(4, true) !== 1 ||
    kind > 1 ||
    handle === 0n ||
    b.subarray(12, 16).some(Boolean) ||
    b.subarray(64).some(Boolean) ||
    length > BigInt(MAX) ||
    companion > 32n << 20n ||
    (kind === 0 && (companion !== 0n || b.subarray(48, 64).some(Boolean)))
  )
    throw new TypeError("invalid snapshot planes");
  if (
    kind === 1 &&
    (v.getUint32(48, true) > 5 ||
      v.getUint32(52, true) < 1 ||
      v.getUint32(52, true) > 100 ||
      !Number.isFinite(v.getFloat64(56, true)) ||
      v.getFloat64(56, true) <= 0)
  )
    throw new TypeError("invalid typed artifact reply");
  return {
    handle,
    sequence: v.getBigUint64(24, true),
    length: Number(length),
    companion: Number(companion),
    kind,
  };
}
export async function geoSnapshotExecute(request) {
  if (!(request instanceof ArrayBuffer) || request.byteLength !== HEADER)
    throw new TypeError("snapshot command must have256bytes");
  const n = await import("./native.js"),
    out = new Uint8Array(HEADER),
    input = new Uint8Array(request);
  const status = n.xyGeoSnapshotExecute(
    n.pointer(input, "uint8_t *"),
    256n,
    n.pointer(out, "uint8_t *"),
    256n,
  );
  if (status) throw new GeoSnapshotError(status);
  return out.buffer;
}
export async function geoSnapshotRead(request, limit) {
  budget(limit);
  if (!(request instanceof ArrayBuffer) || request.byteLength !== HEADER)
    throw new TypeError("invalid snapshot read");
  const n = await import("./native.js"),
    input = new Uint8Array(request),
    length = new BigUint64Array(1);
  let status = n.xyGeoSnapshotRead(
    n.pointer(input, "uint8_t *"),
    256n,
    BigInt(limit),
    null,
    0n,
    n.pointer(length, "size_t *"),
  );
  if (status) throw new GeoSnapshotError(status);
  if (length[0] > BigInt(MAX) || 4n * length[0] + 256n > BigInt(limit))
    throw new GeoSnapshotError(-9);
  const out = new Uint8Array(Number(length[0]));
  status = n.xyGeoSnapshotRead(
    n.pointer(input, "uint8_t *"),
    256n,
    BigInt(limit),
    n.pointer(out, "uint8_t *"),
    BigInt(out.length),
    n.pointer(length, "size_t *"),
  );
  if (status) throw new GeoSnapshotError(status);
  if (length[0] !== BigInt(out.length))
    throw new TypeError("snapshot length changed");
  return out.buffer;
}
export function nativeGeoSnapshotBridge(limit) {
  budget(limit);
  return {
    execute: geoSnapshotExecute,
    read: (q) => geoSnapshotRead(q, limit),
  };
}
export async function exportGeoFrame(
  frame,
  sequence,
  format = "png",
  {
    scale = 1,
    quality = 90,
    budget: limit = BUDGET,
    bridge = nativeGeoSnapshotBridge(limit),
    signal,
  } = {},
) {
  budget(limit);
  void frame.data;
  let frozen, artifact, data, companion, owner;
  const check = () => {
    if (signal?.aborted)
      throw signal.reason ?? new Error("geographic export aborted");
  };
  try {
    check();
    const f = decodeGeoSnapshotReply(
      await bridge.execute(
        encodeGeoSnapshotRequest(frame._freezeCommand ?? 1, frame.handle, {
          sequence,
          budget: Math.min(limit, 128 << 20),
        }),
      ),
    );
    frozen = f.handle;
    if (f.kind !== 0 || f.sequence !== sequence)
      throw new TypeError("mismatched frozen frame identity");
    check();
    const a = decodeGeoSnapshotReply(
      await bridge.execute(
        encodeGeoSnapshotRequest(2, frozen, {
          budget: limit,
          format,
          scale,
          quality,
        }),
      ),
    );
    artifact = a.handle;
    if (a.kind !== 1 || a.sequence !== sequence)
      throw new TypeError("mismatched artifact identity");
    check();
    data = await bridge.read(encodeGeoSnapshotRequest(22, artifact));
    check();
    companion = await bridge.read(encodeGeoSnapshotRequest(21, artifact));
    check();
    if (data.byteLength !== a.length || companion.byteLength !== a.companion)
      throw new TypeError("mismatched snapshot export lengths");
    let disposal;
    const handle = artifact;
    owner = {
      handle,
      format,
      get bytes() {
        if (!data) throw new Error("geographic artifact disposed");
        return data;
      },
      get snapshot() {
        if (!companion) throw new Error("geographic artifact disposed");
        return companion;
      },
      dispose() {
        data = companion = undefined;
        return (disposal ??= bridge
          .execute(encodeGeoSnapshotRequest(3, handle))
          .then(() => {}));
      },
    };
    artifact = undefined;
  } catch (error) {
    data = companion = undefined;
    throw error;
  } finally {
    try {
      if (artifact !== undefined)
        await bridge.execute(encodeGeoSnapshotRequest(3, artifact));
      if (frozen !== undefined)
        await bridge.execute(encodeGeoSnapshotRequest(3, frozen));
    } catch (error) {
      if (owner) await owner.dispose();
      throw error;
    }
    if (signal?.aborted && owner) {
      await owner.dispose();
      throw signal.reason ?? new Error("geographic export aborted");
    }
  }
  return owner;
}
