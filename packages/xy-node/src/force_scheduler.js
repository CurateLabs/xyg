/**
 * Progressive force-layout tick helper (graph-mark.md §5).
 *
 * Hosts schedule Rust `xyg_graph_force_tick` off the interactive paint path.
 * The default is a dedicated `worker_threads` job so force never stalls the
 * event loop that serves uploads. `mode = "immediate"` is an explicit testing
 * or batch-only escape hatch; interactive hosts must keep the default.
 *
 * Never run force on the browser JS main thread; this module is Node-host only.
 */

import { Worker, isMainThread, parentPort, workerData } from "node:worker_threads";
import { fileURLToPath } from "node:url";
import {
  graphForceCreate,
  graphForceDestroy,
  graphForceTick,
} from "./abi.js";

const selfPath = fileURLToPath(import.meta.url);

/**
 * Run progressive force ticks, yielding between chunks.
 *
 * @param {object} args
 * @param {number} args.nNodes
 * @param {BigUint64Array|ArrayLike} args.sources
 * @param {BigUint64Array|ArrayLike} args.targets
 * @param {number} [args.totalSteps=300]
 * @param {number} [args.chunkSteps=10] — ticks per yield
 * @param {number|bigint} [args.seed=0]
 * @param {Float64Array} [args.x]
 * @param {Float64Array} [args.y]
 * @param {"immediate"|"worker"} [args.mode="worker"]
 * @param {(state: {x: Float64Array, y: Float64Array, alpha: number, step: number, phase: "initial"|"update"|"complete", revision: number, jobId: string|number|undefined}) => void} [args.onTick]
 * @param {AbortSignal} [args.signal]
 * @param {string|number} [args.jobId]
 * @param {number} [args.revision=1]
 * @param {number} [args.maxWallMs=30000]
 * @returns {Promise<{x: Float64Array, y: Float64Array, alpha: number, steps: number}>}
 */
export async function runForceTicks(args) {
  if (!args || typeof args !== "object") throw new TypeError("force scheduler arguments are required");
  const maxWallMs = Number(args.maxWallMs ?? 30_000);
  if (!Number.isFinite(maxWallMs) || maxWallMs <= 0 || maxWallMs > 300_000) throw new RangeError("maxWallMs must be in (0, 300000]");
  if (args.onTick !== undefined && typeof args.onTick !== "function") throw new TypeError("onTick must be a function");
  if (args.signal !== undefined && (typeof args.signal?.aborted !== "boolean"
      || typeof args.signal.addEventListener !== "function"
      || typeof args.signal.removeEventListener !== "function")) {
    throw new TypeError("signal must be an AbortSignal");
  }
  if (args.jobId !== undefined && typeof args.jobId !== "string" && typeof args.jobId !== "number") throw new TypeError("jobId must be a string or number");
  args = { ...args, maxWallMs };
  const mode = args.mode ?? "worker";
  if (mode === "worker") {
    return runForceTicksInWorker(args);
  }
  if (mode === "immediate") return runForceTicksImmediate(args);
  throw new RangeError("mode must be 'worker' or explicit batch-only 'immediate'");
}

function yieldEventLoop() {
  return new Promise((resolve) => {
    setImmediate(resolve);
  });
}

async function runForceTicksImmediate(args, acceptTick) {
  const nNodes = Number(args.nNodes);
  const totalSteps = Number(args.totalSteps ?? 300);
  const chunkSteps = Number(args.chunkSteps ?? 10);
  const revision = Number(args.revision ?? 1);
  const maxWallMs = Number(args.maxWallMs ?? 30_000);
  if (!Number.isSafeInteger(nNodes) || nNodes < 0 || nNodes > 1_000_000) throw new RangeError("nNodes must be an integer in 0..1000000");
  if (!Number.isInteger(totalSteps) || totalSteps <= 0 || totalSteps > 1_000_000) throw new RangeError("totalSteps must be an integer in 1..1000000");
  if (!Number.isInteger(chunkSteps) || chunkSteps <= 0 || chunkSteps > 1000) throw new RangeError("chunkSteps must be an integer in 1..1000");
  if (!Number.isInteger(revision) || revision <= 0 || revision > 0xffffffff) throw new RangeError("revision must be a nonzero u32");
  if (!Number.isFinite(maxWallMs) || maxWallMs <= 0 || maxWallMs > 300_000) throw new RangeError("maxWallMs must be in (0, 300000]");
  const started = performance.now();
  const handle = graphForceCreate(nNodes, args.sources, args.targets, {
    x: args.x,
    y: args.y,
    seed: args.seed ?? 0,
    algorithm: args.algorithm ?? args.layout ?? "force",
    cose: args.cose,
    pinned: args.pinned,
    parents: args.parents,
  });
  let step = 0;
  let last = { x: new Float64Array(nNodes), y: new Float64Array(nNodes), alpha: 1.0 };
  try {
    while (step < totalSteps) {
      if (args.signal?.aborted) {
        throw new Error("force ticks aborted");
      }
      if (performance.now() - started > maxWallMs) throw new Error("force ticks exceeded maxWallMs");
      const take = step === 0 ? 1 : Math.min(chunkSteps, totalSteps - step);
      last = graphForceTick(handle, nNodes, take);
      step += take;
      const phase = step >= totalSteps || last.alpha < 0.001 ? "complete" : step === 1 ? "initial" : "update";
      const state = { x: last.x, y: last.y, alpha: last.alpha, step, phase, revision, jobId: args.jobId };
      if (acceptTick) {
        // A worker must not enter the next native chunk until the parent has
        // accepted this checkpoint (graph-mark.md §5).
        await acceptTick(state);
      } else if (typeof args.onTick === "function") {
        args.onTick(state);
      }
      if (phase === "complete") break;
      if (step < totalSteps) {
        await yieldEventLoop();
      }
    }
  } finally {
    graphForceDestroy(handle);
  }
  return { x: last.x, y: last.y, alpha: last.alpha, steps: step, phase: "complete", revision, jobId: args.jobId };
}

