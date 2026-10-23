// Browser consumer: Node owns authoring, the shared client owns paint and gestures.
import { renderStandalone } from './client.js';

const container = document.getElementById('chart')!;
const status = document.getElementById('status')!;
const kind = document.getElementById('kind') as HTMLSelectElement;
let count = 8;
export let view: ReturnType<typeof renderStandalone> | undefined;
let request: AbortController | undefined;

async function update() {
  request?.abort();
  const current = new AbortController();
  request = current;
  const params = new URLSearchParams({ kind: kind.value, count: String(count) });
  try {
    const [metadata, binary] = await Promise.all([
      fetch(`/spec?${params}`, { signal: current.signal }),
      fetch(`/buffers?${params}`, { signal: current.signal }),
    ]);
    if (!metadata.ok || !binary.ok) throw new Error('Chart request failed');
    const [spec, buffers] = await Promise.all([metadata.json(), binary.arrayBuffer()]);
    if (current.signal.aborted) return;
    view?.destroy();
    container.replaceChildren();
    view = renderStandalone(container, spec, buffers);
    status.textContent = `${kind.value} · ${count} rows`;
    (document.getElementById('export') as HTMLAnchorElement).href = `/export.svg?${params}`;
  } catch (error) {
    if (!current.signal.aborted) status.textContent = String(error);
  }
}
kind.addEventListener('change', () => { count = 8; void update(); });
document.getElementById('update')!.addEventListener('click', () => {
  count = count >= 32 ? 8 : count + 8;
  void update(); // Full replacement. Incremental append is covered by the shared streaming tests.
});
document.getElementById('dispose')!.addEventListener('click', () => {
  request?.abort();
  view?.destroy();
  view = undefined;
  container.replaceChildren();
  status.textContent = 'Disposed';
});
container.addEventListener('xy:brush', () => {
  document.getElementById('selection')!.textContent = 'Selection changed in the browser';
});
window.addEventListener('pagehide', () => { request?.abort(); view?.destroy(); });
void update();
