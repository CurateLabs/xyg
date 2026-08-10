import { ChartView } from "./50_chartview";

// Optional graph-mark client enhancement (graph-mark.md §6).
//
// Cache CSR meta from the figure spec and dim non-neighbors on node hover
// via the existing point-shader selection path (`g.selActive` / `g.selBuf`,
// see `_drawPoints` / `POINT_VS`). Geometry is already uploaded as segments
// + scatter — this module never owns layout or edge tessellation
// (`edge_curve` meta is recorded but MVP keeps straight segments).
//
// Safe to omit from the bundle: every wire mark (including graph's
// segments/scatter) renders through MARK_KINDS without these hooks.

Object.assign(ChartView.prototype, {
  _cacheGraphsFromSpec(spec = this.spec) {
    this._graphs = Array.isArray(spec?.graph) ? spec.graph : [];
  },

  _graphMetaForNodeTrace(traceId) {
    const graphs = this._graphs || [];
    for (const meta of graphs) {
      if (meta && meta.node_trace === traceId) return meta;
    }
    return null;
  },

  // Sync neighborhood dim to the current `_hoverTarget`. Returns true when
  // the GPU selection mask changed (caller may need an extra keep-pick draw
  // only when not already inside `_drawKeepPick`).
  _syncGraphNeighborhoodHighlight() {
    // Durable box/lasso/rows selection owns `selBuf`; never overwrite it.
    if (this._stateSelection != null) {
      this._graphNbrKey = null;
      this._graphNbrGpu = null;
      return false;
    }
    const hit = this._hoverTarget;
    if (!hit || !hit.g || hit.g.trace?.kind !== "scatter") {
      return this._clearGraphNeighborhoodHighlight();
    }
    const meta = this._graphMetaForNodeTrace(hit.trace);
    if (!meta) return this._clearGraphNeighborhoodHighlight();
    const offsets = meta.csr_offsets;
    const neighbors = meta.csr_neighbors;
    const node = hit.index | 0;
    if (!Array.isArray(offsets) || !Array.isArray(neighbors)
        || node < 0 || node + 1 >= offsets.length) {
      return this._clearGraphNeighborhoodHighlight();
    }
    const key = `${hit.trace}:${node}`;
    if (key === this._graphNbrKey && hit.g.selActive) return false;

    const g = hit.g;
    const n = g.n | 0;
    if (n <= 0 || !this.gl) return this._clearGraphNeighborhoodHighlight();

    // Drop a prior graph's temporary mask when the hover moves across graphs.
    if (this._graphNbrGpu && this._graphNbrGpu !== g) {
      this._graphNbrGpu.selActive = false;
    }

    const mask = new Float32Array(n);
    const mark = (canonicalIdx) => {
      const idx = g._visInv ? g._visInv[canonicalIdx] : canonicalIdx;
      if (idx >= 0 && idx < n) mask[idx] = 1;
    };
    mark(node);
    const start = Number(offsets[node]) || 0;
    const end = Number(offsets[node + 1]) || 0;
    for (let i = start; i < end; i++) {
      mark(Number(neighbors[i]) || 0);
    }
    this._applySelMask(g, mask);
    this._graphNbrKey = key;
    this._graphNbrGpu = g;
    return true;
  },

  _clearGraphNeighborhoodHighlight() {
    if (!this._graphNbrKey && !this._graphNbrGpu) return false;
    const g = this._graphNbrGpu;
    this._graphNbrKey = null;
    this._graphNbrGpu = null;
    // Leave durable selections untouched (they cleared our key above or own sel).
    if (this._stateSelection != null) return false;
    if (g) g.selActive = false;
    return true;
  },
});

// Cache graph meta on mount and whenever the figure spec is replaced.
const _initViewState = ChartView.prototype._initViewState;
ChartView.prototype._initViewState = function () {
  this._cacheGraphsFromSpec(this.spec);
  this._graphNbrKey = null;
  this._graphNbrGpu = null;
  return _initViewState.apply(this, arguments);
};

const _updatePayload = ChartView.prototype.updatePayload;
if (typeof _updatePayload === "function") {
  ChartView.prototype.updatePayload = function (spec, buffer) {
    const ok = _updatePayload.apply(this, arguments);
    if (ok !== false) this._cacheGraphsFromSpec(spec || this.spec);
    // Spec rebuild drops transient selActive; drop our hover-mask bookkeeping.
    this._graphNbrKey = null;
    this._graphNbrGpu = null;
    return ok;
  };
}

const _applyAppend = ChartView.prototype._applyAppend;
if (typeof _applyAppend === "function") {
  ChartView.prototype._applyAppend = function (msg, buffers) {
    const result = _applyAppend.apply(this, arguments);
    this._cacheGraphsFromSpec(this.spec);
    return result;
  };
}

// Hover highlight frames already funnel through `_drawKeepPick` (pointer
// move, leave, a11y escape). Sync the CSR neighborhood mask just before
// that draw so leave clears dimming and enter applies it in one pass.
const _drawKeepPick = ChartView.prototype._drawKeepPick;
ChartView.prototype._drawKeepPick = function () {
  this._syncGraphNeighborhoodHighlight();
  return _drawKeepPick.apply(this, arguments);
};
