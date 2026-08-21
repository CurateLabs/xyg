import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

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

  const spec = { protocol: 12, title: "fixture", traces: [], columns: [] };
  const doc = toHtml({ spec, buffers: Buffer.from([1, 2, 3]) });
  const client = fs.readFileSync(clientPath, "utf8");
  assert.ok(doc.startsWith("<!doctype html>"));
  assert.ok(doc.includes("var xy="));
  assert.ok(doc.includes("xy.renderStandalone"));
  assert.ok(doc.includes(client.slice(0, 80)));
  assert.ok(doc.includes("AQID")); // base64 of 0x01 0x02 0x03
  assert.ok(doc.includes("xyDecodeB64"));
});

test("toHtml writes a destination path when given", () => {
  const spec = { protocol: 12, title: "saved", traces: [], columns: [] };
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
  const spec = { protocol: 12, traces: [], columns: [] };
  assert.throws(
    () => toHtml({ spec, buffers: Buffer.alloc(0) }, null, { customCss: "</style>" }),
    /customCss/,
  );
});
