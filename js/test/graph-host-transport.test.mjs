import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";
import { stripTypeScriptTypes } from "node:module";
import vm from "node:vm";
import test from "node:test";

function fixture(saved) {
  const source = readFileSync(new URL("../src/66_graph_host.ts", import.meta.url), "utf8")
    .replace(/^import .*;$/mg, "").replace("export function", "function");
  let view, status, serial = 0;
  const frames = new Map();
  class ChartView {
    constructor(el, spec, payload, comm) {
      this.spec = spec; this.comm = comm; this._graphs = []; this.gpuTraces = [];
      this.replies = []; this.swaps = 0;
      this._stateSelection = null; this._historyPast = []; this._historyFuture = [];
      this.broadcasts = []; this._interactionSeq = 0; this.seq = 0;
      this.axes = { x: { range: [0, 10] }, y: { range: [0, 10] } };
      this.view = this._copyView({}); this.view0 = this._copyView(this.view);
      this.unsubscribe = comm.onMessage(content => {
        this.replies.push(content);
        if (content.type === "selection") this.mask = content.total;
        if (content.type === "selection_rows") this._applyRowsSelection(content, []);
      });
      view = this;
    }
    _applyAppend({ spec }) { this.spec = spec; this.swaps++; }
    _graphMetaArray() { return null; }
    _restoreGraphLegendVisibility(state) { this.restoredVisibility = state; }
    _applySelectionBuffers(content) { this.mask = content.total ?? 0; }
    _clearLassoOverlay() {} _clearBoxOverlay() {} _renderBoxSelection() {} _renderLassoSelection() {}
    _interactionFlag() { return true; } _updateHistoryButtons() {} _dispatchChartEvent() {}
    _eventView() { return {}; }
    _axisIds() { return []; } _setView() {}
    _broadcastLinkedSelection(selection) { this.broadcasts.push(selection); }
    _durableState() { return { v: 1, ranges: {}, selection: structuredClone(this._stateSelection) }; }
    _validateStatePatch() { return null; }
    draw() {}
    destroy() { this.unsubscribe(); this.destroyed = true; }
  }
  const context = { ChartView, payloadBuffers: (_, buffers) => buffers, crypto: webcrypto,
    document: { createElement: () => (status = { setAttribute() {}, remove() {} }) },
    requestAnimationFrame: cb => { frames.set(++serial, cb); return serial; },
    cancelAnimationFrame: id => frames.delete(id), clearTimeout };
  vm.createContext(context);
  for (const name of ["53_interaction", "57_viewstate"]) {
    const methods = readFileSync(new URL(`../src/${name}.ts`, import.meta.url), "utf8").replace(/^import .*;$/mg, "");
    vm.runInContext(stripTypeScriptTypes(methods), context);
  }
  // Exercise actual range mutation, state validation and history together.
  // Only drawing/transport and unbounded linear fixture-axis clamping are stubbed.
  for (const name of ["_clearLassoOverlay", "_clearBoxOverlay", "_renderBoxSelection", "_renderLassoSelection", "_updateHistoryButtons", "_dispatchChartEvent", "_scheduleViewRequest", "_emitViewChange"]) ChartView.prototype[name] = () => {};
  const axes = readFileSync(new URL("../src/50_chartview.ts", import.meta.url), "utf8");
  const axisMethods = axes.slice(axes.indexOf("  _axisIds() {"), axes.indexOf("  _axisPolicy(name) {"))
    + axes.slice(axes.indexOf("  _axisRange(axisId, view = this.view) {"), axes.indexOf("  // Stride-thin radial tick LABELS"));
  const AxisView = vm.runInContext(stripTypeScriptTypes(`(class { ${axisMethods} })`), context);
  for (const name of ["_axisIds", "_copyView", "_viewFrom", "_axisRange"]) ChartView.prototype[name] = AxisView.prototype[name];
  ChartView.prototype._axis = function (id) { return this.axes[id]; };
  ChartView.prototype._clampView = view => view;
  ChartView.prototype._prefersReducedMotion = () => true;
  ChartView.prototype._now = () => 0;
  ChartView.prototype._broadcastLinkedSelection = function (selection) { this.broadcasts.push(selection); };
  vm.runInContext(stripTypeScriptTypes(source) + ";globalThis.render=renderGraphHost;", context);
  const model = { state: { spec: { instance: "test", graph_snapshot: saved }, buffers: [] }, sent: [],
    get(key) { return this.state[key]; }, set(state) { Object.assign(this.state, state); },
    send(content) { this.sent.push(content); }, on(_, cb) { this.handler = cb; }, off() { this.handler = null; } };
  const cleanup = context.render({ model, el: { dataset: {}, append() {} }, attachTicks() {} });
  const epoch = model.sent[0].graph_epoch;
  const deliver = content => model.handler({ graph_instance: "test", graph_epoch: epoch, ...content }, []);
  return { model, cleanup, get view() { return view; }, get status() { return status.textContent; }, deliver,
    paint() { for (const [id, cb] of frames) { frames.delete(id); cb(); } },
    frame(revision, extra = {}) { deliver({ type: "graph_frame", graph_revision: revision, spec: { traces: [], _graph_row_space: "a".repeat(64) }, step: revision, phase: "running", ...extra }); } };
}

