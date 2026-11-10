// Capture the exact state admitted by the wait predicate. Kernel startup can
// change the DOM before a later page.evaluate call reads it again.
export async function namedIdleKernel(page, kind, timeout = 45000) {
  const witness = await page.waitForFunction(kind => {
    const name = document.querySelector('.jp-Toolbar-kernelName')?.getAttribute('aria-label');
    const status = document.querySelector('.jp-Notebook-ExecutionIndicator')?.getAttribute('data-status');
    return document.querySelector('.jp-Notebook .cm-content') && name && name !== 'No Kernel'
      && status === 'idle' && (kind === 'notebook7' || document.body.innerText.includes('Idle'))
      ? { name, status } : false;
  }, kind, { timeout });
  try { return await witness.jsonValue(); } finally { await witness.dispose(); }
}
