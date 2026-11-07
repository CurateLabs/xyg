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
  } = {},
  payload = new Uint8Array(),
) {
  if (typeof exact !== "boolean") throw new TypeError("exact must be boolean");
  if (96 + payload.byteLength > MAX_FILTER_PACKET_BYTES)
    throw new RangeError("XYFC packet exceeds its transport extent");
  const out = new Uint8Array(96 + payload.byteLength),
    d = new DataView(out.buffer);
  out.set([88, 89, 70, 67]);
  d.setUint32(4, 1, true);
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
export class FilterSessionClient {
  constructor(
    execute,
    close,
    columns,
    { sourceId, epoch = 1n, firstRow = 0n, budgetBytes = 64n << 20n } = {},
  ) {
    this.executeTransport = execute;
    this.closeTransport = close;
    this.names = Object.keys(columns);
    this.sourceId = wireU64(sourceId);
    this.epoch = wireU64(epoch);
    this.sourceRevision = 1n;
    this.budgetBytes = wireU64(budgetBytes);
    this.revision = 0n;
    this.firstRow = wireU64(firstRow);
    this.rows = BigInt(Object.values(columns)[0]?.length ?? 0);
    this.closed = false;
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
    this.sourceRevision = result.sourceRevision;
    this.rows = result.sourceRows;
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
  range(lo, hi, { exact = false } = {}) {
    return this.call(this.request(5, { range: [lo, hi], exact }));
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
      return this.closeTransport();
    }
  }
  call(packet) {
    const reply = this.executeTransport(packet);
    return reply instanceof Promise
      ? reply.then((b) => this.accept(b))
      : this.accept(reply);
  }
}
