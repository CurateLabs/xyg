# Main-only 100M colored-spill host/kernel evidence

Source: `71e48b67827709ed251ae05b90d010a8cef824eb` (clean `main`).
Execution: [density authority run 40055564684](https://github.com/CurateLabs/xyg/actions/runs/40055564684),
attempt 1, manual dispatch, 2026-10-24. The existing Blacksmith four-vCPU Ubuntu
lane completed all four producer/verifier pairs successfully. Artifact
`12545361832` contains both resident-count reports and both distinct colored-spill
reports. These original JSON bytes are retained losslessly as gzip files;
`manifest.json` records compressed and decoded hashes and sizes. `job.log.gz`
retains the complete job log, including capacity, commands and verifier output;
`workflow-run.json` and `artifacts.json` retain GitHub execution metadata.

## Colored-spill authority result

| Observation | Measured value / contract |
| --- | --- |
| Canonical source | 100,000,000 rows; three f64 mappings, 2,400,000,000 bytes |
| Policy | Production admission; adaptive base 4096; no control override/prewarm |
| Journey | 24 pans and eight actual adjacent-level zooms, 512 × 512 viewport |
| Kernel pan p95 | 0.37907085 ms, hard gate <16 ms |
| Slowest kernel zoom | 8.125563 ms, every step hard gate <50 ms |
| Largest sampled resident tile cache | 16,517,088 bytes ≤ 16,777,216-byte budget |
| Spilled tile bytes | 274,468,864 |
| Final cache hits / misses | 2,334 / 265; `over_budget: false` |
| Cached / separate fetch-all reply bytes | 2,423,728 / 49,012,864 |
| Independent overview oracle | All 100M counts conserved; maximum count/RGB error 0 |
| Admission / build-spill-first-payload | 0.109040 s / 2.211616 s |
| Process-tree peak RSS / worker VmHWM | 3,397,898,240 / 3,436,040,192 bytes |
| Temporary disk peak | 2,674,664,607 bytes |
| Cleanup | Store/figure/mappings released, budget restored, temporary tree removed, no orphan processes |

The timer wraps `tile_store_paint` including its Python/ABI wrapper. It excludes
host dispatch, instrumentation, parsing, oracle work and browser work. The raw
report retains every timing, window, served level, normalization, tile inventory,
hash, residency observation and source/environment/native/client identity.
The 409 source-file and eight harness-file hashes were also compared with the
parent checkout at this source commit; all matched.

This is the **host/kernel slice** defined by
[density-spill-evidence.md](../../../../spec/design/density-spill-evidence.md).
Its `browser.status` remains `not-run`; texture ownership is simulated. It does
not prove colored browser continuity, physical GPU allocation, seam/pixel
equality, larger-than-RAM operation, the competitive comparison, final candidate
artifacts or complete #11/#5/#108 acceptance. The count-only resident browser
report is a separate workload and cannot supply those colored-spill claims.
No performance comparison between the 1M control and 100M authority is asserted.

## Reproduce and inspect

On accepted main, use the existing scheduled/manual lane, once per changed
measurement source; do not execute 100M locally or spoof Actions context:

```bash
gh workflow run density-100m.yml --repo CurateLabs/xyg --ref main
gh run download 40055564684 --repo CurateLabs/xyg \
  --name density-e2e-71e48b67827709ed251ae05b90d010a8cef824eb --dir retained-density
```

The retained source workflow records the exact producer command with `--workload
colored-spill --points 100000000 --authority --timeout 3600 --max-rss-gib 12
--max-disk-gib 4`. Its verifier ran in the same trusted Actions step with external
`--sha "$GITHUB_SHA" --artifact-root "$GITHUB_WORKSPACE"`. The retained log has
`colored-spill host/kernel slice OK (100000000 rows)` at 02:48:14 UTC.
Authority verification deliberately refuses promotion from an ordinary local
shell; the report's self-described Actions fields are insufficient authorization.
Use the retained hosted verifier outcome and independently inspect the raw data.

Both control reports are independently checkable locally after decompression:

```bash
python3 scripts/verify_density_spill_report.py retained-density/density-e2e-colored-control-71e48b67827709ed251ae05b90d010a8cef824eb.json \
  --sha 71e48b67827709ed251ae05b90d010a8cef824eb
python3 scripts/verify_density_e2e_report.py retained-density/density-e2e-control-71e48b67827709ed251ae05b90d010a8cef824eb.json \
  --sha 71e48b67827709ed251ae05b90d010a8cef824eb
```

No `--artifact-root` is claimed for a separately rebuilt local native library:
the loaded hosted binary/client hashes are in the raw report. Later changes do
not alter this historical source identity or turn this run into candidate proof.
