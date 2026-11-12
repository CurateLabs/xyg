# Materialized-100M native dashboard walltime baseline

This checkpoint adds four manual CodSpeed rows. It does not optimize product
code, qualify 50 FPS, or complete #112 or milestones 4–7. The independently
reviewed parent is `53bc3215a00044e93c28722ce8a4b48720e52ab2`; native,
WASM, client and compiled inputs remain identical. PR1122 stays at that reviewed
parent while this separate local branch is qualified.

The new `benchmarks/test_codspeed_filter_dashboard.py` fixture launches the
public Node native session and five composed browser views once. Index building,
initial correctness checks and teardown are outside measurement. Each timed
operation includes Python/Node/DevTools IPC. Query/density include the binary
loopback HTTP callback, Rust work and browser decoding. `update` also includes
the ordinary dashboard publication and five explicit synchronized paints.
`cached` paints the previously published textures. Independent rows are not
additive latency components.

The source is the earlier fully materialized and fully verified deterministic
100M fixture, with four XYGC files, five corresponding dimensions and high-u64
row identity. Recipe and file digests remain in the parent native-callback
receipt; the 6.4 GB generated files are not committed and are not beyond RAM.
This checkpoint does not regenerate or independently rescan that full source.
The source-manifest SHA is
`616229518a5b58e10ebbeb54de84350b8e6de7fcb8ecd32f8de27799890a8219`.

Five carriers are 400×260 CSS pixels. The five passive count grids remain
100×100, with 346 active cells over the first view's 346-pixel plot width.
The explicit session budget is 256 MiB; the unchanged 128 MiB declaration
refuses this index before publication (status 2). Accounted index bytes are
139,608,328, resident bytes 139,906,392 and query/paint peak 141,587,096.
These logical quantities exclude caller scratch, HTTP/DevTools copies, OS
caches and browser/GPU storage; there is no process-wide memory claim.

Every successful measured query/paint reports tier 3, zero canonical rows read
and exactly one source build. Two exact cut-aligned ranges alternate; arbitrary
endpoints and active-view switches are not this workload. Each update asserts
the exact selected total. Earlier parent evidence supplies independent full
count/texture/membership oracles; those broader oracles are not rerun here.
Headless Chromium uses explicitly disclosed ANGLE SwiftShader. The driver
requires the full source and explicit Chromium, and requires native close ACK,
zero pending transport and zero page errors after the successful run.

See `checks.json` for final CodSpeed run IDs, CLI results, artifact/source pins,
commands, raw output archives, setup failures and measurement limits. The first
private four-cell probe reported best 35.32 ms. A private 346-cell probe reported
best 34.51 ms; an initial promoted-harness probe reported best 35.00 ms.
These diagnostic URIs and all failed attempts remain preserved. None supplies
a speed improvement or 20 ms update-budget qualification. Relative variance,
including unstable cached-paint and query samples, is retained rather than
treated as an optimization result.

The final-source CodSpeed run is
[`6af50211cca4517c4307b1f4`](https://app.codspeed.io/CurateLabs/xyg/runs/6af50211cca4517c4307b1f4).
Each row has 100 measured iterations. CLI-processed results are:

| Path | Best | Relative standard deviation |
| --- | ---: | ---: |
| Range reply | 5.03 ms | 311.42% |
| Density reply | 11.69 ms | 14.88% |
| Cached five-view paint | 8.39 ms | 94.76% |
| Complete five-view update | 33.21 ms | 10.09% |

Only the complete-update row describes the full measured update path. Even its
best sample exceeds 20 ms. This is neither a p95 nor a reliable cadence result;
variation between diagnostic runs is not credited as an improvement. The
CodSpeed profile's sampling-event losses are retained in the CLI logs. CPU
samples from the first diagnostic profile were restricted to its measured
SampleStart/SampleEnd window; setup scans were excluded. They show substantial
software-renderer work and Node marking/collection, without establishing an
exhaustive latency attribution or a specific optimization.

Two initial private-harness errors accompanied the valid 128 MiB refusal:
Playwright did not propagate the original error usefully, then the driver's
cleanup attempted a command after the host exited. The diagnostic harness now
returns an explicit setup failure and preserves the primary error. An initial
Ruff import-order check failed and was corrected. Missing-browser and smaller-
source negative controls deliberately exit 1. Ordinary CI discovers four
manual rows but skips them without the materialized source; these skips carry
no qualification. All 227 previous benchmark IDs are retained, for 231 total.

Reproduce with the exact command and scope in
[`spec/benchmarks/methodology.md`](../../benchmarks/methodology.md#manual-native-callback-dashboard-walltime).
The fixture can be authored and verified separately, without timing claims:

```bash
uv run --no-sync python scripts/gen_filter_paged_fixture.py generate /new/fixture --rows 100000000
uv run --no-sync python scripts/gen_filter_paged_fixture.py verify /new/fixture
```

Trusted pointer/keyboard end-to-end timing, RAF cadence, hardware GPU/platform
coverage, wider index/grid sizes, arbitrary-boundary work, scale distributions,
full memory accounting, competing systems and all broader acceptance remain
open. Hosted checks, current-main freshness and merge queue are not qualified
by this local baseline.
