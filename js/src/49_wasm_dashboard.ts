import type { XygWasmDashboardPlan, XygWasmWorker } from "./47_wasm";
import type { GLHost } from "./42_glhost";

export interface XygWasmDashboardResource {
  stableId: bigint;
  derivedBytes: bigint;
  lastUsed: bigint;
  visible?: boolean;
  interacting?: boolean;
}

export function encodeWasmDashboardPlan(resources: readonly XygWasmDashboardResource[], budgetBytes: bigint): ArrayBuffer {
  const maxU64 = 0xffffffffffffffffn;
  if (!Array.isArray(resources) || resources.length > 4096) throw new RangeError("dashboard resource plan exceeds its bound");
  if (typeof budgetBytes !== "bigint" || budgetBytes < 0n || budgetBytes > maxU64) throw new TypeError("dashboard budgetBytes must be a u64 bigint");
  for (const resource of resources) {
    if (resource === null || typeof resource !== "object" || Array.isArray(resource)) throw new TypeError("dashboard resources must be objects");
    for (const field of ["stableId", "derivedBytes", "lastUsed"] as const) {
      const value = resource[field];
      if (typeof value !== "bigint" || value < 0n || value > maxU64) throw new TypeError(`dashboard ${field} must be a u64 bigint`);
    }
    for (const field of ["visible", "interacting"] as const) {
      const value = resource[field];
      if (value !== undefined && typeof value !== "boolean") throw new TypeError(`dashboard ${field} must be boolean or undefined`);
    }
  }
  const buffer = new ArrayBuffer(32 + resources.length * 32), bytes = new Uint8Array(buffer), view = new DataView(buffer);
  bytes.set([88, 89, 68, 80]); view.setUint32(4, 1, true); view.setUint32(8, 32, true); view.setUint32(12, resources.length, true); view.setBigUint64(16, budgetBytes, true);
  resources.forEach((resource, index) => {
    const at = 32 + index * 32; view.setBigUint64(at, resource.stableId, true); view.setBigUint64(at + 8, resource.derivedBytes, true); view.setBigUint64(at + 16, resource.lastUsed, true);
    bytes[at + 24] = Number(resource.visible === true) | (Number(resource.interacting === true) << 1);
  });
  return buffer;
}

export function decodeWasmDashboardPlan(buffer: ArrayBuffer, count: number): XygWasmDashboardPlan {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength !== 24 + count) throw new TypeError("Rust dashboard plan length is invalid");
  const bytes = new Uint8Array(buffer), view = new DataView(buffer);
  if (bytes.subarray(0, 4).join(",") !== "88,89,68,79" || view.getUint32(4, true) !== 1 || view.getUint32(8, true) !== count || view.getUint32(12, true) !== 0 || bytes.subarray(24).some((value) => value > 1)) throw new TypeError("Rust dashboard plan is malformed");
  return Object.freeze({ retainedBytes: view.getBigUint64(16, true), retained: Object.freeze(Array.from(bytes.subarray(24), Boolean)) });
}

export async function planWasmDashboardResources(worker: XygWasmWorker, resources: readonly XygWasmDashboardResource[], budgetBytes: bigint): Promise<XygWasmDashboardPlan> {
  const result = await worker.dashboardPlan(encodeWasmDashboardPlan(resources, budgetBytes)).result;
  return decodeWasmDashboardPlan(result, resources.length);
}

export async function applyWasmDashboardResourceBudget(
  worker: XygWasmWorker,
  host: GLHost,
  budgetBytes: bigint,
): Promise<Readonly<{
  plan: XygWasmDashboardPlan;
  applied: boolean;
  beforeBytes: bigint;
  afterBytes: bigint;
}>> {
  if (!host || typeof host.dashboardResourceSnapshot !== "function"
      || typeof host.applyDashboardResidency !== "function") {
    throw new TypeError("a shared GLHost is required");
  }
  // Rendering may finish a transition while Rust is planning. Re-snapshot a
  // bounded number of times so one ordinary lifecycle edge does not turn a
  // valid public request into a no-op; every individual apply remains atomic.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const snapshot = host.dashboardResourceSnapshot();
    const beforeBytes = snapshot.resources.reduce((sum, resource) => sum + resource.derivedBytes, 0n);
    const plan = await planWasmDashboardResources(worker, snapshot.resources, budgetBytes);
    const applied = host.applyDashboardResidency(snapshot, plan.retained);
    if (applied) {
      const afterBytes = host.dashboardResourceSnapshot().resources.reduce(
        (sum, resource) => sum + resource.derivedBytes, 0n,
      );
      return Object.freeze({ plan, applied, beforeBytes, afterBytes });
    }
    if (attempt === 2) return Object.freeze({ plan, applied, beforeBytes, afterBytes: beforeBytes });
  }
  throw new Error("unreachable dashboard admission retry state");
}

export interface XygWasmDashboardAdmissionController {
  readonly settled: Promise<void>;
  request(): void;
  dispose(): void;
}

/** Keep one shared host under a Rust-owned resource budget as its measured
 * client state changes. Notifications are coalesced and never overlap; a
 * change during an in-flight plan schedules exactly one fresh snapshot. */
export function watchWasmDashboardResourceBudget(
  worker: XygWasmWorker,
  host: GLHost,
  budgetBytes: bigint,
): XygWasmDashboardAdmissionController {
  // Validate before installing a lifecycle listener.
  encodeWasmDashboardPlan([], budgetBytes);
  if (!host || typeof host.subscribeDashboardResources !== "function") {
    throw new TypeError("a shared GLHost is required");
  }
  let disposed = false, scheduled = false, running = false, rerun = false;
  let resolveSettled: (() => void) | null = null;
  let rejectSettled: ((reason: unknown) => void) | null = null;
  let settled = Promise.resolve();
  const request = () => {
    if (disposed) return;
    if (running) { rerun = true; return; }
    if (scheduled) return;
    scheduled = true;
    settled = new Promise<void>((resolve, reject) => { resolveSettled = resolve; rejectSettled = reject; });
    // Automatic passes may happen long after the caller last awaited
    // `settled`; mark the rejection observed while preserving it for callers
    // that do await the original promise.
    void settled.catch(() => {});
    queueMicrotask(async () => {
      scheduled = false;
      if (disposed) { resolveSettled?.(); return; }
      running = true;
      let failure: unknown = null;
      try {
        do {
          rerun = false;
          await applyWasmDashboardResourceBudget(worker, host, budgetBytes);
        } while (rerun && !disposed);
      } catch (error) {
        failure = error;
        rejectSettled?.(error);
      } finally {
        running = false;
        const resolve = resolveSettled;
        resolveSettled = null;
        rejectSettled = null;
        if (failure === null) resolve?.();
      }
    });
  };
  const unsubscribe = host.subscribeDashboardResources(request);
  request();
  return Object.freeze({
    get settled() { return settled; },
    request,
    dispose() {
      if (disposed) return;
      disposed = true;
      rerun = false;
      unsubscribe();
      resolveSettled?.();
      resolveSettled = null;
      rejectSettled = null;
    },
  });
}
