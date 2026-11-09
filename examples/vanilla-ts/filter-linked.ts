/** Opt-in ordinary linked density. Author charts with the existing Python/Node
 * composition API and hydrate each payload with renderStandalone first.
 * This attaches those views; it does not build charts or create a renderer.
 * Serve the packaged Worker/WASM assets from the same application origin. */
import {
  attachFilterDashboard,
  createWasmFilterSession,
  createXygWasmWorker,
} from "../../packages/xy-client/dist/index.js";

export async function linkExistingCharts(
  views,
  columns: Record<string, Float64Array>,
) {
  const names = Object.keys(columns);
  const worker = createXygWasmWorker({
    workerUrl: "/assets/wasm-worker.js",
    wasm: "/assets/xyg-wasm.wasm",
    maxArenaBytes: 64 << 20,
  });
  const session = await createWasmFilterSession(worker, columns, {
    sourceId: 112n,
    epoch: 1n,
    firstRow: 0n,
    budgetBytes: 64n << 20n,
  });
  try {
    const dashboard = await attachFilterDashboard(
      session,
      views.map((view, i) => ({
        view,
        id: BigInt(i + 1),
        sourceId: 112n,
        epoch: 1n,
        dimension: names[i],
        cuts: [-1, 0, 1],
        step: 0.25,
        grid: {
          x: names[i],
          y: names[(i + 1) % names.length],
          width: 32,
          height: 32,
          xRange: [-2, 2],
          yRange: [-2, 2],
        },
      })),
    );
    return {
      session,
      dashboard,
      dispose: async () => {
        dashboard.destroy();
        await session.close();
      },
    };
  } catch (error) {
    await session.close();
    throw error;
  }
}
// Focus a plot with Tab: B creates a range, Home/End chooses its endpoint,
// arrows edit it, Enter commits, Escape cancels, Delete clears all ranges.
// Partial-bin boundaries are explicit exact scans (tier 2/fallback 1).
// This bounded example makes no 100M/50 FPS or competitor-performance claim.
