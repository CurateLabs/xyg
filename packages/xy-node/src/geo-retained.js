/** Retained point-source coordinator. Rust owns validation, projection and tier policy. */
import {
  encodeGeoScaleRequest as encode,
  decodeGeoScaleReply as decode,
  driveGeoSession,
  prepareGeoSceneData,
  nativeGeoScaleBridge,
  geoScaleExecute,
  parseGeoRowsData,
} from "./geoscale.js";
const HEADER = 256;
function uint(n, bits = 64) {
  if (typeof n !== "bigint" || n < 0n || n >= 1n << BigInt(bits))
    throw new TypeError(`expected u${bits} bigint`);
  return n;
}
function cellPayload(cell, max, cursor) {
  if (!Number.isInteger(cell) || cell < 0 || cell > 0xffffffff)
    throw new TypeError("expected u32 cell");
  uint(max);
  if (
    cursor !== undefined &&
    (!(cursor instanceof Uint8Array) || cursor.byteLength !== 208)
  )
    throw new TypeError("cursor must be opaque208 bytes");
  const b = new Uint8Array(16 + (cursor ? 208 : 0)),
    v = new DataView(b.buffer);
  v.setUint32(0, cell, true);
  v.setUint32(4, cursor ? 1 : 0, true);
  v.setBigUint64(8, max, true);
  if (cursor) b.set(cursor, 16);
  return b;
}
export function parseGeoMembershipData(packet, owner, sequence) {
  const b = new Uint8Array(packet),
    v = new DataView(packet);
  if (
    b.length < HEADER ||
    String.fromCharCode(...b.subarray(0, 4)) !== "XYGZ" ||
    v.getUint32(4, true) !== 1 ||
    v.getUint32(8, true) !== 2
  )
    throw new TypeError("invalid membership frame");
  const count = v.getBigUint64(32, true),
    flag = v.getUint32(72, true),
    size = v.getUint32(76, true);
  if (
    v.getBigUint64(16, true) !== owner ||
    v.getBigUint64(24, true) !== sequence ||
    v.getBigUint64(80, true) !== owner ||
    count > 4096n ||
    flag > 1 ||
    size !== flag * 208 ||
    b.length !== 256 + size + Number(count) * 32 ||
    b.subarray(248, 256).some((x) => x)
  )
    throw new TypeError("invalid membership planes");
  validateKey(b.subarray(88, 248));
  if (
    flag &&
    (b.subarray(256, 416).some((n, i) => n !== b[88 + i]) ||
      v.getUint32(416, true) !== v.getUint32(12, true))
  )
    throw new TypeError("mismatched membership cursor");
  const records = b.subarray(256 + size);
  for (let i = 0; i < records.length; i += 32)
    if (records.subarray(i + 24, i + 32).some((x) => x))
      throw new TypeError("invalid member padding");
  return {
    packet,
    cell: v.getUint32(12, true),
    count,
    cursor: flag ? b.slice(256, 464) : undefined,
    key: b.subarray(88, 248),
    records,
    projectedVertices: v.getBigUint64(40, true),
    record(index) {
      if (!Number.isInteger(index) || index < 0 || BigInt(index) >= count)
        throw new RangeError("member index");
      const at = 256 + size + index * 32;
      return {
        featureId: v.getBigUint64(at, true),
        sourceRow: v.getBigUint64(at + 8, true),
        chunkIndex: v.getUint32(at + 16, true),
        row: v.getUint32(at + 20, true),
      };
    },
  };
}
async function prepare(
  bridge,
  { command, handle, sequence, budget, payload, parse },
) {
  const r = decode(
    await bridge.execute(
      encode({ command, handle, sequence, budget, payload }),
    ),
  );
  let packet, data;
  try {
    if (
      r.sourceHandle !== handle ||
      r.sequence !== sequence ||
      r.dataLength > 33554432n ||
      4n * r.dataLength > BigInt(budget.processorBytes)
    )
      throw new TypeError("invalid retained data reply");
    packet = await bridge.read(encode({ command: 23, handle: r.handle }));
    if (BigInt(packet.byteLength) !== r.dataLength)
      throw new TypeError("invalid retained length");
    data = parse(packet, handle, sequence);
    packet = undefined;
  } catch (e) {
    packet = data = undefined;
    await bridge.execute(encode({ command: 10, handle: r.handle }));
    throw e;
  }
  let disposal;
  return {
    handle: r.handle,
    get data() {
      if (!data) throw new Error("data disposed");
      return data;
    },
    dispose() {
      data = undefined;
      return (disposal ??= bridge
        .execute(encode({ command: 10, handle: r.handle }))
        .then(() => {}));
    },
  };
}
export class RetainedGeoSource {
  static async create(manifest, readChunk, options) {
    const {
      budget,
      bridge = nativeGeoScaleBridge(budget.processorBytes),
      signal,
    } = options;
    if (
      Object.keys(options).some(
        (k) => !["budget", "bridge", "signal"].includes(k),
      )
    )
      throw new TypeError("unsupported retained source option");
    if (typeof readChunk !== "function")
      throw new TypeError("readChunk must be callable");
    const source = new RetainedGeoSource();
    source.bridge = bridge;
    source.budget = { ...budget };
    source.readChunk = readChunk;
    source.closed = false;
    source.sequence = 0n;
    source.handle = decode(
      await bridge.execute(encode({ command: 4, budget, payload: manifest })),
    ).handle;
    try {
      const r = await driveGeoSession(bridge, {
        handle: source.handle,
        sequence: 0n,
        budget: source.budget,
        readChunk,
        signal,
      });
      if (r.code !== 3) throw new Error("source validation did not complete");
      if (r.source.geometry !== 1 && r.source.geometry !== 4)
        throw new TypeError("retained source requires Point or MultiPoint");
      source.info = r.source;
      return source;
    } catch (e) {
      await source.dispose();
      throw e;
    }
  }
  _run(operation, detached = false) {
    if (!detached && (this.closed || this.disposing))
      throw new Error("source disposed");
    if (this.active) throw new Error("source operation already active");
    const controller = new AbortController();
    this.abort = controller;
    const promise = operation(controller.signal);
    this.active = promise;
    promise
      .finally(() => {
        if (this.active === promise) {
          this.active = undefined;
          this.abort = undefined;
        }
      })
      .catch(() => {});
    return promise;
  }
  update(query, { sequence, style, signal }) {
    uint(sequence);
    if (!(style instanceof Uint8Array) || style.length !== 48)
      throw new TypeError("style must be exact48 bytes");
    const request = encode({
      command: 5,
      handle: this.handle,
      sequence,
      budget: this.budget,
      query,
    });
    const queryPacket = request.slice(0);
    style = style.slice();
    return this._run(async (ownSignal) => {
      const abort = () => this.abort?.abort();
      signal?.addEventListener("abort", abort, { once: true });
      try {
        if (signal?.aborted) abort();
        if (ownSignal.aborted) throw new Error("operation aborted");
        await this.bridge.execute(request);
        this.sequence = sequence;
        const r = await driveGeoSession(this.bridge, {
          handle: this.handle,
          sequence,
          budget: this.budget,
          readChunk: this.readChunk,
          signal: ownSignal,
        });
        if (r.code !== 4) throw new Error("retained update did not complete");
        const frame = await prepareGeoSceneData(this.bridge, {
          handle: this.handle,
          sequence,
          budget: this.budget,
          style,
        });
        if (ownSignal.aborted) {
          await frame.dispose();
          throw new Error("operation aborted");
        }
        attachRetainedFrame(this, frame, sequence, queryPacket, style);
        this.current = frame;
        return frame;
      } finally {
        signal?.removeEventListener("abort", abort);
      }
    });
  }
  membership(cell, { sequence, maxProjectedVertices, cursor, _owner }) {
    const owner = _owner ?? this.current?.handle;
    if (owner === undefined) throw new Error("no published frame");
    const payload = cellPayload(cell, maxProjectedVertices, cursor);
    return this._run(async (signal) => {
      const member = decode(
        await this.bridge.execute(
          encode({
            command: 12,
            handle: owner,
            sequence,
            budget: this.budget,
            payload,
          }),
        ),
      ).handle;
      let page;
      try {
        const r = await driveGeoSession(this.bridge, {
          handle: member,
          sequence,
          budget: this.budget,
          readChunk: this.readChunk,
          signal,
        });
        if (r.code !== 4) throw new Error("membership did not complete");
        page = await prepare(this.bridge, {
          command: 13,
          handle: member,
          sequence,
          budget: this.budget,
          parse: parseGeoMembershipData,
        });
        if (signal.aborted) {
          await page.dispose();
          throw new Error("operation aborted");
        }
        return page;
      } finally {
        try {
          await this.bridge.execute(encode({ command: 10, handle: member }));
          if (signal.aborted) {
            if (page) await page.dispose();
            throw new Error("operation aborted");
          }
        } catch (error) {
          if (page) await page.dispose();
          throw error;
        }
      }
    }, _owner !== undefined);
  }
  cancel() {
    this.abort?.abort();
    if (this.active)
      return this.active.then(
        () => {},
        () => {},
      );
    if (this.closed) return Promise.resolve();
    return this.bridge
      .execute(
        encode({ command: 9, handle: this.handle, sequence: this.sequence }),
      )
      .then(() => {});
  }
  dispose() {
    return (this.disposing ??= (async () => {
      this.abort?.abort();
      if (this.active)
        try {
          await this.active;
        } catch {}
      await this.bridge.execute(encode({ command: 10, handle: this.handle }));
      this.closed = true;
    })());
  }
}
export function parseGeoPickData(packet, owner, sequence) {
  const b = new Uint8Array(packet),
    v = new DataView(packet);
  if (
    b.length < 256 ||
    String.fromCharCode(...b.subarray(0, 4)) !== "XYGZ" ||
    v.getUint32(4, true) !== 1 ||
    v.getUint32(8, true) !== 3
  )
    throw new TypeError("invalid pick frame");
  const count = v.getBigUint64(32, true),
    mode = v.getUint32(40, true),
    max = v.getUint32(44, true);
  if (
    v.getBigUint64(16, true) !== owner ||
    v.getBigUint64(24, true) !== sequence ||
    v.getBigUint64(80, true) !== owner ||
    mode > 1 ||
    max < 1 ||
    max > 4096 ||
    count > BigInt(max) ||
    b.length !== 256 + Number(count) * 48 ||
    b.subarray(12, 16).some((x) => x) ||
    b.subarray(72, 80).some((x) => x) ||
    b.subarray(248, 256).some((x) => x)
  )
    throw new TypeError("invalid pick planes");
  validateKey(b.subarray(88, 248));
  if ([48, 56, 64].some((at) => !Number.isFinite(v.getFloat64(at, true))))
    throw new TypeError("nonfinite pick coordinates");
  for (let at = 256; at < b.length; at += 48) {
    const tag = v.getUint32(at, true);
    if (
      tag > 1 ||
      v.getUint32(at + 36, true) !== 0 ||
      (tag === 0 &&
        (v.getUint32(at + 32, true) !== 0 ||
          v.getBigUint64(at + 40, true) !== 0n)) ||
      (tag === 1 &&
        (b.subarray(at + 4, at + 32).some((x) => x) ||
          v.getBigUint64(at + 40, true) === 0n))
    )
      throw new TypeError("invalid pick record");
  }
  return {
    packet,
    count,
    key: b.subarray(88, 248),
    record(index) {
      if (!Number.isInteger(index) || index < 0 || BigInt(index) >= count)
        throw new RangeError("pick index");
      const at = 256 + index * 48;
      return {
        tag: v.getUint32(at, true),
        vertex: v.getUint32(at + 4, true),
        featureId: v.getBigUint64(at + 8, true),
        sourceRow: v.getBigUint64(at + 16, true),
        chunkIndex: v.getUint32(at + 24, true),
        row: v.getUint32(at + 28, true),
        cell: v.getUint32(at + 32, true),
        count: v.getBigUint64(at + 40, true),
      };
    },
  };
}
RetainedGeoSource.prototype.pick = function ({
  sequence,
  style,
  x,
  y,
  tolerance,
  mode,
  maxHits,
  _owner,
}) {
  const owner = _owner ?? this.current?.handle;
  if (owner === undefined) throw new Error("no published frame");
  if (
    !(style instanceof Uint8Array) ||
    style.length !== 48 ||
    !Number.isInteger(mode) ||
    mode < 0 ||
    mode > 1 ||
    !Number.isInteger(maxHits) ||
    maxHits < 1 ||
    maxHits > 4096
  )
    throw new TypeError("invalid typed pick framing");
  if ([x, y, tolerance].some((n) => typeof n !== "number"))
    throw new TypeError("pick coordinates must be numbers");
  const payload = new Uint8Array(80),
    v = new DataView(payload.buffer);
  payload.set(style);
  v.setFloat64(48, x, true);
  v.setFloat64(56, y, true);
  v.setFloat64(64, tolerance, true);
  v.setUint32(72, mode, true);
  v.setUint32(76, maxHits, true);
  return this._run(async (signal) => {
    const result = await prepare(this.bridge, {
      command: 14,
      handle: owner,
      sequence,
      budget: this.budget,
      payload,
      parse: parseGeoPickData,
    });
    if (signal.aborted) {
      await result.dispose();
      throw new Error("operation aborted");
    }
    return result;
  }, _owner !== undefined);
};

