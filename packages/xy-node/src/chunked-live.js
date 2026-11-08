/** Transport/lifetime orchestration only; Rust owns selection, paging and encoding. */
import {pointer, xyChunkedColumnsChart, xyRangeIndices, xyPolygonSelect} from './native.js';
import {scatterChart} from './charts.js';
import {scatterPaintChannelNames} from './scene.js';
import {PAYLOAD_TRACE_EMIT_MAX_BYTES} from './payloadTraceMaterialize.js';
import {statSync} from 'node:fs';

const decimal = value => typeof value === 'string' && /^\d{1,20}$/.test(value);
export class ChunkedLiveHost {
  constructor(source, chart, options, send, callbacks = {}) {
    if (typeof send !== 'function') throw new TypeError('liveHost requires a binary send function');
    this.source = source; this.chart = this.initial = chart; this.options = options;
    this.send = send; this.callbacks = callbacks; this.generation = options.generation;
    this.mount = null; this.mountEpoch = 0n; this.intent = null;
    this.pending = this.active = this.ready = this.staged = null;
    this.closed = false; this.frame = String(options.generation); this.lastError = null;
    this.sourceFileBytes = statSync(source.path, {bigint: true}).size.toString();
    this.waiters = new Set(); this.outputCapacity = Math.floor(options.budgetBytes / 16) * 24;
  }
  compact(produced) {
    const bound = 64 * Math.floor(this.options.budgetBytes / 16) + 65536;
    if (produced.reduce((n, b) => n + b.byteLength, 0) > bound) throw new RangeError('chunked paint output exceeds derived capacity bound');
    return produced.map(b => new Uint8Array(b.buffer, b.byteOffset, b.byteLength).slice());
  }
  drop(chart) { if (chart && chart !== this.initial) chart.dispose(); }
  advance() {
    if (this.generation >= Number.MAX_SAFE_INTEGER) throw new RangeError('chunked generation exhausted');
    this.source.cancelBefore(++this.generation);
  }
  payload() {
    if (this.acceptedPayload) {this.acceptedPayload.spec.chunked.mount_epoch = String(this.mountEpoch); this.acceptedPayload.spec.chunked.state = this.viewState; return this.acceptedPayload;}
    const {spec, buffers: produced} = this.initial.buildPayload({split: true});
    const buffers = this.compact(produced);
    spec.chunked = {frame: String(this.options.generation), mount_epoch: String(this.mountEpoch), state: this.viewState};
    this.homeSpec = spec;
    spec.interaction = {...spec.interaction, _transport_view_change: true, hover: this.callbacks.onHover ? true : spec.interaction?.hover, click: this.callbacks.onClick ? true : spec.interaction?.click, select: this.callbacks.onSelect ? true : spec.interaction?.select};
    return {spec, buffers};
  }
  message(msg) {
    if (this.closed || !msg || typeof msg !== 'object') return;
    if (msg.type === 'chunked_mount') {
      if (typeof msg.mount !== 'string' || !msg.mount.length || msg.mount.length > 128 || !decimal(msg.mount_epoch) || BigInt(msg.mount_epoch) <= this.mountEpoch) return;
      const bootstrap = msg.chunked_frame ?? String(this.options.generation);
      if (bootstrap !== this.frame && bootstrap !== String(this.options.generation)) throw new Error('unowned chunked bootstrap frame');
      this.advance(); this.mountEpoch = BigInt(msg.mount_epoch);
      this.drop(this.staged?.chart); this.drop(this.ready?.chart);
      if (bootstrap === String(this.options.generation)) {this.drop(this.chart); this.chart = this.initial; this.frame = bootstrap; this.acceptedPayload = null;}
      this.pending = this.staged = this.ready = null;
      this.mount = msg.mount; this.intent = null;
      this.lastError = null; this.settle(); return;
    }
    if (msg.mount !== this.mount || this.mount === null) return;
    if (msg.type === 'chunked_unmount') {
      this.advance(); this.mount = null; this.pending = null;
      this.drop(this.staged?.chart); this.drop(this.ready?.chart); this.staged = this.ready = null;
      this.lastError = new Error('chunked painter unmounted'); this.settle(); return;
    }
    if (msg.type === 'chunked_painted' || msg.type === 'chunked_rejected') {
      const staged = this.staged;
      if (staged && msg.intent === staged.intent && msg.frame === staged.frame) {
        if (msg.type === 'chunked_painted') {
          this.drop(this.chart); this.chart = staged.chart; this.frame = staged.frame;
          this.acceptedPayload = {spec: staged.spec, buffers: staged.buffers};
        } else {
          this.drop(staged.chart);
          if (staged.request.generation === this.generation) this.lastError = new Error('chunked frame rejected by painter');
        }
        this.staged = null; this.publish(); this.settle();
      }
      return;
    }
    if (['select', 'select_polygon', 'select_clear', 'pick', 'click'].includes(msg.type)) {
      if (msg.chunked_frame !== this.frame) return;
      if (msg.type === 'pick' || msg.type === 'click') {
        const i = msg.index, ids = this.chart.sourceRowIds;
        if (msg.trace !== 0 || !Number.isSafeInteger(i) || i < 0 || i >= ids.length) return;
        const trace = this.chart.traces[0];
        const row = {trace: 0, index: i, source_row_id: String(ids[i]), x: trace.x[i], y: trace.y[i]};
        if (msg.type === 'pick') this.send({type: 'pick_result', seq: msg.seq, chunked_frame: this.frame, row}, []);
        (msg.type === 'pick' ? this.callbacks.onHover : this.callbacks.onClick)?.(row);
        return row;
      }
      return this.select(msg);
    }
    if (msg.type !== 'view_change') return;
    const x = msg.ranges?.x, y = msg.ranges?.y;
    if (!Array.isArray(x) || !Array.isArray(y) || x.length !== 2 || y.length !== 2 || ![...x, ...y].every(Number.isFinite) || x[0] >= x[1] || y[0] >= y[1] || !decimal(msg.chunked_intent)) return;
    if (this.intent !== null && BigInt(msg.chunked_intent) <= BigInt(this.intent)) return;
    this.advance(); this.lastError = null; this.intent = msg.chunked_intent;
    this.viewState = {v: 1, ranges: {x: [...x], y: [...y]}, selection: this.viewState?.selection || null};
    this.pending = {x: [...x], y: [...y], generation: this.generation, mount: this.mount, intent: this.intent};
    this.drop(this.ready?.chart); this.ready = null;
    if (!this.active) this.active = Promise.resolve().then(() => this.pump()).finally(() => {this.active = null; this.settle();});
    this.callbacks.onViewChange?.({ranges: {x: [...x], y: [...y]}});
  }
  select(msg) {
    const trace = this.chart.traces[0], indices = new Uint32Array(trace.x.length);
    let n = 0, candidates = indices;
    if (msg.type === 'select_polygon') {
      const points = msg.points;
      if (!Array.isArray(points) || points.length < 3 || points.length > 2048 || !points.every(p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite))) return;
      const px = Float64Array.from(points, p => p[0]), py = Float64Array.from(points, p => p[1]);
      const count = Number(xyRangeIndices(pointer(trace.x, 'double *'), pointer(trace.y, 'double *'), trace.x.length, Math.min(...px), Math.max(...px), Math.min(...py), Math.max(...py), pointer(indices, 'uint32_t *')));
      candidates = indices.subarray(0, count);
      const output = new Uint32Array(count);
      n = Number(xyPolygonSelect(pointer(trace.x, 'double *'), pointer(trace.y, 'double *'), trace.x.length, pointer(candidates, 'uint32_t *'), count, pointer(px, 'double *'), pointer(py, 'double *'), points.length, pointer(output, 'uint32_t *')));
      candidates = output.subarray(0, n);
    } else if (msg.type === 'select') {
      const bounds = [msg.x0, msg.x1, msg.y0, msg.y1];
      if (!bounds.every(Number.isFinite)) return;
      n = Number(xyRangeIndices(pointer(trace.x, 'double *'), pointer(trace.y, 'double *'), trace.x.length, Math.min(bounds[0], bounds[1]), Math.max(bounds[0], bounds[1]), Math.min(bounds[2], bounds[3]), Math.max(bounds[2], bounds[3]), pointer(indices, 'uint32_t *')));
      candidates = indices.subarray(0, n);
    } else candidates = indices.subarray(0, 0);
    const ids = new BigUint64Array(n);
    for (let i = 0; i < n; i++) ids[i] = this.chart.sourceRowIds[candidates[i]];
    if (this.viewState) this.viewState.selection = msg.type === 'select_clear' ? null : msg.type === 'select_polygon' ? {polygon: msg.points.map(p => [...p])} : {range: {x0: Math.min(msg.x0,msg.x1), x1: Math.max(msg.x0,msg.x1), y0: Math.min(msg.y0,msg.y1), y1: Math.max(msg.y0,msg.y1)}};
    const result = {indices: candidates, sourceRowIds: ids};
    this.send({type: 'selection', chunked_frame: this.frame, traces: msg.type === 'select_clear' ? [] : [{id: 0, count: n, buf: 0}], total: n, source_row_ids: [{trace: 0, buffer: 1, length: n, dtype: 'u64'}]}, [candidates, ids]);
    this.callbacks.onSelect?.(result); return result;
  }
  async pump() {
    while (this.pending && !this.closed) {
      const request = this.pending; this.pending = null;
      const {budgetBytes, pageBytes} = this.options, capacity = Math.floor(budgetBytes / 16);
      const ids = new BigUint64Array(capacity), x = new Float64Array(capacity), y = new Float64Array(capacity), stats = new BigUint64Array(6);
      let chart;
      try {
        const n = await new Promise((resolve, reject) => xyChunkedColumnsChart.async(this.source.handle, ...request.x, ...request.y, 1, BigInt(budgetBytes), BigInt(request.generation), BigInt(pageBytes), pointer(ids, 'uint64_t *'), pointer(x, 'double *'), pointer(y, 'double *'), capacity, pointer(stats, 'uint64_t *'), (error, n) => error ? reject(error) : resolve(n)));
        if (this.closed || request.generation !== this.generation || request.mount !== this.mount) continue;
        if (n === 18446744073709551615n) throw Error(`chunked-column chart failed: native code ${stats[5]}, required ${stats[4]}, budget ${stats[3]}`);
        const count = Number(n), authored = this.initial.traces[0];
        if (scatterPaintChannelNames(authored).length) throw new TypeError('chunked refinement cannot resolve per-item paint channels: XYGC contains only canonical x/y columns');
        chart = scatterChart(x.subarray(0, count), y.subarray(0, count), {density: false});
        Object.assign(chart.traces[0], {
          id: authored.id, name: authored.name, style: structuredClone(authored.style),
          color_ch: structuredClone(authored.color_ch), size_ch: structuredClone(authored.size_ch), stroke_ch: structuredClone(authored.stroke_ch),
          x_axis: authored.x_axis, y_axis: authored.y_axis,
        });
        chart.sourceRowIds = ids.subarray(0, count);
        chart.sourceProvenance = {generation: stats[0], firstChunk: stats[1], chunksConsidered: stats[2], chunksRead: stats[3], bytesRead: stats[4]};
        this.homeSpec ??= this.initial.buildPayload({split: true}).spec;
        const {spec: paintSpec, buffers: produced} = chart.buildPayload({split: true});
        const spec = {...this.homeSpec, columns: paintSpec.columns, traces: paintSpec.traces, buffer_layout: paintSpec.buffer_layout};
        const buffers = this.compact(produced);
        spec.chunked = {frame: String(request.generation), mount_epoch: String(this.mountEpoch), state: this.viewState};
        this.ready = {chart, intent: request.intent, frame: String(request.generation), request, spec, buffers};
        this.publish(); chart = null;
      } catch (error) {
        this.drop(chart);
        if (!this.closed && request.generation === this.generation) {
          this.lastError = error;
          try {this.send({type: 'chunked_error', mount: request.mount, intent: request.intent, error: String(error)}, []);} catch (sendError) {this.lastError = sendError;}
        }
      }
    }
  }
  publish() {
    if (this.staged || !this.ready || this.closed) return;
    const ready = this.ready; this.ready = null;
    if (ready.request.generation !== this.generation || ready.request.mount !== this.mount) {this.drop(ready.chart); return;}
    this.staged = ready;
    try {this.send({type: 'chunked_frame', mount: ready.request.mount, intent: ready.intent, spec: ready.spec}, ready.buffers);}
    catch (error) {this.staged = null; this.drop(ready.chart); this.lastError = error;}
  }
  async whenIdle() {await this.active; if (this.lastError) throw this.lastError;}
  whenPainted({signal} = {}) {
    if (signal?.aborted) return Promise.reject(Object.assign(new Error('chunked wait cancelled'), {name: 'AbortError'}));
    if (this.waiters.size >= 16) return Promise.reject(new Error('chunked waiter limit is 16'));
    return new Promise((resolve, reject) => {
      const cleanup = () => signal?.removeEventListener('abort', cancel);
      const waiter = {resolve: () => {cleanup(); resolve();}, reject: error => {cleanup(); reject(error);}};
      const cancel = () => {this.waiters.delete(waiter); waiter.reject(Object.assign(new Error('chunked wait cancelled'), {name: 'AbortError'}));};
      this.waiters.add(waiter); signal?.addEventListener('abort', cancel, {once: true}); this.settle();
    });
  }
  settle() {
    if (!this.closed && (this.active || this.pending || this.staged || this.ready)) return;
    const waiters = [...this.waiters]; this.waiters.clear();
    for (const waiter of waiters) {
      if (this.closed || this.lastError) waiter.reject(this.lastError ?? new Error('chunked host closed'));
      else waiter.resolve();
    }
  }
  memoryReport() {
    const buffers = new Set();
    const add = array => {if (ArrayBuffer.isView(array)) buffers.add(array.buffer);};
    const chart = value => {if (!value) return; add(value.sourceRowIds); for (const trace of value.traces) {add(trace.x); add(trace.y);}};
    chart(this.initial); chart(this.chart); chart(this.staged?.chart); chart(this.ready?.chart);
    for (const payload of [this.acceptedPayload, this.staged, this.ready]) for (const buffer of payload?.buffers ?? []) add(buffer);
    return {hostRetainedCapacityBytes: [...buffers].reduce((n, b) => n + b.byteLength, 0), hostInflightOutputCapacityBytes: this.active ? this.outputCapacity + 48 : 0,
      hostTypedCapacityBoundBytes: 4 * (2 * this.outputCapacity + 2 * (64 * Math.floor(this.options.budgetBytes / 16) + 65536)) + this.initial.sourceRowIds.byteLength * 3,
      originalOverviewCapacityBytes: this.initial.sourceRowIds.byteLength + this.initial.traces.reduce((n,t)=>n+t.x.buffer.byteLength+t.y.buffer.byteLength,0),
      nativeSourceFileBytes: this.sourceFileBytes, nativeCacheEntryCountBound: Math.floor(Math.min(this.options.pageBytes,8<<20)/16),
      processMemoryObserved: process.memoryUsage(),
      existingTraceEmitterArenaBytes: PAYLOAD_TRACE_EMIT_MAX_BYTES, paintSerializationCapacityBoundBytes: 64 * Math.floor(this.options.budgetBytes / 16) + 65536,
      nativeCanonicalAdmissionBytes: this.options.budgetBytes, nativeCachePayloadBoundBytes: Math.min(this.options.pageBytes, 8 << 20), nativeResultCapacityBoundBytes: Math.max(4 * this.outputCapacity,192),
      pendingIntents: Number(this.pending !== null), stagedFrames: Number(this.staged !== null), completedResults: Number(this.ready !== null), waiterCount: this.waiters.size};
  }
  close() {
    if (this.closing) return this.closing;
    this.closed = true;
    let error;
    try {this.advance();} catch (e) {error = e;}
    try {this.drop(this.staged?.chart); this.drop(this.ready?.chart); this.drop(this.chart);} catch (e) {error ??= e;}
    this.pending = this.staged = this.ready = this.acceptedPayload = null;
    this.settle();
    return this.closing = Promise.resolve(this.active).finally(() => {this.source.close(); if (error) throw error;});
  }
}
