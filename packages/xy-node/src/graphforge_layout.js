/** Node live scheduling only; spec/design/graphforge-node-scheduling.md. */
import { Worker } from "node:worker_threads";
import { randomUUID } from "node:crypto";

const error = (code, message) => Object.assign(new Error(message), { code });

/** One live view. Each render supersedes the previous job, including its callbacks. */
export class GraphForgeLayoutController {
  #revision = 0;
  #identity = randomUUID();
  #active;
  #jobs = new Set();
  #disposed = false;
  #disposal;

  get revision() { return this.#revision; }

  render(input, options = {}) {
    if (this.#disposed) return Promise.reject(error("GF_LAYOUT_DISPOSED", "GraphForge view is disposed"));
    const { signal, onPayload, maxWallMs = 30_000, ...opts } = options;
    if (signal !== undefined && (typeof signal?.aborted !== "boolean"
      || typeof signal.addEventListener !== "function" || typeof signal.removeEventListener !== "function")) {
      return Promise.reject(new TypeError("signal must be an AbortSignal"));
    }
    if (onPayload !== undefined && typeof onPayload !== "function") return Promise.reject(new TypeError("onPayload must be a function"));
    if (!Number.isFinite(maxWallMs) || maxWallMs <= 0 || maxWallMs > 300_000) {
      return Promise.reject(new RangeError("maxWallMs must be in (0, 300000]"));
    }
    if (this.#revision === 0xffffffff) return Promise.reject(new RangeError("GraphForge view revision exhausted; create a new owner"));
    this.#active?.cancel(error("GF_LAYOUT_SUPERSEDED", "GraphForge layout superseded"));
    const revision = ++this.#revision;
    // A revision is meaningful only within its owner; never accept a caller job ID.
    const jobId = `${this.#identity}:${revision}`;
    let worker, outcome, last, timer, grace;
    let settle;
    const promise = new Promise((resolve, reject) => { settle = { resolve, reject }; });
    const live = () => !outcome && this.#active === job && !this.#disposed;
    const stop = () => { clearTimeout(timer); signal?.removeEventListener("abort", abort); };
    const cancel = cause => {
      if (outcome?.failed) return;
      outcome = { failed: true, value: cause };
      stop();
      if (worker) {
        worker.postMessage({ type: "cancel" });
        // Allow the existing force scheduler its own native cleanup/exit grace.
        grace ??= setTimeout(() => { worker.terminate().catch(() => {}); }, 2500);
      }
    };
    const abort = () => cancel(error("GF_LAYOUT_ABORTED", "GraphForge layout aborted"));
    const job = { promise, cancel };
    this.#active = job;
    this.#jobs.add(job);
    const finish = () => {
      stop(); clearTimeout(grace);
      if (this.#active === job) this.#active = undefined;
      this.#jobs.delete(job);
      if (outcome?.failed) settle.reject(outcome.value);
      else settle.resolve(last);
    };
    if (signal?.aborted) { abort(); finish(); return promise; }
    signal?.addEventListener("abort", abort, { once: true });
    timer = setTimeout(() => cancel(error("GF_LAYOUT_TIMEOUT", "GraphForge layout exceeded maxWallMs")), maxWallMs);
    try {
      // Composition instances contain lazy accessors: send only their canonical
      // document. Raw input is cloned once by Worker; no host-side O(source) pack.
      const request = input?.bytes instanceof Uint8Array ? { documentBytes: input.bytes } : { input };
      worker = new Worker(new URL("./graphforge_layout_worker.js", import.meta.url), {
        workerData: { ...request, opts, revision, jobId, maxWallMs },
      });
    } catch (cause) { cancel(cause); finish(); return promise; }
    worker.on("message", msg => {
      if (!live() || msg?.revision !== revision || msg?.jobId !== jobId) return;
      if (msg.type === "payload") {
        const payload = msg.payload;
        if (payload.revision !== revision || payload.jobId !== jobId) {
          cancel(error("GF_LAYOUT_PROTOCOL", "GraphForge checkpoint identity mismatch")); return;
        }
        last = payload;
        const checkpointStep = payload.step;
        // One presentation at a time. A pending callback never blocks cancellation.
        // ACK only after the consumer accepts; the bridge keeps the latest update.
        Promise.resolve().then(() => live() ? onPayload?.(payload) : undefined).then(() => {
          if (live()) worker.postMessage({ type: "accept", revision, jobId, step: checkpointStep });
        }, cause => { if (live()) cancel(cause); });
      } else if (msg.type === "done") {
        outcome = { failed: false }; stop();
      } else if (msg.type === "error") {
        cancel(Object.assign(new Error(msg.message), { name: msg.name ?? "Error", code: msg.code,
          layer: msg.layer, field: msg.field }));
      }
    });
    worker.on("error", cause => cancel(cause));
    worker.on("exit", code => {
      if (!outcome || (!outcome.failed && code !== 0)) outcome = { failed: true,
        value: error("GF_LAYOUT_WORKER_EXIT", `GraphForge worker exited with code ${code}`) };
      finish();
    });
    return promise;
  }

  /** Cancel the current job and settle only after all worker exits. */
  async cancel() {
    this.#active?.cancel(error("GF_LAYOUT_ABORTED", "GraphForge layout cancelled"));
    await Promise.allSettled([...this.#jobs].map(job => job.promise));
  }

  /** Terminal and idempotent. A replacement webview needs a new owner. */
  dispose() {
    if (!this.#disposal) {
      this.#disposed = true;
      for (const job of this.#jobs) job.cancel(error("GF_LAYOUT_DISPOSED", "GraphForge view disposed"));
      this.#disposal = Promise.allSettled([...this.#jobs].map(job => job.promise)).then(() => undefined);
    }
    return this.#disposal;
  }
}

/** Default LIVE payload API. Static/batch callers explicitly use graphforgeStaticPayload. */
export function graphforgeWebviewPayload(owner, input, options = {}) {
  if (!(owner instanceof GraphForgeLayoutController)) {
    return Promise.reject(new TypeError("graphforgeWebviewPayload requires a GraphForgeLayoutController owner"));
  }
  return owner.render(input, options);
}