test("selection clear holds a checkpoint until the exact clear reply", () => {
  const f = fixture();
  f.frame(1); f.paint();
  f.deliver({ type: "selection", graph_revision: 1, traces: [{ id: 0 }], total: 1 });
  f.view.mask = 0; // the existing generic painter clears immediately
  f.view.comm.send({ type: "select_clear" });
  f.frame(2);
  assert.equal(f.view.swaps, 0);
  assert.equal(f.view.mask, 0);
  f.deliver({ type: "selection", graph_revision: 1, seq: f.model.sent.at(-1).seq, selection: null, traces: [], total: 0 });
  assert.equal(f.view.swaps, 1);
  assert.equal(f.view.mask, 0);
  f.paint();
  assert.equal(f.model.sent.at(-1).graph_revision, 2);
  f.cleanup();
});

const json = value => JSON.parse(JSON.stringify(value));
const predicate = x => ({ range: { x0: x, x1: x + 1, y0: 0, y1: 1 } });
function accept(f, request, total = 1) {
  f.deliver({ type: "selection", graph_revision: 1, seq: request.seq,
    selection: request.type === "select_clear" ? null : predicate(request.x0), traces: [{ id: 0 }], total });
}
test("accepted graph predicates commit history and linked geometry once", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); const request = f.model.sent.at(-1);
  assert.equal(f.view._historyPast.length, 0); assert.equal(f.view.broadcasts.length, 0);
  accept(f, request); accept(f, request);
  assert.equal(f.view._historyPast.length, 1);
  assert.deepEqual(json(f.view._stateSelection), predicate(2));
  assert.deepEqual(json(f.view.broadcasts), [predicate(2)]);
  f.cleanup();
});
test("older refusal cannot replace the latest accepted predicate", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); const a = f.model.sent.at(-1);
  f.view._sendSelect([4, 0], [5, 1]);
  f.deliver({ type: "selection_refused", graph_revision: 1, seq: a.seq, selection: null });
  const b = f.model.sent.at(-1);
  accept(f, b, 2);
  f.deliver({ type: "selection_refused", graph_revision: 1, seq: a.seq, selection: null });
  assert.deepEqual(json(f.view._stateSelection), predicate(4)); assert.equal(f.view.mask, 2);
  assert.equal(f.view._historyPast.length, 1); assert.equal(f.view.broadcasts.length, 1);
  f.cleanup();
});
test("latest refusal presents an accepted intermediate result with its own intent", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1], { history: false, broadcast: false }); const a = f.model.sent.at(-1);
  f.view._sendSelect([4, 0], [5, 1]);
  accept(f, a, 3); assert.equal(f.view.mask, undefined);
  const b = f.model.sent.at(-1);
  f.deliver({ type: "selection_refused", graph_revision: 1, seq: b.seq, selection: predicate(2) });
  assert.deepEqual(json(f.view._stateSelection), predicate(2)); assert.equal(f.view.mask, 3);
  assert.equal(f.view._historyPast.length, 0); assert.equal(f.view.broadcasts.length, 0);
  f.cleanup();
});
test("newer server row selection owns the facet before a reentrant old reply", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); const request = f.model.sent.at(-1);
  f.deliver({ type: "selection_rows", graph_revision: 1, traces: [{ id: 0 }], total: 7 });
  accept(f, request);
  assert.equal(f.view.replies.at(-1).type, "selection_rows");
  assert.equal(f.view._historyPast.length, 0); assert.equal(f.view.broadcasts.length, 0);
  f.cleanup();
});
test("duplicate replies cannot release a different outstanding selection", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); const a = f.model.sent.at(-1);
  f.view._sendSelect([4, 0], [5, 1]);
  f.frame(2); accept(f, a); accept(f, a);
  const b = f.model.sent.at(-1);
  assert.equal(f.view.swaps, 0);
  accept(f, b); assert.equal(f.view.swaps, 1);
  f.cleanup();
});

