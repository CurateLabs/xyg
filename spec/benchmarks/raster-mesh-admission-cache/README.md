# Cached mesh admission count

The regression came from counting every record again inside
`SceneDocument::check_mesh_budgets` before raster export. A scene with no
triangles paid that full scan. The decoder now retains the triangle record
count during its existing validation pass, including invisible records.
Repeated exports use that private count for the face-count gate. The
format-specific fill/outline work checks and all thresholds remain unchanged.

The source comparison is `fdf7a374` → `f839e295`. `environment.json` records
full commits, tool versions, CPU, and benchmark/lockfile hashes. The existing
`scene_v4_raster_commands` fixture contains mixed polyline, scatter, and
rectangle records with no triangles. Its timed region is
`to_raster_commands(1.0)`; construction and decoding are excluded, so this
report makes no claim about end-to-end scene compilation or decode latency.

All measurements run through CodSpeed CLI. Committed JSON files are raw
responses from CodSpeed MCP `get_benchmark_result`, `compare_runs`, and
`query_flamegraph`; no authentication material is included. Simulation
profiles explain the mechanism; walltime validates the result on hardware.
Local x86_64 runs use runner 5.6.0 and must not be numerically compared with
the historical aarch64 CI runs using runner 5.0.2.

## Results

[Simulation comparison](https://app.codspeed.io/CurateLabs/xyg/runs/compare/6adb80a882e29de63121bbd9..6adb7ff182e29de63121bbb2)
and [initial walltime comparison](https://app.codspeed.io/CurateLabs/xyg/runs/compare/6adb8135f7565a2f9679617a..6adb815b82e29de63121bc09):

| Records | Simulation base → head (ms) | Simulated time reduction | Walltime best base → head (ms) | Walltime reduction |
| ---: | ---: | ---: | ---: | ---: |
| 10,000 | 3.743 → 3.619 | 3.32% | 0.224 → 0.218 | 2.76% |
| 100,000 | 38.517 → 34.960 | 9.23% | 2.293 → 2.150 | 6.24% |
| 1,000,000 | 405.124 → 348.288 | 14.03% | 40.157 → 36.790 | 8.38% |

CodSpeed classifies the 100,000- and 1,000,000-record simulation results as
improvements and the 10,000-record result as unchanged. It classifies all
three initial walltime results as unchanged. The percentages above express
reduced elapsed/simulated time (`1 - head/base`), not CodSpeed's reciprocal
speedup percentage. Walltime results come from 100 rounds per size on a
shared development host; they are local observations, not a dedicated-runner
performance gate or a measurement of other chart families.

A [second walltime pair](https://app.codspeed.io/CurateLabs/xyg/runs/compare/6adb81c082e29de63121bc21..6adb81960e3bbd9ef5636396),
run in reverse order (head then base), observed the million-record best time
at 39.437 ms → 36.834 ms (6.60% less time).
Its medians were 40.835 ms → 37.186 ms. CodSpeed also classifies
these repeat results as unchanged. Both pairs favor the patch on hardware,
but the classification and host variance limit the strength of a walltime
claim. The deterministic simulation regression is removed; no dedicated
runner walltime win is claimed.

The million-record simulation profile retains essentially the same raster
emission cost (348.2 ms → 348.1 ms), while the 56.2 ms mesh-count iterator
scan disappears. The patch does not bypass the safety check; it derives its
count once during validation.

## Reproduction

Check out each recorded commit in separate clean worktrees on the same
machine, install `cargo-codspeed` 4.6.0 and CodSpeed CLI 5.6.0, and authenticate
with `codspeed auth login`. In each worktree run:

```bash
cargo codspeed build -m simulation --bench kernels --locked
codspeed run -m simulation -- cargo codspeed run --bench kernels scene_v4_raster_commands
cargo codspeed build -m walltime --bench kernels --locked
codspeed run -m walltime -- cargo codspeed run --bench kernels scene_v4_raster_commands
```

Run walltime sequentially after both worktrees finish compiling, with no
other benchmark or build in progress. Compare matching modes through
CodSpeed MCP `compare_runs`; the run IDs and benchmark URIs in the raw
responses select the measurements for `get_benchmark_result` and
`query_flamegraph`.

## Correctness and output contract

The benchmark produces a successful native raster command byte vector. The
cache is not serialized and does not change the C ABI or emitted geometry.
`mesh_admission_counts_mixed_and_invisible_records_during_decode` checks
mixed records, invisible triangles, repeated exports, and the raster face
threshold. Existing scene tests preserve format-aware vector/raster limits,
outline/sliver charging, and dense-image refusal. Validation on the rebuilt
core passed 156 Rust scene tests, 18 Python static mesh tests, and 4 Node
static mesh tests. Full-worktree pre-commit hooks and Ruff checks also pass.
