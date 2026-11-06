/** Native force checkpoints use the ordinary notebook painter and channel. */
import { payloadBuffers } from "./00_header";
import { ChartView } from "./50_chartview";

export function renderGraphHost({ model, el, attachTicks }) {
  const bootstrap = model.get("spec"), instance = bootstrap.instance;
  const epoch = Array.from(crypto.getRandomValues(new Uint32Array(4)), value => value.toString(16).padStart(8, "0")).join("");
  el.dataset.graphInstance = instance;
  const status = document.createElement("div"); status.setAttribute("aria-live", "polite");
  status.textContent = "Laying out graph"; el.append(status);
  let revision = 0, disposed = false, view: ChartView | null = null, frame: number | null = null;
  let selection: { content: any; buffers: any } | null = null;
  const rowSpace = () => (view?._graphs || []).flatMap(g => [g.ids, g.source_edge_ids,
    ...["member_of", "render_edge_index"].map(key => view!._graphMetaArray(g, key))]);
  const sameRows = (a, b) => a.length === b.length && a.every((values, i) =>
    values == null ? b[i] == null : b[i] != null && values.length === b[i].length && values.every((v, j) => v === b[i][j]));
  let selectedRows: any[] = [];
  const picks = new Set<string>();
  let selections = 0;
  let pendingFrame: { content: any; buffers: any } | null = null;
  const listeners = new Set<(content: any, buffers: any) => void>();
  const send = (content, buffers = []) => {
    if (revision === 0 && !["graph_mount", "graph_dispose"].includes(content.type)) return;
    if (content.type === "select" || content.type === "select_polygon" || content.type === "select_clear") selections++;
    if (content.type === "pick") picks.add(`${revision}:${content.seq}`);
    model.send({ ...content, graph_instance: instance, graph_epoch: epoch, graph_revision: revision }, {}, buffers);
  };
  const comm = {
    send,
    wantsViewChange: () => view?.spec?.interaction?._transport_view_change === true,
    onMessage: cb => { listeners.add(cb); return () => listeners.delete(cb); },
  };
  function refresh(spec, buffers, affected = spec.traces.map(t => t.id)) {
      const previousRows = rowSpace(), hover = view._hoverTarget;
      // The generic refresh replaces GPU trace objects. Release transient
      // handles before it draws; retain an index only when Rust's ordered
      // row space survives, then bind it to the new GPU object.
      view._hoverTarget = null; view._graphNbrKey = null; view._graphNbrGpu = null;
      view._applyAppend({ spec, affected }, buffers);
      if (!sameRows(previousRows, rowSpace())) {
        view._hoverId = null; view._a11yPointIndex = -1; view._hideTooltip?.();
      } else if (hover) {
        const next = view.gpuTraces.find(g => g.trace.id === hover.trace);
        if (next && hover.index >= 0 && hover.index < next.n && !next._legendHidden) {
          view._hoverTarget = { ...hover, g: next }; view._drawKeepPick();
        }
      }
      // Same generic canonical trace-row contract as selection_rows; the
      // native compiler emits the routing/membership planes for every frame.
      // Revoke a cached mask if Rust emitted a different ordered row space.
      // This compares native planes; it never guesses or remaps identities.
      if (selection && !sameRows(selectedRows, rowSpace())) selection = null;
      if (selection) { view._applySelectionBuffers(selection.content, selection.buffers); view.draw(); }
  }
  function message(content, buffers) {
    if (disposed || content.graph_instance !== instance || content.graph_epoch !== epoch) return;
    if (content.type === "graph_failed") { status.textContent = "XYG_GRAPH_WORKER_FAILED"; return; }
    if (content.type !== "graph_frame") {
      if (content.graph_revision === revision) {
        if (content.type === "append") {
          refresh(content.spec, buffers, content.affected);
          const saved = model.get("spec");
          model.set({ spec: { ...saved, graph_snapshot: { ...saved.graph_snapshot, spec: content.spec } }, buffers }, { silent: true });
          return;
        }
        if (content.type === "selection" || content.type === "selection_rows") {
          selection = { content, buffers }; selectedRows = rowSpace();
        }
        if (content.type === "state_patch" && content.state?.selection === null) selection = null;
        for (const cb of listeners) cb(content, buffers);
        if (content.type === "selection") selections = Math.max(0, selections - 1);
        if (content.type === "pick_result") picks.delete(`${revision}:${content.seq}`);
        if (!picks.size && !selections && pendingFrame) { const next = pendingFrame; pendingFrame = null; message(next.content, next.buffers); }
      }
      return;
    }
    if (!Number.isSafeInteger(content.graph_revision) || content.graph_revision <= revision) return;
    // Keep the displayed revision until its in-flight exact readout returns.
    // This is bounded transport backpressure, not an inspection hold.
    if (picks.size || selections) { pendingFrame = { content, buffers }; return; }
    try {
    const spec = content.spec, payload = payloadBuffers(spec, buffers);
    revision = content.graph_revision;
    if (!view) { view = new ChartView(el, spec, payload, comm); attachTicks(view, spec); }
    else {
      refresh(spec, buffers);
    }
    if (content.restore_state) {
      for (const cb of listeners) cb({ type: "state_patch", state: content.restore_state, animate: false, history: false }, []);
    }
    // Saved notebook/embed state uses the same accepted picture, with no
    // second wire transfer or save_changes echo to the kernel.
    model.set({ spec: { graph_host: true, instance, graph_snapshot: { spec, step: content.step, phase: content.phase, restore_state: content.restore_state } }, buffers }, { silent: true });
    el.dataset.graphRevision = String(revision); el.dataset.graphSteps = String(content.step);
    status.textContent = content.phase === "complete" ? "Layout complete" : "Laying out graph";
    // A presented frame releases exactly one subsequent native checkpoint.
    frame = requestAnimationFrame(() => { frame = null; if (!disposed) send({ type: "graph_painted" }); });
    } catch {
      status.textContent = "XYG_GRAPH_WORKER_FAILED";
      send({ type: "graph_dispose" });
    }
  }
  if (bootstrap.graph_snapshot) {
    const saved = bootstrap.graph_snapshot;
    view = new ChartView(el, saved.spec, payloadBuffers(saved.spec, model.get("buffers")), comm);
    attachTicks(view, saved.spec);
    if (saved.restore_state) for (const cb of listeners) cb({ type: "state_patch", state: saved.restore_state, animate: false, history: false }, []);
    el.dataset.graphSteps = String(saved.step);
    status.textContent = saved.phase === "complete" ? "Layout complete" : "Laying out graph";
  }
  model.on("msg:custom", message); send({ type: "graph_mount" });
  return () => {
    if (disposed) return;
    send({ type: "graph_dispose" }); disposed = true;
    if (frame !== null) cancelAnimationFrame(frame);
    model.off("msg:custom", message); listeners.clear(); picks.clear(); pendingFrame = null; selection = null; view?.destroy(); status.remove();
  };
}