// Cancellation normally finishes at a native chunk boundary. Only an
// unresponsive worker may be terminated after this additional cleanup grace.
const WORKER_CLEANUP_GRACE_MS = 1_000;

function runForceTicksInWorker(args) {
  const {
    onTick: _onTick,
    signal,
    mode: _mode,
    ...serializable
  } = args;
  return new Promise((resolve, reject) => {
    let outcome;
    let worker;
    let cleanupTimeout;
    const stopListening = () => {
      clearTimeout(timeout);
      if (signal) signal.removeEventListener("abort", onAbort);
    };
    const finish = () => {
      stopListening();
      clearTimeout(cleanupTimeout);
      if (outcome.failed) reject(outcome.value);
      else resolve(outcome.value);
    };
    const awaitExit = () => {
      if (cleanupTimeout !== undefined) return;
      cleanupTimeout = setTimeout(() => {
        // Emergency escape only: normal cancellation must never interrupt FFI.
        worker.terminate().catch(() => {});
      }, WORKER_CLEANUP_GRACE_MS);
    };
    const cancel = (cause) => {
      if (outcome) return;
      // Keep the first cause, including the exact object thrown by onTick.
      // Suppress all further callbacks while the worker destroys its handle.
      outcome = { failed: true, value: cause };
      stopListening();
      if (!worker) {
        finish();
        return;
      }
      worker.postMessage({ type: "cancel" });
      awaitExit();
    };
    const onAbort = () => cancel(new Error("force ticks aborted"));
    const timeout = setTimeout(() => {
      cancel(new Error("force ticks exceeded maxWallMs"));
    }, Number(args.maxWallMs ?? 30_000));
    if (signal) {
      if (signal.aborted) {
        onAbort();
        return;
      }
      signal.addEventListener("abort", onAbort, { once: true });
    }
    try {
      worker = new Worker(selfPath, {
        workerData: { type: "force_ticks", args: serializable },
      });
    } catch (cause) {
      outcome = { failed: true, value: cause };
      finish();
      return;
    }
    worker.on("message", (msg) => {
      if (outcome) return;
      if (msg?.type === "done" || msg?.type === "error") {
        // These are sent only after graphForceDestroy. Still wait for exit so
        // no native environment remains live when the public promise settles.
        outcome = msg.type === "done"
          ? { failed: false, value: msg.result }
          : { failed: true, value: new Error(msg.message ?? "worker force tick failed") };
        stopListening();
        awaitExit();
      } else if (msg?.type === "tick") {
        const checkpointStep = msg.state.step;
        try {
          if (typeof args.onTick === "function") args.onTick(msg.state);
        } catch (cause) {
          cancel(cause);
        }
        // The callback can synchronously abort the signal as well as throw.
        if (!outcome) worker.postMessage({ type: "accept", step: checkpointStep });
      }
    });
    worker.on("error", (cause) => {
      if (!outcome) outcome = { failed: true, value: cause };
      stopListening();
      awaitExit();
    });
    worker.on("exit", (code) => {
      if (!outcome || (!outcome.failed && code !== 0)) outcome = { failed: true, value: new Error(`force tick worker exited with code ${code}`) };
      finish();
    });
  });
}

// Worker entry — only active when this module is loaded as a Worker.
if (!isMainThread && parentPort && workerData?.type === "force_ticks") {
  const controller = new AbortController();
  let checkpoint;
  parentPort.on("message", (msg) => {
    if (msg?.type === "cancel") {
      controller.abort();
      checkpoint?.reject(new Error("force ticks aborted"));
      checkpoint = undefined;
    } else if (msg?.type === "accept" && msg.step === checkpoint?.step) {
      checkpoint.resolve();
      checkpoint = undefined;
    }
  });
  runForceTicksImmediate({
    ...workerData.args,
    signal: controller.signal,
  }, (state) => new Promise((resolve, reject) => {
    checkpoint = { step: state.step, resolve, reject };
    parentPort.postMessage({ type: "tick", state });
  }))
    .then((result) => {
      // Transfer typed-array buffers back to the parent after handle cleanup.
      parentPort.postMessage(
        { type: "done", result },
        [result.x.buffer, result.y.buffer],
      );
    })
    .catch((err) => {
      // runForceTicksImmediate's finally destroys the native handle before
      // acknowledging cancellation or reporting any native/validation error.
      parentPort.postMessage(controller.signal.aborted
        ? { type: "cancelled" }
        : { type: "error", message: String(err?.message ?? err) });
    })
    .finally(() => parentPort.close());
}
