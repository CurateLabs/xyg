import {
  pointer,
  xyFilterSessionNew,
  xyFilterSessionExecute,
  xyFilterSessionFree,
} from "./native.js";
import { FilterSessionClient } from "./filter-protocol.js";
import { ChunkedColumnRef } from "./chunked-column-ref.js";
export {
  filterRequest,
  decodeFilterReply,
  FilterTierCError,
} from "./filter-protocol.js";
export function executeFilterPacket(handle, packet, capacity = 2 << 20) {
  const output = new Uint8Array(capacity),
    written = new BigUint64Array(1);
  const status = xyFilterSessionExecute(
    handle,
    pointer(packet, "uint8_t *"),
    packet.byteLength,
    pointer(output, "uint8_t *"),
    capacity,
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
      const values = Object.values(columns);
      if (values.some((c) => c instanceof ChunkedColumnRef)) {
        if (!values.every((c) => c instanceof ChunkedColumnRef))
          throw new TypeError("filter columns must be all arrays or all issued chunked planes");
        const payload = new Uint8Array(values.length * 16), d = new DataView(payload.buffer);
        values.forEach((c, i) => {
          d.setBigUint64(i * 16, BigInt(c.source.handle), true);
          d.setBigUint64(i * 16 + 8, BigInt(c.plane), true);
        });
        this.call(this.request(16, {
          version: 2,
          args: [BigInt(values.length), this.rows, this.firstRow],
        }, payload));
      } else this.initialize(columns);
    } catch (error) {
      this.close();
      throw error;
    }
  }
}
