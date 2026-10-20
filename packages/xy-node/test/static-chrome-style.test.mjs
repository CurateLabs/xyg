// #1004: Node Figure export applies the Rust chrome-style projection exactly.
import assert from "node:assert/strict";
import test from "node:test";
import { inflateSync } from "node:zlib";

import { Figure, staticChromeStyle } from "../src/index.js";

function chart({ styles = {}, root = {}, xStyle = {}, yStyle = {} } = {}) {
  const fig = new Figure({
    width: 320,
    height: 240,
    title: "Title",
    showLegend: false,
    style: root,
    chromeStyles: styles,
    xAxis: { domain: [0, 1], label: "X", style: xStyle },
    yAxis: { domain: [0, 1], label: "Y", style: yStyle },
  });
  fig.line([0, 1], [0, 1], { color: "#ef4444", width: 2 });
  return fig;
}

const TYPOGRAPHY = {
  title: { "font-weight": "bold", color: "#102030" },
  axis_title: { color: "#ff0000", "font-style": "italic", "font-size": "16px" },
  tick_label: { color: "#00ff00", "font-weight": "bold", "font-size": "10px" },
};

function texts(svg) {
  return [...svg.matchAll(/<text ([^>]*)>([^<]*)<\/text>/g)].map((m) => ({
    ...Object.fromEntries([...m[1].matchAll(/([\w-]+)="([^"]*)"/g)].map((a) => [a[1], a[2]])),
    text: m[2],
  }));
}
const byText = (svg) => Object.fromEntries(texts(svg).map((t) => [t.text, t]));
const svgOf = (fig) => Buffer.from(fig.toSvg({ scale: 1 })).toString("utf8");

test("tick-label size reaches SVG and every raster/vector format", () => {
  const small = chart({ styles: { tick_label: { "font-size": "12px" } } });
  const large = chart({ styles: { tick_label: { "font-size": "30px" } } });
  assert.notEqual(svgOf(small), svgOf(large));
  const sizes = new Set(texts(svgOf(large)).filter((t) => ["0.0", "0.5", "1.0"].includes(t.text)).map((t) => t["font-size"]));
  assert.deepEqual([...sizes], ["30"]);
  for (const format of ["png", "jpeg", "webp", "pdf"]) {
    const a = Buffer.from(small.toImage(format, { scale: 1 }));
    const b = Buffer.from(large.toImage(format, { scale: 1 }));
    assert.ok(!a.equals(b), format);
  }
  assert.deepEqual(large.chrome_styles, { tick_label: { "font-size": "30px" } });
});

test("legacy defaults are unchanged", () => {
  const defaults = byText(svgOf(chart()));
  assert.equal(defaults.Title["font-size"], "14");
  assert.equal(defaults.Title["font-weight"], "400");
  assert.equal(defaults.X["font-size"], "12");
  assert.equal(defaults["0.5"]["font-size"], "12");
  assert.equal(defaults["0.5"]["font-weight"], undefined);
  assert.equal(svgOf(chart()), svgOf(chart({ styles: {} })));
});

test("SVG and PDF carry resolved paint, weight, style and fonts", () => {
  const fig = chart({ styles: TYPOGRAPHY });
  const t = byText(svgOf(fig));
  assert.equal(t.Title["font-weight"], "700");
  assert.equal(t.Title.fill, "rgba(16,32,48,1.000000)");
  for (const axis of ["X", "Y"]) {
    assert.equal(t[axis]["font-style"], "italic");
    assert.equal(t[axis].fill, "rgba(255,0,0,1.000000)");
    assert.equal(t[axis]["font-size"], "16");
  }
  assert.equal(t["0.5"]["font-weight"], "700");
  assert.equal(t["0.5"].fill, "rgba(0,255,0,1.000000)");
  const pdf = Buffer.from(fig.toPdf());
  assert.ok(pdf.includes("/BaseFont /Helvetica-Bold"));
  assert.ok(pdf.includes("/BaseFont /Helvetica-Oblique"));
  assert.ok(!Buffer.from(chart().toPdf()).includes("/BaseFont /Helvetica-Bold"));
  // Searchable text and paint live in the (single) flate content stream.
  const streams = [...pdf.toString("latin1").matchAll(/stream\n([\s\S]*?)\nendstream/g)]
    .map((m) => { try { return inflateSync(Buffer.from(m[1], "latin1")).toString("latin1"); } catch { return ""; } });
  const content = streams.find((s) => s.includes("(Title) Tj")) ?? "";
  for (const label of ["(Title) Tj", "(X) Tj", "(Y) Tj", "(0.5) Tj", "1 0 0 rg", "0 1 0 rg"]) {
    assert.ok(content.includes(label), label);
  }
});

test("precedence: axis, then slot, then root theme, then default", () => {
  const fig = chart({
    styles: { tick_label: { "font-size": "20px", color: "#00ff00" } },
    root: { "--chart-text": "#0000ff" },
    xStyle: { tick_label_size: 9, label_color: "#ff0000" },
  });
  const all = texts(svgOf(fig));
  const ticks = all.filter((t) => ["0.0", "0.5", "1.0"].includes(t.text));
  assert.deepEqual(new Set(ticks.filter((t) => t["text-anchor"] === "middle").map((t) => t["font-size"])), new Set(["9"]));
  assert.deepEqual(new Set(ticks.filter((t) => t["text-anchor"] === "end").map((t) => t["font-size"])), new Set(["20"]));
  assert.deepEqual(new Set(ticks.map((t) => t.fill)), new Set(["rgba(0,255,0,1.000000)"]));
  const t = byText(svgOf(fig));
  assert.equal(t.X.fill, "rgba(255,0,0,1.000000)");
  assert.equal(t.Y.fill, "rgba(0,0,255,1.000000)");
  assert.equal(t.Title.fill, "rgba(0,0,255,1.000000)");
});

test("malformed or browser-only styles fail atomically with stable reasons", () => {
  const cases = [
    [{ tick_label: { "font-size": "2em" } }, "XYG_STATIC_UNSUPPORTED_CHROME_FONT_SIZE"],
    [{ tick_label: { "font-size": 12 } }, "XYG_STATIC_UNSUPPORTED_CHROME_FONT_SIZE"],
    [{ title: { "font-weight": "600" } }, "XYG_STATIC_UNSUPPORTED_CHROME_FONT_WEIGHT"],
    [{ title: { "font-style": "oblique" } }, "XYG_STATIC_UNSUPPORTED_CHROME_FONT_STYLE"],
    [{ title: { color: "var(--x)" } }, "XYG_STATIC_UNSUPPORTED_CHROME_COLOR"],
    [{ title: { "font-family": "Comic Sans" } }, "XYG_STATIC_UNSUPPORTED_CUSTOM_FONT"],
    [{ legend: { "font-size": "12px" } }, "XYG_STATIC_UNSUPPORTED_CHROME_STYLE"],
    [{ title: { "letter-spacing": "2px" } }, "XYG_STATIC_UNSUPPORTED_CHROME_STYLE"],
  ];
  for (const [styles, reason] of cases) {
    for (const format of ["svg", "png", "pdf", "jpeg", "webp"]) {
      assert.throws(() => chart({ styles: { ...TYPOGRAPHY, ...styles } }).toImage(format), (e) => e.message.includes(reason), `${reason} ${format}`);
    }
  }
  assert.throws(() => chart({ root: { "box-shadow": "none" } }).toSvg(), /XYG_STATIC_UNSUPPORTED_BROWSER_CSS/);
  assert.throws(() => chart({ root: { "--chart-text": "var(--ink)" } }).toSvg(), /XYG_STATIC_UNSUPPORTED_CHROME_COLOR/);
  assert.throws(() => chart({ yStyle: { tick_label_size: 1e9 } }).toSvg(), /XYG_STATIC_UNSUPPORTED_CHROME_AXIS_STYLE/);
});

// -- Ownership: the XYST panel record is exactly the native projection result.

function frame({ slots, root }) {
  const parts = [];
  const u32 = (v) => { const b = Buffer.alloc(4); b.writeUInt32LE(v); parts.push(b); };
  const text = (s) => { const b = Buffer.from(s); u32(b.length); parts.push(b); };
  const entries = (m) => { const keys = Object.keys(m ?? {}).sort(); u32(keys.length); for (const k of keys) { text(k); u32(1); text(m[k]); } };
  parts.push(Buffer.from("XYCS"));
  u32(1); u32(1); u32(0);
  entries(root);
  const names = Object.keys(slots).sort();
  u32(names.length);
  for (const name of names) { text(name); entries(slots[name]); }
  for (let i = 0; i < 4; i += 1) entries({});
  return Buffer.concat(parts);
}

test("the document panel carries exactly the native projection result", () => {
  const fig = chart({ styles: TYPOGRAPHY, root: { "--chart-text": "#0000ff" } });
  const doc = Buffer.from(fig.toStaticDocument());
  const resolved = Buffer.from(staticChromeStyle(frame({ slots: TYPOGRAPHY, root: { "--chart-text": "#0000ff" } })));
  const panel = 64;
  assert.equal(doc.readUInt32LE(panel + 24) & (1 << 15), 1 << 15);
  assert.equal(doc.readUInt32LE(panel + 108), resolved.readUInt32LE(12)); // chrome_text word
  assert.ok(doc.subarray(panel + 112, panel + 128).equals(resolved.subarray(16, 32))); // four paints
  assert.equal(doc.readFloatLE(panel + 92), resolved.readDoubleLE(32)); // title size
  assert.ok(doc.subarray(panel + 96, panel + 100).equals(resolved.subarray(40, 44))); // title paint
  for (let i = 0; i < 6; i += 1) assert.equal(doc.readFloatLE(panel + 32 + 4 * i), resolved.readDoubleLE(44 + 8 * i));
  assert.notEqual(resolved.readUInt32LE(12), 0);
});

test("the Node host carries no chrome-style policy tables", async () => {
  const { readFileSync } = await import("node:fs");
  const source = readFileSync(new URL("../src/scene.js", import.meta.url), "utf8");
  for (const banned of ["STATIC_CHROME_SLOTS", "STATIC_ROOT_STYLE_KEYS", "STATIC_CHROME_FAMILIES", "XYG_STATIC_UNSUPPORTED_CHROME_STYLE", "XYG_STATIC_UNSUPPORTED_TITLE_STYLE"]) {
    assert.ok(!source.includes(banned), banned);
  }
});
