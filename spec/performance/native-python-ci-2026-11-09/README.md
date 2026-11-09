# Native library selection in Python CI

This correction exports the existing release native library in both Python
pytest steps. Node subprocesses inherit that explicit selection. No loader,
runtime, browser assertion, timeout, package cap or merge-queue gate changes.

Published head `32d5839b522534efb10f61c8bea898ad0b3baac8` failed main CI run
`42688274537`, job `129403131762`, in the required chunked browser batch:
13 passed and the Node bridge case failed with `XYG_NATIVE_LIBRARY_MISSING`.
The Node host suite's export belongs to its earlier shell step and does not
persist into pytest. The later missing consumer-app artifact is a consequence
of that failure; its strict upload behavior is preserved.

The same public Node bridge failure is reproduced locally with
`XYG_NATIVE_LIB` removed. The required browser batch and workflow guards pass
on Python 3.12 with explicit native selection. The Python 3.11 batch records
18 passes and one installed-Jupyter startup connection refusal; that unchanged
case passes on a separate rerun. The original failure is retained, and no
startup-reliability repair or all-green full Python 3.11 batch is claimed. Exact commands, exits and immutable log
hashes are recorded in `checks.json`. Earlier receipts remain unchanged;
the successor binding preserves their complete source history and current
runtime identities. Existing product approvals apply only to equal bytes.

This is a CI configuration correction. It establishes no new 100k rendering
responsiveness, reliability, performance, host or milestone acceptance. The
published head's 100k wall-limit failure remains open. Final-head hosted checks,
current-main freshness and merge queue remain required.
