import { bytesToSpan, decodeFrame, payloadBuffers, payloadCoherent } from "./00_header";
import { ChartView } from "./50_chartview";
import { MARK_KINDS, markOf } from "./55_marks";
import { createXygWasmWorker, XygWasmError, XygWasmWorker } from "./47_wasm";
export { encodeWasmDashboardPlan, decodeWasmDashboardPlan, planWasmDashboardResources, applyWasmDashboardResourceBudget, watchWasmDashboardResourceBudget } from "./49_wasm_dashboard";
export type { XygWasmDashboardResource, XygWasmDashboardAdmissionController } from "./49_wasm_dashboard";
import {
  attachWasmTicks,
  decodeWasmTickBatch,
  encodeWasmTickBatch,
  resolveWasmTicks,
  XygWasmTicksHandle,
} from "./49_wasm_ticks";
export type {
  XygWasmTickAxisRequest,
  XygWasmTickAxisResult,
  XygWasmTickBatchRequest,
  XygWasmTickBatchResult,
  XygWasmTickFamily,
  XygWasmTickProvenance,
  XygWasmTicksDiagnostics,
  XygWasmTicksOptions,
} from "./49_wasm_ticks";
import { hydrateWasmPainter, renderWasmScene } from "./48_wasm_scene";
import {
  compilePrepareWasmScene,
  compileWasmScene,
  encodeWasmColumns,
  renderWasmColumns,
} from "./49_wasm_columns";
import { frameWasmChart, renderWasmChart } from "./49_wasm_chart";
import {
  aggregateWasmBin2d,
  decodeWasmAggregateOutput,
  encodeWasmAggregate,
} from "./49_wasm_aggregate";
import { attachInlineStandaloneWasmDensity, attachStandaloneWasmDensity, attachWasmDensity, provisionKernelWasmDensity, XygWasmDensityHandle } from "./49_wasm_density";
import { XygWasmTemporalController } from "./49_wasm_temporal";
import { XygWasmTemporalGraph, decodeWasmTemporalGraphFrame, encodeWasmTemporalGraphCreate, encodeWasmTemporalGraphFrame } from "./49_wasm_temporal_graph";
import { decodeWasmGraphCheckpoint, encodeWasmCose, layoutWasmCose } from "./49_wasm_graph";
import {
  compilePrepareWasmSemanticGraph,
  compileWasmSemanticGraph,
  encodeWasmSemanticGraph,
  renderWasmSemanticGraph,
} from "./49_wasm_semantic_graph";
import { decodeWasmCompoundTransition, encodeWasmCompoundTransition, transitionWasmCompound } from "./49_wasm_compound";
// Prototype-augmentation modules: imported for their side effect of attaching
// methods to ChartView.prototype. Every entry point must load them before the
// first ChartView is constructed.
import "./51_annotations";
import "./52_tooltip";
import "./53_interaction";
import "./54_kernel";
import "./56_animation";
import "./57_viewstate";
// Optional graph enhancement (CSR neighborhood dim on node hover). Geometry
// for graph charts is ordinary segments + scatter via MARK_KINDS; omitting
// this import still paints every mark including graph wire traces.
import "./58_graph";

// ---------------------------------------------------------------------------
// Entry points
// ---------------------------------------------------------------------------

export function render({ model, el }) {
  const spec = model.get("spec");
  const buffer = payloadBuffers(spec, model.get("buffers"));
  const comm = {
    send: (msg) => model.send(msg),
    // Read the live spec: appends re-sync it, and the transport flag must
    // survive them (it is re-applied kernel-side on every append).
    wantsViewChange: () => model.get("spec")?.interaction?._transport_view_change === true,
    onMessage: (cb) => {
      const handler = (content, buffers) => cb(content, buffers);
      model.on("msg:custom", handler);
      return () => model.off?.("msg:custom", handler);
    },
  };
  const view = new ChartView(el, spec, buffer, comm);
  // Streaming append rides the spec+buffers trait update itself (§29): one
  // comm message per tick that doubles as notebook-reopen state. A fresh
  // render above already painted the streamed state, so only a *subsequent*
  // advance of `spec.append.seq` applies as an incremental append.
  //
  // Hosts are not guaranteed to set the two traits atomically: one change
  // event may fire between the spec write and the buffers write (in either
  // order). Both events funnel here, a torn pair (a column that no longer
  // fits its buffer) defers without consuming the seq, and applied state is
  // keyed on (seq, buffers identity) — so if a same-length torn pair slips
  // past the fit check, the buffers' own change event re-applies and repairs.
  const applied = { seq: spec.append?.seq ?? null, buffers: model.get("buffers") };
  const onAppendState = () => {
    const nextSpec = model.get("spec");
    const tag = nextSpec?.append;
    if (!tag) return;
    const nextBuffers = model.get("buffers");
    if (tag.seq === applied.seq && nextBuffers === applied.buffers) return;
    if (!payloadCoherent(nextSpec, nextBuffers)) return; // torn: wait for the pair
    applied.seq = tag.seq;
    applied.buffers = nextBuffers;
    view._applyAppend({ type: "append", affected: tag.affected, spec: nextSpec }, nextBuffers);
  };
  model.on("change:spec", onAppendState);
  model.on("change:buffers", onAppendState);
  return () => {
    model.off?.("change:spec", onAppendState);
    model.off?.("change:buffers", onAppendState);
    view.destroy();
  };
}

