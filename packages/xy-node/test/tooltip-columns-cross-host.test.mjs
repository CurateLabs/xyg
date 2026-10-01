// Tooltip columns are one encoding in both hosts (graph-mark.md §2): Node must
// reproduce the Python-pinned `tooltip_columns` entry and shipped column bytes
// for every case in tests/fixtures/tooltip_columns_cross_host.json.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { decodeTooltipRows, encodeTooltipRows } from "../src/tooltip-columns.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const FIXTURE = JSON.parse(fs.readFileSync(path.join(ROOT, "tests/fixtures/tooltip_columns_cross_host.json"), "utf8"));
const NUMBERS = { NaN: Number.NaN, Infinity: Number.POSITIVE_INFINITY };

/** A payload writer that records each shipped column's dtype and bytes. */
function recorder() {
  const columns = [];
  const ship = (bytes, dtype) => {
    columns.push({ dtype, hex: Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength).toString("hex") });
    return columns.length - 1;
  };
  return { columns, shipU8: (v) => ship(v, "u8"), shipU32: (v) => ship(v, "u32") };
}

const rowsOf = (rows) => rows.map((row) => Object.fromEntries(
  Object.entries(row).map(([k, v]) => [k, typeof v === "string" && v in NUMBERS && k === "value" ? NUMBERS[v] : v]),
));

for (const [name, expected] of Object.entries(FIXTURE.cases)) {
  test(`Node tooltip columns match the Python fixture: ${name}`, () => {
    const pw = recorder();
    const columns = encodeTooltipRows(rowsOf(expected.rows), pw);
    assert.deepEqual(columns, expected.tooltip_columns);
    assert.deepEqual(columns ? pw.columns : [], expected.shipped);
  });
}

test("typed columns decode to the rows JSON would have carried", () => {
  const rows = rowsOf(FIXTURE.cases.non_finite_and_bools.rows);
  const pw = recorder();
  const entry = { tooltip_columns: encodeTooltipRows(rows, pw) };
  const blobs = pw.columns.map((c) => Buffer.from(c.hex, "hex"));
  const spec = { columns: pw.columns.map((c, i) => ({ buf: i, byte_offset: 0, len: blobs[i].length / (c.dtype === "u32" ? 4 : 1), dtype: c.dtype })) };
  assert.deepEqual(decodeTooltipRows(spec, blobs, entry), JSON.parse(JSON.stringify(rows)));
});
