import {
  pointer,
  xyFilterSessionNew,
  xyFilterSessionExecute,
  xyFilterSessionFree,
} from "./native.js";
import { FilterSessionClient } from "./filter-protocol.js";
export {
  filterRequest,
  decodeFilterReply,
  FilterTierCError,
} from "./filter-protocol.js";
export function executeFilterPacket(handle, packet, capacity = 1 << 20) {
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
      this.initialize(columns);
    } catch (error) {
      this.close();
      throw error;
    }
  }
}