test("selection ingress retains one active and one latest queued intent", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); const a = f.model.sent.at(-1), sent = f.model.sent.length;
  for (let i = 3; i < 1003; i++) f.view._sendSelect([i, 0], [i + 1, 1]);
  assert.equal(f.model.sent.length, sent);
  accept(f, a); const latest = f.model.sent.at(-1);
  assert.equal(latest.x0, 1002); assert.equal(latest.seq, 1001);
  accept(f, latest); assert.deepEqual(json(f.view._stateSelection), predicate(1002));
  assert.equal(f.view._historyPast.length, 1);
  f.cleanup();
});

test("synchronous brush callback owns a newer intent before outer dispatch", () => {
  const f = fixture(); f.frame(1); f.paint(); let nested = false;
  f.view._dispatchChartEvent = kind => { if (kind === "brush" && !nested) {
    nested = true; f.view._sendSelect([4, 0], [5, 1]);
  } };
  const count = f.model.sent.length;
  f.view._sendSelect([2, 0], [3, 1]);
  assert.equal(f.model.sent.length, count + 1);
  assert.equal(f.model.sent.at(-1).x0, 4);
  accept(f, f.model.sent.at(-1));
  assert.deepEqual(json(f.view._stateSelection), predicate(4));
  f.cleanup();
});

test("disposal during brush dispatch prevents a later native command", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._dispatchChartEvent = kind => { if (kind === "brush") f.cleanup(); };
  f.view._sendSelect([2, 0], [3, 1]);
  assert.equal(f.model.sent.at(-1).type, "graph_dispose");
  assert.ok(!f.model.sent.some(msg => msg.type === "select"));
});

test("disposal during accepted notification prevents a later linked broadcast", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view.comm.onMessage(() => f.cleanup());
  f.view._sendSelect([2, 0], [3, 1]); accept(f, f.model.sent.at(-1));
  assert.equal(f.view.broadcasts.length, 0);
  assert.equal(f.model.sent.at(-1).type, "graph_dispose");
});
test("ordinary non-graph transport keeps immediate selection history and broadcasts", () => {
  const f = fixture(); f.frame(1); f.paint();
  delete f.view.comm.deferSelection;
  f.view._sendSelect([2, 0], [3, 1]);
  assert.deepEqual(json(f.view._stateSelection), predicate(2));
  assert.equal(f.view._historyPast.length, 1); assert.equal(f.view.broadcasts.length, 1);
  f.cleanup();
});

test("refused clear restores accepted masks and geometry without another history entry", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); accept(f, f.model.sent.at(-1), 2);
  f.view._clearSelection(); const request = f.model.sent.at(-1);
  f.deliver({ type: "selection_refused", graph_revision: 1, seq: request.seq, selection: predicate(2) });
  assert.deepEqual(json(f.view._stateSelection), predicate(2)); assert.equal(f.view.mask, 2);
  assert.equal(f.view._historyPast.length, 1); assert.equal(f.view.broadcasts.length, 1);
  f.cleanup();
});

