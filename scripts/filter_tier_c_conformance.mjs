#!/usr/bin/env node
import {proveFilterCooperative} from "./filter_cooperative_browser.mjs";
// Bounded real Chromium Worker, composed density, pointer and keyboard journey.
import {
  densityAssets,
  runLinkedDensityBrowser,
} from "./filter_density_browser.mjs";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
const root = fileURLToPath(new URL("../", import.meta.url));
// Explicit diagnostic artifact controls never replace the separate package gate.
const wasmPath=process.env.XYG_FILTER_WASM
  ? resolve(process.env.XYG_FILTER_WASM)
  : join(root,"packages/xy-client/dist/xyg-wasm.wasm");
const wasmSource={path:wasmPath,diagnosticOverride:!!process.env.XYG_FILTER_WASM,
  sha256:createHash("sha256").update(await readFile(wasmPath)).digest("hex")};
const density = await densityAssets(new URL("../", import.meta.url));
const allowed = new Set([
  "/tests/fixtures/filter_tier_c/density.bin",
  "/packages/xy-client/dist/index.js",
  "/packages/xy-client/dist/wasm-worker.js",
  "/packages/xy-client/dist/xyg-wasm.wasm",
  "/tests/fixtures/filter_tier_c/session.bin",
]);
const server = createServer(async (req, res) => {
  const path = new URL(req.url, "http://localhost").pathname;
  res.setHeader(
    "Content-Security-Policy",
    "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; style-src 'unsafe-inline'",
  );
  if (path === "/") {
    res.setHeader("Content-Type", "text/html");
    res.end("<!doctype html><title>Filter session conformance</title>");
    return;
  }
  if (density.has(path)) {
    const asset = density.get(path);
    res.setHeader("Content-Type", asset.type);
    res.end(asset.data);
    return;
  }
  if (!allowed.has(path)) {
    res.writeHead(404).end();
    return;
  }
  try {
    res.setHeader(
      "Content-Type",
      extname(path) === ".js"
        ? "text/javascript"
        : extname(path) === ".wasm"
          ? "application/wasm"
          : "application/octet-stream",
    );
    res.end(await readFile(path==="/packages/xy-client/dist/xyg-wasm.wasm"?wasmPath:join(root, path)));
  } catch (error) {
    res.writeHead(500).end(String(error));
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const flag = process.argv.indexOf("--chromium"),
  executablePath = flag < 0 ? process.env.XYG_CHROMIUM : process.argv[flag + 1];
const browser = await chromium.launch({
  headless: true,
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
  ...(executablePath ? { executablePath: resolve(executablePath) } : {}),
});
try {
  const page = await browser.newPage({
    viewport: { width: 1000, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  const report = await page.evaluate(async () => {
    const xy = await import("/packages/xy-client/dist/index.js");
    const module = await WebAssembly.compileStreaming(
      fetch("/packages/xy-client/dist/xyg-wasm.wasm"),
    );
    const make = () =>
      xy.createXygWasmWorker({
        workerUrl: "/packages/xy-client/dist/wasm-worker.js",
        wasm: module,
        maxArenaBytes: 1 << 20,
      });
    const worker = make();
    let packets = 0;
    try {
      const stream = await (
          await fetch("/tests/fixtures/filter_tier_c/session.bin")
        ).arrayBuffer(),
        d = new DataView(stream);
      let at = 0;
      while (at < stream.byteLength) {
        const n = d.getUint32(at, true),
          cap = d.getUint32(at + 4, true),
          status = d.getInt32(at + 8, true),
          replyN = d.getUint32(at + 12, true);
        at += 24;
        const input = stream.slice(at, at + n);
        at += n;
        const expected = new Uint8Array(stream, at, replyN);
        at += replyN;
        // The explicit adapter-capacity test is exercised at raw WASM/native seams;
        // Worker output uses its declared arena cap. Skip that *one request* so
        // its failed intent is not published by an intentionally larger capacity.
        if (status === -4) {
          continue;
        }
        const actual = new Uint8Array(await worker.filterCommand(input));
        if (
          actual.length !== expected.length ||
          actual.some((b, i) => b !== expected[i])
        )
          throw new Error(`Worker full packet drift at ${packets}`);
        packets++;
      }
    } finally {
      await worker.dispose();
    }
    const densityWorker = make();
    let densityPackets = 0;
    try {
      const stream = await (
          await fetch("/tests/fixtures/filter_tier_c/density.bin")
        ).arrayBuffer(),
        d = new DataView(stream);
      let at = 0;
      while (at < stream.byteLength) {
        const n = d.getUint32(at, true),
          status = d.getInt32(at + 8, true),
          size = d.getUint32(at + 12, true);
        at += 24;
        const input = stream.slice(at, at + n);
        at += n;
        const expected = new Uint8Array(stream, at, size);
        at += size;
        if (status === -4) continue;
        const actual = new Uint8Array(await densityWorker.filterCommand(input));
        if (
          actual.length !== expected.length ||
          actual.some((b, i) => b !== expected[i])
        )
          throw new Error(`Worker density packet drift at ${densityPackets}`);
        densityPackets++;
      }
    } finally {
      await densityWorker.dispose();
    }
    const live = make();
    let session;
    try {
      session = await xy.createWasmFilterSession(
        live,
        {
          a: [0, 0.25, 0.5, 1],
          b: [3, 2, 1, 0],
          c: [0, 1, 2, 3],
          d: [3, 1, 0, 2],
          e: [4, 3, 2, 1],
        },
        { sourceId: 91n, budgetBytes: 1n << 20n },
      );
      await session.configure(
        { id: 1n, dimension: "a", cuts: [0, 1] },
        ["a", "b", "c", "d", "e"].map((dimension, i) => ({
          id: BigInt(i + 11),
          dimension,
          cuts: [1, 3],
        })),
      );
      const result = await session.range(0, 0.5);
      if (
        result.views.length !== 5 ||
        result.selectedCount !== 3n ||
        result.rowsRead !== 0n ||
        result.tier !== 3n
      )
        throw new Error("public five-view indexed query failed");
      let rejected = false;
      try {
        await session.range(0.1, 0.4);
      } catch (e) {
        rejected = e.status === 6;
      }
      if (!rejected) throw new Error("boundary did not fail closed");
      const exact = await session.range(0.1, 0.4, { exact: true });
      if (exact.selectedCount !== 1n || exact.fallback !== 1n)
        throw new Error("explicit exact boundary scan failed");
      await session.append({ a: [0.2], b: [2], c: [2], d: [2], e: [2] });
      await session.rebuild();
      const after = await session.range(0.1, 0.4, { exact: true });
      if (after.selectedCount !== 2n) throw new Error("append/rebuild failed");
      return {
        packets,
        densityPackets,
        passiveViews: result.views.length,
        selected: Number(after.selectedCount),
        rowsRead: Number(after.rowsRead),
        rendered: false,
      };
    } finally {
      if (session) await session.close();
      else await live.dispose();
    }
  });
  const out = process.argv.indexOf("--capture");
  const linked = await runLinkedDensityBrowser(
    page,
    out >= 0 ? `${process.argv[out + 1]}.indexed.png` : null,
  );
  if (out >= 0) {
    await page.screenshot({ path: process.argv[out + 1], fullPage: true });
    const packets = await page.evaluate(() =>
      window.filterDensity.packets.map((packet) =>
        Array.from(new Uint8Array(packet)),
      ),
    );
    const raw = packets.flatMap((packet) => {
      const header = Buffer.alloc(4);
      header.writeUInt32LE(packet.length);
      return [header, Buffer.from(packet)];
    });
    await writeFile(
      `${process.argv[out + 1]}.requests.bin`,
      Buffer.concat(raw),
    );
  }
  await page.evaluate(async () => {
    const f = window.filterDensity;
    f.bindings[0].view._applyAppend({ type: "append" }, []);
    let refused = false;
    try {
      await f.dashboard.refresh();
    } catch (e) {
      refused = e.message.includes("canonical session");
    }
    if (
      !refused ||
      f.bindings.some((b) => b.view.canvas.style.visibility !== "hidden")
    )
      throw new Error("out-of-band source invalidation did not fail closed");
  });
  await page.evaluate(async () => {
    const f = window.filterDensity;
    f.dashboard.destroy();
    for (const b of f.bindings) b.view.destroy();
    await f.session.close();
    await f.tickWorker.dispose();
  });
  const cooperative=await proveFilterCooperative(page);
  assert.deepEqual(errors, []);
  assert.equal(report.packets, 44);
  assert.equal(report.densityPackets, 56);
  console.log(
    JSON.stringify({
      schema: "xyg.filter-tier-c-browser/v1",
      wasmSource,
      ...report,
      ...linked,
      cooperative,
    }),
  );
} finally {
  await browser.close();
  server.closeAllConnections();
  await new Promise((r) => server.close(r));
}
