/* Native first-paint snapshots: all chart policy was compiled by the Rust core. */
async function renderChart(element) {
  if (element.dataset.rendered) return;
  element.dataset.rendered = 'loading';
  try {
    const response = await fetch(element.dataset.payload);
    if (!response.ok) throw new Error(`Chart payload: HTTP ${response.status}`);
    const frame = window.xy.decodeFrame(await response.arrayBuffer());
    element.replaceChildren();
    const view = window.xy.renderStandalone(element, frame.message, frame.buffers[0]);
    element.dataset.rendered = 'true';
    element.chartView = view;
  } catch (error) {
    element.dataset.rendered = 'error';
    element.classList.add('xyg-demo-error');
    element.textContent = `Chart preview unavailable: ${error.message}`;
    console.error(error);
  }
}
const observer = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    if (entry.isIntersecting) {
      observer.unobserve(entry.target);
      renderChart(entry.target);
    }
  }
}, { rootMargin: '160px' });
for (const element of document.querySelectorAll('.xyg-demo')) observer.observe(element);
