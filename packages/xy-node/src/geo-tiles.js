/** Explicit tile source/session data API; Rust owns selection and atomic publication. */
import { createHash } from "node:crypto";
import { encodeGeoViewportRequest } from "./geoviewport.js";
import { encodeGeoScaleStyle } from "./geoscale.js";
import { decodeGeoCatalogResponse } from "./geocatalog.js";
const HEADER = 128,
  REPLY = 256,
  MAX = 32 << 20,
  PHASE = 128 << 20;
const decoder = new TextDecoder("utf-8", { fatal: true });
function uint(n, bits = 64) {
  if (typeof n !== "bigint" || n < 0n || n >= 1n << BigInt(bits))
    throw new TypeError(`expected u${bits} bigint`);
  return n;
}
function u32(n) {
  if (!Number.isInteger(n) || n < 0 || n > 0xffffffff)
    throw new TypeError("expected u32");
  return n;
}
function bytes(n) {
  if (n instanceof ArrayBuffer) return new Uint8Array(n);
  if (n instanceof Uint8Array) return n;
  throw new TypeError("expected raw bytes");
}
function budget(n) {
  if (!Number.isSafeInteger(n) || n < 256 || n > PHASE)
    throw new RangeError("invalid tile budget");
  return n;
}
function pad(n) {
  return (n + 7) & ~7;
}
function zero(b) {
  if (b.some(Boolean)) throw new TypeError("nonzero reserved tile bytes");
}
function fixed(packet) {
  const b = bytes(packet);
  if (b.length !== REPLY || String.fromCharCode(...b.subarray(0, 4)) !== "XYGU")
    throw new TypeError("invalid tile reply");
  const v = new DataView(b.buffer, b.byteOffset, b.length);
  if (v.getUint32(4, true) !== 1) throw new TypeError("tile version");
  zero(b.subarray(12, 16));
  return {
    b,
    v,
    handle: v.getBigUint64(16, true),
    epoch: v.getBigUint64(24, true),
    kind: v.getUint32(8, true),
  };
}
export function encodeGeoTileRequest(
  command,
  handle = 0n,
  { epoch = 0n, view = 0n, budget: limit = 0, payload = new Uint8Array() } = {},
) {
  if (![1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 21, 22].includes(command))
    throw new TypeError("unknown tile command");
  const p = bytes(payload);
  if (p.length + 128 > MAX || (limit && p.length + 128 > budget(limit)))
    throw new RangeError("tile framing budget");
  const out = new ArrayBuffer(128 + p.length),
    b = new Uint8Array(out),
    v = new DataView(out);
  b.set([88, 89, 71, 84]);
  v.setUint32(4, 1, true);
  v.setUint32(8, command, true);
  v.setBigUint64(16, uint(handle), true);
  v.setBigUint64(24, uint(epoch), true);
  v.setBigUint64(32, uint(view), true);
  v.setBigUint64(40, BigInt(limit), true);
  v.setBigUint64(48, BigInt(p.length), true);
  b.set(p, 128);
  return out;
}
export async function geoTileExecute(request) {
  const p = bytes(request);
  if (p.length < 128 || p.length > MAX)
    throw new RangeError("invalid tile request");
  const n = await import("./native.js"),
    a = await import("./abi.js"),
    out = new Uint8Array(256);
  const status = n.xyGeoTileExecute(
    n.pointer(p, "uint8_t *"),
    BigInt(p.length),
    n.pointer(out, "uint8_t *"),
    256n,
  );
  if (status) throw new a.GeoNativeError(status);
  return out.buffer;
}
export async function geoTileRead(request, limit) {
  budget(limit);
  const p = bytes(request);
  if (p.length < 128 || p.length > Math.min(MAX, limit))
    throw new RangeError("invalid tile read");
  const n = await import("./native.js"),
    a = await import("./abi.js"),
    len = new BigUint64Array(1);
  let status = n.xyGeoTileRead(
    n.pointer(p, "uint8_t *"),
    BigInt(p.length),
    BigInt(limit),
    null,
    0n,
    n.pointer(len, "size_t *"),
  );
  if (status) throw new a.GeoNativeError(status);
  if (len[0] > BigInt(MAX) || len[0] * 2n > BigInt(limit))
    throw new a.GeoNativeError(-9);
  const out = new Uint8Array(Number(len[0]));
  status = n.xyGeoTileRead(
    n.pointer(p, "uint8_t *"),
    BigInt(p.length),
    BigInt(limit),
    n.pointer(out, "uint8_t *"),
    BigInt(out.length),
    n.pointer(len, "size_t *"),
  );
  if (status) throw new a.GeoNativeError(status);
  if (len[0] !== BigInt(out.length)) throw new TypeError("tile length changed");
  return out.buffer;
}
export function nativeGeoTileBridge(limit) {
  budget(limit);
  return { execute: geoTileExecute, read: (p) => geoTileRead(p, limit) };
}
export class GeoTileSource {
  constructor(config) {
    this.config = Object.freeze({
      ...config,
      time: config.time ? Object.freeze({ ...config.time }) : undefined,
    });
    Object.freeze(this);
  }
  encode() {
    const s = this.config;
    if (
      typeof s.network !== "boolean" ||
      typeof s.locator !== "string" ||
      typeof s.attribution !== "string"
    )
      throw new TypeError("explicit tile location required");
    const locator = new TextEncoder().encode(s.locator),
      attr = new TextEncoder().encode(s.attribution);
    if (locator.length > 4096 || attr.length > 4096)
      throw new RangeError("tile text framing");
    const b = new Uint8Array(112 + locator.length + attr.length),
      v = new DataView(b.buffer);
    [
      s.sourceId,
      s.generation,
      s.layerId,
      s.layerRevision,
      s.styleRevision,
    ].forEach((n, i) => v.setBigUint64(i * 8, uint(n), true));
    if (s.time) {
      for (const n of [s.time.start, s.time.end])
        if (
          typeof n !== "bigint" ||
          n < -0x8000000000000000n ||
          n > 0x7fffffffffffffffn
        )
          throw new TypeError("expected i64");
      v.setBigInt64(40, s.time.start, true);
      v.setBigInt64(48, s.time.end, true);
      v.setUint32(56, 1, true);
    }
    v.setUint32(60, u32(s.kind), true);
    if (
      !Number.isInteger(s.minZoom) ||
      s.minZoom < 0 ||
      s.minZoom > 255 ||
      !Number.isInteger(s.maxZoom) ||
      s.maxZoom < 0 ||
      s.maxZoom > 255
    )
      throw new TypeError("expected u8 zoom");
    b[64] = s.minZoom;
    b[65] = s.maxZoom;
    [s.maxBytes, s.maxFeatures, s.maxVertices].forEach((n, i) =>
      v.setBigUint64(72 + i * 8, uint(n), true),
    );
    v.setUint32(96, locator.length, true);
    v.setUint32(100, attr.length, true);
    v.setUint32(104, Number(s.network), true);
    b.set(locator, 112);
    b.set(attr, 112 + locator.length);
    return b;
  }
}
export function encodeGeoTileBegin(camera, sources) {
  const wire = new Uint8Array(encodeGeoViewportRequest(camera)),
    encoded = sources.map((s) => s.encode()),
    size = 80 + encoded.reduce((n, b) => n + b.length, 0);
  if (sources.length > 16 || size + 128 > MAX)
    throw new RangeError("tile config framing");
  const b = new Uint8Array(size),
    v = new DataView(b.buffer);
  b.set(wire.subarray(12, 20));
  b.set(wire.subarray(24, 80), 8);
  v.setUint32(64, sources.length, true);
  let at = 80;
  for (const s of encoded) {
    b.set(s, at);
    at += s.length;
  }
  return b;
}
export function encodeGeoTilePrepare(catalog, styles, imageId) {
  const cat = bytes(catalog);
  if (styles.length > 64 || 32 + styles.length * 64 + cat.length + 128 > MAX)
    throw new RangeError("tile Scene framing");
  const b = new Uint8Array(32 + 64 * styles.length + cat.length),
    v = new DataView(b.buffer);
  v.setBigUint64(0, uint(imageId), true);
  v.setUint32(8, styles.length, true);
  v.setBigUint64(16, BigInt(cat.length), true);
  styles.forEach((s, i) => {
    const at = 32 + i * 64,
      style =
        s.style instanceof Uint8Array ? s.style : encodeGeoScaleStyle(s.style);
    if (style.length !== 48) throw new TypeError("style48 required");
    zero(style.subarray(33));
    v.setBigUint64(at, uint(s.layerId), true);
    v.setUint32(at + 8, u32(s.kind), true);
    b.set(style.subarray(0, 33), at + 16);
  });
  b.set(cat, 32 + styles.length * 64);
  return b;
}
function key(b) {
  if (b.length !== 80) throw new TypeError("key80 required");
  zero(b.subarray(76));
  const v = new DataView(b.buffer, b.byteOffset, b.length),
    time = v.getUint32(56, true),
    kind = v.getUint32(60, true),
    z = v.getUint32(64, true);
  if (
    time > 1 ||
    kind > 1 ||
    z > 25 ||
    (!time && (v.getBigUint64(40, true) || v.getBigUint64(48, true)))
  )
    throw new TypeError("typed tile key");
  return {
    sourceId: v.getBigUint64(0, true),
    generation: v.getBigUint64(8, true),
    layerId: v.getBigUint64(16, true),
    layerRevision: v.getBigUint64(24, true),
    styleRevision: v.getBigUint64(32, true),
    time: time
      ? { start: v.getBigInt64(40, true), end: v.getBigInt64(48, true) }
      : undefined,
    kind,
    z,
    x: v.getUint32(68, true),
    y: v.getUint32(72, true),
  };
}
export function decodeGeoTileReadReceipt(packet, handle, epoch) {
  const b = bytes(packet);
  if (b.length < 256) throw new TypeError("tile receipt");
  const { v, kind, handle: h, epoch: e } = fixed(b.slice(0, 256)),
    location = v.getUint32(48, true),
    ln = v.getUint32(52, true),
    an = v.getUint32(56, true);
  if (
    v.getBigUint64(32, true) === 0n ||
    v.getBigUint64(32, true) > 8388608n ||
    kind !== 2 ||
    h !== handle ||
    e !== epoch ||
    location > 1 ||
    ln > 4096 ||
    an > 4096 ||
    b.length !== 256 + ln + an
  )
    throw new TypeError("tile receipt planes");
  zero(b.subarray(60, 64));
  zero(b.subarray(84, 88));
  zero(b.subarray(168, 256));
  return {
    packet,
    handle,
    epoch,
    maxBytes: Number(v.getBigUint64(32, true)),
    ticket: b.slice(64, 168),
    key: key(b.subarray(88, 168)),
    location,
    locator: decoder.decode(b.subarray(256, 256 + ln)),
    attribution: decoder.decode(b.subarray(256 + ln)),
  };
}
export function decodeGeoTileFrame(packet) {
  const b = bytes(packet);
  if (b.length < 256) throw new TypeError("tile frame");
  const { v, handle, epoch } = fixed(b.slice(0, 256)),
    catLength = v.getBigUint64(40, true),
    keyCount = v.getBigUint64(48, true),
    attrCount = v.getBigUint64(56, true),
    attrBytes = v.getBigUint64(64, true);
  if (
    catLength > BigInt(MAX) ||
    keyCount > 64n ||
    attrCount > 16n ||
    attrBytes > 65536n ||
    256 + pad(Number(catLength)) + Number(keyCount) * 80 + Number(attrBytes) !==
      b.length
  )
    throw new TypeError("tile frame planes");
  zero(b.subarray(144, 256));
  zero(b.subarray(256 + Number(catLength), 256 + pad(Number(catLength))));
  const catalog = decodeGeoCatalogResponse(
    b.slice(256, 256 + Number(catLength)).buffer,
  );
  let at = 256 + pad(Number(catLength));
  const keys = [];
  for (let i = 0; i < Number(keyCount); i++) {
    keys.push(key(b.subarray(at, at + 80)));
    at += 80;
  }
  const attributions = [];
  for (let i = 0; i < Number(attrCount); i++) {
    if (at + 8 > b.length) throw new TypeError("attribution record");
    const length = new DataView(b.buffer, b.byteOffset + at, 8).getUint32(
      0,
      true,
    );
    zero(b.subarray(at + 4, at + 8));
    const end = at + 8 + length,
      next = pad(end);
    if (length > 4096 || next > b.length)
      throw new TypeError("attribution extent");
    zero(b.subarray(end, next));
    attributions.push(decoder.decode(b.subarray(at + 8, end)));
    at = next;
  }
  if (at !== b.length) throw new TypeError("tile trailing bytes");
  return {
    packet,
    epoch,
    cache: handle,
    view: v.getBigUint64(32, true),
    catalog,
    scene: catalog.scene,
    keys,
    attributions,
  };
}
class OwnedTileFrame {
  constructor(handle, data, session) {
    this.handle = handle;
    this._data = data;
    this.session = session;
    this.epoch = data.epoch;
    this._freezeCommand = 4;
    this.committed = false;
  }
  get data() {
    if (!this._data) throw new Error("tile frame disposed");
    return this._data;
  }
  async commit() {
    void this.data;
    await this.session.bridge.execute(
      encodeGeoTileRequest(7, this.handle, { epoch: this.epoch }),
    );
    this.committed = true;
    this.session.current = this;
  }
  async export(format = "png", options = {}) {
    void this.data;
    if (this.session.bridge.execute !== geoTileExecute && !options.bridge)
      throw new TypeError(
        "remote tile frame requires matching snapshot bridge",
      );
    const { exportGeoFrame } = await import("./geo-snapshot.js");
    return exportGeoFrame(this, this.epoch, format, options);
  }
  dispose() {
    this._data = undefined;
    return (this.disposal ??= (async () => {
      if (!this.committed && !this.session.closed)
        await this.session.bridge.execute(
          encodeGeoTileRequest(9, this.session.handle, { epoch: this.epoch }),
        );
      await this.session.bridge.execute(encodeGeoTileRequest(10, this.handle));
    })());
  }
}
export class GeoTileSession {
  static async create(
    sources,
    readTile,
    { viewId, budget: limit, bridge = nativeGeoTileBridge(limit) },
  ) {
    if (
      !sources.every((s) => s instanceof GeoTileSource) ||
      typeof readTile !== "function"
    )
      throw new TypeError("explicit sources/reader required");
    budget(limit);
    const s = new GeoTileSession();
    s.sources = Object.freeze([...sources]);
    s.readTile = readTile;
    s.viewId = uint(viewId);
    s.budget = limit;
    s.bridge = bridge;
    s.handle = fixed(await bridge.execute(encodeGeoTileRequest(1))).handle;
    return s;
  }
  _run(operation) {
    if (this.closed || this.active) throw new Error("tile session unavailable");
    this.controller = new AbortController();
    const controller = this.controller,
      promise = operation(controller.signal);
    this.active = promise;
    promise
      .finally(() => {
        if (this.active === promise) {
          this.active = undefined;
          this.controller = undefined;
        }
      })
      .catch(() => {});
    return promise;
  }
  async _prepare(camera, { catalog, vectorStyles, imageId }, signal) {
    const b = encodeGeoTileBegin(camera, this.sources),
      p = encodeGeoTilePrepare(catalog, vectorStyles, imageId);
    let epoch, frameHandle, data;
    const check = () => {
      if (signal.aborted)
        throw signal.reason ?? new Error("tile operation cancelled");
    };
    try {
      check();
      epoch = fixed(
        await this.bridge.execute(
          encodeGeoTileRequest(2, this.handle, {
            view: this.viewId,
            budget: this.budget,
            payload: b,
          }),
        ),
      ).epoch;
      check();
      while (true) {
        const issued = fixed(
            await this.bridge.execute(
              encodeGeoTileRequest(3, this.handle, { epoch }),
            ),
          ),
          readHandle = issued.handle;
        if (!readHandle) break;
        let receipt, payload, view;
        try {
          receipt = decodeGeoTileReadReceipt(
            await this.bridge.read(
              encodeGeoTileRequest(21, readHandle, {
                epoch,
                budget: this.budget,
              }),
            ),
            readHandle,
            epoch,
          );
          check();
          payload = await this.readTile(receipt, signal);
          view = bytes(payload);
          if (
            view.byteLength > receipt.maxBytes ||
            view.buffer.byteLength > receipt.maxBytes
          )
            throw new RangeError("tile read exceeds authorized capacity");
          check();
          await this.bridge.execute(
            encodeGeoTileRequest(4, readHandle, { epoch, payload: view }),
          );
        } finally {
          receipt = payload = view = undefined;
          await this.bridge.execute(
            encodeGeoTileRequest(5, readHandle, { epoch }),
          );
        }
        check();
      }
      const issued = fixed(
        await this.bridge.execute(
          encodeGeoTileRequest(6, this.handle, {
            epoch,
            budget: this.budget,
            payload: p,
          }),
        ),
      );
      frameHandle = issued.handle;
      check();
      data = decodeGeoTileFrame(
        await this.bridge.read(
          encodeGeoTileRequest(22, frameHandle, { epoch, budget: this.budget }),
        ),
      );
      check();
      if (
        data.epoch !== epoch ||
        data.cache !== this.handle ||
        data.view !== this.viewId
      )
        throw new TypeError("tile frame authority mismatch");
      const f = new OwnedTileFrame(frameHandle, data, this);
      f._cameraPacket = b.slice(0, 64);
      f._prepareDigest = createHash("sha256").update(p).digest("hex");
      frameHandle = undefined;
      return f;
    } catch (error) {
      data = undefined;
      if (frameHandle !== undefined)
        await this.bridge.execute(encodeGeoTileRequest(10, frameHandle));
      if (epoch !== undefined)
        await this.bridge.execute(
          encodeGeoTileRequest(9, this.handle, { epoch }),
        );
      throw error;
    }
  }
  prepare(camera, options) {
    return this._run((signal) => this._prepare(camera, options, signal));
  }
  update(camera, options) {
    if (typeof options.stage !== "function")
      throw new TypeError("explicit target stage required");
    return this._run(async (signal) => {
      const f = await this._prepare(camera, options, signal);
      try {
        await options.stage(f, signal);
        if (signal.aborted)
          throw signal.reason ?? new Error("tile staging cancelled");
        await f.commit();
        return f;
      } catch (error) {
        await this.bridge.execute(
          encodeGeoTileRequest(9, this.handle, { epoch: f.epoch }),
        );
        await f.dispose();
        throw error;
      }
    });
  }
  async cancel() {
    this.controller?.abort();
    if (this.active)
      try {
        await this.active;
      } catch {}
  }
  dispose() {
    this.closed = true;
    return (this.disposal ??= (async () => {
      await this.cancel();
      await this.bridge.execute(encodeGeoTileRequest(10, this.handle));
      this.closed = true;
    })());
  }
}
export async function httpTileLoader(receipt, signal) {
  if (
    receipt.location !== 1 ||
    !receipt.attribution ||
    !Number.isSafeInteger(receipt.maxBytes) ||
    receipt.maxBytes < 1 ||
    receipt.maxBytes > 8 << 20
  )
    throw new TypeError("configured attributed bounded network tile required");
  let url = receipt.locator;
  for (const name of ["z", "x", "y"])
    url = url.replaceAll("{" + name + "}", String(receipt.key[name]));
  if (!["http:", "https:"].includes(new URL(url).protocol))
    throw new TypeError("HTTP(S) URL required");
  const response = await fetch(url, { signal });
  if (
    !response.ok ||
    !["http:", "https:"].includes(new URL(response.url).protocol) ||
    !response.body
  )
    throw new Error("tile HTTP response rejected");
  const reader = response.body.getReader(),
    out = new Uint8Array(receipt.maxBytes);
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (
        value.buffer.byteLength > receipt.maxBytes ||
        length + value.byteLength > receipt.maxBytes
      )
        throw new RangeError("tile response exceeds authorized capacity");
      out.set(value, length);
      length += value.byteLength;
    }
    return out.subarray(0, length);
  } finally {
    await reader.cancel();
    reader.releaseLock();
  }
}
