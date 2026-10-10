/**
 * Chart convenience constructors — all dual-host mark families.
 * Thin wrappers over mark composers + the minimal Node Figure.
 */

import { figure } from "./figure.js";
import { applyGraphHomeView } from "./scene.js";
import { attachScatter } from "./marks/scatter.js";
import { attachLine } from "./marks/line.js";
import { attachHistogram } from "./marks/histogram.js";
import { attachArea } from "./marks/area.js";
import { attachBar, attachColumn } from "./marks/bar.js";
import { attachBox } from "./marks/box.js";
import { attachEcdf } from "./marks/ecdf.js";
import { attachSegments } from "./marks/segments.js";
import { attachHeatmap } from "./marks/heatmap.js";
import { attachHexbin } from "./marks/hexbin.js";
import { attachViolin } from "./marks/violin.js";
import { attachContour } from "./marks/contour.js";
import { attachErrorbar } from "./marks/errorbar.js";
import { attachErrorBand } from "./marks/error_band.js";
import { attachStem } from "./marks/stem.js";
import { attachStep, attachStairs } from "./marks/step.js";
import { attachTriangleMesh } from "./marks/triangle_mesh.js";
import { attachRadar } from "./marks/radar.js";
import {
  pieChart,
  windRoseChart,
  polarChart,
  facetChart,
} from "./marks/polar.js";

function chartWith(figOpts, attachFn, ...args) {
  const { width, height, title, ...markOpts } = figOpts;
  const fig = figure({ width, height, title });
  attachFn(fig, ...args, markOpts);
  return fig;
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{width?: number, height?: number, title?: string|null, name?: string|null, style?: object}} [opts]
 */