test("refused predicate preserves an accepted opaque row selection", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.deliver({ type: "selection_rows", graph_revision: 1, traces: [{ id: 0 }], total: 7 });
  f.view._sendSelect([2, 0], [3, 1]); const request = f.model.sent.at(-1);
  f.deliver({ type: "selection_refused", graph_revision: 1, seq: request.seq, selection: { rows: true } });
  assert.deepEqual(json(f.view._stateSelection), { rows: true }); assert.equal(f.view.mask, 7);
  assert.equal(f.view._historyPast.length, 0); assert.equal(f.view.broadcasts.length, 0);
  f.cleanup();
});

test("refused history navigation preserves both stacks and the accepted selection", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); accept(f, f.model.sent.at(-1));
  f.view._sendSelect([4, 0], [5, 1]); accept(f, f.model.sent.at(-1));
  assert.equal(f.view._historyBack(), true); const request = f.model.sent.at(-1);
  f.deliver({ type: "selection_refused", graph_revision: 1, seq: request.seq, selection: predicate(4) });
  assert.equal(f.view._historyPast.length, 2); assert.equal(f.view._historyFuture.length, 0);
  assert.deepEqual(json(f.view._stateSelection), predicate(4));
  f.cleanup();
});

test("accepted graph history moves each stack once and stays idle while pending", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); accept(f, f.model.sent.at(-1));
  f.view._sendSelect([4, 0], [5, 1]); accept(f, f.model.sent.at(-1));
  assert.equal(f.view._historyBack(), true); const back = f.model.sent.at(-1);
  assert.equal(f.view._historyBack(), false); assert.equal(f.view._historyPast.length, 2);
  accept(f, back); accept(f, back);
  assert.equal(f.view._historyPast.length, 1); assert.equal(f.view._historyFuture.length, 1);
  assert.deepEqual(json(f.view._stateSelection), predicate(2));
  assert.equal(f.view._historyForward(), true); accept(f, f.model.sent.at(-1));
  assert.equal(f.view._historyPast.length, 2); assert.equal(f.view._historyFuture.length, 0);
  assert.deepEqual(json(f.view._stateSelection), predicate(4));
  f.cleanup();
});

test("a combined range and selection patch creates one complete undo entry", () => {
  const f = fixture(); f.frame(1); f.paint();
  const before = json(f.view._durableState());
  f.view._applyStatePatch({ ranges: { x: [20, 30] }, selection: predicate(2) });
  accept(f, f.model.sent.at(-1));
  assert.equal(f.view._historyPast.length, 1);
  assert.deepEqual(json(f.view._historyPast[0]), before);
  assert.deepEqual(json(f.view._durableState()), { ...before, ranges: { ...before.ranges, x: [20, 30] }, selection: predicate(2) });
  f.cleanup();
});

test("refused history navigation preserves ranges and every accepted facet", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); accept(f, f.model.sent.at(-1), 2);
  f.view._applyStatePatch({ ranges: { x: [20, 30] } });
  const before = json(f.view._durableState()), past = json(f.view._historyPast), future = json(f.view._historyFuture);
  assert.equal(f.view._historyBack(), true); const request = f.model.sent.at(-1);
  f.deliver({ type: "selection_refused", graph_revision: 1, seq: request.seq, selection: predicate(2) });
  assert.deepEqual(json(f.view._durableState()), before);
  assert.deepEqual(json(f.view._historyPast), past); assert.deepEqual(json(f.view._historyFuture), future);
  assert.equal(f.view.mask, 2);
  f.cleanup();
});

