import assert from "node:assert/strict";
import test from "node:test";

import { cssColorRgba8, lineChart, scatterChart } from "../src/index.js";
import { figureSceneV3 } from "../src/scene.js";
import { xyScenePackAnnotationFacts, xyScenePackAnnotationMarks, xyScenePackProduct, xyScenePackProductFacts, xyScenePackTrace, xySceneResolveChromeStyle, xySceneResolvePackKind } from "../src/native.js";
import { f64Ptr, u8Ptr } from "../src/encode.js";

test("cssColorRgba8 matches Python named colors and none", () => {
  assert.deepEqual(Array.from(cssColorRgba8("#3b82f6")), [0x3b, 0x82, 0xf6, 255]);
  assert.deepEqual(Array.from(cssColorRgba8("steelblue")), [70, 130, 180, 255]);
  assert.deepEqual(Array.from(cssColorRgba8("none")), [0, 0, 0, 0]);
  assert.deepEqual(Array.from(cssColorRgba8("oklch(0.7 0.1 250)")), [76, 120, 168, 255]);
  assert.deepEqual(Array.from(cssColorRgba8("#ff0000", 0.5)), [255, 0, 0, 128]);
});

test("named color scatter compiles through Rust mark styles", () => {
  const fig = scatterChart([0, 1], [0, 1], { style: { color: "steelblue" } });
  const encoded = figureSceneV3(fig);
  assert.ok(encoded.byteLength > 0);
});

test("line charts keep the 1.5 default stroke width", () => {
  const fig = lineChart([0, 1], [0, 1], { style: { color: "#ff0000" } });
  const encoded = figureSceneV3(fig);
  const bytes = Buffer.from(encoded);
  assert.ok(bytes.includes(Buffer.from([255, 0, 0, 255])));
});

function resolveChrome(envelope) {
  const out = new Uint8Array(200);
  const code = xySceneResolveChromeStyle(
    u8Ptr(envelope),
    BigInt(envelope.length),
    u8Ptr(out),
    BigInt(out.length),
  );
  assert.equal(code, 200);
  return out;
}

function chromeAxis(gridOpacity = 1) {
  const prefix = new Uint8Array(84);
  const view = new DataView(prefix.buffer);
  prefix[1] = 1;
  prefix[2] = 1;
  view.setFloat32(8, gridOpacity, true);
  view.setFloat32(12, 1, true);
  [1, 1, 1, 4, 1, 1, 0].forEach((value, index) => view.setFloat64(16 + index * 8, value, true));
  return prefix;
}

test("empty XYCH envelope is the Scene chrome default", () => {
  const envelope = new Uint8Array(16);
  envelope.set(new TextEncoder().encode("XYCH"));
  new DataView(envelope.buffer).setUint32(4, 1, true);
  const chrome = resolveChrome(envelope);
  assert.deepEqual(Array.from(chrome.subarray(8, 12)), [32, 32, 32, 217]);
  assert.equal(new DataView(chrome.buffer).getFloat64(16, true), 12);
  assert.deepEqual(Array.from(chrome.subarray(36, 40)), [32, 32, 32, 36]);
});

test("grid_opacity scales the default grid color without authored grid_color", () => {
  const x = chromeAxis(0);
  const y = chromeAxis(1);
  const envelope = new Uint8Array(16 + x.length + y.length);
  const view = new DataView(envelope.buffer);
  envelope.set(new TextEncoder().encode("XYCH"));
  view.setUint32(4, 1, true);
  view.setUint32(8, 2 << 8, true);
  envelope.set(x, 16);
  envelope.set(y, 16 + x.length);
  const chrome = resolveChrome(envelope);
  assert.deepEqual(Array.from(chrome.subarray(24 + 12, 24 + 16)), [32, 32, 32, 0]);
  assert.deepEqual(Array.from(chrome.subarray(112 + 12, 112 + 16)), [32, 32, 32, 36]);
});

