/** Marshaling/presentation bridge. Rust and force_scheduler.js remain authorities. */
import { parentPort, workerData } from "node:worker_threads";
import { graphIsProgressiveForce } from "./abi.js";
import { runForceTicks } from "./force_scheduler.js";
import { composeGraphForge, decodeGraphForgeDocument, graphforgeGraphData,
  graphforgeStaticPayload } from "./graphforge.js";

const { opts, revision, jobId, maxWallMs } = workerData;
const abort = new AbortController();
let pending, presenting, schedulerDone = false, closed = false;
let composition;
const send = (msg, transfer = []) => parentPort.postMessage({ ...msg, revision, jobId }, transfer);
const close = () => { closed = true; parentPort.close(); };
function finish() {
  if (schedulerDone && !presenting && !pending && !closed) { send({ type: "done" }); close(); }
}
function present() {
  if (closed || abort.signal.aborted || presenting || !pending) return;
  const state = pending;
  pending = undefined;
  const started = performance.now();
  // Every force checkpoint is SOURCE-indexed. Preset packing cannot step force,
  // including at Aggregate LOD (never use returned render centroids as seeds).
  const positions = state.x ? { uuid: composition.nodes.uuid, x: state.x, y: state.y } : null;
  const { figure, ...payload } = graphforgeStaticPayload(composition, {
    ...opts, ...(positions ? { positions, layout: "preset" } : {}),
  });
  const sourcePositions = positions ?? payload.positions;
  const meta = figure._graphMeta?.[0];
  // Serialize existing Rust membership answers; never reconstruct routes or UUID
  // joins in the host. Pick data stays in the Node host, outside the paint wire.
  const edgeTrace = payload.edgeTrace;
  const edges = meta ? Array.from({ length: figure.traces[edgeTrace].x0.length }, (_, i) => figure.graphEdgePick(edgeTrace, i)) : [];
  presenting = state;
  const message = { ...payload, positions: sourcePositions, pickData: { nodeTrace: payload.nodeTrace,
    edgeTrace, aggregate: meta?.tier_name === "aggregate", edges },
    revision, jobId, step: state.step, phase: state.phase, alpha: state.alpha,
    packingMs: performance.now() - started };
  send({ type: "payload", payload: message }, [message.buffer,
    ...(sourcePositions ? [sourcePositions.x.buffer, sourcePositions.y.buffer] : [])]);
}
function checkpoint(state) {
  if (abort.signal.aborted) return;
  // The first checkpoint is presented before returning its scheduler ACK.
  // Later callbacks retain only the newest source snapshot while presentation
  // waits for the consumer. The scheduler still ACKs each native chunk.
  pending = state;
  present();
}
parentPort.on("message", msg => {
  if (msg?.type === "cancel") {
    abort.abort(); pending = undefined; presenting = undefined;
    if (schedulerDone) close();
  }
  else if (msg?.type === "accept" && msg.revision === revision && msg.jobId === jobId && msg.step === presenting?.step) {
    presenting = undefined;
    try { present(); finish(); } catch (cause) { fail(cause); }
  }
});
function fail(cause) {
  if (closed) return;
  abort.abort();
  send({ type: "error", message: String(cause?.message ?? cause), code: cause?.code,
    name: cause?.name, layer: cause?.layer, field: cause?.field });
  if (schedulerDone) close();
  // `main` owns scheduler settlement; don't close its parent before force exit.
}
async function main() {
  try {
    if (workerData.documentBytes) composition = decodeGraphForgeDocument(workerData.documentBytes);
    else {
      // `render` is the explicit one-shot Scene API; live requests must never
      // accidentally enter it before scheduling the real source graph.
      if (workerData.input?.render != null) throw new TypeError("live input must omit render; use graphforgeChart for static Scene export");
      composition = composeGraphForge(workerData.input);
    }
    const layout = String(opts.layout ?? "force").trim().toLowerCase();
    if (composition.kind === "graph" && graphIsProgressiveForce(layout)) {
      const data = graphforgeGraphData(composition);
      let x, y;
      if (opts.positions != null) {
        const p = opts.positions;
        if (!Array.isArray(p.uuid) || p.x?.length !== p.uuid.length || p.y?.length !== p.uuid.length) throw new TypeError("positions must be { uuid, x, y }");
        const at = new Map(p.uuid.map((id, i) => [id, i]));
        if (data.ids.some(id => !at.has(id))) throw new RangeError("live source positions must cover every composed UUID");
        x = Float64Array.from(data.ids, id => p.x[at.get(id)]);
        y = Float64Array.from(data.ids, id => p.y[at.get(id)]);
      }
      let parents;
      if (layout === "cose" && data.parentIndices != null) {
        if (data.parentIndices.length !== data.nNodes || data.parentValidity?.length !== data.nNodes) throw new RangeError("compound parent planes must match source nodes");
        parents = BigUint64Array.from(data.parentIndices, (v, i) => data.parentValidity[i] ? v : 0xffffffffffffffffn);
      }
      const pinned = typeof opts.pinned === "string" ? data.nodeAttrs[opts.pinned] : opts.pinned;
      if (typeof opts.pinned === "string" && pinned == null) throw new RangeError("unknown pinned node column");
      await runForceTicks({ nNodes: data.nNodes, sources: data.sources, targets: data.targets,
        x, y, pinned, parents, algorithm: layout, cose: opts.cose, seed: opts.seed,
        totalSteps: opts.iterations ?? 300, chunkSteps: opts.chunkSteps ?? 10,
        revision, jobId, maxWallMs, signal: abort.signal, onTick: checkpoint });
    } else checkpoint({ phase: "complete", step: 0, alpha: null });
    schedulerDone = true;
    if (abort.signal.aborted) close(); else finish();
  } catch (cause) {
    fail(cause); close();
  }
}
main();
