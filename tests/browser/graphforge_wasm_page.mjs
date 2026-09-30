// Strict-CSP GraphForge composition page for scripts/graphforge_wasm_smoke.mjs.
import {
  composeWasmGraphForge,
  createXygWasmWorker,
  graphforgeTableElement,
  renderWasmGraphForge,
} from "/packages/xy-client/dist/index.js";

const results = "/tests/fixtures/graphforge/results/";
const bytes = async (name) => new Uint8Array(await (await fetch(`${results}${name}.arrow`)).arrayBuffer());
const manifest = await (await fetch(`${results}manifest.json`)).json();
const generation = manifest.bases.cyclic.generation;

try {
  const worker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: "/packages/xy-client/dist/xyg-wasm.wasm",
    maxArenaBytes: 64 * 1024 * 1024,
  });
  await worker.ready;
  const base = { tables: [await bytes("base-cyclic-nodes"), await bytes("base-cyclic-edges")], generation };
  const el = document.createElement("div");
  Object.assign(el.style, { width: "640px", height: "420px", position: "relative" });
  document.body.append(el);
  const { view, composition } = await renderWasmGraphForge({
    el, worker, width: 640, height: 420, theme: "dark", title: "GraphForge",
    input: {
      base,
      layers: [
        { result: await bytes("pagerank"), intent: "graph", generation, resultId: "result-rank" },
        { result: await bytes("node_similarity"), intent: "graph", generation, resultId: "result-similar" },
      ],
    },
  });
  // Every painted row maps back to a composed identity.
  const painted = new Set();
  let derived = 0;
  view.gpuTraces.forEach((trace, t) => {
    const rows = trace._sceneIds?.lo?.length ?? 0;
    for (let i = 0; i < rows; i++) {
      const id = view.sceneStableId(t, i);
      const identity = id == null ? null : composition.identifyStableId(id);
      if (!identity) continue;
      if (identity.uuid) painted.add(identity.uuid);
      else if (identity.derived) derived += 1;
    }
  });
  // A pick on a node dispatches its UUID and result row.
  const nodeTrace = view.gpuTraces.findIndex((trace) => {
    const id = trace._sceneIds?.lo?.length ? view.sceneStableId(view.gpuTraces.indexOf(trace), 0) : null;
    return id != null && id >= (1n << 32n);
  });
  const selected = new Promise((resolve) => view.root.addEventListener("xy:graphforge-select", (e) => resolve(e.detail), { once: true }));
  view.root.dispatchEvent(new CustomEvent("xy:click", { detail: { trace: nodeTrace, index: 0 } }));
  const pick = await selected;
  // Table-only results render as text, never markup.
  const table = await composeWasmGraphForge(worker, { layers: [{ result: await bytes("triad_census"), intent: "table" }] }).result;
  const element = graphforgeTableElement(table);
  document.body.append(element);
  // Stale generations fail with the Rust code.
  let staleCode = null;
  try {
    await composeWasmGraphForge(worker, { base, layers: [{ result: await bytes("pagerank"), intent: "graph", generation: manifest.bases.dag.generation }] }).result;
  } catch (error) { staleCode = error.code; }
  // A composition cancelled at once rejects with the cancellation code and
  // leaves the worker ready for the next request.
  const cancelled = composeWasmGraphForge(worker, { base, layers: [{ result: await bytes("pagerank"), intent: "graph", generation }] });
  cancelled.cancel();
  let cancelCode = null;
  try { await cancelled.result; } catch (error) { cancelCode = error.code; }
  const after = await composeWasmGraphForge(worker, { base, layers: [{ result: await bytes("pagerank"), intent: "graph", generation }] }).result;
  window.__graphforge = {
    ok: true,
    cancelCode,
    afterCancel: after.nodeUuid.length,
    nodes: composition.nodeUuid,
    edges: composition.edgeUuid.filter(Boolean),
    painted: [...painted],
    derived,
    pick,
    tableRows: element.tBodies[0].rows.length,
    tableHtml: element.outerHTML,
    staleCode,
    legend: [...view.root.querySelectorAll("*")].map((n) => n.textContent).join("|").includes("similar (derived)"),
    diagnostics: composition.diagnostics(),
  };
} catch (error) {
  window.__graphforge = { ok: false, code: error?.code ?? null, message: String(error?.message ?? error) };
}