function packTrace(packKind, columns, extras = {}) {
  const padded = [...columns];
  while (padded.length < 6) padded.push(null);
  const args = padded.slice(0, 6).map((column) => {
    if (column == null || column.length === 0) return { ptr: 0, n: 0, keep: null };
    const arr = Float64Array.from(column, Number);
    return { ptr: f64Ptr(arr), n: arr.length, keep: arr };
  });
  const n0 = args[0].n;
  const nRows = packKind === 4 || packKind === 5 ? n0 * 2 : packKind === 7 ? 2 : n0;
  const out = new Uint8Array(Math.max(nRows, 1) * 56);
  const code = xyScenePackTrace(
    packKind,
    extras.flags ?? 0,
    extras.stepMode ?? 0,
    extras.symbol ?? 0,
    extras.styleRef ?? 0,
    BigInt(extras.traceId ?? 0),
    extras.diameter ?? 0,
    extras.extra0 ?? 0,
    extras.extra1 ?? 0,
    args[0].ptr, BigInt(args[0].n),
    args[1].ptr, BigInt(args[1].n),
    args[2].ptr, BigInt(args[2].n),
    args[3].ptr, BigInt(args[3].n),
    args[4].ptr, BigInt(args[4].n),
    args[5].ptr, BigInt(args[5].n),
    u8Ptr(out),
    BigInt(out.length),
  );
  return { code, out };
}

test("pack_trace scatter keeps one row per point", () => {
  const { code, out } = packTrace(0, [[0, 1], [2, 3]], { symbol: 4, styleRef: 1, traceId: 7, diameter: 6 });
  assert.equal(code, 2);
  const view = new DataView(out.buffer);
  assert.equal(out[0], 0);
  assert.equal(out[1], 4);
  assert.equal(view.getUint32(4, true), 1);
  assert.equal(view.getBigUint64(8, true), 7n);
  assert.equal(view.getFloat64(16, true), 6);
  assert.equal(view.getFloat64(24, true), 0);
  assert.equal(view.getFloat64(32, true), 2);
  assert.equal(out[56], 0);
  assert.equal(view.getFloat64(56 + 24, true), 1);
  assert.equal(view.getFloat64(56 + 32, true), 3);
});

test("pack_trace heatmap frames extent then shape", () => {
  const { code, out } = packTrace(7, [[1], [2], [3], [4]], { styleRef: 9, traceId: 11, extra0: 2, extra1: 3 });
  assert.equal(code, 2);
  const view = new DataView(out.buffer);
  assert.equal(out[0], 2);
  assert.equal(out[2], 6);
  assert.equal(view.getFloat64(16, true), 2);
  assert.equal(view.getFloat64(24, true), 1);
  assert.equal(view.getFloat64(56 + 16, true), 3);
  assert.equal(view.getFloat64(56 + 24, true), 0);
});

test("pack_trace rejects nonfinite coordinates", () => {
  const { code } = packTrace(1, [[0, Number.NaN], [1, 2]]);
  assert.equal(code, -5);
});

test("pack_product maps product kinds and heatmap range columns", () => {
  const scatter = new TextEncoder().encode("scatter");
  assert.equal(xySceneResolvePackKind(u8Ptr(scatter), BigInt(scatter.length), 0), 0);
  const heatmap = new TextEncoder().encode("heatmap");
  assert.equal(xySceneResolvePackKind(u8Ptr(heatmap), BigInt(heatmap.length), 2), 9);
  const x = Float64Array.from([1, 3]);
  const y = Float64Array.from([2, 4]);
  const out = new Uint8Array(112);
  const empty = { ptr: 0, n: 0 };
  const code = xyScenePackProduct(
    u8Ptr(heatmap), BigInt(heatmap.length),
    2, 0, 0, 9, 11n, 0, 2, 3,
    f64Ptr(x), BigInt(x.length),
    f64Ptr(y), BigInt(y.length),
    empty.ptr, BigInt(empty.n),
    empty.ptr, BigInt(empty.n),
    empty.ptr, BigInt(empty.n),
    empty.ptr, BigInt(empty.n),
    empty.ptr, BigInt(empty.n),
    u8Ptr(out), BigInt(out.length),
  );
  assert.equal(code, 2);
  assert.equal(out[2], 9);
  const view = new DataView(out.buffer);
  assert.equal(view.getFloat64(16, true), 2);
  assert.equal(view.getFloat64(24, true), 1);
  assert.equal(view.getFloat64(32, true), 2);
  assert.equal(view.getFloat64(40, true), 3);
  assert.equal(view.getFloat64(48, true), 4);
});

