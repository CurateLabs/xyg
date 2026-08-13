/**
 * VS Code extension surface for `@curatelabs/xyg-node`.
 *
 * Architecture note:
 * - The **extension host** is a Node process — import this package
 *   (`createEngine`, chart builders, `abiVersion`, graph layout) there.
 * - A **webview** is a browser context; it must use the browser/WebGL client
 *   (`python/xy/static` / `window.xy`), not this Node binding.
 * - Typical flow: extension host runs Rust layouts via the C ABI, encodes
 *   §29 f32 buffers, and posts them into the webview for paint. Do not expect
 *   `window` / `document` in this module (or anywhere under `@curatelabs/xyg-node`).
 *
 * This file is a thin re-export of the stable public API.
 */

export {
  createEngine,
  abiVersion,
  figure,
  Figure,
  PROTOCOL_VERSION,
  scatterChart,
  lineChart,
  histogramChart,
  areaChart,
  barChart,
  columnChart,
  boxChart,
  ecdfChart,
  segmentsChart,
  heatmapChart,
  hexbinChart,
  violinChart,
  contourChart,
  errorbarChart,
  errorBandChart,
  stemChart,
  stepChart,
  stairsChart,
  triangleMeshChart,
  radarChart,
  graphChart,
  sankeyChart,
  pieChart,
  windRoseChart,
  polarChart,
  facetChart,
  composeSankey,
  composeRibbon,
  composeGraph,
  composeContour,
  composeErrorbar,
  composeErrorBand,
  composeStem,
  composeStep,
  composeStairs,
  composeTriangleMesh,
  composeRadar,
  runLayout,
  normalizeGraphInputs,
  runForceAnimation,
  GRAPH_LAYOUT_IDS,
  graphLayoutId,
  graphForceCreate,
  graphForceTick,
  graphForceDestroy,
  SCATTER_DENSITY_THRESHOLD,
  DENSITY_GRID,
  shouldUseDensity,
  PYRAMID_MIN_POINTS,
  pyramidBuild,
  pyramidCompose,
  pyramidFree,
  shouldUsePyramid,
} from "./index.js";