test("accepted Back and Next commit the complete range and selection snapshot once", () => {
  const f = fixture(); f.frame(1); f.paint();
  const before = json(f.view._durableState());
  f.view._applyStatePatch({ ranges: { x: [20, 30] }, selection: predicate(2) });
  accept(f, f.model.sent.at(-1)); const after = json(f.view._durableState());
  assert.equal(f.view._historyBack(), true);
  assert.deepEqual(json(f.view._durableState()), after);
  accept(f, f.model.sent.at(-1), 0);
  assert.deepEqual(json(f.view._durableState()), before);
  assert.equal(f.view._historyPast.length, 0); assert.equal(f.view._historyFuture.length, 1);
  assert.equal(f.view._historyForward(), true);
  assert.deepEqual(json(f.view._durableState()), before);
  accept(f, f.model.sent.at(-1));
  assert.deepEqual(json(f.view._durableState()), after);
  assert.equal(f.view._historyPast.length, 1); assert.equal(f.view._historyFuture.length, 0);
  f.cleanup();
});

test("a newer non-history range write supersedes pending navigation without rollback", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); accept(f, f.model.sent.at(-1), 2);
  f.view._applyStatePatch({ ranges: { x: [20, 30] } });
  const past = json(f.view._historyPast), future = json(f.view._historyFuture);
  assert.equal(f.view._historyBack(), true); const request = f.model.sent.at(-1);
  f.view._applyStatePatch({ ranges: { x: [40, 50] } }, { history: false, source: "linked" });
  const newer = json(f.view._durableState());
  accept(f, request, 1);
  assert.deepEqual(json(f.view._durableState()), newer); assert.equal(f.view.mask, 2);
  assert.deepEqual(json(f.view._historyPast), past); assert.deepEqual(json(f.view._historyFuture), future);
  f.cleanup();
});

test("a newer animation owns the camera before its first frame", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); accept(f, f.model.sent.at(-1), 2);
  f.view._applyStatePatch({ ranges: { x: [20, 30] } });
  const past = json(f.view._historyPast), future = json(f.view._historyFuture);
  f.view._historyBack(); const request = f.model.sent.at(-1);
  f.view._prefersReducedMotion = () => false;
  f.view._applyStatePatch({ ranges: { x: [40, 50] } }, { animate: true, history: false });
  assert.deepEqual(json(f.view.view.ranges.x), [20, 30]);
  const animation = f.view._viewAnim;
  accept(f, request);
  assert.equal(f.view._viewAnim, animation); assert.deepEqual(json(animation.target.ranges.x), [40, 50]);
  assert.deepEqual(json(f.view._historyPast), past); assert.deepEqual(json(f.view._historyFuture), future);
  assert.equal(f.view.mask, 2);
  f.cleanup();
});

test("camera writes returning to the same coordinates still supersede pending navigation", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); accept(f, f.model.sent.at(-1));
  f.view._applyStatePatch({ ranges: { x: [20, 30] } });
  const past = json(f.view._historyPast), future = json(f.view._historyFuture);
  f.view._historyBack(); const request = f.model.sent.at(-1);
  f.view._applyStatePatch({ ranges: { x: [40, 50] } }, { history: false });
  f.view._applyStatePatch({ ranges: { x: [20, 30] } }, { history: false });
  accept(f, request);
  assert.deepEqual(json(f.view.view.ranges.x), [20, 30]);
  assert.deepEqual(json(f.view._historyPast), past); assert.deepEqual(json(f.view._historyFuture), future);
  f.cleanup();
});

test("an explicit same-value camera write owns its facet while an empty patch leaves it alone", () => {
  for (const empty of [false, true]) {
    const f = fixture(); f.frame(1); f.paint();
    f.view._sendSelect([2, 0], [3, 1]); accept(f, f.model.sent.at(-1));
    f.view._applyStatePatch({ ranges: { x: [20, 30] } });
    const count = f.view._historyPast.length;
    f.view._historyBack(); const request = f.model.sent.at(-1);
    f.view._applyStatePatch({ ranges: empty ? {} : { x: [20, 30] } }, { history: false });
    accept(f, request);
    assert.deepEqual(json(f.view.view.ranges.x), empty ? [0, 10] : [20, 30]);
    assert.equal(f.view._historyPast.length, count - Number(empty));
    f.cleanup();
  }
});