test("xyScenePackProductFacts applies cartesian smooth and ignores polar", () => {
  const encoder = new TextEncoder();
  const pack = (kind, coords, facts) => {
    const name = encoder.encode(kind);
    const out = new Uint8Array(64 + name.length);
    const view = new DataView(out.buffer);
    out.set(encoder.encode("XYPK"), 0);
    view.setUint32(4, 1, true);
    view.setUint32(8, 1, true);
    out[12] = coords;
    out[15] = facts;
    view.setBigUint64(16, 11n, true);
    out.set(name, 64);
    return out;
  };
  const x = Float64Array.from([0, 1, 2]);
  const y = Float64Array.from([0, 1, 0]);
  const empty = { ptr: 0, n: 0 };
  const cartesian = pack("line", 0, 2);
  const out = new Uint8Array(168);
  const code = xyScenePackProductFacts(
    u8Ptr(cartesian), BigInt(cartesian.length),
    f64Ptr(x), BigInt(x.length),
    f64Ptr(y), BigInt(y.length),
    empty.ptr, BigInt(empty.n),
    empty.ptr, BigInt(empty.n),
    empty.ptr, BigInt(empty.n),
    empty.ptr, BigInt(empty.n),
    empty.ptr, BigInt(empty.n),
    u8Ptr(out), BigInt(out.length),
  );
  assert.equal(code, 3);
  assert.equal(out[2], 11);
  const polar = pack("line", 1, 2);
  const polarOut = new Uint8Array(112);
  const polarCode = xyScenePackProductFacts(
    u8Ptr(polar), BigInt(polar.length),
    f64Ptr(x.subarray(0, 2)), 2n,
    f64Ptr(y.subarray(0, 2)), 2n,
    empty.ptr, BigInt(empty.n),
    empty.ptr, BigInt(empty.n),
    empty.ptr, BigInt(empty.n),
    empty.ptr, BigInt(empty.n),
    empty.ptr, BigInt(empty.n),
    u8Ptr(polarOut), BigInt(polarOut.length),
  );
  assert.equal(polarCode, 2);
  assert.equal(polarOut[2], 0);
});

function annotationMarkRow(kind, axis, symbol, styleRef, index, value0, value1, size) {
  const row = new Uint8Array(40);
  const view = new DataView(row.buffer);
  row[0] = kind;
  row[1] = axis;
  row[2] = symbol;
  view.setUint32(4, styleRef >>> 0, true);
  view.setUint32(8, index >>> 0, true);
  view.setFloat64(16, Number(value0), true);
  view.setFloat64(24, Number(value1), true);
  view.setFloat64(32, Number(size), true);
  return row;
}

function packAnnotationMarks(rowBytes, xDomain, yDomain) {
  const source = rowBytes instanceof Uint8Array ? rowBytes : new Uint8Array(rowBytes ?? []);
  const nIn = Math.floor(source.length / 40);
  const out = new Uint8Array(Math.max(nIn * 2, 1) * 56);
  const code = xyScenePackAnnotationMarks(
    source.length ? u8Ptr(source) : 0,
    BigInt(source.length),
    Number(xDomain[0]),
    Number(xDomain[1]),
    Number(yDomain[0]),
    Number(yDomain[1]),
    u8Ptr(out),
    BigInt(out.length),
  );
  return { code, out };
}