/** Standalone (static HTML export — no kernel). Retains typed CPU views of
 * shipped channels so hover can read approximate values without a kernel (§37). */
export function renderStandalone(el, spec, arrayBuffer) {
  const buffer = bytesToSpan(arrayBuffer);
  const view = new ChartView(el, spec, buffer, null);
  const column = (idx) => view._columnView(buffer, spec.columns[idx]);
  for (const g of view.gpuTraces) {
    if (markOf(g.trace.kind).retainCpu && g.tier !== "density") {
      // Ribbon build retains its six specialized geometry columns directly in
      // `_cpuRibbon`; it has no generic trace.x/trace.y wire fields. Trying to
      // load those nonexistent fields aborts standalone hydration after the
      // first paint and leaves hover without a usable ChartView.
      if (g._cpuRibbon) continue;
      if (!Number.isInteger(g.trace.x) || !Number.isInteger(g.trace.y)) continue;
      g._cpu = {
        x: column(g.trace.x),
        y: column(g.trace.y),
        xMeta: g.xMeta,
        yMeta: g.yMeta,
      };
      if (g.trace.color && Number.isInteger(g.trace.color.buf)) {
        g._cpu.color = column(g.trace.color.buf);
      }
      if (g.trace.size && Number.isInteger(g.trace.size.buf)) {
        g._cpu.size = column(g.trace.size.buf);
      }
    }
  }
  // `to_html()` embeds the checked bytes plus a classic IIFE only for density
  // documents. This establishes the Rust-owned path without a module URL or
  // network fetch. An unavailable/invalid artifact deliberately leaves the
  // existing Rust-authored overview in place; it never starts a JavaScript
  // aggregation fallback.
  const inline = (globalThis as any).__xygInlineWasm;
  const observer = (globalThis as any).__xygStandaloneObserver;
  // This opaque capability exists only when CDP has installed the evidence
  // observer. Normal self-contained exports do not expose failure controls.
  const evidenceCapability = typeof observer === "function"
    ? `xyg-evidence-${crypto.getRandomValues(new Uint32Array(6)).join("-")}` : undefined;
  let densityHandle: XygWasmDensityHandle | null = null;
  const attachInline = async () => {
    if (!inline) return null;
    const handle = await attachInlineStandaloneWasmDensity(view, { inline, delay: 0, evidenceCapability });
    densityHandle = handle;
    return handle;
  };
  const densityTraces = view.gpuTraces.filter((g: any) => g.tier === "density");
  const retainedDensity = densityTraces.some((g: any) => g.sampleOverlay?._cpu);
  if (densityTraces.length && !inline) {
    view._reportDensityNoRefinement?.("XYG_WASM_UNAVAILABLE", "self-contained Rust/WASM density artifact is unavailable");
  } else if (densityTraces.length && !retainedDensity) {
    view._reportDensityNoRefinement?.("XYG_WASM_SOURCE_UNAVAILABLE", "density refinement requires a retained typed source");
  } else if (inline && retainedDensity) {
    void attachInline().then((handle) => {
      if (!handle) return;
      // The exported document has no kernel viewport message to trigger the
      // first refinement. Start the initial Rust-owned grid explicitly.
      handle.schedule(view.view, { delay: 0, force: true });
      if (typeof observer === "function") observer({ phase: "density_ready", diagnostics: handle.diagnostics() });
    }).catch((cause) => {
      const code = cause instanceof XygWasmError ? cause.code : "XYG_WASM_UNAVAILABLE";
      const message = cause instanceof Error ? cause.message : "inline WASM density provisioning failed";
      view._reportDensityNoRefinement?.(code, message);
      if (typeof observer === "function") observer({ phase: "density_no_refinement", code, message });
    });
  }
  // Test/host observability only: no runtime policy is selected from this
  // hook. It lets strict-CSP file evidence distinguish successful attachment
  // from a later density worker failure.
  if (typeof observer === "function") observer({ phase: "attached", inline: !!inline, view });
  if (typeof observer === "function") (globalThis as any).__xygStandaloneDensityControl = {
    home: () => {
      const revision = densityHandle?.schedule(view.view0, { delay: 0, force: true });
      observer({ phase: "home", revision: revision || null }); return revision;
    },
    zoom: () => {
      const revision = densityHandle?.schedule({ ...view.view, x0: view.view.x0 + 1, x1: view.view.x1 - 1 }, { delay: 0, force: true });
      observer({ phase: "zoom", revision: revision || null });
      if (revision) observer({ phase: "revision", revision }); return revision;
    },
    supersede: () => {
      const oldRevision = densityHandle?.schedule(
        { ...view.view, x0: view.view.x0 + 0.5, x1: view.view.x1 - 0.5 },
        { delay: 0, force: true },
      );
      const revision = densityHandle?.schedule(
        { ...view.view, x0: view.view.x0 + 1, x1: view.view.x1 - 1 },
        { delay: 0, force: true },
      );
      observer({ phase: "superseded", oldRevision: oldRevision || null, revision: revision || null });
      return { oldRevision, revision };
    },
    diagnostics: () => densityHandle?.diagnostics() || null,
    payload: () => {
      const density = densityTraces[0]?.density;
      const bytes = (density?.grid?.byteLength || 0) + (density?.rgba?.byteLength || 0);
      return { bytes, xRange: density?.xRange || null, yRange: density?.yRange || null };
    },
    cancel: () => {
      densityHandle?.schedule({ ...view.view, x0: view.view.x0 + 1, x1: view.view.x1 - 1 }, { delay: 100 });
      densityHandle?.cancel(); observer({ phase: "cancelled" });
    },
    malformed: async () => {
      try { await densityHandle?.evidenceLifecycle("malformed"); }
      catch (cause) { observer({ phase: "malformed", code: cause instanceof XygWasmError ? cause.code : "XYG_WASM_WORKER_ERROR" }); return; }
      throw new Error("malformed lifecycle evidence unexpectedly succeeded");
    },
    resource: async () => {
      try { await densityHandle?.evidenceLifecycle("resource"); }
      catch (cause) { observer({ phase: "resource", code: cause instanceof XygWasmError ? cause.code : "XYG_WASM_WORKER_ERROR" }); return; }
      throw new Error("resource lifecycle evidence unexpectedly succeeded");
    },
    trap: async () => {
      try { await densityHandle?.evidenceLifecycle("trap"); }
      catch (cause) {
        observer({ phase: "trap", code: cause instanceof XygWasmError ? cause.code : "XYG_WASM_WORKER_ERROR" });
        await densityHandle?.dispose(); densityHandle = null;
        const recovered = await attachInline();
        recovered?.schedule(view.view, { delay: 0, force: true });
        observer({ phase: "recovered", diagnostics: recovered?.diagnostics() || null }); return;
      }
      throw new Error("trap lifecycle evidence unexpectedly succeeded");
    },
    dispose: async () => { await densityHandle?.dispose(); densityHandle = null; observer({ phase: "disposed" }); },
  };
  return view;
}

