import { FilterSessionClient } from "../../packages/xy-node/src/filter-protocol.js";
import type { XygWasmWorker } from "./47_wasm";
export {
  filterRequest,
  decodeFilterReply,
  FilterTierCError,
} from "../../packages/xy-node/src/filter-protocol.js";
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
  const client = new FilterSessionClient(
    (packet: Uint8Array) => worker.filterCommand(packet.slice().buffer),
    () => worker.dispose(),
    columns,
    options,
  );
  try {
    await client.initialize(columns);
    return client;
  } catch (error) {
    client.close();
    throw error;
  }
}