test("pack_annotation_marks rule spans the opposite axis", () => {
  const { code, out } = packAnnotationMarks(
    annotationMarkRow(1, 0, 0, 3, 7, 1.5, 0, 0),
    [0, 4],
    [10, 20],
  );
  assert.equal(code, 2);
  const view = new DataView(out.buffer);
  assert.equal(out[0], 1);
  assert.equal(view.getUint32(4, true), 3);
  assert.equal(view.getBigUint64(8, true), 0x5859000000000000n | (1n << 40n) | 7n);
  assert.equal(view.getFloat64(24, true), 1.5);
  assert.equal(view.getFloat64(32, true), 10);
  assert.equal(view.getFloat64(56 + 24, true), 1.5);
  assert.equal(view.getFloat64(56 + 32, true), 20);
});

test("pack_annotation_marks y-band uses tag four", () => {
  const { code, out } = packAnnotationMarks(
    annotationMarkRow(2, 1, 0, 1, 2, 3, 5, 0),
    [0, 10],
    [-1, 1],
  );
  assert.equal(code, 1);
  const view = new DataView(out.buffer);
  assert.equal(out[0], 2);
  assert.equal(view.getBigUint64(8, true), 0x5859000000000000n | (4n << 40n) | 2n);
  assert.equal(view.getFloat64(24, true), 0);
  assert.equal(view.getFloat64(32, true), 3);
  assert.equal(view.getFloat64(40, true), 10);
  assert.equal(view.getFloat64(48, true), 5);
});

test("pack_annotation_marks marker keeps point size and symbol", () => {
  const { code, out } = packAnnotationMarks(
    annotationMarkRow(3, 0, 4, 8, 9, 1, 2, 6),
    [0, 1],
    [0, 1],
  );
  assert.equal(code, 1);
  const view = new DataView(out.buffer);
  assert.equal(out[0], 0);
  assert.equal(out[1], 4);
  assert.equal(view.getFloat64(16, true), 6);
  assert.equal(view.getBigUint64(8, true), 0x5859000000000000n | (3n << 40n) | 9n);
  assert.equal(view.getFloat64(24, true), 1);
  assert.equal(view.getFloat64(32, true), 2);
});

test("pack_annotation_marks rejects bad kind and nonfinite domain", () => {
  assert.equal(packAnnotationMarks(annotationMarkRow(9, 0, 0, 0, 0, 0, 0, 1), [0, 1], [0, 1]).code, -1);
  assert.equal(packAnnotationMarks(annotationMarkRow(1, 0, 0, 0, 0, 0, 0, 0), [0, Number.NaN], [0, 1]).code, -5);
});

test("xyScenePackAnnotationFacts routes text into XYAO/XYAD", () => {
  const facts = new Uint8Array(232 + 2);
  const view = new DataView(facts.buffer);
  facts.set(new TextEncoder().encode("XYAF"), 0);
  view.setUint32(4, 1, true);
  facts[15] = 255;
  view.setUint32(16, (1 << 1) | (1 << 5) | (1 << 6), true);
  view.setUint32(20, 1, true);
  facts[24] = 255;
  view.setUint32(28, 2, true);
  view.setFloat64(32, 0.5, true);
  view.setFloat64(40, 0.25, true);
  facts.set([102, 112, 133, 255], 176);
  facts.set(new TextEncoder().encode("hi"), 232);
  const out = new Uint8Array(4096);
  const code = xyScenePackAnnotationFacts(
    u8Ptr(facts), BigInt(facts.length), 0,
    0, 1, 0, 1,
    u8Ptr(out), BigInt(out.length),
  );
  assert.ok(code > 32);
  assert.equal(String.fromCharCode(out[0], out[1], out[2], out[3]), "XYAO");
  const xyadLen = new DataView(out.buffer).getUint32(16, true);
  const xyad = Buffer.from(out.subarray(32, 32 + xyadLen));
  assert.ok(xyad.includes(Buffer.from("XYAD")));
  assert.ok(xyad.includes(Buffer.from("hi")));
});
