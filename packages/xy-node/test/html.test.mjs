import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { runInNewContext } from "node:vm";
import { fileURLToPath, pathToFileURL } from "node:url";

import { standaloneClientPath, toHtml } from "../src/html.js";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const htmlSrc = fs.readFileSync(path.join(root, "src", "html.js"), "utf8");
const clientPath = path.join(root, "..", "xy-client", "dist", "standalone.js");

test("packaged standalone client wins over a separately installed client", () => {
  const external = path.join("external", "@curatelabs", "xyg", "standalone.js");
  const seen = [];
  const selected = standaloneClientPath({
    exists(candidate) {
      seen.push(candidate);
      return candidate.endsWith(path.join("client", "standalone.js")) || candidate === external;
    },
    requireFn: { resolve: () => external },
  });
  assert.ok(selected.endsWith(path.join("client", "standalone.js")));
  assert.deepEqual(seen, [selected]);
});

test("standalone client falls back to a separately installed client", () => {
  const external = path.join("external", "@curatelabs", "xyg", "standalone.js");
  const seen = [];
  const selected = standaloneClientPath({
    exists(candidate) {
      seen.push(candidate);
      return candidate === external;
    },
    requireFn: { resolve: () => external },
  });
  assert.equal(selected, external);
  assert.equal(seen.length, 2);
  assert.ok(seen[0].endsWith(path.join("client", "standalone.js")));
  assert.equal(seen[1], external);
});

test("toHtml inlines the host-neutral standalone client", () => {
  assert.equal(
    htmlSrc.includes("python/xyg/static"),
    false,
    "toHtml must not read the Python wheel copy",
  );
  assert.ok(
    htmlSrc.includes("xy-client") || htmlSrc.includes("@curatelabs/xyg"),
    "toHtml must resolve @curatelabs/xyg / packages/xy-client",
  );
  assert.ok(fs.existsSync(clientPath), "run `node js/build.mjs` so packages/xy-client/dist exists");

  const spec = { protocol: 13, title: "fixture", traces: [], columns: [] };
  const doc = toHtml({ spec, buffers: Buffer.from([1, 2, 3]) });
  const client = fs.readFileSync(clientPath, "utf8");
  assert.ok(doc.startsWith("<!doctype html>"));
  assert.ok(doc.includes("var xy="));
  assert.ok(doc.includes("xy.renderStandalone"));
  assert.ok(doc.includes(client.slice(0, 80)));
  assert.ok(doc.includes("AQID")); // base64 of 0x01 0x02 0x03
  assert.ok(doc.includes("xyDecodeB64"));
  assert.ok(doc.includes("xy.attachWasmTicks"));
  assert.ok(doc.includes("workerOwnership: \"own\""));
  assert.ok(doc.includes("'wasm-unsafe-eval'"));
  assert.ok(doc.includes("connect-src 'none'"));
  assert.ok(doc.includes(fs.readFileSync(path.join(path.dirname(clientPath), "xyg-wasm.wasm")).toString("base64")));
});

test("standalone HTML escapes hostile payload text and worker script boundaries", () => {
  const title = '</script><script>globalThis.exportInjection=true</script>';
  const doc = toHtml({ spec: { protocol: 13, title, traces: [], columns: [] }, buffers: new Uint8Array() });
  assert.ok(!doc.includes(title));
  assert.ok(doc.includes("\\u003c/script\\u003e"));
  assert.ok(doc.includes("pagehide"));
});

test("cached pagehide retains the chart across repeated restores and final exit cleans up", async () => {
  const doc = toHtml({ spec: {}, buffers: new Uint8Array() });
  const bootstrap = doc.slice(doc.lastIndexOf("<script>") + 8, doc.lastIndexOf("</script>"));
  const events = new EventTarget();
  let destroyed = 0;
  runInNewContext(bootstrap, {
    __xyChunks: [],
    document: { getElementById: () => ({ remove() {} }) },
    xy: { renderStandalone: () => ({ destroy() { destroyed++; } }),
      XygWasmWorker: class {}, attachWasmTicks: async () => {} },
    addEventListener: events.addEventListener.bind(events),
  });
  await Promise.resolve();
  for (const persisted of [true, true, false]) {
    events.dispatchEvent(Object.assign(new Event("pagehide"), { persisted }));
    assert.equal(destroyed, persisted ? 0 : 1);
  }
});

test("an incomplete installed client fails before writing an HTML artifact", async () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "xy-html-assets-"));
  try {
    fs.mkdirSync(path.join(temporary, "src"));
    fs.mkdirSync(path.join(temporary, "client"));
    fs.writeFileSync(path.join(temporary, "package.json"), '{"type":"module"}');
    fs.copyFileSync(path.join(root, "src/html.js"), path.join(temporary, "src/html.js"));
    fs.writeFileSync(path.join(temporary, "client/standalone.js"), "var xy={};");
    const { toHtml: installedToHtml } = await import(pathToFileURL(path.join(temporary, "src/html.js")));
    const output = path.join(temporary, "export.html");
    assert.throws(() => installedToHtml({ spec: {}, buffers: Buffer.alloc(0) }, output),
      error => error.code === "XYG_HTML_ASSET_MISSING");
    assert.ok(!fs.existsSync(output));
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
});

test("toHtml writes a destination path when given", () => {
  const spec = { protocol: 13, title: "saved", traces: [], columns: [] };
  const dest = path.join(os.tmpdir(), `xy-tohtml-${process.pid}.html`);
  try {
    const doc = toHtml({ spec, buffers: Buffer.alloc(0), title: "saved" }, dest);
    assert.equal(fs.readFileSync(dest, "utf8"), doc);
    assert.ok(doc.includes("<title>saved</title>"));
  } finally {
    fs.rmSync(dest, { force: true });
  }
});

test("toHtml rejects customCss that could break out of <style>", () => {
  const spec = { protocol: 13, traces: [], columns: [] };
  assert.throws(
    () => toHtml({ spec, buffers: Buffer.alloc(0) }, null, { customCss: "</style>" }),
    /customCss/,
  );
});
