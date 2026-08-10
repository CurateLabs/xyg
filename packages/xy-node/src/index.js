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

export {
  scatterChart,
  lineChart,
  histogramChart,
  graphChart,
} from "./charts.js";