test("an invalid camera patch does not supersede an admitted navigation", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._sendSelect([2, 0], [3, 1]); accept(f, f.model.sent.at(-1));
  f.view._applyStatePatch({ ranges: { x: [20, 30] } });
  const count = f.view._historyPast.length;
  f.view._historyBack(); const request = f.model.sent.at(-1);
  assert.equal(f.view._applyStatePatch({ ranges: { removed: [40, 50] } }), false);
  accept(f, request);
  assert.deepEqual(json(f.view.view.ranges.x), [0, 10]);
  assert.equal(f.view._historyPast.length, count - 1);
  f.cleanup();
});

test("refused Next preserves the camera, redo target and current masks", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._applyStatePatch({ ranges: { x: [20, 30] }, selection: predicate(2) }); accept(f, f.model.sent.at(-1), 2);
  f.view._historyBack(); accept(f, f.model.sent.at(-1), 0);
  const before = json(f.view._durableState()), past = json(f.view._historyPast), future = json(f.view._historyFuture);
  assert.equal(f.view._historyForward(), true); const request = f.model.sent.at(-1);
  f.deliver({ type: "selection_refused", graph_revision: 1, seq: request.seq, selection: null });
  assert.deepEqual(json(f.view._durableState()), before); assert.equal(f.view.mask, 0);
  assert.deepEqual(json(f.view._historyPast), past); assert.deepEqual(json(f.view._historyFuture), future);
  f.cleanup();
});

test("opaque-row history restores ranges synchronously without requesting a predicate", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.deliver({ type: "selection_rows", graph_revision: 1, traces: [{ id: 0 }], total: 7 });
  const before = json(f.view._durableState());
  f.view._applyStatePatch({ ranges: { x: [20, 30] } }); const sent = f.model.sent.length;
  assert.equal(f.view._historyBack(), true);
  assert.deepEqual(json(f.view._durableState()), before); assert.equal(f.view.mask, 7);
  assert.equal(f.model.sent.length, sent);
  assert.equal(f.view._historyPast.length, 0); assert.equal(f.view._historyFuture.length, 1);
  f.cleanup();
});

test("a history target with an obsolete axis schema refuses before any request or mutation", () => {
  const f = fixture(); f.frame(1); f.paint();
  const before = json(f.view._durableState());
  f.view._historyPast.push({ ...before, ranges: { removed: [0, 10] }, selection: predicate(2) });
  const past = json(f.view._historyPast), count = f.model.sent.length;
  assert.equal(f.view._historyBack(), false);
  assert.deepEqual(json(f.view._durableState()), before);
  assert.deepEqual(json(f.view._historyPast), past); assert.equal(f.view._historyFuture.length, 0);
  assert.equal(f.model.sent.length, count);
  f.cleanup();
});

test("accepted lasso and axis-range geometry retain their authored discriminator", () => {
  const f = fixture(); f.frame(1); f.paint();
  const polygon = [[0, 0], [1, 0], [0, 1]];
  f.view._sendSelectPolygon(polygon); let request = f.model.sent.at(-1);
  f.deliver({ type: "selection", graph_revision: 1, seq: request.seq, selection: { polygon }, traces: [], total: 0 });
  assert.deepEqual(json(f.view._stateSelection), { polygon });
  f.view._sendSelect([2, 0], [3, 1], { mode: "x" }); request = f.model.sent.at(-1);
  assert.equal(request.mode, "x");
  const selection = { range: { ...predicate(2).range, mode: "x" } };
  f.deliver({ type: "selection", graph_revision: 1, seq: request.seq, selection, traces: [], total: 0 });
  assert.deepEqual(json(f.view._stateSelection), selection);
  f.cleanup();
});

