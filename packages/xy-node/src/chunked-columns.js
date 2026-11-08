import { ChunkedLiveHost } from "./chunked-live.js";
import { scatterChart } from "./charts.js";
/** Thin Node host for Rust-owned ordered Tier-3 XYGC range reads. */
import {
  pointer, xyChunkedColumnsCancelBefore, xyChunkedColumnsFree,
  xyChunkedColumnsOpen, xyChunkedColumnsOverview, xyChunkedColumnsRead, xyChunkedColumnsReadPage,
  xyChunkedColumnsRows, xyChunkedColumnsChart, xyChunkedColumnsChartOverview,
} from "./native.js";

function readOverview(columns,maxPoints,generation=null) {
    if (!Number.isSafeInteger(maxPoints) || maxPoints < 1 || maxPoints > 1_000_000) {
      throw new RangeError("chunked-column maxPoints must be an integer in [1, 1,000,000]");
    }
    const rowIds = new BigUint64Array(maxPoints);
    const x = new Float64Array(maxPoints), y = new Float64Array(maxPoints);
    const stats = new BigUint64Array(generation === null ? 2 : 4);
    const outputs = [pointer(rowIds, "uint64_t *"), pointer(x, "double *"), pointer(y, "double *"), pointer(stats, "uint64_t *")];
    const written = generation === null ? xyChunkedColumnsOverview(columns.handle, maxPoints, ...outputs) : xyChunkedColumnsChartOverview(columns.handle, maxPoints, BigInt(generation), ...outputs);
    if (written === BigInt("18446744073709551615") && generation !== null && stats[3] === 5n) throw new Error("chunked-column overview chart failed: cancelled by newer viewport");
    const offset = generation === null ? 0 : 1;
    if (written === BigInt("18446744073709551615")) throw new Error("chunked-column overview read failed: invalid or stale request");
    const n = Number(written);
    return { rowIds: rowIds.slice(0, n), x: x.slice(0, n), y: y.slice(0, n), provenance: { availablePoints: stats[offset], sourceRows: stats[offset+1], detailRowsRead: 0n, ...(generation === null ? {} : {generation: stats[0]}) } };
}

