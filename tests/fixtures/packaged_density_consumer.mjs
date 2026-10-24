// Actual Node-authored split buffers on the public kernel-less ChartView
// boundary. No comm/backend is invented for this unsupported replay source.
import { ChartView, attachHostWasmTicks } from '/client.js';

const spec = await fetch('/spec?kind=density').then(response => response.json());
if (spec.buffer_layout !== 'split') throw Error('density proof requires the native split contract');
const count = Math.max(...spec.columns.map(column => column.buf)) + 1;
const buffers = await Promise.all(Array.from({ length: count }, (_, index) =>
  fetch(`/buffers?kind=density&index=${index}`).then(response => response.arrayBuffer())));
const view = new ChartView(document.getElementById('chart'), spec, buffers.map(buffer => new Uint8Array(buffer)), null);
// Observe the original Rust grid before tick admission/viewport work. This
// hook is proof instrumentation, not an application attachment mechanism.
globalThis.__xygStandaloneObserver({ phase: 'attached', view });
attachHostWasmTicks(view, spec);
window.addEventListener('pagehide', () => view.destroy());
