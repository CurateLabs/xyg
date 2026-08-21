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

export { ChunkedColumns } from "./chunked-columns.js";
export { TemporalGraph } from "./temporal-graph.js";

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
  GRAPH_LAYOUT_COSE,
  GRAPH_LAYOUT_IDS,
  GRAPH_PROGRESSIVE_FORCE,
  SANKEY_ALIGN_IDS,
  SankeyLayoutError,
  TEMPORAL_PRECISION,
  TEMPORAL_DISAMBIGUATION,
  TEMPORAL_DST,
  TEMPORAL_DIRECTION,
  TemporalNativeError,
  TemporalGraphError,
  GEO_GEOMETRY,
  GEO_CRS,
  GeoNativeError,
  abiVersion,
  graphLayout,
  graphForceCreate,
  graphForceTick,
  graphForceDestroy,
  graphIsProgressiveForce,
  graphLodDecision,
  graphClusterAggregate,
  graphBuildRender,
  graphEdgeRouteSegments,
  graphSampleEdges,
  graphBuildCsr,
  sankeyLayout,
  graphLayoutId,
  sankeyAlignId,
  temporalColumnCreate,
  temporalColumnRead,
  temporalColumnDestroy,
  temporalIntervalIndexCreate,
  temporalIntervalVisibilityAt,
  temporalIntervalIndexDestroy,
  temporalEventsInRange,
  geoColumnNew,
  geoColumnMeta,
  geoColumnFree,
  temporalControllerCreate,
  temporalControllerState,
  temporalControllerSetRange,
  temporalControllerSetCursor,
  temporalControllerSetSelection,
  temporalControllerStep,
  temporalControllerPlay,
  temporalControllerPause,
  temporalControllerSetRateMilli,
  temporalControllerSetDirection,
  temporalControllerSetLoop,
  temporalControllerSetReducedMotion,
  temporalControllerTick,
  temporalControllerPollEvent,
  temporalControllerApplyEvent,
  temporalCoordinateDeliver,
  temporalControllerDispose,
  temporalControllerDestroy,
  temporalGraphCreate,
  temporalGraphSetSelection,
  temporalGraphSetFocus,
  temporalGraphSetPinned,
  temporalGraphRequiredBudget,
  temporalGraphFrame,
  temporalGraphCancel,
  temporalGraphSnapshot,
  temporalGraphDestroy,
} from "./abi.js";

export {
  DEFAULT_LAYOUT,
  fromGraphForgeTables,
  looksLikeGraphForgeTables,
  normalizeGraphInputs,
  projectionTooltipRows,
  resolveGraphData,
  runLayout,
  edgeSegmentsFromPositions,
  composeGraph,
} from "./graph.js";

import { Figure, PayloadWriter, figure } from "./figure.js";
import { toHtml } from "./html.js";

/** Stable engine entry — alias of {@link figure} for Node servers / VS Code hosts. */
export function createEngine(opts = {}) {
  return figure(opts);
}

export { Figure, PayloadWriter, figure, toHtml };

export { axisTicks, figureSceneV3, scaleMap, sceneBatchEncode, sceneRasterCommands, sceneSvg, sceneVersion, scatterSceneSvg } from "./scene.js";

export { runForceTicks, runForceTicks as runForceAnimation } from "./force_scheduler.js";

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
  PYRAMID_RESIDENT_BYTES,
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
  pyramidSpill,
  pyramidReportBytes,
  pyramidBaseDimFor,
  pyramidResidentBytes,
  shouldUsePyramid,
  densityViewFromPyramid,
  PyramidCache,
  tileBudgetSet,
  tileStoreCompose,
  tileStoreComposeColor,
  tileStoreAppend,
  tileStoreStats,
  tileStoreFree,
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
