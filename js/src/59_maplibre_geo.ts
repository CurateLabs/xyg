import { hydrateWasmPainter, type XygWasmSceneView } from "./48_wasm_scene";
import type { XygWasmScenePaint } from "./47_wasm";
import { withExternalGLState } from "./43_external_gl";

/** Structural shell interface: MapLibre is supplied by the application and is
 * never imported, downloaded, or configured by the XYG client. */
export interface GeoMapShell {
  getCanvas(): HTMLCanvasElement;
  /** Container for Rust-final SVG/DOM labels and legends. */
  getContainer?(): HTMLElement;
  triggerRepaint(): void;
  on?(type: string, listener: (event: unknown) => void): unknown;
  off?(type: string, listener: (event: unknown) => void): unknown;
}

export interface MapLibreGeoLayerOptions {
  id: string;
  prepared: XygWasmScenePaint;
  /** Forward shell camera events to the application's Rust/WASM camera seam. */
  onCameraEvent?: (event: unknown) => void;
}

/** MapLibre v6.13 custom-layer lifecycle for an already prepared Rust Scene.
 * Geometry/style/pick identifiers are consumed by the existing XYG painter.
 * The shell provides scheduling and its current framebuffer only. */
export function createMapLibreGeoLayer(options: MapLibreGeoLayerOptions) {
  if (!options || typeof options.id !== "string" || !options.id) throw new TypeError("A geographic layer id is required");
  let prepared = options.prepared;
  let map: GeoMapShell | null = null, gl: WebGL2RenderingContext | null = null;
  let view: XygWasmSceneView | null = null;
  let disposed = false;
  const holder = document.createElement("div");
  holder.style.cssText="position:absolute;inset:0;pointer-events:none;";
  holder.dataset.xyGeoDecorations=options.id;
  const cameraEvent = (event: unknown) => options.onCameraEvent?.(event);
  const viewportMatches = () => view && gl && view.canvas.width === gl.drawingBufferWidth
    && view.canvas.height === gl.drawingBufferHeight;
  const releaseView = () => {
    const previous = view;
    view = null;
    if (!previous) return;
    if (!gl || gl.isContextLost()) previous.destroy();
    else withExternalGLState(gl, () => previous.destroy());
  };
  const replace = (next: XygWasmScenePaint) => {
    if (!gl || !map || gl.isContextLost()) { prepared = next; return; }
    const width = new DataView(next.painter).getFloat32(24, true);
    const height = new DataView(next.painter).getFloat32(28, true);
    const ratio = gl.drawingBufferWidth / width;
    // CSS-to-device rounding can differ by less than one pixel on each axis.
    if (!(ratio > 0 && Number.isFinite(ratio)) || Math.abs(gl.drawingBufferHeight - height * ratio) > 1) {
      throw new RangeError("The Rust geographic viewport must match the shell drawing buffer");
    }
    const nextHolder = document.createElement("div");
    const candidate = withExternalGLState(gl, () => hydrateWasmPainter(nextHolder, next,
      { workerPrepareMs: 0 }, { gl, pixelRatio: ratio, requestRepaint: () => map?.triggerRepaint() }));
    // Scheduling is an application callback and may throw. Keep the prior
    // Scene alive until it succeeds, and release the uncommitted candidate.
    try { map.triggerRepaint(); }
    catch (error) {
      withExternalGLState(gl, () => candidate.destroy());
      throw error;
    }
    releaseView();
    holder.replaceChildren(nextHolder);
    prepared = next;
    view = candidate;
  };
  const lost = () => releaseView();
  const restored = () => { if (map && !disposed) replace(prepared); };
  const detach = () => {
    if (!map) return;
    map.getCanvas().removeEventListener("webglcontextlost", lost);
    map.getCanvas().removeEventListener("webglcontextrestored", restored);
    map.off?.("move", cameraEvent);
    releaseView();
    holder.replaceChildren(); holder.remove();
    map = null; gl = null;
  };
  return {
    id: options.id,
    type: "custom" as const,
    renderingMode: "2d" as const,
    onAdd(owner: GeoMapShell, context: WebGL2RenderingContext) {
      if (disposed || map) throw new Error("The geographic layer is disposed or already mounted");
      if (!context || typeof context.createVertexArray !== "function" || context.canvas !== owner.getCanvas()) {
        throw new TypeError("A shell-owned WebGL2 canvas is required");
      }
      map = owner; gl = context;
      try {
        replace(prepared);
        const container=owner.getContainer?.() ?? owner.getCanvas().parentElement;
        if (container) container.appendChild(holder);
        owner.getCanvas().addEventListener("webglcontextlost", lost);
        owner.getCanvas().addEventListener("webglcontextrestored", restored);
        owner.on?.("move", cameraEvent);
      } catch (error) { detach(); throw error; }
    },
    // v6.13 render(gl, options): no matrix assumptions or geometry lowering.
    render(context: WebGL2RenderingContext, _renderOptions?: unknown) {
      if (context !== gl) throw new Error("The geographic layer received a different context");
      if (!view || !gl || gl.isContextLost() || !viewportMatches()) return;
      withExternalGLState(gl, () => view!._renderGlFrame());
    },
    setPrepared(next: XygWasmScenePaint) {
      if (disposed) throw new Error("The geographic layer is disposed");
      replace(next);
    },
    /** Existing direct-point picking only; feature-policy interaction is Rust-owned. */
    pick(x: number, y: number): bigint | null {
      if (!view || !gl || gl.isContextLost() || !viewportMatches()) return null;
      return withExternalGLState(gl, () => {
        const hit = view!._pickAt(x, y);
        if (!hit) return null;
        const trace = view!.gpuTraces.findIndex((item) => item.trace.id === hit.trace);
        return view!.sceneStableId(trace, hit.index);
      });
    },
    onRemove() { detach(); },
    dispose() { detach(); disposed = true; },
  };
}
