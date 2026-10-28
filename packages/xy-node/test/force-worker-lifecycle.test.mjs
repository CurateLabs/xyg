import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { after, test } from "node:test";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// Real Workers and their exit events, with a private loader seam around the ABI.
// No test instrumentation or lifecycle diagnostics enter the public product API.
const dir = mkdtempSync(join(tmpdir(), "xyg-force-lifecycle-"));
after(() => rmSync(dir, { recursive: true, force: true }));
const scheduler = new URL("../src/force_scheduler.js", import.meta.url).href;
const abi = new URL("../src/abi.js", import.meta.url).href;
const write = (name, body) => writeFileSync(join(dir, name), body);
write("register.mjs", `
  import { register } from 'node:module';
  register('./loader.mjs', import.meta.url);
`);
write("loader.mjs", `
  export async function resolve(specifier, context, next) {
    if (context.parentURL === ${JSON.stringify(scheduler)}) {
      if (specifier === './abi.js') return {url: new URL('./abi.mjs', import.meta.url).href, shortCircuit: true};
      if (specifier === 'node:worker_threads') return {url: new URL('./workers.mjs', import.meta.url).href, shortCircuit: true};
    }
    return next(specifier, context);
  }
`);
write("trace.mjs", `
  import { appendFileSync } from 'node:fs';
  export const trace = (type, detail = {}) => appendFileSync(process.env.FORCE_TRACE, JSON.stringify({type, ...detail}) + '\\n');
  export const pause = ms => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
`);
write("workers.mjs", `
  import { Worker as NativeWorker, isMainThread, parentPort, workerData } from 'node:worker_threads';
  import { trace } from './trace.mjs';
  export * from 'node:worker_threads';
  const gate = new Int32Array(isMainThread ? new SharedArrayBuffer(4) : workerData.lifecycleGate);
  let activeWorker;
  if (!isMainThread) parentPort.on('message', msg => {
    if (msg.type === 'lifecycle-probe') {
      // Two explicit task turns let an unacknowledged old loop advance. The
      // repaired loop remains at its checkpoint but can still answer probes.
      setImmediate(() => setImmediate(() => {
        Atomics.store(gate, 0, 1);
        Atomics.notify(gate, 0);
      }));
    }
  });
  export function checkpointTurn() {
    activeWorker.postMessage({type: 'lifecycle-probe'});
    Atomics.wait(gate, 0, 0, 2000);
    trace('probe', {responded: Atomics.load(gate, 0) === 1});
  }
  export class Worker extends NativeWorker {
    constructor(filename, options) {
      super(filename, {...options, workerData: {...options.workerData, lifecycleGate: gate.buffer}});
      activeWorker = this;
      trace('spawn');
      this.on('message', msg => trace('message', {message: msg.type}));
      this.on('exit', code => trace('exit', {code}));
    }
    postMessage(msg, ...args) {
      trace('send', {message: msg.type, step: msg.step});
      // Simulate a worker that cannot process cancellation, while idle at a
      // checkpoint. Emergency termination must still await its real exit.
      if (process.env.FORCE_CASE === 'unresponsive') return;
      return super.postMessage(msg, ...args);
    }
    terminate() { trace('terminate'); return super.terminate(); }
  }
`);
write("abi.mjs", `
  import { trace, pause } from './trace.mjs';
  const native = process.env.FORCE_NATIVE === '1' ? await import(${JSON.stringify(abi)}) : undefined;
  let ticks = 0;
  export function graphForceCreate(...args) { const h = native?.graphForceCreate(...args) ?? 1; trace('create'); return h; }
  export function graphForceTick(...args) {
    trace('tick', {tick: ++ticks});
    if (!native) {
      pause(process.env.FORCE_CASE === 'timeout' ? 400 : 10);
      if (process.env.FORCE_CASE === 'native-error') throw new Error('native tick failed');
    }
    const result = native?.graphForceTick(...args) ?? { x: new Float64Array(2), y: new Float64Array(2), alpha: 1 };
    trace('tick-end', {tick: ticks});
    return result;
  }
  export function graphForceDestroy(...args) {
    const destroyed = native ? native.graphForceDestroy(...args) : true;
    if (!destroyed) throw new Error('native force handle was not destroyed');
    trace('destroy', {destroyed});
  }
`);
write("run.mjs", `
  import assert from 'node:assert/strict';
  import { runForceTicks } from ${JSON.stringify(scheduler)};
  import { trace, pause } from './trace.mjs';
  import { checkpointTurn } from './workers.mjs';
  const scenario = process.env.FORCE_CASE;
  const controller = new AbortController();
  const original = new Error('consumer failed');
  const args = {
    nNodes: 2, sources: new BigUint64Array([0n]), targets: new BigUint64Array([1n]),
    totalSteps: scenario === 'complete-failure' ? 1 : 4, chunkSteps: 1,
    signal: controller.signal,
    maxWallMs: scenario === 'timeout' ? 250 : 5000,
    onTick(state) {
      trace('callback', {step: state.step});
      if (scenario === 'mutated-step') state.step -= 1;
      if (scenario === 'callback' || scenario === 'complete-failure') {
        checkpointTurn();
        throw original;
      }
      if (scenario === 'abort') { checkpointTurn(); controller.abort(); }
      if (scenario === 'timeout' && process.env.FORCE_NATIVE === '1') pause(300);
    },
  };
  if (scenario === 'pre-abort') controller.abort();
  if (scenario === 'unresponsive') args.maxWallMs = 250;
  if (scenario === 'no-callback') delete args.onTick;
  try {
    const result = await runForceTicks(args);
    assert.ok(scenario === 'normal' || scenario === 'no-callback' || scenario === 'mutated-step');
    assert.equal(result.steps, 4);
    trace('settled', {failed: false});
  } catch (error) {
    if (scenario === 'callback' || scenario === 'complete-failure') assert.equal(error, original);
    else assert.match(error.message, scenario === 'native-error' ? /native tick failed/ : scenario === 'timeout' || scenario === 'unresponsive' ? /exceeded maxWallMs/ : /aborted/);
    trace('settled', {failed: true, identity: error === original});
  }
  // A callback arriving after rejection is an observable failure too.
  await new Promise(resolve => setTimeout(resolve, 30));
`);