test("refused graph predicate does not enter history or linked state", () => {
  const f = fixture(); f.frame(1); f.paint();
  f.view._historyFuture.push({ selection: { range: { x0: 8, x1: 9, y0: 8, y1: 9 } } });
  f.view._sendSelect([0, 0], [1, 1]);
  const request = f.model.sent.at(-1);
  f.deliver({ type: "selection_refused", graph_revision: 1, seq: request.seq, code: "XYG_GRAPH_SELECTION_RESOURCE_LIMIT", selection: null });
  assert.equal(f.view._historyPast.length, 0);
  assert.equal(f.view._historyFuture.length, 1);
  assert.equal(f.view.broadcasts.length, 0);
  assert.equal(f.view._stateSelection, null);
  assert.equal(f.status, "Graph selection exceeds the resource limit");
  f.view._sendSelect([2, 0], [3, 1]); accept(f, f.model.sent.at(-1));
  assert.equal(f.status, "Laying out graph");
  f.cleanup();
});

test("restored committed view is applied before the replacement paint acknowledgement", () => {
  const f = fixture(), state = { v: 1, ranges: { x: [-20, 20], y: [-20, 20] } };
  f.frame(1, { restore_state: state });
  assert.equal(f.view.replies.at(-1).type, "state_patch");
  assert.deepEqual(f.view.replies.at(-1).state, state);
  assert.equal(f.model.sent.length, 1);
  assert.deepEqual(f.model.state.spec.graph_snapshot.restore_state, state);
  f.paint();
  assert.equal(f.model.sent.at(-1).type, "graph_painted");
  f.cleanup();
});


test("ordinary append retains the graph saved-state envelope and uses safe refresh", () => {
  const f = fixture();
  f.frame(1); f.paint();
  f.deliver({ type: "append", graph_revision: 1, affected: [], spec: { traces: [], title: "Appended" } });
  assert.equal(f.view.swaps, 1);
  assert.equal(f.view.spec.title, "Appended");
  assert.equal(f.model.state.spec.graph_host, true);
  assert.equal(f.model.state.spec.graph_snapshot.spec.title, "Appended");
  f.cleanup();
});

test("the actual legend renderer restores whole traces/categories before replacement paint", () => {
  const source = readFileSync(new URL("../src/50_chartview.ts", import.meta.url), "utf8");
  const start = source.indexOf("  _restoreGraphLegendVisibility(visibility) {");
  const methods = source.slice(start, source.indexOf("  _legendBox(root, items, options)", start));
  const View = vm.runInNewContext(`(class { ${methods} })`);
  const view = new View();
  view._clearLegendHover = () => {}; view._updatePickable = () => {}; view.draw = () => {};
  view._applyCategoryVisibility = () => {}; view._syncLegendRow = () => {};
  let rows;
  view._legendBox = (_, items) => { rows = items; view._legends.push({ _xyItemRows: items.map(it => ({row: {}, it})) }); };
  view.spec = { traces: [
    { id: 4, kind: "scatter", name: "Whole", style: { color: "red" } },
    { id: 9, kind: "scatter", color: { mode: "categorical", categories: ["a", "b"], palette: ["red", "blue"] } },
  ] };
  view.gpuTraces = [{}, {}];
  view._buildLegend({});
  view._restoreGraphLegendVisibility([
    { trace: 4, hidden: true, categories: [] },
    { trace: 9, hidden: false, categories: [1] },
  ]);
  assert.equal(view._legendOffTraces.has(0), true);
  assert.equal(view._legendOffCats.get(1).has(1), true);
  assert.equal(view.gpuTraces[0]._legendHidden, true);
  assert.equal(rows.find(r => r.name === "Whole").off, true);
  assert.equal(rows.find(r => r.name === "b").off, true);
  view._buildLegend({});
  assert.equal(rows.find(r => r.name === "b").off, true);
  view._restoreGraphLegendVisibility([]);
  assert.equal(view.gpuTraces[0]._legendHidden, false);
});


