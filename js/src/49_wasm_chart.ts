/**
 * Public chart-spec ergonomics above the packed `XYCC` typed-column seam.
 *
 * TypeScript only expands series-shaped inputs into flat columns and frames the
 * request. Domain, margins, Scene policy, and paint lowering stay in Rust WASM.
 */

import {
  encodeWasmColumns,
  renderWasmColumns,
  type XygWasmColumnCompileInput,
  type XygWasmColumnStyle,
  type XygWasmScaleKind,
} from "./49_wasm_columns";
import type { XygWasmSceneView } from "./48_wasm_scene";
import type { XygWasmWorker } from "./47_wasm";

export type XygWasmChartSeriesKind = "scatter" | "line" | "bar" | "area";

export interface XygWasmChartSeries {
  kind: XygWasmChartSeriesKind;
  x: ArrayLike<number>;
  y: ArrayLike<number>;
  /** Required for `bar` (bar tops) and `area` (upper band edge). Defaults to `y`. */
  y1?: ArrayLike<number>;
  /** Required for `bar` (bar bottoms). Defaults to zeros. */
  y0?: ArrayLike<number>;
  diameter?: number | ArrayLike<number>;
  symbol?: number;
  style?: Partial<XygWasmColumnStyle> & {
    fillRgba?: Uint8Array | number[];
    strokeRgba?: Uint8Array | number[];
    strokeWidth?: number;
  };
  /** Base stable id; each expanded record uses `stableIdBase + index`. */
  stableIdBase?: bigint | number;
}

export interface XygWasmChartCompileInput {
  width: number;
  height: number;
  margins?: [number, number, number, number];
  /** Default true — Rust chooses gutters via `cartesian_scene_margins`. */
  autoMargins?: boolean;
  /**
   * Default true when `x.lo`/`x.hi`/`y.lo`/`y.hi` are omitted. Rust derives
   * domains from finite geometry in the Worker so the main thread never scans.
   */
  autoDomain?: boolean;
  xAxisId?: bigint | number;
  yAxisId?: bigint | number;
  x?: {
    kind?: XygWasmScaleKind;
    lo?: number;
    hi?: number;
    constant?: number;
    maskNonpositive?: boolean;
  };
  y?: {
    kind?: XygWasmScaleKind;
    lo?: number;
    hi?: number;
    constant?: number;
    maskNonpositive?: boolean;
  };
  title?: string;
  xLabel?: string;
  yLabel?: string;
  series: XygWasmChartSeries[];
}

const DEFAULT_FILL = [37, 99, 235, 255];
const DEFAULT_STROKE = [0, 0, 0, 0];

function asArray(source: ArrayLike<number>): number[] {
  const out = new Array<number>(source.length);
  for (let index = 0; index < source.length; index++) {
    out[index] = source[index]!;
  }
  return out;
}

function seriesStyle(series: XygWasmChartSeries): XygWasmColumnStyle {
  const fill = series.style?.fillRgba ?? DEFAULT_FILL;
  const stroke = series.style?.strokeRgba ?? DEFAULT_STROKE;
  return {
    fillRgba: fill,
    strokeRgba: stroke,
    strokeWidth: series.style?.strokeWidth ?? (series.kind === "line" ? 1.5 : 0),
  };
}

/**
 * Expand series-shaped chart input into flat typed columns for `encodeWasmColumns`.
 * Framing only — no domain scan, no Scene policy.
 */
