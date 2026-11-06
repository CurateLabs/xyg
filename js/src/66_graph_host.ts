/** Default property-graph notebook transport. Rust owns layout and GPU buffers. */
import { createGraphGpuPainter, decodeGraphGpu } from "./63_graph_gpu";
import { decodeGraphSessionResult, encodeGraphSessionRequest, type GraphSessionCamera } from "./63_graph_session_wire";
import { XYG_WASM_GRAPH_DEFAULT_CHUNK_STEPS, XYG_WASM_GRAPH_DEFAULT_MAX_WALL_MS } from "./wasm_abi_generated";

export function renderGraphHost({ model, el }) {
  const spec = model.get("spec"), epoch = crypto.randomUUID(), instanceId = BigInt(spec.instance);
  const surface = document.createElement("div"), status = document.createElement("div");
  surface.style.width = `${spec.width}px`; surface.style.height = `${spec.height}px`;
  status.setAttribute("aria-live", "polite"); status.textContent = "Laying out graph";
  el.append(surface, status);
  const painter = createGraphGpuPainter(surface);
  const camera: GraphSessionCamera = [1, 1, spec.width / 2, spec.height / 2, spec.width, spec.height, devicePixelRatio || 1];
  let disposed = false, sequence = 2n, revision = 0, frame: number | null = null;
  const send = (operation: string, bytes?: Uint8Array) => model.send({ operation, epoch }, {}, bytes ? [bytes] : []);
  function stop() {
    if (disposed) return;
    disposed = true;
    if (frame !== null) cancelAnimationFrame(frame);
    clearTimeout(deadline); send("dispose"); model.off("msg:custom", message);
  }
  function fail() { status.textContent = "XYG_GRAPH_WORKER_FAILED"; stop(); }
  function message(content, buffers) {
    if (disposed || content.epoch !== epoch) return;
    if (content.type === "graph_failed") { fail(); return; }
    if (content.type !== "graph_reply") return;
    try {
      if (!buffers.length) {
        send("render", encodeGraphSessionRequest({ instanceId, opSeq: sequence++, revision, operation: 21, camera }));
        return;
      }
      const buffer = buffers[0], bytes = buffer instanceof DataView ? new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength) : new Uint8Array(buffer);
      const result = decodeGraphSessionResult(bytes);
      if (result.revision < revision) return;
      painter.paint(decodeGraphGpu(result.sections), camera); revision = result.revision;
      surface.dataset.graphRevision = String(revision);
      surface.dataset.graphSteps = String(result.relayout?.steps ?? 0);
      status.textContent = result.relayout?.done ? "Layout complete" : "Laying out graph";
      if (result.relayout?.done) { clearTimeout(deadline); return; }
      // One request per presented frame: no queue of position publications.
      frame = requestAnimationFrame(() => {
        frame = null;
        if (!disposed) send("step", encodeGraphSessionRequest({ instanceId, opSeq: sequence++, revision, operation: 15, steps: XYG_WASM_GRAPH_DEFAULT_CHUNK_STEPS }));
      });
    } catch { fail(); }
  }
  const deadline = setTimeout(fail, XYG_WASM_GRAPH_DEFAULT_MAX_WALL_MS);
  model.on("msg:custom", message); send("mount");
  return () => { stop(); painter.dispose(); surface.remove(); status.remove(); };
}
