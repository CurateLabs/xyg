// Shared bounded dashboard journey used by the existing Release surfaces command.
import { readFile } from "node:fs/promises";
import { scatterChart } from "../packages/xy-node/src/index.js";
export async function densityAssets(root) {
  const fixture = await readFile(
    new URL("tests/fixtures/filter_tier_c/density.bin", root),
  );
  const input = fixture.subarray(24, 24 + fixture.readUInt32LE(0)),
    names = ["a", "b", "c", "d", "e"],
    rows = Number(input.readBigUInt64LE(64));
  const columns = Object.fromEntries(
    names.map((name, d) => [
      name,
      Array.from({ length: rows }, (_, i) =>
        input.readDoubleLE(96 + (d * rows + i) * 8),
      ),
    ]),
  );
  const assets = new Map();
  for (let i = 0; i < 5; i++) {
    const figure = scatterChart(
      columns[names[i]],
      columns[names[(i + 1) % 5]],
      {
        density: true,
        width: 400,
        height: 260,
        title: `${names[i]} × ${names[(i + 1) % 5]}`,
      },
    );
    figure.interaction = {
      link_group: "filter-density-compat",
      link_select: true,
      link_axes: [],
    };
    figure.setAxis("x", { domain: [-2, 2] });
    figure.setAxis("y", { domain: [-2, 2] });
    const payload = figure.buildPayload();
    assets.set(`/density-${i}.json`, {
      type: "application/json",
      data: JSON.stringify(payload.spec),
    });
    assets.set(`/density-${i}.bin`, {
      type: "application/octet-stream",
      data: payload.buffers,
    });
  }
  return assets;
}
// No browser-side product classifier: this independent oracle is test-only.
export async function setupLinkedDensity() {
  const xy = await import("/packages/xy-client/dist/index.js");
  const stream = await (
      await fetch("/tests/fixtures/filter_tier_c/density.bin")
    ).arrayBuffer(),
    d = new DataView(stream);
  const start = 24,
    names = ["a", "b", "c", "d", "e"],
    n = Number(d.getBigUint64(start + 64, true)),
    first = d.getBigUint64(start + 72, true);
  const cols = Object.fromEntries(
    names.map((name, dim) => [
      name,
      Array.from({ length: n }, (_, i) =>
        d.getFloat64(start + 96 + (dim * n + i) * 8, true),
      ),
    ]),
  );
  const module = await WebAssembly.compileStreaming(
    fetch("/packages/xy-client/dist/xyg-wasm.wasm"),
  );
  const worker = xy.createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: module,
    maxArenaBytes: 1 << 20,
  });
  const session = await xy.createWasmFilterSession(worker, cols, {
    sourceId: 112n,
    epoch: 7n,
    firstRow: first,
    budgetBytes: 1n << 20n,
  });
  const packets = [];
  const execute = session.executeTransport;
  session.executeTransport = (packet) => {
    packets.push(packet.slice());
    return execute(packet);
  };
  const tickWorker = xy.createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: module,
    maxArenaBytes: 1 << 20,
  });
  const container = document.createElement("main");
  container.style.cssText =
    "display:grid;grid-template-columns:repeat(2,400px);gap:12px;background:white;color:#222";
  document.body.append(container);
  const bindings = [];
  for (let i = 0; i < 5; i++) {
    const el = document.createElement("section");
    el.id = `filter-view-${i}`;
    container.append(el);
    const spec = await (await fetch(`/density-${i}.json`)).json(),
      buffer = await (await fetch(`/density-${i}.bin`)).arrayBuffer();
    const view = xy.renderStandalone(el, spec, buffer);
    await xy.attachWasmTicks(view, {
      worker: tickWorker,
      workerOwnership: "borrow",
    });
    bindings.push({
      view,
      id: BigInt(i + 1),
      sourceId: 112n,
      epoch: 7n,
      dimension: names[i],
      cuts: [-1, 0, 1],
      step: 0.5,
      grid: {
        x: names[i],
        y: names[(i + 1) % 5],
        width: 4,
        height: 4,
        xRange: [-2, 2],
        yRange: [-2, 2],
      },
    });
  }
  const dashboard = await xy.attachFilterDashboard(session, bindings);
  const assert = (value, message) => {
    if (!value) throw new Error(message);
  };
  let checks = 0,
    texturePixels = 0,
    canvasProbes = 0;
  const oracle = async (predicates = [], baseMask = null) => {
    const selected = cols.a.map(
      (_, row) =>
        (!baseMask || baseMask[row >> 3] & (1 << (row & 7))) &&
        predicates.every(
          ([name, lo, hi]) =>
            Number.isFinite(cols[name][row]) &&
            cols[name][row] >= Math.min(lo, hi) &&
            cols[name][row] <= Math.max(lo, hi),
        ),
    );
    const reply = dashboard.latest;
    assert(
      reply.selectedCount === BigInt(selected.filter(Boolean).length),
      `ops ${packets.slice(-25).map((p) => {
        const d = new DataView(p.buffer);
        return [
          d.getUint32(8, true),
          d.getBigUint64(56, true).toString(),
          d.getBigUint64(64, true).toString(),
        ];
      })}; canonical selected total ${reply.selectedCount} != ${selected.filter(Boolean).length}; latest range ${packets
        .filter((p) => new DataView(p.buffer).getUint32(8, true) === 5)
        .slice(-1)
        .map((p) => [
          new DataView(p.buffer).getFloat64(80, true),
          new DataView(p.buffer).getFloat64(88, true),
        ])}`,
    );
    assert(
      reply.sourceId === 112n && reply.epoch === 7n && reply.firstRow === first,
      "source identity",
    );
    if (reply.tier === 3n)
      assert(
        reply.rowsRead === 0n && reply.fallback === 0n,
        "Tier C work contract",
      );
    for (const binding of bindings) {
      const actual = reply.density.find((p) => p.id === binding.id),
        totals = Array(16).fill(0n),
        counts = Array(16).fill(0n);
      for (let row = 0; row < cols.a.length; row++)
        for (let y = 0; y < 4; y++)
          for (let x = 0; x < 4; x++)
            if (
              cols[binding.grid.x][row] >= -2 + x &&
              cols[binding.grid.x][row] < -1 + x &&
              cols[binding.grid.y][row] >= -2 + y &&
              cols[binding.grid.y][row] < -1 + y
            ) {
              totals[y * 4 + x]++;
              if (selected[row]) counts[y * 4 + x]++;
            }
      assert(
        actual.totals.every((n, i) => n === totals[i]),
        "independent total bins",
      );
      assert(
        actual.selected.every((n, i) => n === counts[i]),
        "independent selected bins",
      );
      const gpu = binding.view.gpuTraces[0];
      assert(
        gpu.tier === "density" && !gpu.sampleOverlay && !gpu.drill,
        "ordinary aggregate density plane",
      );
      assert(
        gpu.trace.n_points === Number(reply.sourceRows) &&
          gpu.trace.n_marks === actual.width * actual.height,
        "canonical density trace metadata",
      );
      assert(
        gpu.filterCounts.hash === reply.filterHash &&
          gpu.filterCounts.revision === reply.revision,
        "paint metadata",
      );
      assert(
        gpu.filterCounts.selected.every((n, i) => n === counts[i]),
        "paint exact integers",
      );
      checks++;
    }
    const page = await session.membership(first, cols.a.length);
    assert(
      page.membership.every(
        (bits, byte) =>
          bits ===
          selected
            .slice(byte * 8, byte * 8 + 8)
            .reduce((b, v, i) => b | (v ? 1 << i : 0), 0),
      ),
      "independent membership",
    );
    checks++;
    return reply;
  };
  const pixels = () =>
    bindings.map(({ view, id }) => {
      view._cancelDrawFrame();
      view._drawNow();
      const gl = view.gl,
        data = new Uint8Array(view.canvas.width * view.canvas.height * 4);
      gl.readPixels(
        0,
        0,
        view.canvas.width,
        view.canvas.height,
        gl.RGBA,
        gl.UNSIGNED_BYTE,
        data,
      );
      assert(gl.getError() === gl.NO_ERROR, "WebGL paint error");
      const plane = dashboard.latest.density.find((p) => p.id === id),
        saved = gl.getParameter(gl.FRAMEBUFFER_BINDING),
        fbo = gl.createFramebuffer();
      try {
        gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
        gl.framebufferTexture2D(
          gl.FRAMEBUFFER,
          gl.COLOR_ATTACHMENT0,
          gl.TEXTURE_2D,
          view.gpuTraces[0].density.tex,
          0,
        );
        assert(
          gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE,
          "density texture framebuffer",
        );
        const pixels = new Uint8Array(plane.width * plane.height * 4);
        gl.readPixels(
          0,
          0,
          plane.width,
          plane.height,
          gl.RGBA,
          gl.UNSIGNED_BYTE,
          pixels,
        );
        for (let i = 0; i < plane.grid.length; i++)
          for (let c = 0; c < 4; c++) {
            const alpha = plane.grid[i] > 0 ? plane.rgba[i * 4 + 3] : 0;
            const expected =
              c === 3
                ? alpha
                : Math.round((plane.rgba[i * 4 + c] * alpha) / 255);
            assert(
              pixels[i * 4 + c] === expected,
              "exact selected-density texture pixels",
            );
          }
        texturePixels += plane.grid.length;
      } finally {
        gl.bindFramebuffer(gl.FRAMEBUFFER, saved);
        gl.deleteFramebuffer(fbo);
      }

      // Independent data-coordinate probe: raw texture agreement alone cannot
      // detect a buffer whose row order is wrong for the ordinary sampler.
      for (let i = 0; i < plane.grid.length; i++)
        if (plane.grid[i] > 0 && plane.rgba[i * 4 + 3] === 255) {
          const cx = i % plane.width,
            cy = Math.floor(i / plane.width);
          const x =
            plane.xRange[0] +
            ((plane.xRange[1] - plane.xRange[0]) * (cx + 0.5)) / plane.width;
          const y =
            plane.yRange[0] +
            ((plane.yRange[1] - plane.yRange[0]) * (cy + 0.5)) / plane.height;
          const px = Math.floor(
              (view._dataPx("x", x) - view.plot.x) * view.dpr,
            ),
            py = Math.floor(
              view.canvas.height -
                (view._dataPx("y", y) - view.plot.y) * view.dpr,
            );
          const offset = (py * view.canvas.width + px) * 4;
          for (let c = 0; c < 4; c++)
            assert(
              data[offset + c] === plane.rgba[i * 4 + c],
              "exact data-coordinate selected density pixel",
            );
          canvasProbes++;
        }
      let colored = 0,
        hash = 2166136261;
      for (let i = 0; i < data.length; i += 4) {
        if (data[i] !== data[i + 1] || data[i + 1] !== data[i + 2]) colored++;
        for (let c = 0; c < 4; c++)
          hash = Math.imul(hash ^ data[i + c], 16777619) >>> 0;
      }
      assert(colored > 20, "density was not painted");
      return { colored, hash };
    });
  await oracle();
  const initial = pixels();
  window.filterDensity = {
    xy,
    session,
    tickWorker,
    dashboard,
    bindings,
    cols,
    first,
    oracle,
    pixels,
    initial,
    packets,
    checks: () => checks,
    texturePixels: () => texturePixels,
    canvasProbes: () => canvasProbes,
  };
  return { initial, views: bindings.length };
}

