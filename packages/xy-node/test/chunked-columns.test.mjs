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

test("chunked columns matches exact oracle and Python provenance contract", () => {
  const dir = mkdtempSync(join(tmpdir(), "xyg-columns-")), path = join(dir, "ordered.xygc"), rows = artifact(path);
  const columns = new ChunkedColumns(path);
  const got = columns.read([3, 8], { yRange: [1, 2], budgetBytes: 1024, generation: 4 });
  assert.deepEqual(Array.from(got.x, (x, i) => [x, got.y[i]]), rows.filter(([x, y]) => x >= 3 && x <= 8 && y >= 1 && y <= 2));
  assert.deepEqual(got.provenance, { generation: 4n, firstChunk: 0n, chunksConsidered: 3n, chunksRead: 3n, bytesRead: 192n });
  assert.throws(() => columns.read([0, 11], { budgetBytes: 16, generation: 5 }), /read budget exceeded/);
  columns.close(); rmSync(dir, { recursive: true });
});