export class ChunkedColumns {
  constructor(path) {
    const bytes = Buffer.from(String(path), "utf8");
    this.handle = xyChunkedColumnsOpen(pointer(bytes, "uint8_t *"), bytes.length);
    if (this.handle === 0n || this.handle === 0) throw new Error(`cannot open checked XYGC artifact ${JSON.stringify(String(path))}`);
    this.path = String(path);
    try { this.rows = xyChunkedColumnsRows(this.handle); }
    catch (error) { xyChunkedColumnsFree(this.handle); this.handle = 0n; throw error; }
  }
  overview({ maxPoints = 2048 } = {}) { return readOverview(this,maxPoints); }
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
  *pages([x0, x1], { yRange = null, pageBytes = 4 << 20, generation = 0 } = {}) {
    if (!Number.isSafeInteger(pageBytes) || pageBytes < 16) throw new RangeError("chunked-column pageBytes must be at least 16 bytes");
    this.cancelBefore(generation);
    let cursor = 0;
    for (;;) {
      const capacity = Math.floor(pageBytes / 16), x = new Float64Array(capacity), y = new Float64Array(capacity), stats = new BigUint64Array(8);
      const [y0, y1] = yRange ?? [0, 0];
      const written = xyChunkedColumnsReadPage(this.handle, x0, x1, y0, y1, yRange === null ? 0 : 1, BigInt(pageBytes), BigInt(generation), cursor, pointer(x, "double *"), pointer(y, "double *"), capacity, pointer(stats, "uint64_t *"));
      if (written === BigInt("18446744073709551615")) {
        if (stats[7] === 4n) throw new Error(`chunked-column page needs ${stats[4]} bytes, exceeding the ${stats[5]}-byte page budget`);
        const reason = ({ 1: "I/O failure", 2: "corrupt artifact", 3: "invalid cursor or viewport bounds", 5: "cancelled by newer viewport", 6: "output capacity too small" })[Number(stats[7])] ?? "invalid request";
        throw new Error(`chunked-column page read failed: ${reason}`);
      }
      const n = Number(written), progress = { generation: stats[0], firstChunk: stats[1], chunksConsidered: stats[2], chunksRead: stats[3], bytesRead: stats[4], nextCursor: stats[5], done: stats[6] === 1n };
      yield { x: x.slice(0, n), y: y.slice(0, n), progress };
      if (progress.done) return;
      cursor = Number(progress.nextCursor);
    }
  }
  /** Standard-renderer overview or exact viewport snapshot. No implicit truncation. */
  chart(xRange = null, { yRange = null, budgetBytes = 4 << 20, pageBytes = 1 << 20, generation = 0, maxPoints = 2048 } = {}) {
    if (!Number.isSafeInteger(budgetBytes) || budgetBytes < 16) throw new RangeError("budgetBytes must be at least 16");
    if (!Number.isSafeInteger(pageBytes) || pageBytes < 16 || pageBytes > budgetBytes) throw new RangeError("pageBytes must be in [16, budgetBytes]");
    this.cancelBefore(generation);
    let result;
    if (xRange === null) {
      if (yRange !== null) throw new RangeError("yRange requires an explicit xRange");
      result = readOverview(this,maxPoints,generation);
    } else {
      const capacity = Math.floor(budgetBytes / 16), rowIds = new BigUint64Array(capacity);
      const x = new Float64Array(capacity), y = new Float64Array(capacity), stats = new BigUint64Array(6);
      const [y0, y1] = yRange ?? [0, 0];
      const written = xyChunkedColumnsChart(this.handle, ...xRange, y0, y1, yRange === null ? 0 : 1,
        BigInt(budgetBytes), BigInt(generation), BigInt(pageBytes), pointer(rowIds, "uint64_t *"),
        pointer(x, "double *"), pointer(y, "double *"), capacity, pointer(stats, "uint64_t *"));
      if (written === BigInt("18446744073709551615")) {
        if (stats[5] === 4n) throw new Error(`chunked-column chart needs ${stats[4]} bytes, exceeding the ${stats[3]}-byte budget`);
        const reason = ({1: "I/O failure", 2: "corrupt artifact", 3: "invalid viewport bounds", 5: "cancelled by newer viewport", 6: "output capacity too small"})[Number(stats[5])] ?? "invalid request";
        throw new Error(`chunked-column chart failed: ${reason}`);
      }
      const n = Number(written);
      result = {rowIds: rowIds.slice(0,n), x: x.slice(0,n), y: y.slice(0,n), provenance: {
        generation: stats[0], firstChunk: stats[1], chunksConsidered: stats[2], chunksRead: stats[3], bytesRead: stats[4],
      }};
    }
    const chart = scatterChart(result.x, result.y, {density:false});
    chart.sourceRowIds = result.rowIds;
    chart.sourceProvenance = {...result.provenance, path: this.path};
    chart.liveHost = (send, callbacks = {}) => {
      const source = new ChunkedColumns(this.path);
      try { return new ChunkedLiveHost(source, chart, {budgetBytes,pageBytes,generation}, send, callbacks); }
      catch (error) { source.close(); throw error; }
    };
    return chart;
  }
  cancelBefore(generation) {
    if (!Number.isSafeInteger(generation) || generation < 0) throw new RangeError("chunked-column generation must be a non-negative safe integer");
    if (xyChunkedColumnsCancelBefore(this.handle, BigInt(generation)) !== 1) throw new Error("stale chunked-column handle");
  }
  close() { if (this.handle !== 0n) { xyChunkedColumnsFree(this.handle); this.handle = 0n; } }
}
