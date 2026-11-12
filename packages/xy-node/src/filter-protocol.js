// Host-neutral XYFC/XYFR framing. Rust alone admits, bins, hashes, and selects tiers.
// XYFC v1 transport extent; admission/tier/budget decisions still belong to Rust.
const MAX_FILTER_PACKET_BYTES = 256 * 1024 * 1024;
function wireU64(value) {
  if (
    typeof value !== "bigint" &&
    !(typeof value === "number" && Number.isSafeInteger(value))
  )
    throw new TypeError("u64 fields require bigint or a safe integer");
  const result = BigInt(value);
  if (result < 0n || result > 0xffffffffffffffffn)
    throw new RangeError("u64 field is out of range");
  return result;
}
// Host-neutral framing only. Rust admits revisions, work and cancellation.
export function filterControlRequest(operation, token, payload = new Uint8Array()) {
  token = wireU64(token);
  if (!(payload instanceof Uint8Array) || payload.byteLength > MAX_FILTER_PACKET_BYTES - 32)
    throw new RangeError("invalid filter control payload extent");
  if (!(operation === 1 ? token === 0n && payload.length > 0
    : (operation === 2 || operation === 3) && token !== 0n && payload.length === 0))
    throw new TypeError("invalid filter control framing");
  const packet = new Uint8Array(32 + payload.byteLength), d = new DataView(packet.buffer);
  packet.set([88, 89, 70, 74]); d.setUint32(4, 1, true);
  d.setUint32(8, operation, true); d.setBigUint64(16, token, true); packet.set(payload, 32);
  return packet;
}
export function decodeFilterProgress(packet) {
  if (!(packet instanceof Uint8Array) || packet.length < 4)
    throw new Error("invalid filter response");
  const d = new DataView(packet.buffer, packet.byteOffset, packet.byteLength);
  if (d.getUint32(0, true) !== 0x4a465958) return null;
  if (packet.length !== 32 || d.getUint32(4, true) !== 1)
    throw new Error("invalid filter progress reply");
  const token = d.getBigUint64(8, true), rows = d.getBigUint64(16, true), totalRows = d.getBigUint64(24, true);
  if (!token || rows > totalRows) throw new Error("invalid filter progress reply");
  return {token, rows, totalRows};
}
export function filterReplyRetires(packet, token) {
  if (!(packet instanceof Uint8Array) || packet.length < 192)
    throw new Error("invalid filter response");
  const d = new DataView(packet.buffer, packet.byteOffset, packet.byteLength);
  if (d.getUint32(0, true) !== 0x52465958 || d.getUint32(4, true) !== 1)
    throw new Error("invalid filter response");
  return d.getBigUint64(144, true) > token || d.getBigUint64(24, true) >= token;
}
export function filterRequest(
  op,
  {
    revision,
    sourceId,
    epoch = 1n,
    sourceRevision = 1n,
    budgetBytes = 64n << 20n,
    args = [],
    range = [0, 0],
    exact = false,
    version = 1,
  } = {},
  payload = new Uint8Array(),
) {
  if (typeof exact !== "boolean") throw new TypeError("exact must be boolean");
  if (96 + payload.byteLength > MAX_FILTER_PACKET_BYTES)
    throw new RangeError("XYFC packet exceeds its transport extent");
  const out = new Uint8Array(96 + payload.byteLength),
    d = new DataView(out.buffer);
  const wireVersion = wireU64(version);
  if (wireVersion > 0xffffffffn) throw new RangeError("version must fit u32");
  out.set([88, 89, 70, 67]);
  d.setUint32(4, Number(wireVersion), true);
  d.setUint32(8, op, true);
  d.setUint32(12, exact ? 1 : 0, true);
  [
    revision,
    sourceId,
    epoch,
    sourceRevision,
    budgetBytes,
    ...Array.from({ length: 3 }, (_, i) => args[i] ?? 0n),
  ].forEach((x, i) => d.setBigUint64(16 + i * 8, wireU64(x), true));
  d.setFloat64(80, range[0], true);
  d.setFloat64(88, range[1], true);
  out.set(payload, 96);
  return out;
}
export function filterColumns(columns) {
  const arrays = Object.values(columns),
    n = arrays[0]?.length ?? 0;
  if (!arrays.length || arrays.some((a) => a.length !== n))
    throw new TypeError("filter columns must have equal lengths");
  if (
    !Number.isSafeInteger(n) ||
    n < 0 ||
    96 + arrays.length * n * 8 > MAX_FILTER_PACKET_BYTES
  )
    throw new RangeError(
      "XYFC columns exceed the transport extent; append bounded chunks instead",
    );
  const out = new Uint8Array(arrays.length * n * 8),
    d = new DataView(out.buffer);
  arrays.forEach((a, i) => {
    for (let j = 0; j < n; j++)
      d.setFloat64((i * n + j) * 8, Number(a[j]), true);
  });
  return out;
}
export function filterConfig(names, active, views) {
  const items = [active, ...views];
  const length =
    8 +
    active.cuts.length * 8 +
    views.reduce((n, v) => n + 24 + v.cuts.length * 8, 0);
  const out = new Uint8Array(length),
    d = new DataView(out.buffer);
  let at = 0;
  items.forEach((v, i) => {
    if (i) {
      d.setBigUint64(at, wireU64(v.id), true);
      d.setBigUint64(at + 8, wireU64(names.indexOf(v.dimension)), true);
      at += 16;
    }
    d.setBigUint64(at, BigInt(v.cuts.length), true);
    at += 8;
    for (const cut of v.cuts) {
      d.setFloat64(at, cut, true);
      at += 8;
    }
  });
  return out;
}
export function filterDensityConfig(names, active, views) {
  const u32 = (n) => {
    const value = wireU64(n);
    if (value > 0xffffffffn) throw new RangeError("u32 field is out of range");
    return Number(value);
  };
  const out = new Uint8Array(8 + active.cuts.length * 8 + views.length * 80),
    d = new DataView(out.buffer);
  d.setBigUint64(0, BigInt(active.cuts.length), true);
  active.cuts.forEach((v, i) => d.setFloat64(8 + i * 8, v, true));
  let at = 8 + active.cuts.length * 8;
  for (const v of views) {
    d.setBigUint64(at, wireU64(v.id), true);
    d.setBigUint64(at + 8, wireU64(names.indexOf(v.x)), true);
    d.setBigUint64(at + 16, wireU64(names.indexOf(v.y)), true);
    d.setUint32(at + 24, u32(v.width), true);
    d.setUint32(at + 28, u32(v.height), true);
    if (v.xRange.length !== 2 || v.yRange.length !== 2)
      throw new TypeError("density ranges require two endpoints");
    [...v.xRange, ...v.yRange].forEach((x, i) =>
      d.setFloat64(at + 32 + i * 8, x, true),
    );
    if (v.colors !== undefined) {
      const colors = v.colors;
      if (
        colors.length !== 8 ||
        colors.some((c) => !Number.isInteger(c) || c < 0 || c > 255)
      )
        throw new TypeError("density colors require eight u8 components");
      out.set(colors, at + 64);
      d.setUint32(at + 72, 1, true);
    }
    at += 80;
  }
  return out;
}
export function decodeFilterReply(packet) {
  const b = packet instanceof Uint8Array ? packet : new Uint8Array(packet),
    d = new DataView(b.buffer, b.byteOffset, b.byteLength);
  if (
    b.length < 192 ||
    d.getUint32(0, true) !== 0x52465958 ||
    d.getUint32(4, true) !== 1
  )
    throw new TypeError("invalid XYFR packet");
  const fields = [
    "requestedRevision",
    "revision",
    "sourceId",
    "epoch",
    "sourceRevision",
    "filterHash",
    "tier",
    "indexBytes",
    "residentBytes",
    "peakBytes",
    "rowsRead",
    "prefixCellsRead",
    "fallback",
    "activeView",
    "selectedCount",
    "affectedCount",
    "newestRevision",
    "firstRow",
    "sourceRows",
    "pageFirst",
    "membershipBytes",
    "hasIntent",
  ];
  const result = {
    packet: b.slice(),
    status: d.getUint32(8, true),
    views: [],
    membership: new Uint8Array(),
  };
  fields.forEach(
    (name, i) => (result[name] = d.getBigUint64(16 + i * 8, true)),
  );
  if (result.status || result.tier === 0n) result.selectedCount = null;
  if (result.affectedCount > 64n || result.membershipBytes > 8192n)
    throw new TypeError("invalid XYFR bounds");
  let at = 192;
  for (let i = 0n; i < result.affectedCount; i++) {
    const id = d.getBigUint64(at, true),
      n = Number(d.getBigUint64(at + 8, true));
    at += 16;
    if (n > 65536 || at + n * 8 > b.length)
      throw new TypeError("invalid XYFR bin extent");
    const counts = new BigUint64Array(n);
    for (let j = 0; j < n; j++) {
      counts[j] = d.getBigUint64(at, true);
      at += 8;
    }
    result.views.push({ id, counts });
  }
  const extension = d.getUint32(12, true);
  if (extension > 1) throw new TypeError("unknown XYFR extension");
  result.density = [];
  if (extension === 1) {
    if (
      at + 16 > b.length ||
      d.getUint32(at, true) !== 0x50465958 ||
      d.getUint32(at + 4, true) !== 1 ||
      d.getBigUint64(at + 8, true) !== result.affectedCount
    )
      throw new TypeError("invalid XYFP");
    at += 16;
    for (const view of result.views) {
      const id = d.getBigUint64(at, true),
        width = d.getUint32(at + 8, true),
        height = d.getUint32(at + 12, true),
        n = width * height;
      if (
        id !== view.id ||
        !width ||
        !height ||
        n !== view.counts.length ||
        at + 56 + n * 16 > b.length
      )
        throw new TypeError("invalid density extent");
      const ranges = Array.from({ length: 4 }, (_, i) =>
        d.getFloat64(at + 16 + i * 8, true),
      );
      const maximum = d.getFloat64(at + 48, true);
      at += 56;
      const totals = new BigUint64Array(n);
      for (let i = 0; i < n; i++) totals[i] = d.getBigUint64(at + i * 8, true);
      at += n * 8;
      const grid = new Float32Array(n);
      for (let i = 0; i < n; i++) grid[i] = d.getFloat32(at + i * 4, true);
      at += n * 4;
      const rgba = b.slice(at, at + n * 4);
      at += n * 4;
      result.density.push({
        id,
        width,
        height,
        maximum,
        xRange: ranges.slice(0, 2),
        yRange: ranges.slice(2),
        totals,
        selected: view.counts,
        grid,
        rgba,
      });
    }
  }
  if (at + Number(result.membershipBytes) !== b.length)
    throw new TypeError("invalid XYFR length");
  result.membership = b.slice(at);
  return result;
}
export class FilterTierCError extends Error {
  constructor(reply) {
    super(`Filter Tier C rejected request (status ${reply.status})`);
    this.name = "FilterTierCError";
    this.status = reply.status;
    this.reply = reply;
  }
}
/** Thin programmatic session client. A native handle or dedicated WASM Worker owns state. */
const filterCloseResults = new WeakMap();
function initializeClient(client, execute, close, names, rows,
  {sourceId, epoch = 1n, firstRow = 0n, budgetBytes = 64n << 20n} = {}) {
  client.executeTransport = execute;
  client.closeTransport = close;
  client.names = names;
  client.sourceId = wireU64(sourceId);
  client.epoch = wireU64(epoch);
  client.sourceRevision = 1n;
  client.budgetBytes = wireU64(budgetBytes);
  client.revision = 0n;
  client.firstRow = wireU64(firstRow);
  client.rows = wireU64(rows);
  client.closed = false;
  client._metadataWatermark = 0n;
  client._configurationSequence = 0n;
  client._densityDefinition = null;
}
export class FilterSessionClient {
  constructor(
    execute,
    close,
    columns,
    { sourceId, epoch = 1n, firstRow = 0n, budgetBytes = 64n << 20n } = {},
  ) {
    initializeClient(this, execute, close, Object.keys(columns),
      Object.values(columns)[0]?.length ?? 0, {sourceId, epoch, firstRow, budgetBytes});
  }
  /** Adopt an actual source-registration reply; no array-shaped stand-ins. */
  static fromRegistration(execute, close, registration) {
    const {names, packet, budgetBytes} = registration ?? {};
    if (typeof execute !== "function" || typeof close !== "function"
      || !Array.isArray(names) || names.length < 1 || names.length > 64
      || names.some(name => typeof name !== "string") || new Set(names).size !== names.length
      || !(packet instanceof Uint8Array) || packet.length !== 192)
      throw new TypeError("invalid filter source registration");
    const result = decodeFilterReply(packet);
    if (result.status || result.sourceId === 0n || result.epoch === 0n
      || result.sourceRevision !== 1n || result.revision === 0n
      || result.requestedRevision !== result.revision || result.newestRevision !== result.revision
      || result.affectedCount !== 0n || result.tier !== 0n || result.indexBytes !== 0n
      || result.activeView !== 0n || result.hasIntent !== 0n)
      throw new TypeError("invalid filter source registration");
    const client = Object.create(FilterSessionClient.prototype);
    initializeClient(client, execute, close, [...names], result.sourceRows, {
      sourceId: result.sourceId, epoch: result.epoch, firstRow: result.firstRow, budgetBytes,
    });
    client.revision = result.newestRevision;
    client._metadataWatermark = result.newestRevision;
    client._configurationSequence = result.newestRevision;
    return client;
  }
  request(op, options = {}, payload = new Uint8Array()) {
    if (this.closed) throw new Error("filter session is closed");
    return filterRequest(
      op,
      {
        revision: ++this.revision,
        sourceId: this.sourceId,
        epoch: this.epoch,
        sourceRevision: this.sourceRevision,
        budgetBytes: this.budgetBytes,
        ...options,
      },
      payload,
    );
  }
  accept(packet) {
    const result = decodeFilterReply(packet);
    if (result.status) throw new FilterTierCError(result);
    // Transport completion order need not be Rust publication order.
    if (result.newestRevision >= this._metadataWatermark) {
      this._metadataWatermark = result.newestRevision;
      this.sourceRevision = result.sourceRevision;
      this.rows = result.sourceRows;
    }
    return result;
  }
  initialize(columns) {
    return this.call(
      this.request(
        1,
        { args: [BigInt(this.names.length), this.rows, this.firstRow] },
        filterColumns(columns),
      ),
    );
  }
  configure(active, views) {
    return this.call(
      this.request(
        3,
        {
          args: [
            wireU64(active.id),
            wireU64(this.names.indexOf(active.dimension)),
            BigInt(views.length),
          ],
        },
        filterConfig(this.names, active, views),
      ),
    );
  }
  _densityRequest(active, views) {
    return this.request(
        10,
        {
          args: [
            wireU64(active.id),
            wireU64(this.names.indexOf(active.dimension)),
            BigInt(views.length),
          ],
        },
        filterDensityConfig(this.names, active, views),
      );
  }
  configureDensity(active, views) {
    return this.call(this._densityRequest(active, views));
  }
  /** Submit changed authoring metadata; explicit configureDensity always rebuilds.
   * Rust still decides whether subsequent queries need an index rebuild. */
  activateDensity(active, views) {
    const packet = this._densityRequest(active, views);
    const previous = this._densityDefinition;
    // Ignore only the request sequence (bytes 16..24). Everything else,
    // including source revision, budget, active identity and paint, must match.
    if (previous && previous.sequence === this._configurationSequence
      && previous.packet.length === packet.length
      && packet.every((byte, i) => i >= 16 && i < 24 || byte === previous.packet[i])) {
      return undefined;
    }
    const definition = packet.slice();
    const remember = result => {
      if (!this.closed && this._configurationSequence === result.requestedRevision)
        this._densityDefinition = {packet: definition, sequence: result.requestedRevision};
      return result;
    };
    const result = this.call(packet);
    return result instanceof Promise ? result.then(remember) : remember(result);
  }
  paint({ exact = false } = {}) {
    return this.call(this.request(11, { exact }));
  }
  baseFilter(ranges = [], mask = new Uint8Array()) {
    const payload = new Uint8Array(ranges.length * 24 + mask.length),
      d = new DataView(payload.buffer);
    ranges.forEach((r, i) => {
      d.setBigUint64(i * 24, wireU64(this.names.indexOf(r.dimension)), true);
      d.setFloat64(i * 24 + 8, r.lo, true);
      d.setFloat64(i * 24 + 16, r.hi, true);
    });
    payload.set(mask, ranges.length * 24);
    return this.call(
      this.request(
        12,
        { args: [BigInt(ranges.length), BigInt(mask.length)] },
        payload,
      ),
    );
  }
  beginEdit() {
    return this.call(this.request(13));
  }
  cancelEdit() {
    return this.call(this.request(14));
  }
  commitEdit() {
    return this.call(this.request(15));
  }
  range(lo, hi, { exact = false } = {}) {
    return this.call(this.request(5, { range: [lo, hi], exact }));
  }
  rangePaint(lo, hi, { exact = false } = {}) {
    const legacy = () => {
      const finish = (reply) => {
        if (this.closed || this.revision !== reply.requestedRevision
          || this.sourceRevision !== reply.sourceRevision) {
          const error = new Error("filter range-and-paint was superseded before compatibility paint");
          error.code = "XYG_FILTER_CANCELLED";
          throw error;
        }
        return this.paint({ exact });
      };
      const reply = this.range(lo, hi, { exact });
      return reply instanceof Promise ? reply.then(finish) : finish(reply);
    };
    if (this._rangePaintSupport === false) return legacy();
    const sourceRevision = this.sourceRevision;
    const packet = this.request(5, { version: 3, range: [lo, hi], exact });
    const sequence = new DataView(packet.buffer, packet.byteOffset).getBigUint64(16, true);
    const accepted = (reply) => {
      if (!reply.density.length) throw new Error("range-and-paint response omitted density");
      if (!this.closed) this._rangePaintSupport = true;
      return reply;
    };
    const refused = (error) => {
      const r = error?.reply;
      if (this._rangePaintSupport === undefined && error instanceof FilterTierCError
        && error.status === 1 && !this.closed && this.revision === sequence
        && r.requestedRevision === sequence && r.newestRevision < sequence
        && r.sourceId === this.sourceId && r.epoch === this.epoch
        && r.sourceRevision === sourceRevision && this.sourceRevision === sourceRevision) {
        // Old peers reject the unknown version before admission. A malformed
        // v3 payload instead consumes its watermark and must never be retried.
        this._rangePaintSupport = false;
        return legacy();
      }
      throw error;
    };
    try {
      const reply = this.call(packet);
      return reply instanceof Promise ? reply.then(accepted, refused) : accepted(reply);
    } catch (error) {
      return refused(error);
    }
  }
  clear() {
    return this.call(this.request(7));
  }
  evict() {
    return this.call(this.request(6));
  }
  rebuild() {
    return this.call(this.request(4));
  }
  cancel() {
    return this.call(this.request(8));
  }
  membership(first, count) {
    return this.call(
      this.request(9, { args: [wireU64(first), wireU64(count)] }),
    );
  }
  append(columns) {
    if (Object.keys(columns).join("\0") !== this.names.join("\0"))
      throw new TypeError("append must retain the source schema order");
    const n = BigInt(Object.values(columns)[0]?.length ?? 0);
    return this.call(
      this.request(
        2,
        { args: [BigInt(this.names.length), n, this.firstRow + this.rows] },
        filterColumns(columns),
      ),
    );
  }
  close() {
    if (!this.closed) {
      this.closed = true;
      this._densityDefinition = null;
      const result = this.closeTransport();
      filterCloseResults.set(this, result);
    }
    return filterCloseResults.get(this);
  }
  call(packet) {
    // Rust may accept a configuration while its ACK is held by the transport.
    // Never skip authoring against an earlier accepted ACK during that interval.
    if (packet.length >= 96) {
      const d = new DataView(packet.buffer, packet.byteOffset, packet.byteLength);
      const sequence = d.getBigUint64(16, true);
      if ([1, 3, 10, 16].includes(d.getUint32(8, true))
        && sequence > this._configurationSequence) {
        this._configurationSequence = sequence;
        this._densityDefinition = null;
      }
    }
    const reply = this.executeTransport(packet);
    return typeof reply?.then === "function"
      ? Promise.resolve(reply).then((b) => this.accept(b))
      : this.accept(reply);
  }
}