function run(scenario, native = false) {
  const tracePath = join(dir, `trace-${scenario}-${native}.jsonl`);
  writeFileSync(tracePath, "");
  const child = spawnSync(process.execPath, ["--import", pathToFileURL(join(dir, "register.mjs")).href, join(dir, "run.mjs")], {
    env: { ...process.env, FORCE_CASE: scenario, FORCE_TRACE: tracePath, FORCE_NATIVE: native ? "1" : "0" },
    encoding: "utf8",
    timeout: 10_000,
  });
  const raw = readFileSync(tracePath, "utf8");
  assert.equal(child.status, 0, `${child.error ?? ""}\n${child.stdout}\n${child.stderr}\n${raw}`);
  const events = raw.trim().split("\n").filter(Boolean).map(line => JSON.parse(line));
  if (process.env.XYG_FORCE_LIFECYCLE_TRACE === "1") console.log(JSON.stringify({ scenario, native, events }));
  return events;
}

function cleanedBeforeSettlement(events, terminal) {
  const at = type => events.findIndex(event => event.type === type);
  assert.equal(events.filter(event => event.type === "destroy").length, 1, JSON.stringify(events));
  const receipt = events.findIndex(event => event.type === "message" && event.message === terminal);
  assert.ok(at("destroy") < receipt, JSON.stringify(events));
  assert.ok(receipt < at("exit") && at("exit") < at("settled"), JSON.stringify(events));
  assert.equal(events[at("exit")].code, 0);
  assert.ok(!events.some(event => event.type === "terminate"), JSON.stringify(events));
  assert.ok(!events.slice(at("settled") + 1).some(event => event.type === "callback"));
}

for (const scenario of ["callback", "complete-failure", "abort", "timeout", "normal", "no-callback", "mutated-step", "native-error"]) {
  test(`force worker lifecycle: ${scenario} waits for destroy and exit`, () => {
    const events = run(scenario);
    const cancelled = ["callback", "complete-failure", "abort", "timeout"].includes(scenario);
    const ticks = events.filter(event => event.type === "tick");
    if (cancelled) {
      assert.equal(ticks.length, 1, `parent rejection must prevent the next native tick: ${JSON.stringify(events)}`);
      assert.equal(events.filter(event => event.type === "callback").length, scenario === "timeout" ? 0 : 1);
      if (scenario !== "timeout") assert.ok(events.some(event => event.type === "probe" && event.responded));
      assert.ok(!events.some(event => event.type === "send" && event.message === "accept"));
    } else if (scenario !== "native-error") {
      assert.equal(ticks.length, 4);
      for (let i = 1; i < ticks.length; i++) {
        const accept = events.findIndex(event => event.type === "send" && event.message === "accept" && event.step === i);
        assert.ok(accept < events.indexOf(ticks[i]), "every native chunk needs parent acceptance");
      }
    }
    cleanedBeforeSettlement(events, cancelled ? "cancelled" : scenario === "native-error" ? "error" : "done");
  });
}

test("force worker lifecycle: pre-abort never allocates a worker", () => {
  assert.deepEqual(run("pre-abort"), [{ type: "settled", failed: true, identity: false }]);
});

test("force worker lifecycle: unresponsive worker uses bounded emergency termination and waits for exit", () => {
  const events = run("unresponsive");
  const at = type => events.findIndex(event => event.type === type);
  assert.ok(at("tick") >= 0 && at("terminate") > at("tick"));
  assert.ok(at("exit") > at("terminate") && at("settled") > at("exit"));
  const cancelled = events.findIndex(event => event.type === "send" && event.message === "cancel");
  assert.ok(!events.slice(cancelled + 1).some(event => event.type === "callback"));
  assert.equal(events.filter(event => event.type === "tick").length, 1);
});

// These still use the real ABI and Koffi inside real isolated Worker processes.
// The same trace wrapper observes actual destroy return and actual worker exit.
for (const scenario of ["callback", "complete-failure", "abort", "timeout", "normal", "no-callback", "mutated-step"]) {
  test(`force worker lifecycle with native ABI: ${scenario}`, () => {
    const events = run(scenario, true);
    const terminal = scenario === "timeout"
      ? events.find(event => event.type === "message" && ["cancelled", "error"].includes(event.message))?.message
      : ["callback", "complete-failure", "abort"].includes(scenario) ? "cancelled" : "done";
    cleanedBeforeSettlement(events, terminal);
    if (["callback", "complete-failure", "abort"].includes(scenario)) {
      assert.equal(events.filter(event => event.type === "tick").length, 1);
    }
  });
}
