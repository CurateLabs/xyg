/** Experimental explicit retained WASM graph attachment (#36 bounded S5b).
 * Rust owns every graph decision; this module owns pointer/keyboard/DOM/lifetime only.
 * See spec/design/graph-interaction.md “Bounded explicit S5b attachment”. */
import { claimGraphWorker, XygWasmError, type XygWasmWorker } from "./47_wasm";
import { createGraphGpuPainter, decodeGraphGpu } from "./63_graph_gpu";
import { decodeGraphSessionAck, decodeGraphSessionResult, encodeGraphSessionRequest,
  type GraphSessionCamera, type GraphSessionLoad, type GraphSessionResult,
  type GraphSessionRequest } from "./63_graph_session_wire";

/** @experimental Bounded S5b preparation; broader graph interactions remain open. */
export type XygWasmGraphCamera = GraphSessionCamera;
/** @experimental Bounded S5b preparation; broader graph interactions remain open. */
export type XygWasmGraphLoad = GraphSessionLoad;
/** @experimental Bounded S5b preparation; broader graph interactions remain open. */
export type XygWasmGraphSnapshot = Omit<GraphSessionResult, "sections"> & { camera: XygWasmGraphCamera };
/** @experimental Bounded S5b preparation; broader graph interactions remain open. */
export interface XygWasmGraphSessionOptions {
  el: HTMLElement;
  /** Borrowed. Await attachment.dispose() before disposing an owned Worker. */
  worker: XygWasmWorker;
  instanceId: bigint;
  /** Complete XYGF bytes, for example composeWasmGraphForge(...).result.bytes. */
  document: Uint8Array | ArrayBuffer;
  load?: XygWasmGraphLoad;
  /** Exact Rust session order: scale_x, scale_y, offset_x, offset_y, width, height, DPR. */
  camera: XygWasmGraphCamera;
}
/** @experimental Bounded S5b preparation; broader graph interactions remain open. */
export interface XygWasmGraphSession {
  readonly ready: Promise<XygWasmGraphSnapshot>;
  refreshRender(camera?: XygWasmGraphCamera): Promise<XygWasmGraphSnapshot>;
  snapshot(): XygWasmGraphSnapshot | null;
  dispose(): Promise<void>;
}

/** Attach one initially Owned, unlinked session to one packaged Worker.
 * @experimental S5b subset; no temporal/link/update/hover/gesture/force API. */
