/** Browser event/DOM adapter. Rust owns feature hits, state transitions and paint. */
import { captureGesturePointer } from "./50_chartview";
import { XygWasmWorker } from "./47_wasm";
import { hydrateWasmPainter, type XygWasmSceneView } from "./48_wasm_scene";
import { encodeGeoCatalogRequest, decodeGeoCatalogResponse, type XygGeoCatalogRequest,
  type XygGeoInteractionEvent } from "./61_geo_catalog";
import type { XygGeoCamera } from "./49_wasm_geoviewport";
import { RetainedGeographicController, type RetainedGeographicChartOptions } from './64_geo_retained_controller';

type Output = ReturnType<typeof decodeGeoCatalogResponse>;
export interface GeographicChartOptions {
  el: HTMLElement;
  worker: XygWasmWorker;
  catalog: XygGeoCatalogRequest;
  /** An application-owned MapLibre custom layer; no map or provider is created. */
  layer?: { setPrepared(prepared: Awaited<ReturnType<XygWasmWorker["prepareScene"]>["result"]>): void };
  pointerSurface?: HTMLElement;
  onChange?: (output: Output) => void;
  onError?: (error: unknown) => void;
}

export class XygGeographicChart {
  /** Retained data uses the same geographic chart surface and Rust painter. */
  static async fromSource(options:RetainedGeographicChartOptions):Promise<RetainedGeographicController> {
    await options.worker.acquireGeoTransport();
    return new RetainedGeographicController(options);
  }
  readonly ready: Promise<Output>;
  private catalog: XygGeoCatalogRequest;
  private output: Output | null = null;
  private view: XygWasmSceneView | null = null;
  private disposed = false;
  private chain: Promise<unknown> = Promise.resolve();
  private active: { cancel(): void } | null = null;
  private readonly paint = document.createElement("div");
  private readonly companion = document.createElement("div");
  private page = 0;
  private readonly surface: HTMLElement;
  private readonly surfaceAttributes: Map<string, string | null>;
  private brushPointer: number | null = null;
  private brushCapture: ReturnType<typeof captureGesturePointer> | null = null;
  private readonly captureListeners = new Map<(event: PointerEvent) => void, HTMLElement>();
  private readonly captureContext = {
    _listen: (owner: HTMLElement, type: string, handler: (event: PointerEvent) => void) => {
      owner.addEventListener(type, handler as EventListener);
      this.captureListeners.set(handler, owner);
      return handler;
    },
    _unlisten: (handler: (event: PointerEvent) => void) => {
      this.captureListeners.get(handler)?.removeEventListener("lostpointercapture", handler as EventListener);
      this.captureListeners.delete(handler);
    },
  };
  private hover: [number, number] | null = null;
  private hoverRunning = false;
  private brushStart: [number, number] | null = null;
  constructor(private readonly options: GeographicChartOptions) {
    if (!(options.el instanceof HTMLElement) || !(options.worker instanceof XygWasmWorker)) {
      throw new TypeError("A geographic container and Worker are required");
    }
    this.catalog = { ...options.catalog, layers: options.catalog.layers.map(layer => ({...layer})) };
    this.surface = options.pointerSurface || this.paint;
    this.surfaceAttributes = new Map(["tabindex", "role", "aria-label"].map(name => [name, this.surface.getAttribute(name)]));
    this.surface.tabIndex = 0;
    this.surface.setAttribute("role", "application");
    this.surface.setAttribute("aria-label", "Geographic analysis. Arrow keys move feature focus; Enter selects. Shift drag brushes.");
    this.companion.setAttribute("aria-label", "Geographic features");
    options.el.append(this.paint, this.companion);
    this.surface.addEventListener("pointermove", this.pointerMove);
    this.surface.addEventListener("pointerdown", this.pointerDown);
    this.surface.addEventListener("pointerup", this.pointerUp);
    this.surface.addEventListener("pointercancel", this.cancelBrush);
    this.surface.addEventListener("keydown", this.keyDown);
    this.ready = this.enqueue().catch(error => { this.dispose(); throw error; });
  }
  private coordinates(event: PointerEvent): [number, number] {
    const box = this.surface.getBoundingClientRect();
    return [event.clientX - box.left, event.clientY - box.top];
  }
  private report(error: unknown) {
    // Observer callbacks cannot turn an accepted Rust transition into a failed operation.
    try { this.options.onError?.(error); } catch { /* Observer isolation. */ }
  }
  private cancelBrush = (event?: PointerEvent) => {
    if (event && event.pointerId !== this.brushPointer) return;
    const capture = this.brushCapture;
    this.brushCapture = null; this.brushStart = null; this.brushPointer = null;
    capture?.release();
  };
  private submit(event: XygGeoInteractionEvent) {
    void this.enqueue(event).catch(error => { if (!this.disposed) this.report(error); });
  }
  private pointerMove = (event: PointerEvent) => {
    if (this.brushPointer !== null) {
      if (event.pointerId === this.brushPointer) this.brushCapture?.guard(event);
      return;
    }
    if (!this.brushStart) {
      this.hover = this.coordinates(event);
      if (!this.hoverRunning) void this.drainHover();
    }
  };
  private async drainHover() {
    this.hoverRunning = true;
    try {
      while (this.hover && !this.disposed) {
        const coordinates = this.hover; this.hover = null;
        try { await this.enqueue({operation: 1, coordinates}); }
        catch (error) { if (!this.disposed) this.report(error); }
      }
    } finally { this.hoverRunning = false; }
  }
  private pointerDown = (event: PointerEvent) => {
    if (this.brushPointer !== null) return;
    if (event.button === 0 && event.shiftKey) {
      this.brushStart = this.coordinates(event);
      this.brushPointer = event.pointerId;
      this.brushCapture = captureGesturePointer(this.captureContext, this.surface, event, this.cancelBrush);
    }
  };
  private pointerUp = (event: PointerEvent) => {
    if (event.button !== 0 || (this.brushPointer !== null && event.pointerId !== this.brushPointer)) return;
    const mode = event.ctrlKey || event.metaKey ? 2 : 0;
    const end = this.coordinates(event);
    if (this.brushStart) {
      if (!this.brushCapture?.guard(event)) return;
      const start = this.brushStart; this.cancelBrush();
      this.submit({operation: 3, mode, coordinates: [Math.min(start[0], end[0]), Math.min(start[1], end[1]), Math.max(start[0], end[0]), Math.max(start[1], end[1])]});
    } else this.submit({operation: 2, mode, coordinates: end});
  };
  private keyDown = (event: KeyboardEvent) => {
    if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) {
      event.preventDefault(); this.submit({operation: 5, delta: ["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 1});
    } else if ((event.key === "Enter" || event.key === " ") && this.output?.focus) {
      event.preventDefault(); this.submit({operation: 7, mode: event.ctrlKey || event.metaKey ? 2 : 0, ...this.output.focus});
    } else if (event.key === "Escape") { event.preventDefault(); this.submit({operation: 4}); }
  };
  private enqueue(event?: XygGeoInteractionEvent, camera?: XygGeoCamera): Promise<Output> {
    if (this.disposed) return Promise.reject(new Error("Geographic chart is disposed"));
    const operation = this.chain.then(async () => {
      if (this.disposed) throw new Error("Geographic chart is disposed");
      const transition = event || (camera && this.output?.focus ? {operation: 6, ...this.output.focus} : undefined);
      const input = {...this.catalog, camera: camera || this.catalog.camera, event: transition};
      await this.options.worker.ready;
      if (this.disposed) throw new Error("Geographic chart is disposed");
      const task = this.options.worker.geoCatalogCompile(encodeGeoCatalogRequest(input));
      this.active = task;
      const result = decodeGeoCatalogResponse(await task.result);
      if (this.disposed) throw new Error("Geographic chart is disposed");
      const preparation = this.options.worker.prepareScene(new Uint8Array(result.scene));
      this.active = preparation;
      const prepared = await preparation.result;
      if (this.disposed) throw new Error("Geographic chart is disposed");
      if (this.options.layer) this.options.layer.setPrepared(prepared);
      else {
        const holder = document.createElement("div");
        const candidate = hydrateWasmPainter(holder, prepared);
        this.view?.destroy(); this.view = candidate; this.paint.replaceChildren(holder);
      }
      this.catalog = {...input, event: undefined, camera: result.camera,
        layers: input.layers.map((layer, i) => ({...layer, stateFlags: result.layers[i].stateFlags.slice()}))};
      this.output = result;
      this.active = null;
      this.renderCompanion();
      try { this.options.onChange?.(result); } catch (error) { this.report(error); }
      return result;
    });
    this.chain = operation.catch(() => {});
    return operation;
  }
  /** Forward an explicit shell camera snapshot; no browser projection is performed. */
  updateCamera(camera: XygGeoCamera): Promise<Output> { return this.enqueue(undefined, camera); }
  interact(event: XygGeoInteractionEvent): Promise<Output> { return this.enqueue(event); }
  snapshot(): Output | null { return this.output; }
  private renderCompanion() {
    const output = this.output!;
    const activeKey = (document.activeElement as HTMLElement | null)?.dataset.xyFeatureAction;
    // Render at most 50 rows; paging exposes all Rust-admitted valid, nonhidden rows.
    let total = 0;
    for (const layer of output.layers) for (let i = 0; i < layer.validity.length; i++) {
      if (layer.validity[i] && !(layer.stateFlags[i] & 1)) total++;
    }
    this.page = Math.min(this.page, Math.max(0, Math.ceil(total / 50) - 1));
    const table = document.createElement("table");
    const caption = document.createElement("caption");
    caption.textContent = `Geographic features, ${total} selectable source rows, page ${this.page + 1}`;
    table.append(caption);
    const head = table.createTHead().insertRow();
    for (const text of ["Layer", "Feature", "Source row", "Selected", "Focus", "Select"]) {
      const cell = document.createElement("th"); cell.scope = "col"; cell.textContent = text; head.append(cell);
    }
    const body = table.createTBody(); let ordinal = 0;
    for (const layer of output.layers) for (let i = 0; i < layer.validity.length; i++) {
      if (!layer.validity[i] || layer.stateFlags[i] & 1) continue;
      const index = ordinal++;
      if (index < this.page * 50 || index >= (this.page + 1) * 50) continue;
      const row = body.insertRow();
      for (const text of [String(layer.layerId), String(layer.featureIds[i]), String(i), layer.stateFlags[i] & 2 ? "yes" : "no"]) row.insertCell().textContent = text;
      for (const [name, operation] of [["Focus", 6], ["Select", 7]] as const) {
        const button = document.createElement("button"); button.type = "button"; button.textContent = name;
        button.dataset.xyFeatureAction = `${layer.layerId}:${layer.featureIds[i]}:${i}:${operation}`;
        button.setAttribute("aria-label", `${name} layer ${layer.layerId}, feature ${layer.featureIds[i]}, source row ${i}`);
        button.onclick = () => this.submit({operation, layerId: layer.layerId, featureId: layer.featureIds[i], ...(operation === 7 ? {mode: 2} : {})});
        row.insertCell().append(button);
      }
    }
    const navigation = document.createElement("div");
    for (const [text, delta] of [["Previous", -1], ["Next", 1]] as const) {
      const button = document.createElement("button"); button.type = "button"; button.textContent = text;
      button.disabled = delta < 0 ? this.page === 0 : (this.page + 1) * 50 >= total;
      button.onclick = () => { this.page += delta; this.renderCompanion(); }; navigation.append(button);
    }
    this.companion.replaceChildren(table, navigation);
    if (activeKey) for (const button of this.companion.querySelectorAll("button")) {
      if (button.dataset.xyFeatureAction === activeKey) { button.focus({preventScroll: true}); break; }
    }
  }
  dispose() {
    if (this.disposed) return;
    this.disposed = true; this.hover = null; this.active?.cancel(); this.active = null;
    this.surface.removeEventListener("pointermove", this.pointerMove);
    this.surface.removeEventListener("pointerdown", this.pointerDown);
    this.surface.removeEventListener("pointerup", this.pointerUp);
    this.surface.removeEventListener("pointercancel", this.cancelBrush);
    this.cancelBrush();
    for (const [name, value] of this.surfaceAttributes) {
      if (value === null) this.surface.removeAttribute(name); else this.surface.setAttribute(name, value);
    }
    this.surface.removeEventListener("keydown", this.keyDown);
    this.view?.destroy(); this.view = null; this.paint.remove(); this.companion.remove();
  }
}
