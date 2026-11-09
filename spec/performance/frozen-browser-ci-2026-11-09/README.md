# Offline frozen browser capture

Hosted head `32d5839b522534efb10f61c8bea898ad0b3baac8`, CI run
`42688274537`, Python-floor job `129403131741`, records 8,454 passes,
four frozen HTML screenshot timeouts, 365 skips and 84 expected failures.
Explicit Playwright Chromium selection alone did not resolve those timeouts.

The same Chrome 149 executable reproduces the original 30-second screenshot
CLI timeout locally. A separate minimal static page also fails to produce a
screenshot before its diagnostic ten-second limit. The evidence establishes
the failing CLI path, not its browser-internal cause.

The test-only capture now uses the existing Playwright dependency to own the
browser, navigate the unchanged file, wait for the public frozen-ready marker
and retained GPU traces, capture actual pixels and close the browser. It rejects
page errors and HTTP/HTTPS attempts. The Python subprocess retains its original
30-second limit, and all existing pixel, artifact recovery, tampering, capacity,
source-disposal and scale assertions remain intact. No product renderer,
artifact bytes, module, package cap or native ABI changes.

Exact commands, outcomes, archived failures, output hashes and successor
bindings are in `checks.json`. The native-library CI correction is inherited
only over verified unchanged bytes. This is bounded test-harness qualification,
not a repair for earlier application startup/Worker failures or 100k scheduling,
nor whole-issue or milestone completion. New-head hosted checks, freshness and
the merge queue remain required.
