/**
 * @curatelabs/xyg-node public surface — ABI bindings + host composition helpers.
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
  contourfBands,
  barStack,
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
  xyStreamNew,
  xyStreamAppend,
  xyStreamSeal,
  xyStreamFree,
  xyStreamLen,
  xyStreamCapacity,
  xyStreamCopy,
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
  GRAPH_LAYOUT_BARNES_HUT,
  GRAPH_LAYOUT_SPRING,
  GRAPH_LAYOUT_FORCEATLAS2,
  GRAPH_LAYOUT_KAMADA_KAWAI,
  GRAPH_LAYOUT_YIFANHU,
  GRAPH_LAYOUT_LINLOG,
  GRAPH_LAYOUT_STRESS,
  GRAPH_LAYOUT_IDS,
  GRAPH_PROGRESSIVE_FORCE,
  SANKEY_ALIGN_IDS,
  SankeyLayoutError,
  abiVersion,
  graphLayout,
  graphForceCreate,
  graphForceTick,
  graphForceDestroy,
  graphIsProgressiveForce,
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

import { Figure, PayloadWriter, figure } from "./figure.js";

/** Stable engine entry — alias of {@link figure} for Node servers / VS Code hosts. */
export function createEngine(opts = {}) {
  return figure(opts);
}

export { Figure, PayloadWriter, figure };

export { runForceTicks } from "./force_scheduler.js";

export { composeSankey } from "./sankey.js";

export { composeRibbon, attachRibbon } from "./marks/ribbon.js";

export {
  parseCssColor,
  cssColorsToRgba8,
  resolveColorChannel,
} from "./color.js";

export {
  distributionGroups,
  categoryPositions,
  splitByPositions,
} from "./marks/distribution.js";

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
  composeContour,
  attachContour,
} from "./marks/contour.js";

export {
  composeErrorbar,
  attachErrorbar,
} from "./marks/errorbar.js";

export {
  composeErrorBand,
  attachErrorBand,
} from "./marks/error_band.js";

export { composeStem, attachStem } from "./marks/stem.js";

export {
  composeStep,
  attachStep,
  composeStairs,
  attachStairs,
} from "./marks/step.js";

export {
  composeTriangleMesh,
  attachTriangleMesh,
} from "./marks/triangle_mesh.js";

export { composeRadar, attachRadar } from "./marks/radar.js";

export {
  composePie,
  composeWindRose,
  composeFacet,
  shareFacetAxes,
} from "./marks/polar.js";

export {
  bin2d,
  densityLogU8,
  marchingSquares,
  lodPlan,
  drillDecision,
  shouldUseDensity,
  DENSITY_GRID,
  PYRAMID_MIN_POINTS,
  PYRAMID_BASE_DIM,
  PYRAMID_NO_RESCAN_ROWS,
  PYRAMID_MAX_DIM,
} from "./encode.js";

export {
  pyramidBuild,
  pyramidBuildColor,
  pyramidBuildFromStream,
  pyramidAppend,
  pyramidAppendFromStream,
  pyramidCount,
  pyramidCompose,
  pyramidComposeColor,
  pyramidFree,
  pyramidReportBytes,
  pyramidBaseDimFor,
  shouldUsePyramid,
  densityViewFromPyramid,
  PyramidCache,
} from "./pyramid.js";

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
} from "./charts.js";