function validateKey(b) {
  const v = new DataView(b.buffer, b.byteOffset, b.byteLength);
  if (
    b.length !== 160 ||
    b.subarray(156).some((n) => n) ||
    ![4326, 3857].includes(v.getUint32(24, true)) ||
    ![1, 4].includes(v.getUint32(28, true)) ||
    ![4326, 3857].includes(v.getUint32(56, true)) ||
    v.getUint32(60, true) > 1 ||
    v.getUint32(120, true) > 2 ||
    v.getUint32(124, true) > 1 ||
    v.getUint32(144, true) > 1 ||
    [64, 72, 80, 88, 96, 104, 112].some(
      (at) => !Number.isFinite(v.getFloat64(at, true)),
    )
  )
    throw new TypeError("invalid typed geographic key");
}


RetainedGeoSource.prototype._rows = function (owner, sequence) {
  return this._run(async (signal) => {
    let session, page;
    try {
      const issued = decode(await this.bridge.execute(encode({
        command: 15, handle: owner, sequence, budget: this.budget,
      })));
      session = issued.handle;
      if (issued.sequence !== sequence) throw new TypeError("mismatched row sequence");
      if (signal.aborted) throw new Error("operation aborted");
      const completed = await driveGeoSession(this.bridge, {
        handle: session, sequence, budget: this.budget, readChunk: this.readChunk, signal,
      });
      if (completed.code !== 4) throw new Error("geographic rows did not complete");
      page = await prepare(this.bridge, {
        command: 16, handle: session, sequence, budget: this.budget,
        parse(packet, handle, sequence) {
          const data = parseGeoRowsData(packet);
          data.records = new Uint8Array(packet, 256);
          const v = new DataView(packet);
          data.stats = {rowsExamined: v.getBigUint64(48, true), bytesRead: v.getBigUint64(56, true), chunksRead: v.getUint32(64, true), chunksConsidered: v.getUint32(68, true)};
          if (data.owner !== handle || data.sequence !== sequence) throw new TypeError("mismatched row packet identity");
          return data;
        },
      });
      if (signal.aborted) throw new Error("operation aborted");
      const pageOwner = page.handle;
      page.nextPage = (...args) => {
        if (args.length) throw new TypeError("nextPage accepts no cursor or options");
        if (!page.data.hasNext) throw new Error("no next geographic row page");
        return this._rows(pageOwner, sequence);
      };
      return page;
    } catch (error) {
      if (page) await page.dispose();
      throw error;
    } finally {
      if (session !== undefined) {
        try {
          await this.bridge.execute(encode({command: 10, handle: session}));
          if (signal.aborted) throw new Error("operation aborted");
        } catch (error) {
          if (page) await page.dispose();
          throw error;
        }
      }
    }
  }, true);
};