test("legend choices enter saved notebook state and the bootstrap replacement", () => {
  const first = fixture(); first.frame(1); first.paint();
  first.view.spec.traces = [{ id: 4 }, { id: 9 }];
  first.view._legendOffTraces = new Set([0]);
  first.view._legendOffCats = new Map([[1, new Set([1])]]);
  first.view.comm.send({ type: "legend_toggle", trace: 9, category: 1, hidden: true });
  const saved = first.model.state.spec.graph_snapshot;
  const choices = [{ trace: 4, hidden: true, categories: [] }, { trace: 9, hidden: false, categories: [1] }];
  assert.deepEqual(JSON.parse(JSON.stringify(saved.spec._graph_legend_visibility)), choices);
  const second = fixture(saved);
  assert.deepEqual(JSON.parse(JSON.stringify(second.view.restoredVisibility)), choices);
  first.cleanup(); second.cleanup();
});


test("replacement frame restores its native legend metadata before paint ACK", () => {
  const f = fixture(), choices = [{ trace: 0, hidden: true, categories: [1] }];
  f.frame(1, { spec: { traces: [], _graph_legend_visibility: choices } });
  assert.deepEqual(f.view.restoredVisibility, choices);
  assert.equal(f.model.sent.length, 1); // mount only; no paint ACK yet
  f.paint();
  assert.equal(f.model.sent.at(-1).type, "graph_painted");
  f.cleanup();
});

test("row masks survive identical compiler stamps and revoke on changed or missing stamps", () => {
  for (const token of ["b".repeat(64), null, [], "invalid"]) {
    const f = fixture(); f.frame(1); f.paint();
    f.deliver({ type: "selection_rows", graph_revision: 1, traces: [{ id: 0 }], total: 7 });
    f.frame(2); assert.equal(f.view.mask, 7);
    f.frame(3, { spec: { traces: [], _graph_row_space: token } });
    assert.equal(f.view.mask, 0); assert.equal(f.status, "Graph selection is unavailable for this picture");
    f.cleanup();
  }
});

test("segment dash packing preserves reversed-contour phase and exact f32 pairs", () => {
  const source = readFileSync(new URL("../src/50_chartview.ts", import.meta.url), "utf8");
  const start = source.indexOf("  _segmentDash(g, prog) {");
  const method = source.slice(start, source.indexOf("  _drawMesh(g, xm, ym)", start));
  const View = vm.runInNewContext(`(class { ${method} })`, { uniformOf: (_, __, name) => name });
  const view = new View(), uniforms = {}; let bound;
  view.gl = { ARRAY_BUFFER: 1, DYNAMIC_DRAW: 2,
    bindBuffer: (_, buffer) => { bound = buffer; },
    bufferData: (_, data) => { bound.values = Array.from(data); },
    uniform1i: (name, value) => { uniforms[name] = value; },
    uniform1f: (name, value) => { uniforms[name] = value; },
    uniform1fv: (name, value) => { uniforms[name] = Array.from(value); } };
  view.dpr = 2; view._polarGeometry = () => null;
  const rows = [[[0, 0], [10.125, 0]], [[20.25, 0], [10.125, 0]], [[20.25, 0], [30.375, 0]]];
  view._projectSegmentEndpoints = (_, __, index) => rows[index];
  view._upload = values => ({ values: Array.from(values) });
  const g = { n: 3, trace: { style: { dash: [2, 3] } }, _segmentCpu: {} };
  assert.equal(view._segmentDash(g, {}), true);
  assert.deepEqual(g._segmentDashOffsetBuf.values, [0, 1, 40.5, -1, 40.5, 1]);
  assert.deepEqual(uniforms.u_dashArr, [4, 6, 0, 0, 0, 0, 0, 0]);
  const buffer = g._segmentDashOffsetBuf;
  rows[2][1] = [35.75, 0]; view._segmentDash(g, {});
  assert.equal(g._segmentDashOffsetBuf, buffer);
  assert.equal(g._segmentDashData.length, 2 * g.n);
  assert.equal(g._segmentDashDirBuf, undefined);
});
