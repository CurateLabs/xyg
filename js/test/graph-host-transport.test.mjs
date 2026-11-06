import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";
import { stripTypeScriptTypes } from "node:module";
import vm from "node:vm";
import test from "node:test";

function fixture(saved) {
  const source = readFileSync(new URL("../src/66_graph_host.ts", import.meta.url), "utf8")
    .replace(/^import .*;$/mg, "").replace("export function", "function");
  let view, serial = 0;
  const frames = new Map();
  class ChartView {
    constructor(el, spec, payload, comm) {
      this.spec = spec; this.comm = comm; this._graphs = []; this.gpuTraces = [];
      this.replies = []; this.swaps = 0;
      this.unsubscribe = comm.onMessage(content => {
        this.replies.push(content);
        if (content.type === "selection") this.mask = content.total;
      });
      view = this;
    }
    _applyAppend({ spec }) { this.spec = spec; this.swaps++; }
    _graphMetaArray() { return null; }
    _applySelectionBuffers(content) { this.mask = content.total; }
    draw() {}
    destroy() { this.unsubscribe(); this.destroyed = true; }
  }
  const context = { ChartView, payloadBuffers: (_, buffers) => buffers, crypto: webcrypto,
    document: { createElement: () => ({ setAttribute() {}, remove() {} }) },
    requestAnimationFrame: cb => { frames.set(++serial, cb); return serial; },
    cancelAnimationFrame: id => frames.delete(id) };
  vm.createContext(context);
  vm.runInContext(stripTypeScriptTypes(source) + ";globalThis.render=renderGraphHost;", context);
  const model = { state: { spec: { instance: "test", graph_snapshot: saved }, buffers: [] }, sent: [],
    get(key) { return this.state[key]; }, set(state) { Object.assign(this.state, state); },
    send(content) { this.sent.push(content); }, on(_, cb) { this.handler = cb; }, off() { this.handler = null; } };
  const cleanup = context.render({ model, el: { dataset: {}, append() {} }, attachTicks() {} });
  const epoch = model.sent[0].graph_epoch;
  const deliver = content => model.handler({ graph_instance: "test", graph_epoch: epoch, ...content }, []);
  return { model, cleanup, get view() { return view; }, deliver,
    paint() { for (const [id, cb] of frames) { frames.delete(id); cb(); } },
    frame(revision, extra = {}) { deliver({ type: "graph_frame", graph_revision: revision, spec: { traces: [] }, step: revision, phase: "running", ...extra }); } };
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
  f.deliver({ type: "selection", graph_revision: 1, traces: [], total: 0 });
  assert.equal(f.view.swaps, 1);
  assert.equal(f.view.mask, 0);
  f.paint();
  assert.equal(f.model.sent.at(-1).graph_revision, 2);
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