const frameAuthorities=new WeakMap();
export function retainedFrameAuthority(frame){return frameAuthorities.get(frame);}
export function attachRetainedFrame(source, frame, sequence, queryPacket, style, provenance) {
  frameAuthorities.set(frame,Object.freeze({source,bridge:source.bridge}));
  provenance?.(frame);
  frame.retain = async () => {
    void frame.data;
    const querySnapshot=queryPacket.slice(0),styleSnapshot=style.slice();
    const owned = await prepareGeoSceneData(source.bridge, {
      command:26, handle:frame.handle, sequence, budget:source.budget,
    });
    attachRetainedFrame(source, owned, sequence, querySnapshot, styleSnapshot, provenance);
    if(frame.indexStats)owned.indexStats={...frame.indexStats};
    return owned;
  };

        const rowsOwner = frame.handle;
        frame.rows = (...args) => {
          if (args.length) throw new TypeError("rows accepts no cursor or options");
          void frame.data;
          return source._rows(rowsOwner, sequence);
        };
        frame.membership = (cell, options) => {
          void frame.data;
          return source.membership(cell, {
            ...options,
            sequence,
            _owner: frame.handle,
          });
        };
        frame.pick = (options) => {
          void frame.data;
          return source.pick({ ...options, sequence, _owner: frame.handle });
        };
        frame._source = source;
        frame._queryPacket = queryPacket;
        frame._style = style.slice();
        frame.export = async (format = "png", options = {}) => {
          if (source.bridge.execute !== geoScaleExecute && !options.bridge)
            throw new TypeError(
              "remote frame requires its matching snapshot bridge",
            );
          const { exportGeoFrame } = await import("./geo-snapshot.js");
          return exportGeoFrame(frame, sequence, format, options);
        };
  frame.spatialIndex = async (options) => {
    void frame.data;
    const { GeoSpatialIndex } = await import("./geo-spatial.js");
    return GeoSpatialIndex._fromFrame(frame, source, options);
  };
}