export function attachWasmGraphSession(options: XygWasmGraphSessionOptions): XygWasmGraphSession {
  if (!options || !(options.el instanceof HTMLElement)) throw new TypeError("A graph container is required");
  // Frame immutable ingress synchronously before asynchronous application work.
  const instanceId = options.instanceId;
  let opening: Uint8Array | null = encodeGraphSessionRequest({ instanceId, opSeq: 1n, revision: 0,
    operation: 19, document: options.document, load: options.load });
  const cameraCopy = (camera: XygWasmGraphCamera): XygWasmGraphCamera => {
    if (!camera || camera.length !== 7 || Array.from(camera).some(v => typeof v !== "number")) throw new TypeError("An explicit seven-f64 session camera is required");
    return Object.freeze([...camera]) as unknown as XygWasmGraphCamera;
  };
  let camera = cameraCopy(options.camera);
  const lane = claimGraphWorker(options.worker), doc = options.el.ownerDocument;
  let disposed = false, terminal = false, busy = true, needsRefresh = false, sequence = 2n, output: GraphSessionResult | null = null;
  let disposal: Promise<void> | null = null, page = 0;
  const surface = doc.createElement("div"), companion = doc.createElement("div"), live = doc.createElement("div");
  const previous = doc.createElement("button"), next = doc.createElement("button"), table = doc.createElement("table"), body = doc.createElement("tbody");
  const surfaceAttributes = new Map(["tabindex", "role", "aria-label", "aria-busy"].map(name => [name, surface.getAttribute(name)]));
  surface.dataset.xyGraphSession = "experimental";
  surface.setAttribute("role", "application"); surface.tabIndex = 0;
  surface.setAttribute("aria-label", "Graph. Arrow keys move focus; Enter selects; Control or Command Enter toggles; Escape clears selection.");
  companion.setAttribute("aria-label", "Graph companion"); live.setAttribute("aria-live", "polite"); live.setAttribute("aria-atomic", "true");
  previous.type = next.type = "button"; previous.textContent = "Previous"; next.textContent = "Next";
  previous.setAttribute("aria-label", "Previous graph companion page"); next.setAttribute("aria-label", "Next graph companion page");
  const head = doc.createElement("thead"), header = doc.createElement("tr");
  for (const label of ["Kind", "Identity", "Label", "Relationship", "Selected", "Action"]) {
    const cell = doc.createElement("th"); cell.scope = "col"; cell.textContent = label; header.append(cell);
  }
  head.append(header); table.append(head, body); companion.append(table, previous, next, live);
  let painter: ReturnType<typeof createGraphGpuPainter>;
  try { painter = createGraphGpuPainter(surface); options.el.append(surface, companion); }
  catch (error) { surface.remove(); companion.remove(); void lane.close(); throw error; }
  function snapshot(): XygWasmGraphSnapshot | null {
    if (!output) return null;
    const { sections: _sections, ...semantic } = output;
    return structuredClone({ ...semantic, camera });
  }
  function dispatch(name: string, detail: unknown) {
    if (disposed) return;
    // Observer failures cannot roll back an already accepted Rust transition.
    try { surface.dispatchEvent(new CustomEvent(`xy:graph-${name}`, { bubbles: true, detail })); } catch { /* observer isolation */ }
  }
  function report(error: unknown) {
    if (disposed) return;
    if (error instanceof XygWasmError && error.code.startsWith("XYG_WASM_")) terminal = true;
    if (error instanceof XygWasmError && error.code === "GF_INTERACTION_STALE") {
      needsRefresh = true; dispatch("stale", { code: error.code, revision: output?.revision ?? 0 });
    } else dispatch("error", { code: error instanceof XygWasmError ? error.code : "GF_INTERACTION_INVALID", message: error instanceof Error ? error.message : String(error) });
  }
  function setBusy(value: boolean) {
    busy = value;
    if (disposed) return;
    surface.setAttribute("aria-busy", String(value));
    for (const button of companion.querySelectorAll("button")) {
      const unavailable = button === previous ? page === 0 : button === next ? !output || (page + 1) * 50 >= output.companion.total : false;
      button.setAttribute("aria-disabled", String(value || unavailable || needsRefresh));
    }
  }
  function install(bytes: ArrayBuffer, candidateCamera: XygWasmGraphCamera, candidatePage: number): XygWasmGraphSnapshot {
    // Validate the entire reply and all GPU sections before any upload/DOM/state.
    let candidate: GraphSessionResult, gpu: ReturnType<typeof decodeGraphGpu>;
    try { candidate = decodeGraphSessionResult(bytes); gpu = decodeGraphGpu(candidate.sections); }
    catch (error) { needsRefresh = true; throw error; }
    const fragment = doc.createDocumentFragment();
    candidate.companion.rows.forEach((cells, index) => {
      const row = doc.createElement("tr");
      for (const value of cells) { const cell = doc.createElement("td"); cell.textContent = value; row.append(cell); }
      const cell = doc.createElement("td"), button = doc.createElement("button"); button.type = "button";
      button.textContent = "Select"; button.dataset.graphRow = String(index);
      // Ref is the ALIGNED Rust candidate; no parsing labels/identities/source rows.
      button.addEventListener("click", () => {
        if (disposed || busy || needsRefresh || output !== candidate) return;
        submit({ operation: 11, mode: 0, refs: [candidate.companion.refs[index]!] }, "select");
      });
      cell.append(button); row.append(cell); fragment.append(row);
    });
    if (disposed) throw new XygWasmError("XYG_WASM_DISPOSED", "Graph attachment was disposed");
    const focusedRow = doc.activeElement instanceof HTMLElement && body.contains(doc.activeElement) ? doc.activeElement.dataset.graphRow : undefined;
    // Painter stages a complete picture before presentation. Validation/refusal
    // leaves the preceding camera/revision/picture/selection/companion intact.
    try { painter.paint(gpu, candidateCamera); } catch (error) { needsRefresh = true; throw error; }
    body.replaceChildren(fragment); output = candidate; camera = candidateCamera; page = candidatePage; needsRefresh = false;
    // Keep navigation buttons mounted and focusable at a page boundary. Native
    // disabled on a currently focused button can blur it while rows rebuild.
    previous.setAttribute("aria-disabled", String(page === 0));
    next.setAttribute("aria-disabled", String((page + 1) * 50 >= candidate.companion.total));
    live.textContent = candidate.summary;
    if (focusedRow !== undefined) {
      const target = body.querySelector<HTMLButtonElement>(`button[data-graph-row="${focusedRow}"]`) ?? (page === 0 ? next : previous);
      target.focus({ preventScroll: true });
    }
    return snapshot()!;
  }
  function request(input: Pick<GraphSessionRequest, "operation"> & Partial<GraphSessionRequest>, candidateCamera = camera, candidatePage = page) {
    if (sequence > 0xffffffffffffffffn) throw new RangeError("Graph op_seq exhausted");
    const bytes = encodeGraphSessionRequest({ ...input, instanceId, opSeq: sequence++, revision: output?.revision ?? 0 });
    return lane.execute(input.operation === 21 ? "render" : "interact", bytes).then(bytes => install(bytes, candidateCamera, input.operation === 17 || input.operation === 21 ? candidatePage : 0));
  }
  // Framing and lane admission happen synchronously. No event is retained by
  // asynchronous work, and no observer runs between choosing a Rust fact and
  // accepting its command locally. Applicability is not a Rust reservation.
  function admit(input: Pick<GraphSessionRequest, "operation"> & Partial<GraphSessionRequest>, kind: "focus" | "select" | "render", candidateCamera = camera, candidatePage = page): Promise<XygWasmGraphSnapshot> {
    if (disposed) throw new XygWasmError("XYG_WASM_DISPOSED", "Graph attachment was disposed");
    if (terminal) throw new XygWasmError("XYG_WASM_DISPOSED", "Graph Worker lifetime ended; mutation outcome may be unknown");
    if (busy) throw new XygWasmError("XYG_WASM_GRAPH_BUSY", "One graph UI action is already outstanding");
    if (needsRefresh && input.operation !== 21) throw new XygWasmError("GF_INTERACTION_STALE", "Refresh the graph publication before further input", -1);
    const pending = request(input, candidateCamera, candidatePage);
    setBusy(true);
    return pending.then(value => {
      if (!disposed) dispatch(kind, value);
      return value;
    }).catch(error => { report(error); throw error; }).finally(() => setBusy(false));
  }
  function run(input: Pick<GraphSessionRequest, "operation"> & Partial<GraphSessionRequest>, kind: "focus" | "select" | "render", candidateCamera = camera, candidatePage = page): Promise<XygWasmGraphSnapshot> {
    try { return admit(input, kind, candidateCamera, candidatePage); }
    catch (error) { return Promise.reject(error); }
  }
  function submit(input: Pick<GraphSessionRequest, "operation"> & Partial<GraphSessionRequest>, kind: "focus" | "select" | "render") {
    void run(input, kind).catch(() => {});
  }
  const keyDown = (event: KeyboardEvent) => {
    if (disposed || terminal || busy || needsRefresh || !output || event.defaultPrevented || event.repeat || event.altKey || event.shiftKey) return;
    if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key) && !event.ctrlKey && !event.metaKey) {
      event.preventDefault(); submit({ operation: 5, direction: ["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1 }, "focus");
    } else if (event.key === "Enter") {
      event.preventDefault(); submit({ operation: 7, mode: event.ctrlKey || event.metaKey ? 2 : 0 }, "select");
    } else if (event.key === "Escape" && !event.ctrlKey && !event.metaKey) {
      const applicable = output.clearAction.applicable;
      try {
        const accepted = admit({ operation: 4 }, "select");
        if (applicable) event.preventDefault();
        void accepted.catch(() => {});
      } catch (error) { report(error); }
    }
  };
  // Presentation mapping only. Rust picks against its accepted CSS-screen
  // geometry. Reject unsupported transforms instead of guessing graph targets.
  function clickCoordinates(event: MouseEvent): readonly [number, number] | null {
    const canvas = painter.canvas, win = doc.defaultView;
    if (!win || !canvas.isConnected || canvas.scrollLeft || canvas.scrollTop) return null;
    for (let element: Element | null = canvas; element;) {
      const style = win.getComputedStyle(element);
      // Motion-path distance/rotation/anchor are separate from transform's
      // matrix. Reject every active path, including on shadow ancestors.
      if (style.offsetPath !== "none") return null;
      if (style.perspective !== "none" || style.rotate !== "none" || style.scale !== "none" || style.translate !== "none") return null;
      if (style.transform !== "none") {
        const matrix = new DOMMatrixReadOnly(style.transform);
        if (!matrix.is2D || matrix.b !== 0 || matrix.c !== 0 || matrix.a <= 0 || matrix.d <= 0) return null;
      }
      const root = element.getRootNode();
      // Slots supply displayed ancestors before the light-DOM parent does.
      element = element.assignedSlot ?? element.parentElement ?? (root instanceof ShadowRoot ? root.host : null);
    }
    const style = win.getComputedStyle(canvas), rect = canvas.getBoundingClientRect();
    if (style.objectFit !== "fill") return null;
    const left = parseFloat(style.borderLeftWidth) + parseFloat(style.paddingLeft);
    const top = parseFloat(style.borderTopWidth) + parseFloat(style.paddingTop);
    const horizontal = left + parseFloat(style.borderRightWidth) + parseFloat(style.paddingRight);
    const vertical = top + parseFloat(style.borderBottomWidth) + parseFloat(style.paddingBottom);
    const width = parseFloat(style.width), height = parseFloat(style.height);
    const borderWidth = width + (style.boxSizing === "border-box" ? 0 : horizontal);
    const borderHeight = height + (style.boxSizing === "border-box" ? 0 : vertical);
    const contentWidth = borderWidth - horizontal, contentHeight = borderHeight - vertical;
    if (![left, top, borderWidth, borderHeight, contentWidth, contentHeight, rect.width, rect.height].every(Number.isFinite) ||
        contentWidth <= 0 || contentHeight <= 0 || rect.width <= 0 || rect.height <= 0) return null;
    const x = (event.clientX - rect.left) * borderWidth / rect.width - left;
    const y = (event.clientY - rect.top) * borderHeight / rect.height - top;
    if (x < 0 || y < 0 || x >= contentWidth || y >= contentHeight) return null;
    return [x * camera[4] / contentWidth, y * camera[5] / contentHeight];
  }
  const primaryClick = (event: MouseEvent) => {
    if (disposed || terminal || busy || needsRefresh || !output || event.defaultPrevented || event.altKey ||
        event.button !== 0 || event.buttons !== 0 || event.detail !== 1) return;
    const coordinates = clickCoordinates(event);
    if (!coordinates) return;
    const mode = event.ctrlKey || event.metaKey ? 2 : event.shiftKey ? 1 : 0;
    try {
      const accepted = admit({ operation: 1, coordinates, mode }, "select");
      event.preventDefault(); surface.focus({ preventScroll: true });
      void accepted.catch(() => {});
    } catch (error) { report(error); }
  };
  const previousPage = () => { if (!disposed && !busy && !needsRefresh && page > 0) void run({ operation: 17, page: page - 1, pageSize: 50 }, "render", camera, page - 1).catch(() => {}); };
  const nextPage = () => { if (!disposed && !busy && !needsRefresh && output && (page + 1) * 50 < output.companion.total) void run({ operation: 17, page: page + 1, pageSize: 50 }, "render", camera, page + 1).catch(() => {}); };
  painter.canvas.addEventListener("click", primaryClick);
  surface.addEventListener("keydown", keyDown); previous.addEventListener("click", previousPage); next.addEventListener("click", nextPage);
  setBusy(true);
  const ready = (async () => {
    const ack = await lane.execute("open", opening!); opening = null; decodeGraphSessionAck(ack);
    if (disposed) throw new XygWasmError("XYG_WASM_DISPOSED", "Graph attachment was disposed");
    return await request({ operation: 21, camera, page: 0, pageSize: 50 });
  })().then(value => { if (!disposed) dispatch("render", value); return value; }).catch(async error => { report(error); await dispose(); throw error; }).finally(() => setBusy(false));
  // Do not await ready in cleanup: its failure path itself awaits disposal.
  function dispose(): Promise<void> {
    if (disposal) return disposal;
    disposed = true;
    painter.canvas.removeEventListener("click", primaryClick);
    surface.removeEventListener("keydown", keyDown); previous.removeEventListener("click", previousPage); next.removeEventListener("click", nextPage);
    for (const [name, value] of surfaceAttributes) { if (value === null) surface.removeAttribute(name); else surface.setAttribute(name, value); }
    // Suppress DOM/events immediately, drain commands before CLOSE and release.
    output = null; opening = null;
    painter.dispose(); surface.remove(); companion.remove();
    disposal = lane.close(); return disposal;
  }
  return Object.freeze({ ready, snapshot, dispose,
    refreshRender(nextCamera?: XygWasmGraphCamera) {
      const target = nextCamera === undefined ? camera : cameraCopy(nextCamera);
      return run({ operation: 21, camera: target, page, pageSize: 50 }, "render", target);
    },
  });
}
