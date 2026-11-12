# Benchmark catalog and hosted failure correction

Hosted CI for `0a4449db` failed the unchanged benchmark-catalog assertion on both
Python versions: actual 227 rows versus declared 219. Main recorded 9,390 passes,
178 skips and 85 xfails with one failure; the Python 3.11 floor recorded 8,870 passes,
369 skips and 84 xfails with the same failure. These remain failed runs. Main's
later missing consumer-app artifact is downstream of the failed test step; its
strict uploader is unchanged.

The methodology now lists all ten existing modules and 227 rows. The omitted
eight are four geographic membership/clipping ordering cases and four filter
clause-edit cases. Selection's own description now accounts for all 20 rows.
No benchmark source, identifier, workload, fixture, counter implementation,
assertion, timing threshold, runtime source, workflow or artifact changes.
No row is renamed/deleted; no dashboard archiving or hosted rerun is performed.

Fresh checks reproduce the original assertion and pass all 18 benchmark
metadata controls on Python 3.12 and actual 3.11 after the prose correction.
Actual pytest collection agrees on the same 227 unique IDs and per-module counts
on both interpreters. These are collection/correctness checks, not measurements.
The original collection attempt raced directory creation and failed before
execution. Four provenance checks also started before the new manifest finished
writing and failed with missing-manifest errors. The corrected run starts only
after sealing succeeds; neither setup failure receives pass credit.

The complete `90744f31` native callback checkpoint received independent bounded
APPROVE before this correction. Its immutable review record, command logs and
SHA are preserved here. Product/runtime approval carries forward only through
exact source/artifact identity checks. The materialized 100M functional witness
is producer evidence, not a new performance claim. All previous receipts and
failures remain unchanged; a 58-parent successor preserves their source history.

Reproduce with explicit checkout source/native paths and Node 22:

```bash
uv run --no-sync pytest -q tests/test_benchmark_environment.py
uv run --no-sync pytest --collect-only -q benchmarks/test_codspeed_*.py
```

For actual 3.11 activate its existing environment with `VIRTUAL_ENV` and
`uv --active --no-sync`; do not sync the borrowed environment. No new timing run,
broad product rebuild or repeated broad-suite pass is claimed. New-head hosted
CI, required merge queue, 100M/50 FPS/pixel-active/global-budget/host/accessibility/
competitor acceptance, whole issues and milestones 4–7 remain open.