export function expandWasmChart(input: XygWasmChartCompileInput): XygWasmColumnCompileInput {
  if (!input?.series || !Array.isArray(input.series) || input.series.length === 0) {
    throw new TypeError("series must be a non-empty array");
  }

  const kinds: number[] = [];
  const stableIds: bigint[] = [];
  const styleRefs: number[] = [];
  const diameter: number[] = [];
  const symbols: number[] = [];
  const x0: number[] = [];
  const y0: number[] = [];
  const x1: number[] = [];
  const y1: number[] = [];
  const styles: XygWasmColumnStyle[] = [];

  for (const series of input.series) {
    const styleRef = styles.length;
    styles.push(seriesStyle(series));
    const xs = asArray(series.x);
    const ys = asArray(series.y);
    if (xs.length !== ys.length) {
      throw new TypeError("each series x and y must share the same length");
    }
    if (xs.length === 0) {
      throw new TypeError("each series must contain at least one point");
    }
    const base =
      typeof series.stableIdBase === "bigint"
        ? series.stableIdBase
        : BigInt(series.stableIdBase ?? styles.length);

    if (series.kind === "scatter") {
      const diameters =
        typeof series.diameter === "number"
          ? null
          : series.diameter
            ? asArray(series.diameter)
            : null;
      if (diameters && diameters.length !== xs.length) {
        throw new TypeError("scatter diameter must match series length");
      }
      for (let index = 0; index < xs.length; index++) {
        kinds.push(0);
        stableIds.push(base + BigInt(index));
        styleRefs.push(styleRef);
        diameter.push(diameters ? diameters[index]! : (series.diameter as number | undefined) ?? 8);
        symbols.push(series.symbol ?? 0);
        x0.push(xs[index]!);
        y0.push(ys[index]!);
        x1.push(0);
        y1.push(0);
      }
      continue;
    }

    if (series.kind === "line") {
      // Scene polylines are one vertex per record; consecutive same-style
      // vertices form a stroke run in the painter.
      for (let index = 0; index < xs.length; index++) {
        kinds.push(1);
        stableIds.push(base + BigInt(index));
        styleRefs.push(styleRef);
        diameter.push(0);
        symbols.push(0);
        x0.push(xs[index]!);
        y0.push(ys[index]!);
        x1.push(0);
        y1.push(0);
      }
      continue;
    }

    if (series.kind === "bar") {
      const bottoms = series.y0 ? asArray(series.y0) : xs.map(() => 0);
      const tops = series.y1 ? asArray(series.y1) : ys;
      if (bottoms.length !== xs.length || tops.length !== xs.length) {
        throw new TypeError("bar y0/y1 must match series length");
      }
      // Unit-width bars centered on each x.
      for (let index = 0; index < xs.length; index++) {
        const cx = xs[index]!;
        kinds.push(2);
        stableIds.push(base + BigInt(index));
        styleRefs.push(styleRef);
        diameter.push(0);
        symbols.push(0);
        x0.push(cx - 0.4);
        y0.push(bottoms[index]!);
        x1.push(cx + 0.4);
        y1.push(tops[index]!);
      }
      continue;
    }

    if (series.kind === "area") {
      const upper = series.y1 ? asArray(series.y1) : ys;
      const lower = series.y0 ? asArray(series.y0) : xs.map(() => 0);
      if (upper.length !== xs.length || lower.length !== xs.length) {
        throw new TypeError("area y0/y1 must match series length");
      }
      for (let index = 0; index < xs.length; index++) {
        kinds.push(3);
        stableIds.push(base + BigInt(index));
        styleRefs.push(styleRef);
        diameter.push(0);
        symbols.push(0);
        x0.push(xs[index]!);
        y0.push(lower[index]!);
        x1.push(xs[index]!);
        y1.push(upper[index]!);
      }
      continue;
    }

    throw new TypeError("series kind must be scatter, line, bar, or area");
  }

  const explicitDomain =
    input.x?.lo !== undefined
    || input.x?.hi !== undefined
    || input.y?.lo !== undefined
    || input.y?.hi !== undefined;
  const autoDomain = input.autoDomain ?? !explicitDomain;

  return {
    width: input.width,
    height: input.height,
    margins: input.margins,
    autoMargins: input.autoMargins ?? true,
    autoDomain,
    xAxisId: input.xAxisId,
    yAxisId: input.yAxisId,
    x: input.x,
    y: input.y,
    title: input.title,
    xLabel: input.xLabel,
    yLabel: input.yLabel,
    kinds,
    stableIds,
    styleRefs,
    diameter,
    symbols,
    x0,
    y0,
    x1,
    y1,
    styles,
  };
}

/** Pack a series-shaped chart into the little-endian `XYCC` request. */
export function encodeWasmChart(input: XygWasmChartCompileInput): ArrayBuffer {
  return encodeWasmColumns(expandWasmChart(input));
}

export interface RenderWasmChartOptions {
  el: HTMLElement;
  chart: XygWasmChartCompileInput;
  worker: XygWasmWorker;
  transfer?: boolean;
}

/**
 * Expand series → columns, compile in the Rust WASM worker, hydrate the painter.
 */
export async function renderWasmChart(
  options: RenderWasmChartOptions,
): Promise<XygWasmSceneView> {
  if (!options?.el || !options.chart || !options.worker) {
    throw new TypeError("el, chart, and worker are required");
  }
  return renderWasmColumns({
    el: options.el,
    columns: expandWasmChart(options.chart),
    worker: options.worker,
    transfer: options.transfer,
  });
}
