/** Thin Node host for Rust-owned ordered Tier-3 XYGC range reads. */
import {
  pointer, xyChunkedColumnsCancelBefore, xyChunkedColumnsFree,
  xyChunkedColumnsOpen, xyChunkedColumnsRead, xyChunkedColumnsRows,
} from "./native.js";

export class ChunkedColumns {
  constructor(path) {
    const bytes = Buffer.from(String(path), "utf8");
    this.handle = xyChunkedColumnsOpen(pointer(bytes, "uint8_t *"), bytes.length);
    if (this.handle === 0n) throw new Error(`cannot open checked XYGC artifact ${JSON.stringify(String(path))}`);
    this.rows = xyChunkedColumnsRows(this.handle);
  }
  read([x0, x1], { yRange = null, budgetBytes = 64 << 20, generation = 0 } = {}) {
    if (!Number.isSafeInteger(budgetBytes) || budgetBytes < 16) throw new RangeError("chunked-column read budget must be at least 16 bytes");
    if (!Number.isSafeInteger(generation) || generation < 0) throw new RangeError("chunked-column generation must be a non-negative safe integer");
    const capacity = Math.floor(budgetBytes / 16);
    const x = new Float64Array(capacity), y = new Float64Array(capacity), stats = new BigUint64Array(6);
    this.cancelBefore(generation);
    const [y0, y1] = yRange ?? [0, 0];
    const written = xyChunkedColumnsRead(this.handle, x0, x1, y0, y1, yRange === null ? 0 : 1, BigInt(budgetBytes), BigInt(generation), pointer(x, "double *"), pointer(y, "double *"), capacity, pointer(stats, "uint64_t *"));
    if (written === BigInt("18446744073709551615")) {
      if (stats[5] === 4n && stats[4] !== 0n) throw new Error(`chunked-column viewport read needs ${stats[4]} bytes, exceeding the ${stats[3]}-byte read budget`);
      const reason = ({ 1: "I/O failure", 2: "corrupt artifact", 3: "invalid viewport bounds", 5: "cancelled by newer viewport", 6: "output capacity too small" })[Number(stats[5])] ?? "invalid request";
      throw new Error(`chunked-column viewport read failed: ${reason}`);
    }
    const n = Number(written);
    return { x: x.slice(0, n), y: y.slice(0, n), provenance: { generation: stats[0], firstChunk: stats[1], chunksConsidered: stats[2], chunksRead: stats[3], bytesRead: stats[4] } };
  }
  cancelBefore(generation) {
    if (!Number.isSafeInteger(generation) || generation < 0) throw new RangeError("chunked-column generation must be a non-negative safe integer");
    if (xyChunkedColumnsCancelBefore(this.handle, BigInt(generation)) !== 1) throw new Error("stale chunked-column handle");
  }
  close() { if (this.handle !== 0n) { xyChunkedColumnsFree(this.handle); this.handle = 0n; } }
}
