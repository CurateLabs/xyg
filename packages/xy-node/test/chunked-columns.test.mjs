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

test("chunked columns pages apply pull backpressure and preserve exact order", () => {
  const dir = mkdtempSync(join(tmpdir(), "xyg-pages-")), path = join(dir, "ordered.xygc"), rows = artifact(path);
  const columns = new ChunkedColumns(path), pages = Array.from(columns.pages([1, 10], { yRange: [1, 2], pageBytes: 64, generation: 9 }));
  assert.deepEqual(pages.flatMap(({ x, y }) => Array.from(x, (value, i) => [value, y[i]])), rows.filter(([x, y]) => x >= 1 && x <= 10 && y >= 1 && y <= 2));
  assert.ok(pages.length >= 3 && pages.every(({ progress }) => progress.bytesRead <= 64n));
  assert.equal(pages.at(-1).progress.done, true);
  columns.close(); rmSync(dir, { recursive: true });
});

test("chunked column pages expose budget and stale-generation diagnostics", () => {
  const dir = mkdtempSync(join(tmpdir(), "xyg-page-errors-")), path = join(dir, "ordered.xygc");
  artifact(path);
  const columns = new ChunkedColumns(path);
  assert.throws(
    () => Array.from(columns.pages([0, 11], { pageBytes: 16, generation: 1 })),
    /needs 64 bytes, exceeding the 16-byte page budget/,
  );
  columns.cancelBefore(3);
  assert.throws(
    () => Array.from(columns.pages([0, 11], { pageBytes: 64, generation: 2 })),
    /cancelled by newer viewport/,
  );
  columns.close(); rmSync(dir, { recursive: true });
});


test("fetched detail corruption and stale empty reads fail closed", () => {
  const dir = mkdtempSync(join(tmpdir(), "xyg-corrupt-detail-")), path = join(dir, "ordered.xygc");
  artifact(path);
  const columns = new ChunkedColumns(path);
  try {
    columns.cancelBefore(3);
    assert.throws(() => columns.read([20, 30], { generation: 2 }), /cancelled by newer viewport/);
    const fd = openSync(path, "r+"), value = Buffer.alloc(8);
    try { value.writeDoubleLE(99); writeSync(fd, value, 0, 8, 64 + 48 * 3 + 16 + 8); }
    finally { closeSync(fd); }
    assert.throws(() => columns.read([0, 11], { generation: 3 }), /corrupt artifact/);
    assert.throws(() => Array.from(columns.pages([0, 11], { pageBytes: 64, generation: 3 })), /corrupt artifact/);
  } finally { columns.close(); rmSync(dir, { recursive: true }); }
});

test("resident overlap reuses native chunks across read modes", () => {
  const dir = mkdtempSync(join(tmpdir(), "xyg-reuse-")), path = join(dir, "ordered.xygc"), rows = artifact(path);
  const columns = new ChunkedColumns(path);
  try {
    columns.read([0, 7], { budgetBytes: 192, generation: 1 });
    const got = columns.read([4, 11], { budgetBytes: 192, generation: 2 });
    assert.deepEqual(Array.from(got.x, (x, i) => [x, got.y[i]]), rows.slice(4));
    assert.equal(got.provenance.chunksRead, 1n);
    assert.equal(got.provenance.bytesRead, 64n);
    const pages = Array.from(columns.pages([4, 11], { pageBytes: 192, generation: 3 }));
    assert.equal(pages.length, 1);
    assert.equal(pages[0].progress.bytesRead, 0n);
    assert.throws(() => columns.read([4, 11], { budgetBytes: 64, generation: 4 }), /needs 128 bytes/);
  } finally { columns.close(); rmSync(dir, { recursive: true }); }
});


test("chart overview, paged viewport, reuse, generation and disposal", () => {
  const dir = mkdtempSync(join(tmpdir(), "xyg-chart-")), path = join(dir, "chart.xygc");
  const rows = overviewArtifact(path), columns = new ChunkedColumns(path);
  try {
    const overview = columns.chart(null, {maxPoints: 5});
    assert.equal(overview.sourceRowIds.length, 5);
    assert.equal(overview.sourceProvenance.detailRowsRead, 0n);
    for (const [generation, bounds] of [[1,[2,9]], [2,[5,10]], [3,[6,7]]]) {
      const chart = columns.chart(bounds, {generation, budgetBytes:256, pageBytes:128});
      assert.deepEqual(Array.from(chart.sourceRowIds, Number), rows.flatMap(([x],i)=>x>=bounds[0] && x<=bounds[1] ? [i]:[]));
      chart.buildPayload();
    }
    const warm = columns.chart([6,7], {generation:4, budgetBytes:256, pageBytes:128});
    assert.equal(warm.sourceProvenance.bytesRead, 0n);
    assert.throws(()=>columns.chart([6,7], {generation:3}), /cancelled/);
    assert.throws(()=>columns.chart([0,11], {generation:5,budgetBytes:64,pageBytes:64}), /exceeding/);
    columns.close();
    assert.throws(()=>columns.chart(), /stale/);
  } finally { columns.close(); rmSync(dir,{recursive:true}); }
});

test("chart overview rejects superseded generations while static overview remains usable", () => {
  const dir=mkdtempSync(join(tmpdir(),"xyg-overview-generation-")),path=join(dir,"chart.xygc");
  overviewArtifact(path);const columns=new ChunkedColumns(path);
  try {
    columns.cancelBefore(5);
    assert.throws(()=>columns.chart(null,{generation:4,maxPoints:5}),/cancelled by newer viewport/);
    const current=columns.chart(null,{generation:5,maxPoints:5});
    assert.equal(current.sourceProvenance.generation,5n);
    assert.equal(current.sourceProvenance.detailRowsRead,0n);
    assert.equal(current.sourceRowIds.length,5);
    columns.cancelBefore(6);
    assert.throws(()=>columns.chart(null,{generation:5,maxPoints:5}),/cancelled by newer viewport/);
    assert.equal(columns.overview({maxPoints:5}).rowIds.length,5);
  } finally {columns.close();rmSync(dir,{recursive:true});}
});

test("chart chunk candidate counts are independent of page boundaries", () => {
  const dir=mkdtempSync(join(tmpdir(),"xyg-chart-chunks-")),path=join(dir,"chart.xygc");
  overviewArtifact(path);const columns=new ChunkedColumns(path);
  try {
    for(const pageBytes of [64,128,192]) {
      const chart=columns.chart([0,11],{budgetBytes:192,pageBytes});
      assert.equal(chart.sourceProvenance.chunksConsidered,3n);
      assert.deepEqual(Array.from(chart.sourceRowIds,Number),Array.from({length:12},(_,i)=>i));
    }
  } finally {columns.close();rmSync(dir,{recursive:true});}
});