// Public API. The ESM bundle (static/index.js, anywidget's `_esm`) re-exports
// these directly; the IIFE bundle (static/standalone.js) exposes the same
// namespace as `window.xy`.
export {
  decodeFrame,
  ChartView,
  MARK_KINDS,
  markOf,
  createXygWasmWorker,
  XygWasmError,
  XygWasmWorker,
  attachWasmTicks,
  decodeWasmTickBatch,
  encodeWasmTickBatch,
  resolveWasmTicks,
  XygWasmTicksHandle,
  renderWasmScene,
  hydrateWasmPainter,
  encodeWasmColumns,
  compileWasmScene,
  compilePrepareWasmScene,
  renderWasmColumns,
  frameWasmChart,
  renderWasmChart,
  encodeWasmAggregate,
  decodeWasmAggregateOutput,
  aggregateWasmBin2d,
  attachWasmDensity,
  attachInlineStandaloneWasmDensity,
  attachStandaloneWasmDensity,
  provisionKernelWasmDensity,
  XygWasmDensityHandle,
  XygWasmTemporalController,
  XygWasmTemporalGraph,
  decodeWasmTemporalGraphFrame,
  encodeWasmTemporalGraphCreate,
  encodeWasmTemporalGraphFrame,
  encodeWasmCose,
  decodeWasmGraphCheckpoint,
  layoutWasmCose,
  encodeWasmSemanticGraph,
  compileWasmSemanticGraph,
  compilePrepareWasmSemanticGraph,
  renderWasmSemanticGraph,
  encodeWasmCompoundTransition,
  decodeWasmCompoundTransition,
  transitionWasmCompound,
};
export type { XygWasmAggregateTaskOptions } from "./47_wasm";
export type {
  XygStandaloneWasmDensityOptions,
  XygWasmDensityInput,
  XygWasmDensityOptions,
  XygWasmDensityDiagnostics,
} from "./49_wasm_density";
export type {
  XygTemporalControllerOptions,
  XygTemporalEvent,
  XygTemporalResult,
  XygTemporalState,
} from "./49_wasm_temporal";
export type { XygWasmCoseOptions, XygWasmGraphCheckpoint, XygWasmGraphRequest } from "./49_wasm_graph";
export type { XygTemporalPlane, XygWasmTemporalGraphBinding, XygWasmTemporalGraphFrame } from "./49_wasm_temporal_graph";
export type { XygWasmSemanticGraphInput } from "./49_wasm_semantic_graph";
export type { XygCompoundAction, XygWasmCompoundTransitionInput, XygWasmCompoundTransitionResult } from "./49_wasm_compound";
export default { render, decodeFrame };