export async function runLinkedDensityBrowser(page, indexedCapture = null) {
  const initial = await page.evaluate(setupLinkedDensity);
  await page.evaluate(async () => {
    const f = window.filterDensity,
      v = f.bindings[0].view,
      revision = f.session.revision,
      mode = v.dragMode;
    v._setDragMode("select-lasso");
    if (
      v.dragMode !== mode ||
      !f.dashboard.error ||
      f.session.revision !== revision
    )
      throw new Error("unsupported predicate tool did not fail closed");
    await f.dashboard.refresh();
  });
  const focus = async (index) => {
    const target = page.locator(`#filter-view-${index} canvas[tabindex="0"]`);
    for (let i = 0; i < 40; i++) {
      if (await target.evaluate((el) => document.activeElement === el)) return;
      await page.keyboard.press("Tab");
    }
    throw new Error("keyboard tab journey did not reach chart canvas");
  };

  const points = await page.evaluate(() => {
    const v = window.filterDensity.bindings[0].view,
      r = v.root.getBoundingClientRect();
    return {
      x0: r.left + v._dataPx("x", 0),
      x1: r.left + v._dataPx("x", 0.5),
      y: r.top + v.plot.y + v.plot.h / 2,
    };
  });
  // Use the actual pointer listeners and pointer capture, not _sendSelect.
  await page.mouse.move(points.x0, points.y);
  await page.mouse.down();
  await page.mouse.move(points.x1, points.y, { steps: 5 });
  await page.mouse.up();
  const pointer = await page.evaluate(async () => {
    const f = window.filterDensity;
    await f.dashboard.ready();
    const r = await f.oracle([["a", 0, 0.5]]);
    return {
      hash: r.filterHash.toString(),
      tier: r.tier.toString(),
      rowsRead: r.rowsRead.toString(),
      fallback: r.fallback.toString(),
      prefixCellsRead: r.prefixCellsRead.toString(),
      pixels: f.pixels(),
      selected: r.selectedCount.toString(),
    };
  });
  await focus(0);
  await page.keyboard.press("Delete");
  await page.evaluate(() => window.filterDensity.dashboard.ready());
  await page.keyboard.press("b");
  await page.evaluate(() => window.filterDensity.dashboard.ready());
  for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowRight");
  await page.keyboard.press("End");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("Enter");
  const keyboard = await page.evaluate(async () => {
    const f = window.filterDensity;
    await f.dashboard.ready();
    const r = await f.oracle([["a", 0, 0.5]]);
    return {
      hash: r.filterHash.toString(),
      tier: r.tier.toString(),
      rowsRead: r.rowsRead.toString(),
      fallback: r.fallback.toString(),
      prefixCellsRead: r.prefixCellsRead.toString(),
      pixels: f.pixels(),
      selected: r.selectedCount.toString(),
    };
  });
  if (
    pointer.hash !== keyboard.hash ||
    pointer.pixels.some((p, i) => p.hash !== keyboard.pixels[i].hash)
  )
    throw new Error(
      "pointer/keyboard exact predicate and painted-pixel parity failed",
    );
  if (!pointer.pixels.every((p, i) => p.hash !== initial.initial[i].hash))
    throw new Error(
      "selected-count plane did not change all five rendered views",
    );
  if (
    pointer.tier !== "3" ||
    keyboard.tier !== "3" ||
    pointer.rowsRead !== "0" ||
    keyboard.rowsRead !== "0"
  )
    throw new Error("painted indexed subset enumerated canonical rows");
  await page.evaluate(async () => {
    const f = window.filterDensity,
      revision = f.session.revision,
      prior = f.dashboard.latest;
    if (
      !f.bindings[0].view._linkChannel ||
      !f.bindings[0].view._interactionFlag("link_select")
    )
      throw new Error("authored legacy selection channel is missing");
    const received = new Promise((resolve) =>
      f.bindings[0].view.root.addEventListener("xy:filter_error", resolve, {
        once: true,
      }),
    );
    const foreign = new BroadcastChannel("xy:filter-density-compat");
    try {
      foreign.postMessage({
        source: "foreign-source",
        selection: { clear: true },
      });
      await received;
      await f.dashboard.ready();
      if (f.session.revision !== revision || f.dashboard.latest !== prior)
        throw new Error("coordinate broadcast changed canonical filter intent");
    } finally {
      foreign.close();
    }
  });
  if (indexedCapture)
    await page.screenshot({ path: indexedCapture, fullPage: true });
  // Keyboard cancel restores the Rust edit snapshot (including other dimensions).
  await focus(0);
  await page.keyboard.press("b");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Escape");
  await page.evaluate(async () => {
    const f = window.filterDensity;
    await f.dashboard.ready();
    await f.oracle([["a", 0, 0.5]]);
  });
  // Live pointer preview and Escape restore use Rust edit transactions.
  await focus(0);
  await page.mouse.move((points.x0 + points.x1) / 2, points.y);
  await page.mouse.down();
  await page.mouse.move(points.x1 + (points.x1 - points.x0) / 2, points.y, {
    steps: 3,
  });
  await page.evaluate(async () => {
    const f = window.filterDensity;
    await f.dashboard.ready();
    await f.oracle([["a", 0.25, 0.75]]);
  });
  await page.keyboard.press("Escape");
  await page.mouse.up();
  await page.evaluate(async () => {
    const f = window.filterDensity;
    await f.dashboard.ready();
    await f.oracle([["a", 0, 0.5]]);
  });
  // Keyboard-only editing on a different dimension composes membership.
  await focus(1);
  await page.keyboard.press("b");
  for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowRight");
  await page.keyboard.press("End");
  for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("Enter");
  await page.evaluate(async () => {
    const f = window.filterDensity;
    await f.dashboard.ready();
    await f.oracle([
      ["a", 0, 0.5],
      ["b", 0, 0.5],
    ]);
  });
  const lifecycle = await page.evaluate(async () => {
    const f = window.filterDensity,
      d = f.dashboard;
    await d.range(2n, -0.5, 0.5);
    await f.oracle([
      ["a", 0, 0.5],
      ["b", -0.5, 0.5],
    ]);
    await d.evict();
    await f.oracle([
      ["a", 0, 0.5],
      ["b", -0.5, 0.5],
    ]);
    const old = d.latest;
    const [stale, newer] = await Promise.all([
      d.range(3n, -0.25, 0.25),
      d.range(3n, 0, 1),
    ]);
    if (
      d.latest.revision !== newer.revision ||
      stale.revision >= newer.revision ||
      d.latest === old
    )
      throw new Error("newer request publication failed");
    await f.oracle([
      ["a", 0, 0.5],
      ["b", -0.5, 0.5],
      ["c", 0, 1],
    ]);
    await d.append(
      Object.fromEntries(Object.keys(f.cols).map((name) => [name, [0.25]])),
    );
    for (const name of Object.keys(f.cols)) f.cols[name].push(0.25);
    await f.oracle([
      ["a", 0, 0.5],
      ["b", -0.5, 0.5],
      ["c", 0, 1],
    ]);
    await d.baseFilter([{ dimension: "d", lo: 0, hi: 1 }]);
    await f.oracle([
      ["a", 0, 0.5],
      ["b", -0.5, 0.5],
      ["c", 0, 1],
      ["d", 0, 1],
    ]);
    await d.clear();
    await f.oracle([["d", 0, 1]]);
    await d.baseFilter([]);
    await f.oracle();
    const hidden = f.bindings[4].view;
    hidden._legendOffTraces = new Set([0]);
    await d.refresh();
    if (!hidden.gpuTraces[0]._legendHidden)
      throw new Error("filter publication lost legend visibility");
    hidden._legendOffTraces.clear();
    await d.refresh();
    if (hidden.gpuTraces[0]._legendHidden)
      throw new Error("filter publication stranded legend visibility");
    await f.oracle();
    const v = f.bindings[1].view,
      ext = v.gl.getExtension("WEBGL_lose_context");
    if (!ext) throw new Error("required context loss extension absent");
    const restored = new Promise((resolve) =>
      v.root.addEventListener("xy:context_restored", resolve, { once: true }),
    );
    ext.loseContext();
    await new Promise((resolve) =>
      v.root.addEventListener("xy:context_lost", resolve, { once: true }),
    );
    ext.restoreContext();
    await restored;
    await d.ready();
    await f.oracle();
    f.pixels();
    // A failed texture replacement must publish none of the five candidates.
    const records = f.bindings.map((b) => b.view.gpuTraces[0]),
      latest = d.latest,
      broken = f.bindings[2].view,
      build = broken._buildTrace;
    broken._buildTrace = () => {
      throw new Error("injected density upload failure");
    };
    let refused = false;
    try {
      await d.range(1n, 0, 1);
    } catch (e) {
      refused = e.message.includes("injected density upload failure");
    } finally {
      broken._buildTrace = build;
    }
    if (
      !refused ||
      d.latest !== latest ||
      f.bindings.some(
        (b, i) =>
          b.view.gpuTraces[0] !== records[i] ||
          !b.view.gl.isTexture(records[i].density.tex),
      )
    )
      throw new Error("five-view publication failure was not atomic");
    await d.refresh();
    await f.oracle([["a", 0, 1]]);
    f.pixels();
    return {
      checks: f.checks(),
      texturePixels: f.texturePixels(),
      canvasProbes: f.canvasProbes(),
      diagnostics: Object.fromEntries(
        [
          "sourceId",
          "epoch",
          "sourceRevision",
          "filterHash",
          "tier",
          "indexBytes",
          "residentBytes",
          "peakBytes",
          "rowsRead",
          "prefixCellsRead",
          "fallback",
          "revision",
        ].map((k) => [k, d.latest[k].toString()]),
      ),
      environment: {
        userAgent: navigator.userAgent,
        dpr: devicePixelRatio,
        renderer: f.bindings[0].view.gl.getParameter(
          f.bindings[0].view.gl.RENDERER,
        ),
      },
      selected: d.latest.selectedCount.toString(),
      revision: d.latest.revision.toString(),
      aria: f.bindings.every(
        (b) =>
          b.view.canvas.getAttribute("aria-busy") === "false" &&
          b.view.a11yLive.textContent.includes("canonical rows"),
      ),
    };
  });
  if (!lifecycle.aria)
    throw new Error("assistive completion announcement missing");
  return {
    rendered: true,
    paintedViews: 5,
    pointerPreview: true,
    pointerCancel: true,
    keyboardOtherDimension: true,
    publicationFailureAtomic: true,
    pointer,
    keyboard,
    lifecycle,
  };
}
