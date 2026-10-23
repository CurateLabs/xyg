# Colored spill mapped-source control

`control-1m.json.gz` is the losslessly compressed raw 1,000,000-row control
from the working tree over `515aa915` with the distinct colored-spill harness.
The report binds its actual Python/Rust/TypeScript inputs, harnesses, native
library, client, locks and environment by SHA256. It passed the independent
verifier with `--artifact-root` against those measured files. This is a source
checkout control, not an accepted package artifact or a 100M execution.

The run recorded 24 pans and eight actual adjacent-level zooms. Final resident
tile bytes were 16,517,088 under the 16,777,216-byte budget, with 73,142,272
spilled bytes. Borrowed canonical x/y/color mappings, count/mean-color oracles,
inventory/fetch-all equality, reduced cached transfers and complete process,
spill-file and mapping cleanup all passed. Peak observed process-tree RSS was
289,144,832 bytes; worker high-water RSS was 298,713,088 bytes. Sampling and
the worker high-water number measure different quantities, both retained.

Pan p95 was 1.326 ms and maximum zoom was 20.166 ms at the documented
Python/native boundary. The control's timings are advisory, were collected
alongside other validation, and cannot establish the dedicated 100M latency
gate. The report requires `scope: host-kernel-only` and `browser.status:
not-run`: no nonblank pixels, browser continuity, GPU allocations, larger-than-RAM,
competitive advantage or complete #11 acceptance is claimed.

Raw JSON SHA256: `f253c7b2f0c60ad2abadaf63ad9f9ee95ca0e59a379801de91d327262d625e04`.
Gzip SHA256: `0e66c5df59b28d8108c103a9ce36ff28fe07a0a857e19b5ab6160bbdd05da6a0`.

```bash
gzip -dc benchmarks/results/colored-spill-2026-10-23/control-1m.json.gz \
  > target/colored-spill-retained.json
uv run python scripts/verify_density_spill_report.py target/colored-spill-retained.json
# Add --artifact-root "$PWD" only at the exact measured source/build inputs.

uv run python benchmarks/bench_density_e2e.py --workload colored-spill \
  --points 1000000 --chunk-points 262144 --timeout 600 \
  --max-rss-gib 8 --max-disk-gib 2 --output target/colored-spill-1m.json
uv run python scripts/verify_density_spill_report.py target/colored-spill-1m.json \
  --artifact-root "$PWD"
```

The [evidence contract](../../../spec/design/density-spill-evidence.md) defines
the exact scheduled/manual main authority and the remaining browser/scale
acceptance. Report supplied budgets cannot relax that authority.
