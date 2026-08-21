import assert from "node:assert/strict";
import { closeSync, mkdtempSync, openSync, rmSync, writeSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { ChunkedColumns } from "../src/index.js";

function artifact(path) {
  const rows = Array.from({ length: 12 }, (_, i) => [i, i % 3]);
  const fd = openSync(path, "w"), header = Buffer.alloc(64), dataOffset = 64 + 48 * 3;
  header.write("XYGC"); header.writeUInt32LE(1, 4); header.writeBigUInt64LE(12n, 8);
  header.writeUInt32LE(4, 16); header.writeUInt32LE(3, 20); header.writeBigUInt64LE(BigInt(dataOffset), 24); writeSync(fd, header);
  for (let c = 0; c < 3; c++) {
    const meta = Buffer.alloc(48); meta.writeBigUInt64LE(BigInt(c * 4), 0); meta.writeUInt32LE(4, 8);
    meta.writeDoubleLE(c * 4, 16); meta.writeDoubleLE(c * 4 + 3, 24); meta.writeDoubleLE(0, 32); meta.writeDoubleLE(2, 40); writeSync(fd, meta);
  }
  for (const [x, y] of rows) { const row = Buffer.alloc(16); row.writeDoubleLE(x, 0); row.writeDoubleLE(y, 8); writeSync(fd, row); }
  closeSync(fd); return rows;
}

function overviewArtifact(path) {
  const rows = Array.from({ length: 12 }, (_, i) => [i, (i * 5) % 7]);
  const fd = openSync(path, "w"), header = Buffer.alloc(64), dataOffset = 64 + 48 * 3;
  const overviewOffset = dataOffset + rows.length * 16;
  header.write("XYGC"); header.writeUInt32LE(2, 4); header.writeBigUInt64LE(12n, 8);
  header.writeUInt32LE(4, 16); header.writeUInt32LE(3, 20); header.writeBigUInt64LE(BigInt(dataOffset), 24);
  header.writeBigUInt64LE(BigInt(overviewOffset), 32); header.writeUInt32LE(rows.length, 40); writeSync(fd, header);
  for (let c = 0; c < 3; c++) {
    const chunk = rows.slice(c * 4, c * 4 + 4), ys = chunk.map((row) => row[1]);
    const meta = Buffer.alloc(48); meta.writeBigUInt64LE(BigInt(c * 4), 0); meta.writeUInt32LE(4, 8);
    meta.writeDoubleLE(c * 4, 16); meta.writeDoubleLE(c * 4 + 3, 24); meta.writeDoubleLE(Math.min(...ys), 32); meta.writeDoubleLE(Math.max(...ys), 40); writeSync(fd, meta);
  }
  for (const [x, y] of rows) { const row = Buffer.alloc(16); row.writeDoubleLE(x, 0); row.writeDoubleLE(y, 8); writeSync(fd, row); }
  rows.forEach(([x, y], i) => { const point = Buffer.alloc(24); point.writeBigUInt64LE(BigInt(i), 0); point.writeDoubleLE(x, 8); point.writeDoubleLE(y, 16); writeSync(fd, point); });
  closeSync(fd); return rows;
}

test("chunked columns matches exact oracle and Python provenance contract", () => {
  const dir = mkdtempSync(join(tmpdir(), "xyg-columns-")), path = join(dir, "ordered.xygc"), rows = artifact(path);
  const columns = new ChunkedColumns(path);
  const got = columns.read([3, 8], { yRange: [1, 2], budgetBytes: 1024, generation: 4 });
  assert.deepEqual(Array.from(got.x, (x, i) => [x, got.y[i]]), rows.filter(([x, y]) => x >= 3 && x <= 8 && y >= 1 && y <= 2));
  assert.deepEqual(got.provenance, { generation: 4n, firstChunk: 0n, chunksConsidered: 3n, chunksRead: 3n, bytesRead: 192n });
  assert.throws(() => columns.read([0, 11], { budgetBytes: 16, generation: 5 }), /needs 192 bytes, exceeding the 16-byte read budget/);
  assert.throws(() => columns.read([0, 11], { generation: -1 }), /generation must be/);
  columns.read([0, 1], { generation: 6 });
  assert.throws(() => columns.read([0, 1], { generation: 5 }), /cancelled by newer viewport/);
  columns.close(); rmSync(dir, { recursive: true });
});

test("chunked columns overview is bounded and preserves canonical row IDs", () => {
  const dir = mkdtempSync(join(tmpdir(), "xyg-overview-")), path = join(dir, "overview.xygc"), rows = overviewArtifact(path);
  const columns = new ChunkedColumns(path), got = columns.overview({ maxPoints: 5 });
  assert.deepEqual(Array.from(got.rowIds), [0n, 2n, 5n, 8n, 11n]);
  assert.deepEqual(Array.from(got.x, (x, i) => [x, got.y[i]]), Array.from(got.rowIds, (row) => rows[Number(row)]));
  assert.deepEqual(got.provenance, { availablePoints: 12n, sourceRows: 12n, detailRowsRead: 0n });
  columns.close(); rmSync(dir, { recursive: true });
});
