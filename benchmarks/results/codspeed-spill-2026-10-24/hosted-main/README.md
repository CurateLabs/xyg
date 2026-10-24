# Hosted spill benchmark execution receipt

[CodSpeed run 40055566017](https://github.com/CurateLabs/xyg/actions/runs/40055566017)
completed successfully on actual main source
`71e48b67827709ed251ae05b90d010a8cef824eb`, attempt 1, manual dispatch,
2026-10-24. Its benchmark job `120757734227` ran the existing simulation command
over the Rust `kernels`, `aggregate` and `typed_series` suites and all
`benchmarks/test_codspeed_*.py` modules. The complete original job log is
losslessly retained in `benchmarks.log.gz`; execution and job metadata are in
`workflow-run.json` and `jobs.json`.

The log records **131 Python benchmarks passed**, four expected palette warnings,
and successful performance-data upload to `CurateLabs/xyg` at 03:43:43 UTC.
The 88-row kernel module includes the eight count/mean-color spill snapshot,
warm fetch, miss-with-eviction fetch and spilled compose cases. The local
collection receipt names those eight cases without re-running instrumentation;
`source-bindings.json` verifies their source and workflow bytes match the
measured historical commit. `manifest.json` hashes the retained receipt files.

This proves hosted execution and coverage. Numerical simulation samples were
uploaded to CodSpeed; the GitHub log does not contain an export of their per-case
CPU-work values. This directory does not invent those values, a before/after
speedup, cold-disk wall latency or a 100M/browser acceptance result. Fetch output
buffers are preallocated, compose includes wrapper allocations, and snapshot
includes creation/teardown as specified in the methodology. The separate
main-only browser job also passed; its authored-Scene artifact is not relabeled
as colored-spill evidence here.

Reproduce from accepted main with the existing workflow:

```bash
gh workflow run codspeed.yml --repo CurateLabs/xyg --ref main
```

The source workflow's exact instrumented commands and setup are retained in
the log and bound by the source digest file. Do not dispatch a duplicate green
run to validate this receipt or promote it into final-candidate artifact proof.
