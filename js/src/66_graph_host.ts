/** Native force checkpoints use the ordinary notebook painter and channel. */
import { payloadBuffers } from "./00_header";
import { ChartView } from "./50_chartview";

export function renderGraphHost({ model, el, attachTicks }) {
  const bootstrap = model.get("spec"), instance = bootstrap.instance;
  const epoch = Array.from(crypto.getRandomValues(new Uint32Array(4)), value => value.toString(16).padStart(8, "0")).join("");
  el.dataset.graphInstance = instance;
  const status = document.createElement("div"); status.setAttribute("aria-live", "polite");
  let layoutStatus = "Laying out graph";
  status.textContent = layoutStatus; el.append(status);
  let revision = 0, disposed = false, view: ChartView | null = null, frame: number | null = null;
  let selection: { content: any; buffers: any } | null = null;
  const rowSpace = () => view?.spec?._graph_row_space ?? null;
  const sameRows = (a, b) => typeof a === "string" && /^[a-f0-9]{64}$/.test(a) && a === b;
  let selectedRows: string | null = null;
  let selectionUnavailable = false;
  const picks = new Set<string>();
  let selectionPending: { seq: number; intent: any } | null = null;
  let queuedSelection: { content: any; buffers: any; intent: any } | null = null;
  let selectionSequence = 0, selectionBarrier = 0, presentedSelection = 0;
  let acceptedSelection: { content: any; buffers: any; intent: any } | null = null;
  let pendingFrame: { content: any; buffers: any } | null = null;
  const listeners = new Set<(content: any, buffers: any) => void>();
  const send = (content, buffers = [], intent = null) => {
    if (disposed) return;
    if (revision === 0 && !["graph_mount", "graph_dispose"].includes(content.type)) return;
    if (["select", "select_polygon", "select_clear"].includes(content.type)) {
      const seq = intent?.seq ?? ++selectionSequence;
      if (seq < selectionSequence) return; // synchronous brush callback superseded this intent
      content = { ...content, seq };
      if (selectionPending !== null) { queuedSelection = { content, buffers, intent }; return; }
      selectionPending = { seq, intent };
    }
    if (content.type === "pick") picks.add(`${revision}:${content.seq}`);
    if (content.type === "legend_toggle" && view) {
      const saved = model.get("spec");
      const visibility = view.spec.traces.map((trace, i) => ({ trace: trace.id, hidden: !!view!._legendOffTraces?.has(i), categories: Array.from(view!._legendOffCats?.get(i) || []) }));
      model.set({ spec: { ...saved, graph_snapshot: { ...saved.graph_snapshot, spec: { ...view.spec, _graph_legend_visibility: visibility } } } }, { silent: true });
    }
    model.send({ ...content, graph_instance: instance, graph_epoch: epoch, graph_revision: revision }, {}, buffers);
  };
  const comm = {
    send,
    // Only this native graph host defers durable selection mutations. Other
    // chart transports retain their existing immediate mutation semantics.
    deferSelection: opts => ({ seq: ++selectionSequence, history: opts.history !== false, broadcast: opts.broadcast !== false, source: opts.source, commitHistory: opts.commitHistory }),
    deferHistory: direction => {
      if (selectionPending !== null) return false;
      const from = direction === "back" ? view._historyPast : view._historyFuture;
      const to = direction === "back" ? view._historyFuture : view._historyPast;
      const target = from.at(-1), before = view._durableState();
      if (!target) return false;
      const commitHistory = () => {
        if (from.at(-1) !== target) return;
        from.pop(); to.push(before); view._updateHistoryButtons();
      };
      view._historyApply(target, { commitHistory });
      if (selectionPending === null) commitHistory(); // ranges-only/opaque-row snapshot
      return true;
    },
    wantsViewChange: () => view?.spec?.interaction?._transport_view_change === true,
    onMessage: cb => { listeners.add(cb); return () => listeners.delete(cb); },
  };
  function presentSelection(restore = false) {
    if (acceptedSelection && acceptedSelection.content.seq > presentedSelection) {
      const { content, buffers } = acceptedSelection;
      const predicate = content.selection ?? null, intent = acceptedSelection.intent ?? {};
      intent.commitHistory?.();
      if (JSON.stringify(view._stateSelection ?? null) !== JSON.stringify(predicate)) view._historyRecord(intent);
      view._applyStatePatch({ selection: predicate }, { dispatch: false, broadcast: false, history: false });
      selection = acceptedSelection; selectedRows = rowSpace();
      presentedSelection = content.seq;
      for (const cb of listeners) cb(content, buffers);
      if (disposed) return;
      if (intent.broadcast !== false) view._broadcastLinkedSelection(predicate ?? { clear: true });
      selectionUnavailable = false;
      status.textContent = layoutStatus;
    } else if (restore) {
      if (selection?.content.type === "selection_rows") {
        view._applyRowsSelection(selection.content, selection.buffers, { dispatch: false });
        return;
      }
      const predicate = view._stateSelection?.rows ? null : view._stateSelection ?? null;
      view._applyStatePatch({ selection: predicate }, { dispatch: false, broadcast: false, history: false });
      if (selection) { view._applySelectionBuffers(selection.content, selection.buffers); view.draw(); }
    }
  }
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
      if (selection && !sameRows(selectedRows, rowSpace())) {
        selection = null; acceptedSelection = null;
        view._applySelectionBuffers({ traces: [], total: 0 }, []); view._selectionCount = 0; view.draw();
        selectionUnavailable = true;
        status.textContent = "Graph selection is unavailable for this picture";
      }
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
        const selectionReply = content.type === "selection" || content.type === "selection_refused";
        const sequenced = selectionReply && Number.isSafeInteger(content.seq) && content.seq > 0;
        if (sequenced) {
          const pending = selectionPending?.seq === content.seq ? selectionPending : null;
          if (pending) selectionPending = null;
          if (pending && content.seq > selectionBarrier) {
            if (content.type === "selection" && (!acceptedSelection || content.seq > acceptedSelection.content.seq)) acceptedSelection = { content, buffers, intent: pending.intent };
            if (content.seq === selectionSequence) presentSelection(content.type === "selection_refused");
          }
        }
        if (content.type === "selection_rows" || (content.type === "state_patch" && content.state?.selection !== undefined)) {
          // A callback can publish a newer API selection before its old query
          // reply. It owns this facet; old replies only release backpressure.
          selectionBarrier = selectionSequence; acceptedSelection = null;
          queuedSelection = null;
        }
        if (!sequenced && (content.type === "selection" || content.type === "selection_rows")) {
          selection = { content, buffers }; selectedRows = rowSpace();
          selectionUnavailable = false; status.textContent = layoutStatus;
        }
        if (content.type === "state_patch" && content.state?.selection === null) selection = null;
        if (!sequenced && content.type !== "selection_refused") for (const cb of listeners) cb(content, buffers);
        if (content.type === "selection_refused" && content.seq === selectionSequence && content.seq > selectionBarrier) {
          status.textContent = content.code === "XYG_GRAPH_SELECTION_RESOURCE_LIMIT"
            ? "Graph selection exceeds the resource limit" : "Graph selection is unavailable for this picture";
        }
        if (content.type === "pick_result") picks.delete(`${revision}:${content.seq}`);
        if (selectionPending === null && queuedSelection) {
          const next = queuedSelection; queuedSelection = null;
          selectionPending = { seq: next.content.seq, intent: next.intent };
          model.send({ ...next.content, graph_instance: instance, graph_epoch: epoch, graph_revision: revision }, {}, next.buffers);
        }
        if (!picks.size && selectionPending === null && pendingFrame) { const next = pendingFrame; pendingFrame = null; message(next.content, next.buffers); }
      }
      return;
    }
    if (!Number.isSafeInteger(content.graph_revision) || content.graph_revision <= revision) return;
    // Keep the displayed revision until its in-flight exact readout returns.
    // This is bounded transport backpressure, not an inspection hold.
    if (picks.size || selectionPending !== null) { pendingFrame = { content, buffers }; return; }
    try {
    const spec = content.spec, payload = payloadBuffers(spec, buffers);
    revision = content.graph_revision;
    if (!view) { view = new ChartView(el, spec, payload, comm); attachTicks(view, spec); }
    else {
      refresh(spec, buffers);
    }
    view._restoreGraphLegendVisibility(spec._graph_legend_visibility);
    if (content.restore_state) {
      for (const cb of listeners) cb({ type: "state_patch", state: content.restore_state, animate: false, history: false }, []);
    }
    // Saved notebook/embed state uses the same accepted picture, with no
    // second wire transfer or save_changes echo to the kernel.
    model.set({ spec: { graph_host: true, instance, graph_snapshot: { spec, step: content.step, phase: content.phase, restore_state: content.restore_state } }, buffers }, { silent: true });
    el.dataset.graphRevision = String(revision); el.dataset.graphSteps = String(content.step);
    layoutStatus = content.phase === "complete" ? "Layout complete" : "Laying out graph";
    status.textContent = selectionUnavailable ? "Graph selection is unavailable for this picture" : layoutStatus;
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
    view._restoreGraphLegendVisibility(saved.spec._graph_legend_visibility);
    if (saved.restore_state) for (const cb of listeners) cb({ type: "state_patch", state: saved.restore_state, animate: false, history: false }, []);
    el.dataset.graphSteps = String(saved.step);
    layoutStatus = saved.phase === "complete" ? "Layout complete" : "Laying out graph";
    status.textContent = layoutStatus;
  }
  model.on("msg:custom", message); send({ type: "graph_mount" });
  return () => {
    if (disposed) return;
    send({ type: "graph_dispose" }); disposed = true;
    if (frame !== null) cancelAnimationFrame(frame);
    model.off("msg:custom", message); listeners.clear(); picks.clear(); selectionPending = null; queuedSelection = null; pendingFrame = null; selection = null; acceptedSelection = null; view?.destroy(); status.remove();
  };
}
