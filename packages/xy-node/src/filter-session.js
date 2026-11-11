import {
  pointer,
  xyFilterSessionNew,
  xyFilterSessionExecute,
  xyFilterSessionFree,
} from "./native.js";
import { FilterSessionClient } from "./filter-protocol.js";
import { ChunkedColumnRef } from "./chunked-column-ref.js";
import { nativeFilterLane } from "./filter-cooperative.js";
export {
  filterRequest,
  decodeFilterReply,
  FilterTierCError,
} from "./filter-protocol.js";
function executeInto(handle, packet, output) {
  const written = new BigUint64Array(1);
  const status = xyFilterSessionExecute(
    handle,
    pointer(packet, "uint8_t *"),
    packet.byteLength,
    pointer(output, "uint8_t *"),
    output.byteLength,
    pointer(written, "size_t *"),
  );
  if (status !== 0) {
    const error = new Error(
      `native filter adapter failed (${status}); required capacity ${written[0]}`,
    );
    error.status = status;
    error.required = written[0];
    throw error;
  }
  return output.slice(0, Number(written[0]));
}
export function executeFilterPacket(handle, packet, capacity = 2 << 20) {
  return executeInto(handle, packet, new Uint8Array(capacity));
}
function initializeSession(client, columns) {
  const values = Object.values(columns);
  if (values.some((c) => c instanceof ChunkedColumnRef)) {
    if (!values.every((c) => c instanceof ChunkedColumnRef))
      throw new TypeError("filter columns must be all arrays or all issued chunked planes");
    const payload = new Uint8Array(values.length * 16), d = new DataView(payload.buffer);
    values.forEach((c, i) => {
      d.setBigUint64(i * 16, BigInt(c.source.handle), true);
      d.setBigUint64(i * 16 + 8, BigInt(c.plane), true);
    });
    return client.call(client.request(16, {
      version: 2, args: [BigInt(values.length), client.rows, client.firstRow],
    }, payload));
  }
  return client.initialize(columns);
}

export async function createNativeFilterSession(columns, options) {
  // One fixed caller-owned reply scratch serves every bounded native turn.
  // Each returned packet is an independent copy; no progress-sized turn
  // allocates another full-capacity buffer retained until a later GC cycle.
  let handle = 0n, client, output = new Uint8Array(2 << 20);
  const lane = nativeFilterLane(
    b => executeInto(handle, b, output),
    () => { const owned = handle; handle = 0n; output = null; if (owned) xyFilterSessionFree(owned); },
    () => { if (client) client.close().catch(() => {}); },
  );
  client = new FilterSessionClient(lane.execute, lane.close, columns, options);
  handle = xyFilterSessionNew(client.budgetBytes);
  try {
    if (!handle) throw new Error("filter session allocation refused");
    const initial = await initializeSession(client, columns);
    const registration = initial.packet.slice();
    let transferred = false;
    const request = client.request.bind(client);
    client.request = (...args) => {
      if (transferred && !client.closed) throw new Error("filter command authority was transferred");
      return request(...args);
    };
    client.takeRegistration = () => {
      if (transferred || client.closed || client.revision !== initial.newestRevision)
        throw new Error("filter registration requires a fresh owned session");
      transferred = true;
      return {names: [...client.names], packet: registration.slice(), budgetBytes: client.budgetBytes};
    };
    return client;
  } catch (error) {
    try { await client.close(); } catch { /* Preserve the initiating failure. */ }
    throw error;
  }
}
export class FilterTierCSession extends FilterSessionClient {
  constructor(columns, options) {
    let handle = 0n;
    super(
      (b) => executeFilterPacket(handle, b),
      () => xyFilterSessionFree(handle),
      columns,
      options,
    );
    handle = xyFilterSessionNew(this.budgetBytes);
    if (!handle) throw new Error("filter session allocation refused");
    this.handle = handle;
    try {
      initializeSession(this, columns);
    } catch (error) {
      this.close();
      throw error;
    }
  }
}
