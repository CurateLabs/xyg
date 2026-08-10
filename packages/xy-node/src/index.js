/**
 * @xy/node public surface — ABI bindings + host composition helpers.
 */
export {
  encodeF32,
  encodeF32Values,
  m4Points,
  m4Indices,
  minMax,
  isSorted,
  histogramUniform,
  histogramEdges,
  hexbin,
  violinDensity,
  boxStats,
  quantiles,
  weightedEcdf,
  heatmapRgba,
  windRoseBins,
  contourfDensify,
  normalizeF32,
  Column,
  PROTOCOL_VERSION,
  DECIMATION_THRESHOLD,
  SCATTER_DENSITY_THRESHOLD,
  DIRECT_SOFT_CEILING,
  F32_SAFE_MAG,
  LOG_FAMILY_SCALES,
  DEFAULT_PALETTE,
  geometryOffset,
  pinsOffsetToZero,
  f32SafeScale,
} from "./encode.js";

export {
  nativeLibraryPath,
  GRAPH_LAYOUT_PRESET,
  GRAPH_LAYOUT_GRID,
  GRAPH_LAYOUT_CIRCLE,
  GRAPH_LAYOUT_FORCE,
  GRAPH_LAYOUT_BREADTHFIRST,
  GRAPH_LAYOUT_AUTO,
  GRAPH_LAYOUT_RADIAL,
  GRAPH_LAYOUT_CONCENTRIC,
  GRAPH_LAYOUT_HIERARCHICAL,
  GRAPH_LAYOUT_IDS,
  SANKEY_ALIGN_IDS,
  SankeyLayoutError,
  abiVersion,
  graphLayout,
  graphForceCreate,
  graphForceTick,
  graphForceDestroy,
  graphLodDecision,
  graphClusterAggregate,
  graphBuildRender,
  graphSampleEdges,
  graphBuildCsr,
  sankeyLayout,
  graphLayoutId,
  sankeyAlignId,
} from "./abi.js";

export {
  DEFAULT_LAYOUT,
  normalizeGraphInputs,
  runLayout,
  edgeSegmentsFromPositions,
  composeGraph,
} from "./graph.js";

export { Figure, PayloadWriter, figure } from "./figure.js";

export { runForceTicks } from "./force_scheduler.js";

export { composeSankey } from "./sankey.js";

export {
  composeScatter,
  attachScatter,
  encodeScatterPositions,
} from "./marks/scatter.js";

export {
  composeLine,
  attachLine,
  prepareLineSeries,
  m4DecimateLine,
  F64_EPS,
} from "./marks/line.js";

export {
  composeHistogram,
  attachHistogram,
} from "./marks/histogram.js";

export { composeArea, attachArea } from "./marks/area.js";

export {
  composeBar,
  attachBar,
  composeColumn,
  attachColumn,
} from "./marks/bar.js";

export { composeBox, attachBox } from "./marks/box.js";

export { composeEcdf, attachEcdf, computeEcdf } from "./marks/ecdf.js";

export { composeSegments, attachSegments } from "./marks/segments.js";

export { composeHeatmap, attachHeatmap } from "./marks/heatmap.js";

export { composeHexbin, attachHexbin } from "./marks/hexbin.js";

export { composeViolin, attachViolin } from "./marks/violin.js";

export {
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
  graphChart,
} from "./charts.js";
