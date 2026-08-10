/**
 * Progressive force-layout tick helper (graph-mark.md §5).
 *
 * Hosts schedule Rust `xy_graph_force_tick` off the interactive paint path.
 * MVP default: chunked ticks via `setImmediate` on the Node event loop
 * (cooperative yielding). Prefer `worker_threads` for production so force
 * never stalls the event loop that serves uploads — set
 * `opts.mode = "worker"` when spawning dedicated workers.
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
 * @param {"immediate"|"worker"} [args.mode="immediate"]
 * @param {(state: {x: Float64Array, y: Float64Array, alpha: number, step: number}) => void} [args.onTick]
 * @param {AbortSignal} [args.signal]
 * @returns {Promise<{x: Float64Array, y: Float64Array, alpha: number, steps: number}>}
 */
export async function runForceTicks(args) {
  const mode = args.mode ?? "immediate";
  if (mode === "worker") {
    return runForceTicksInWorker(args);
  }
  return runForceTicksImmediate(args);
}

function yieldEventLoop() {
  return new Promise((resolve) => {
    setImmediate(resolve);
  });
}

async function runForceTicksImmediate(args) {
  const nNodes = args.nNodes;
  const totalSteps = Math.max(1, Number(args.totalSteps ?? 300));
  const chunkSteps = Math.max(1, Number(args.chunkSteps ?? 10));
  const handle = graphForceCreate(nNodes, args.sources, args.targets, {
    x: args.x,
    y: args.y,
    seed: args.seed ?? 0,
    algorithm: args.algorithm ?? args.layout ?? "force",
  });
  let step = 0;
  let last = { x: new Float64Array(nNodes), y: new Float64Array(nNodes), alpha: 1.0 };
  try {
    while (step < totalSteps) {
      if (args.signal?.aborted) {
        throw new Error("force ticks aborted");
      }
      const take = Math.min(chunkSteps, totalSteps - step);
      last = graphForceTick(handle, nNodes, take);
      step += take;
      if (typeof args.onTick === "function") {
        args.onTick({ x: last.x, y: last.y, alpha: last.alpha, step });
      }
      if (step < totalSteps) {
        await yieldEventLoop();
      }
    }
  } finally {
    graphForceDestroy(handle);
  }
  return { x: last.x, y: last.y, alpha: last.alpha, steps: step };
}

function runForceTicksInWorker(args) {
  const {
    onTick: _onTick,
    signal,
    mode: _mode,
    ...serializable
  } = args;
  return new Promise((resolve, reject) => {
    const worker = new Worker(selfPath, {
      workerData: { type: "force_ticks", args: serializable },
    });
    const onAbort = () => {
      worker.terminate().catch(() => {});
      reject(new Error("force ticks aborted"));
    };
    if (signal) {
      if (signal.aborted) {
        onAbort();
        return;
      }
      signal.addEventListener("abort", onAbort, { once: true });
    }
    worker.on("message", (msg) => {
      if (msg?.type === "done") {
        resolve(msg.result);
      } else if (msg?.type === "tick" && typeof args.onTick === "function") {
        args.onTick(msg.state);
      } else if (msg?.type === "error") {
        reject(new Error(msg.message ?? "worker force tick failed"));
      }
    });
    worker.on("error", reject);
    worker.on("exit", (code) => {
      if (signal) signal.removeEventListener("abort", onAbort);
      if (code !== 0) {
        reject(new Error(`force tick worker exited with code ${code}`));
      }
    });
  });
}

// Worker entry — only active when this module is loaded as a Worker.
if (!isMainThread && parentPort && workerData?.type === "force_ticks") {
  runForceTicksImmediate(workerData.args)
    .then((result) => {
      // Transfer typed-array buffers back to the parent.
      parentPort.postMessage(
        { type: "done", result },
        [result.x.buffer, result.y.buffer],
      );
    })
    .catch((err) => {
      parentPort.postMessage({ type: "error", message: String(err?.message ?? err) });
    });
}