export function scatterChart(x, y, opts = {}) {
  return chartWith(opts, attachScatter, x, y);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function lineChart(x, y, opts = {}) {
  return chartWith(opts, attachLine, x, y);
}

/**
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function histogramChart(values, opts = {}) {
  return chartWith(opts, attachHistogram, values);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function areaChart(x, y, opts = {}) {
  return chartWith(opts, attachArea, x, y);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function barChart(x, y, opts = {}) {
  return chartWith(opts, attachBar, x, y);
}

/** Column charts share the bar rect renderer. */
export function columnChart(x, y, opts = {}) {
  return chartWith(opts, attachColumn, x, y);
}

/**
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function boxChart(values, opts = {}) {
  return chartWith(opts, attachBox, values);
}

/**
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function ecdfChart(values, opts = {}) {
  return chartWith(opts, attachEcdf, values);
}

/**
 * @param {ArrayLike|TypedArray} x0
 * @param {ArrayLike|TypedArray} y0
 * @param {ArrayLike|TypedArray} x1
 * @param {ArrayLike|TypedArray} y1
 * @param {object} [opts]
 */
export function segmentsChart(x0, y0, x1, y1, opts = {}) {
  return chartWith(opts, attachSegments, x0, y0, x1, y1);
}

/**
 * @param {ArrayLike|TypedArray|number[][]} z
 * @param {object} [opts]
 */
export function heatmapChart(z, opts = {}) {
  return chartWith(opts, attachHeatmap, z);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function hexbinChart(x, y, opts = {}) {
  return chartWith(opts, attachHexbin, x, y);
}

/**
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function violinChart(values, opts = {}) {
  return chartWith(opts, attachViolin, values);
}

/**
 * @param {ArrayLike|TypedArray|number[][]} z
 * @param {object} [opts]
 */
export function contourChart(z, opts = {}) {
  return chartWith(opts, attachContour, z);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function errorbarChart(x, y, opts = {}) {
  return chartWith(opts, attachErrorbar, x, y);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} lower
 * @param {ArrayLike|TypedArray} upper
 * @param {object} [opts]
 */
export function errorBandChart(x, lower, upper, opts = {}) {
  return chartWith(opts, attachErrorBand, x, lower, upper);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function stemChart(x, y, opts = {}) {
  return chartWith(opts, attachStem, x, y);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function stepChart(x, y, opts = {}) {
  return chartWith(opts, attachStep, x, y);
}

/**
 * @param {ArrayLike|TypedArray} edges
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function stairsChart(edges, values, opts = {}) {
  return chartWith(opts, attachStairs, edges, values);
}

/**
 * @param {ArrayLike|TypedArray} x0
 * @param {ArrayLike|TypedArray} y0
 * @param {ArrayLike|TypedArray} x1
 * @param {ArrayLike|TypedArray} y1
 * @param {ArrayLike|TypedArray} x2
 * @param {ArrayLike|TypedArray} y2
 * @param {object} [opts]
 */
export function triangleMeshChart(x0, y0, x1, y1, x2, y2, opts = {}) {
  return chartWith(opts, attachTriangleMesh, x0, y0, x1, y1, x2, y2);
}

/**
 * @param {ArrayLike|TypedArray} categoriesOrAngles
 * @param {ArrayLike|TypedArray|ArrayLike[]} seriesValues
 * @param {object} [opts]
 */
export function radarChart(categoriesOrAngles, seriesValues, opts = {}) {
  return chartWith(opts, attachRadar, categoriesOrAngles, seriesValues);
}

/**
 * @param {Iterable|object} nodes
 * @param {Iterable|object} edges
 * @param {object} [opts]
 */
// Python `graph_chart` authors `x_axis(show=False)` / `y_axis(show=False)`,
// which compile to exactly these transparent / zero-width axis properties.
const HIDDEN_AXIS_STYLE = Object.freeze({
  axis_width: 0,
  axis_color: "#00000000",
  tick_length: 0,
  tick_width: 0,
  grid_opacity: 0,
  tick_label_color: "#00000000",
  label_color: "#00000000",
});

export function graphChart(nodes, edges, opts = {}) {
  const { width, height, title, xAxis, yAxis, legend, ...graphOpts } = opts;
  // `legend` is the chart-level legend (Python `graph_chart(..., xyg.legend())`).
  const fig = figure({
    width,
    height,
    title,
    ...(legend != null ? { legend } : {}),
  });
  fig.graph(nodes, edges, graphOpts);
  // Node–link charts hide axes by default, matching Python `graph_chart`; an
  // authored `xAxis` / `yAxis` is used as given instead (#909).
  fig.setAxis("x", xAxis ?? { style: { ...HIDDEN_AXIS_STYLE } });
  fig.setAxis("y", yAxis ?? { style: { ...HIDDEN_AXIS_STYLE } });
  // Rust home view on the hidden default axes: nothing drawn around a node
  // is clipped (#910).
  if (xAxis == null && yAxis == null) applyGraphHomeView(fig);
  return fig;
}

/**
 * @param {Iterable|object} nodes
 * @param {Iterable|object} links
 * @param {object} [opts]
 */
export function sankeyChart(nodes, links, opts = {}) {
  const { width, height, title, ...sankeyOpts } = opts;
  const fig = figure({ width, height, title });
  fig.sankey(nodes, links, sankeyOpts);
  return fig;
}

export { pieChart, windRoseChart, polarChart, facetChart };

// Geographic composition stays on the shared Rust catalog and retained sessions.
import { createHash } from "node:crypto";
import {
  GeoTileSession,
  geoTileExecute,
  encodeGeoTileBegin,
  encodeGeoTilePrepare,
} from "./geo-tiles.js";
import { RetainedGeoSource } from "./geo-retained.js";
import {GeoOverviewIndex,overviewIndexAuthority,overviewFrameAuthority} from "./geo-overview-source.js";
import {encodeGeoOverviewRequest} from "./geo-overview.js";
import { encodeGeoScaleStyle, encodeGeoScaleRequest } from "./geoscale.js";
import {
  encodeGeoCatalogRequest,
  decodeGeoCatalogResponse,
  geoCatalogCompile,
} from "./geocatalog.js";
import { sceneStaticExport } from "./scene.js";
const GEO_KINDS = Object.freeze({
  points: 1,
  bubbles: 2,
  routes: 3,
  arcs: 4,
  polygons: 5,
  choropleth: 6,
  density: 7,
});
class GeoLayer {
  constructor(kind, source, layerId, properties) {
    this.kind = kind;
    this.source = source;
    this.layerId = layerId;
    this.properties = Object.freeze({ ...properties });
    Object.freeze(this);
  }
}
/** Declare a geographic mark; retained inputs require query, sequence and uniform style. */
export function geoLayer(kind, { source, layerId, ...properties }) {
  if (!Object.hasOwn(GEO_KINDS, kind))
    throw new TypeError("unknown geographic layer kind");
  return new GeoLayer(kind, source, layerId, properties);
}
function exactKeys(value, keys, label) {
  if (
    !value ||
    typeof value !== "object" ||
    Object.keys(value).length !== keys.length ||
    keys.some((k) => !Object.hasOwn(value, k))
  )
    throw new TypeError(`${label} requires exactly ${keys.join(", ")}`);
}
function geoCameraBytes(camera) {
  const keys = [
    "crs",
    "worldWrap",
    "centerX",
    "centerY",
    "zoom",
    "width",
    "height",
    "bearing",
    "pitch",
  ];
  exactKeys(camera, keys, "retained camera");
  if (
    typeof camera.worldWrap !== "boolean" ||
    !Number.isInteger(camera.crs) ||
    camera.crs < 0 ||
    camera.crs > 0xffffffff
  )
    throw new TypeError("invalid typed camera fields");
  const values = keys.slice(2).map((k) => camera[k]);
  if (values.some((n) => typeof n !== "number" || !Number.isFinite(n)))
    throw new TypeError("camera fields must be finite numbers");
  const b = new Uint8Array(64),
    v = new DataView(b.buffer);
  v.setUint32(0, camera.crs, true);
  v.setUint32(4, camera.worldWrap ? 1 : 0, true);
  values.forEach((n, i) => v.setFloat64(8 + i * 8, n, true));
  return b;
}
/** Geographic composition. Static compile returns a catalog; compileRetained returns an owned frame. */
import { GeoHostAdapter } from "./geo-webview.js";

export class GeoChart {
  constructor(
    layers,
    {
      camera,
      legend,
      budget = 384 * 1024 * 1024,
      tileSession,
      tileVectorStyles,
      tileImageId,
    },
  ) {
    if (!Array.isArray(layers) || layers.some((x) => !(x instanceof GeoLayer)))
      throw new TypeError("GeoChart layers must be geoLayer specifications");
    this.layers = Object.freeze([...layers]);
    this.camera = camera;
    this.legend = legend;
    this.budget = budget;
    this.tileSession = tileSession;
    this.tileVectorStyles = tileVectorStyles;
    this.tileImageId = tileImageId;
    if (
      !tileSession &&
      (tileVectorStyles !== undefined || tileImageId !== undefined)
    )
      throw new TypeError("tile options require tileSession");
  }
  host(options) { return new GeoHostAdapter(this, options); }
  _overview(){
    const layers=this.layers.filter(x=>x.source instanceof GeoOverviewIndex);
    if(!layers.length)return undefined;
    if(this.layers.length!==1||this.legend!=null||this.tileSession)throw new TypeError('overview requires one density layer and no legend/tiles');
    if(layers[0].kind!=='density'||!overviewIndexAuthority(layers[0].source))throw new TypeError('issued overview density source required');
    return layers[0];
  }
  _overviewInputs(layer){
    const p=layer.properties;exactKeys(p,['query','sequence'],'overview density layer');
    const q=p.query;exactKeys(q,['camera','reducedKind','maxCells','previousDirect','sourceDigest','generation','layerId','cameraRevision','timeRevision','layerRevision','styleRevision','stateRevision','time','maxProjectedVertices'],'overview query');
    const a=geoCameraBytes(this.camera),b=geoCameraBytes(q.camera);if(a.some((n,i)=>n!==b[i]))throw new TypeError('GeoChart camera must exactly match its overview query');
    if(typeof layer.layerId!=='bigint'||layer.layerId!==q.layerId)throw new TypeError('overview layer must match query identity');
    if(!Number.isSafeInteger(this.budget)||this.budget<layer.source.budget.processorBytes||this.budget>384*1024*1024)throw new RangeError('chart budget must cover explicit overview processor allowance');
    const packet=encodeGeoOverviewRequest({command:28,handle:layer.source.handle,sequence:p.sequence,budget:layer.source.budget,query:q});
    return {query:q,sequence:p.sequence,packet};
  }
  _retained() {
    const layers = this.layers.filter(
      (x) => x.source instanceof RetainedGeoSource,
    );
    if (!layers.length) return undefined;
    if (this.layers.length !== 1 || this.legend != null)
      throw new TypeError(
        "retained geography requires one layer and no legend",
      );
    if (layers[0].kind !== "points")
      throw new TypeError(
        "retained geography initially supports only points layers",
      );
    return layers[0];
  }
  _inputs(layer) {
    const p = layer.properties;
    exactKeys(p, ["query", "sequence", "style"], "retained layer");
    const q = p.query;
    exactKeys(
      q,
      [
        "camera",
        "reducedKind",
        "maxCells",
        "previousDirect",
        "sourceDigest",
        "generation",
        "layerId",
        "cameraRevision",
        "timeRevision",
        "layerRevision",
        "styleRevision",
        "stateRevision",
        "time",
        "maxProjectedVertices",
      ],
      "retained query",
    );
    const a = geoCameraBytes(this.camera),
      b = geoCameraBytes(q.camera);
    if (a.some((n, i) => n !== b[i]))
      throw new TypeError(
        "GeoChart camera must exactly match its retained query",
      );
    if (typeof layer.layerId !== "bigint" || layer.layerId !== q.layerId)
      throw new TypeError("retained query layerId must match geoLayer");
    if (
      !Number.isSafeInteger(this.budget) ||
      this.budget < layer.source.budget.processorBytes ||
      this.budget > 384 * 1024 * 1024
    )
      throw new RangeError(
        "chart budget must cover the source's explicit processor budget",
      );
    let style = p.style;
    if (!(style instanceof Uint8Array)) {
      exactKeys(
        style,
        ["fill", "stroke", "strokeWidth", "diameter", "opacity", "symbol"],
        "retained uniform style",
      );
      style = encodeGeoScaleStyle(style);
    }
    if (style.length !== 48)
      throw new TypeError("retained style requires exact48 bytes");
    return { query: q, sequence: p.sequence, style };
  }
  compile({ event } = {}) {
    if(this._overview())throw new TypeError('use compileRetained for an owned overview frame');
    if (this._retained())
      throw new TypeError("use compileRetained for an owned retained frame");
    if (this.tileSession)
      throw new TypeError("use compileTiles for an owned tile frame");
    return decodeGeoCatalogResponse(
      geoCatalogCompile(this._catalogRequest(event), this.budget),
    );
  }
  _catalogRequest(event) {
    const request = {
      camera: this.camera,
      layers: this.layers.map((l) => ({
        ...l.properties,
        kind: GEO_KINDS[l.kind],
        source: l.source,
        layerId: l.layerId,
      })),
    };
    if (this.legend != null) request.legend = this.legend;
    if (event != null) request.event = event;
    return encodeGeoCatalogRequest(request, this.budget);
  }
  _checkTiles() {
    if (
      !(this.tileSession instanceof GeoTileSession) ||
      this.tileVectorStyles === undefined ||
      this.tileImageId === undefined
    )
      throw new TypeError(
        "tileSession requires explicit tileVectorStyles and tileImageId",
      );
    if (this._retained())
      throw new TypeError(
        "retained point and tile compilation require separate explicit frames",
      );
    if (
      this.budget < this.tileSession.budget ||
      this.budget > 384 * 1024 * 1024
    )
      throw new RangeError(
        "chart budget must cover tile session processor budget",
      );
  }
  compileTiles(options = {}) {
    exactKeys(options, [], "tile compile options");
    this._checkTiles();
    if (this.tileSession.bridge.execute !== geoTileExecute)
      throw new TypeError(
        "native tile chart staging requires the native bridge; use session.update with an explicit remote stage",
      );
    return this.tileSession.update(this.camera, {
      catalog: this._catalogRequest(),
      vectorStyles: this.tileVectorStyles,
      imageId: this.tileImageId,
      stage: async (frame) => {
        const artifact = await frame.export("svg", { budget: this.budget });
        await artifact.dispose();
      },
    });
  }
  compileRetained(options = {}) {
    exactKeys(options, [], "retained compile options");
    const overview=this._overview();if(overview){const {query,sequence}=this._overviewInputs(overview);return overview.source.update(query,{sequence});}
    const layer = this._retained();
    if (this.tileSession)
      throw new TypeError(
        "retained point and tile compilation require separate explicit frames",
      );
    if (!layer)
      throw new TypeError("compileRetained requires a retained source");
    const { query, sequence, style } = this._inputs(layer);
    return layer.source.update(query, { sequence, style });
  }
  toImage(format = "png", { scale = 1, quality = 90, frame } = {}) {
    const overview=this._overview();if(overview){if(!frame)throw new TypeError('compileRetained first, then pass overview frame');const {packet,sequence}=this._overviewInputs(overview),a=overviewFrameAuthority(frame);if(!a||a.index!==overview.source||a.sequence!==sequence||a.query.byteLength!==packet.byteLength||new Uint8Array(a.query).some((n,i)=>n!==new Uint8Array(packet)[i]))throw new TypeError('frame must match this overview source and exact snapshot');return frame.export(format,{scale,quality,budget:this.budget});}
    const retained = this._retained();
    if (this.tileSession) {
      this._checkTiles();
      if (!frame)
        throw new Error(
          "compileTiles first, then pass frame or call frame.export",
        );
      const packet = encodeGeoTilePrepare(
          this._catalogRequest(),
          this.tileVectorStyles,
          this.tileImageId,
        ),
        camera = encodeGeoTileBegin(this.camera, []).subarray(0, 64);
      if (
        frame.session !== this.tileSession ||
        !frame._cameraPacket ||
        camera.some((n, i) => n !== frame._cameraPacket[i]) ||
        createHash("sha256").update(packet).digest("hex") !==
          frame._prepareDigest
      )
        throw new TypeError(
          "frame must match this tile chart's session, camera and catalog",
        );
      return frame.export(format, { scale, quality, budget: this.budget });
    }
    if (retained) {
      if (!frame)
        throw new Error(
          "compileRetained first, then pass frame or call frame.export",
        );
      const { query, sequence, style } = this._inputs(retained);
      const packet = new Uint8Array(
        encodeGeoScaleRequest({
          command: 5,
          handle: retained.source.handle,
          sequence,
          budget: retained.source.budget,
          query,
        }),
      );
      const original = new Uint8Array(frame._queryPacket ?? new ArrayBuffer());
      if (
        frame._source !== retained.source ||
        original.length !== packet.length ||
        original[12] !== packet[12] ||
        original.subarray(24, 32).some((n, i) => n !== packet[24 + i]) ||
        original.subarray(64, 232).some((n, i) => n !== packet[64 + i]) ||
        frame._style.some((n, i) => n !== style[i])
      )
        throw new TypeError(
          "frame must match this retained chart's source, query and style",
        );
      return frame.export(format, { scale, quality, budget: this.budget });
    }
    if (frame)
      throw new TypeError("frame is only accepted for retained geography");
    const result = this.compile();
    return sceneStaticExport(new Uint8Array(result.scene), format, {
      scale,
      quality,
      width: Math.ceil(result.camera.width),
      height: Math.ceil(result.camera.height),
    });
  }
  toSvg() {
    return new TextDecoder().decode(this.toImage("svg"));
  }
}
/** Compose geographic layers, followed by the explicit camera/options object. */
export function geoChart(...children) {
  const options = children.pop();
  return new GeoChart(children, options);
}
