import { FilterSessionClient } from "../../packages/xy-node/src/filter-protocol.js";
import { claimFilterWorker, type XygWasmWorker } from "./47_wasm";
export {
  filterRequest,
  decodeFilterReply,
  FilterTierCError,
} from "../../packages/xy-node/src/filter-protocol.js";
/** Bind a genuine native registration to a caller-owned binary transport.
 * The native endpoint advances Rust jobs; the browser retains no source arrays. */
export function createFilterSession(
  execute: (packet: Uint8Array) => Promise<Uint8Array>,
  close: () => Promise<void>,
  registration: { names: string[]; packet: Uint8Array; budgetBytes: bigint },
) {
  return FilterSessionClient.fromRegistration(execute, close, registration);
}
/** One dedicated ordinary Worker owns the source/session; close disposes it.
 * Uses the same public programmatic protocol as Chart.filter_session/Node.
 * attachFilterDashboard binds existing composed views to its count planes. */
export async function createWasmFilterSession(
  worker: XygWasmWorker,
  columns: Record<string, ArrayLike<number>>,
  options: {
    sourceId: bigint;
    epoch?: bigint;
    firstRow?: bigint;
    budgetBytes: bigint;
  },
) {
  await worker.ready;
  const lane=claimFilterWorker(worker);
  try {
    const client=new FilterSessionClient(lane.execute,lane.close,columns,options);
    await client.initialize(columns);
    return client;
  } catch (error) {
    // Failure after a successful claim settles after its owned Worker drains.
    // A cleanup failure must not replace the original initialization failure.
    try { await lane.close(); } catch { /* owning Worker is already terminal */ }
    throw error;
  }
}
