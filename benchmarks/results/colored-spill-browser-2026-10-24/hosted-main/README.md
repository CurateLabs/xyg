# Retained main 100M colored-spill browser evidence

[Actions run 40063864999](https://github.com/CurateLabs/xyg/actions/runs/40063864999)
completed **successfully**, attempt **1**, manual dispatch on clean `main` at
`885908f2799803c1f9d8f6482d091adbf2c94d76`. Created
`2026-10-24T04:49:35Z`; job `120782890456` ran from `04:49:46Z` to
`04:52:55Z`. This retains the one already-dispatched run; no new benchmark,
browser run, dispatch, retry, cancellation or GitHub mutation was performed.

The source tree is `7f5acb64d4c7b98591ea6bea8fa148234b249534`, identical to
reviewed commit `295278c8` (full identity in `source-bindings.json`). This is
historical evidence for that source. It makes no candidate, competitive winner,
publication, or whole-#11/#108 completion claim. The parent owns independent
review and authoritative specification reconciliation after integration.

## Retained originals and integrity

All **six original JSON files** from artifact **12547963402** are retained,
without parsing/reformatting their decoded bytes, as deterministic gzip
(`gzip.compress`, level 9, `mtime=0`, no filename):

- `density-e2e-control-<source>.json.gz`: resident-count 1M control.
- `density-e2e-100m-<source>.json.gz`: resident-count 100M authority.
- `density-e2e-colored-control-<source>.json.gz`: colored-spill 1M host control.
- `density-e2e-colored-100m-<source>.json.gz`: colored-spill 100M host authority.
- `density-e2e-colored-browser-control-<source>.json.gz`: same-source 1M browser.
- `density-e2e-colored-browser-100m-<source>.json.gz`: same-source 100M browser.

Here `<source>` is the full 40-character commit above. `artifact-12547963402.zip`
preserves the complete original **289,604-byte** archive. Its SHA-256 matches
GitHub's `artifacts.json` digest exactly:
`7d52c3d13cbee0ce883d5044a332dfe3daba9ecb0c011804846bf33827ec0d68`.
ZIP CRCs and each member's exact bytes were checked against the decoded gzip.
Only attempt 1 exists; all available attempt outputs are retained. No missing
report or failed step was observed.

`workflow-run.json`, `workflow-attempt.json`, `jobs.json`, and `artifacts.json`
are the original GitHub API response bodies. `job.log.gz` preserves the complete
job log fetched directly with
`gh api repos/CurateLabs/xyg/actions/jobs/120782890456/logs`, including commands,
checkout, capacity, producer/verifier output and post-job cleanup. It does not
use the quota-constrained `gh run view --log` cache. `source-workflow.yml` is
the exact workflow blob from the historical commit. `manifest.json` records
every retained file's SHA-256/length and each gzip's decoded SHA-256/length;
it excludes itself and `SHA256SUMS`. `SHA256SUMS` additionally hashes the manifest
and excludes only itself.

`source-bindings.json` records successful comparisons of **409 product files**,
**eight host harness/lock/toolchain files**, and **two browser helper/verifier
files** against `git show <source>:<path>`: **419 distinct historical files**.
Manifest and environment aggregate hashes were independently recomputed.
Both companions match their host's source-column hashes, environment,
provenance, spill/oracle/resource observations, cleanup and exact immutable
host-file SHA-256. All reports identify the specified clean commit. The 100M
colored pair records the actual manual-main run ID, attempt and source.

The immutable 100M host report SHA-256 is
`20194b01d6e5112e270ed0df7277e0fdbaca393b38452277a5fe53473c130c24`;
its browser companion is
`64572c562ffb487599e62994310d0ef5fb9d49952d1fe1d748100a12ef1f6492`.
Native ABI is **395**; recorded native binary SHA-256 is
`f7993d672d034c2f592d021ce0240e72ba2bbc419d468a8c2e51e37b03e43923`;
generated standalone client SHA-256 is
`8cb331481653b845d7e081d340c459a914115dddf8864095d502af5f9d664149`.
The Chromium executable hash is recorded in both original companions and
`source-bindings.json`. Those generated binaries were not downloaded or rebuilt
locally: their hosted `--artifact-root` verifier outcomes are retained proof;
recorded hashes alone do not provide independent runner attestation.

## Actual 100M colored journey

The companion uses the existing host worker's actual figure, native tile store,
three f64 source mappings and windows. This is the colored-spill workload;
the separately retained resident-count reports supply no colored-browser claim.

| Observation | Actual 100M result |
| --- | --- |
| Source | 100,000,000 rows; x/y/color mappings total 2,400,000,000 bytes |
| Policy | Production eligibility 2M; adaptive base 4096; no control override/prewarm |
| Initial density payload | `pyramid-L3-tiles` / `pyramid-count` |
| Browser journey | Seed plus 24 pans at level 2 and eight alternating level 1/2 zooms; 512 × 512 framebuffer |
| Cached/fetch-all equality | **33/33** complete RGBA framebuffer SHA-256 matches |
| Actual adjacent fades | **8/8**; both levels draw at midpoint, source survives, fade retires |
| Minimum density ink | **3,204 pixels** across cached and fetch-all samples; red and blue both present |
| Seam strips | At least **3,552 examined pixels**, at least **30 density pixels**, maximum channel error **0** (tolerance 2) |
| Browser cached/fetch-all transfers | **9 / 188 tiles**, **2,424,240 / 50,078,400 reply bytes** |
| Shared bootstrap, excluded above | Four tiles, 1,065,536 reply bytes; subsequent seed request is included above |
| Maximum owned tile allocation | Cached **3,461,328 bytes**; fetch-all **2,396,304 bytes**, each within 8,388,608-byte policy |
| Instrumented allocation peak | Cached **5,832,928 bytes**; fetch-all **4,767,904 bytes** |
| Textures created/uploaded/deleted | Cached **46/46/46**; fetch-all **225/225/225**; zero instrumented textures remain |
| Native spill file | **274,468,864 bytes** |
| Largest host sampled native resident tile cache | **16,517,088 bytes**, within **16,777,216-byte** budget |
| Host final pre-browser cache stats | 2,334 hits / 265 misses; `over_budget: false` |
| Independent count/mean oracle | Exactly 100,000,000 counts; maximum count/RGB errors **0/0** |
| Host pan p95 | **0.7684425499999998 ms**, hard gate <16 ms |
| Slowest host zoom | **11.230729 ms**, every zoom hard gate <50 ms |
| Source generation / admission | **6.928350239000025 / 0.14590304799997966 s** |
| Build/spill/first payload | **2.9617231680000202 s** |
| Complete supervised invocation | **22.598387021999997 s**, ceiling 3,600 s |
| Process-tree peak RSS / worker VmHWM | **4,002,086,912 / 3,436,269,568 bytes**, ceiling 12,884,901,888 bytes |
| Peak temporary disk | **2,689,169,487 bytes**, ceiling 4,294,967,296 bytes |

Actual WebGL calls establish RGBA8 extent/ownership, successful allocation,
native-byte reconciliation, and deletion. Instrumented peaks include **33
monolithic seam-oracle textures per browser mode**, and exclude initial-payload
textures allocated before instrumentation. Thus these are measured WebGL
allocation/ownership accounting on **software** rendering, not physical GPU
allocation, hardware VRAM measurement or a complete allocator audit.

The real browser is **Chrome/149.0.7827.55**, WebGL2 through ANGLE Vulkan
**SwiftShader Device (Subzero)**. The source report records four CPUs, Linux
x86_64, CPython 3.11.16, NumPy 2.4.6, Rust 1.96.0 and Node 22.23.4. Runner
capacity in the full log is `MemTotal: 16167124 kB`; this is not a
larger-than-RAM workload.

Presentation is deliberately stepped with a frozen clock at fade start,
+70 ms and +210 ms. Midpoint draws use both actual adjacent levels at opacity
0.5. It proves deterministic continuity for these scripted windows, not natural
animation cadence, FPS, user interaction latency or physical-GPU performance.
The host timer wraps only `tile_store_paint` including its Python/ABI wrapper;
it excludes dispatch, instrumentation, parsing, oracle and browser work.
Browser scheduling/readback/manual-clock values do not become host timings.
The host report correctly remains `scope: host-kernel-only` with
`browser.status: not-run`; the immutable companion supplies the separate browser
evidence. Supervisor RSS/disk/elapsed observations cover the complete optional
host-plus-browser invocation. RSS is sampled process-tree accounting, not VRAM.

All cleanup fields passed: the browser was observed in the supervised worker
group, exited and was reaped, its profile and socket alias disappeared, HTTP
thread stopped, figure/native spill store released, spill files disappeared,
mappings closed, tile budget restored and owned temporary tree removed.
No process-group orphan remained. Both charts destroyed their tile ownership
and ignored a real saved late reply without allocating.

## Control, hosted verification and limits

The same-run **1M** colored control passed 33 framebuffer matches and eight
adjacent level 0/1 fades at explicit base 2048 with lowered eligibility/prewarm.
Minimum density ink was 3,172 pixels, minimum seam ink 30, maximum seam error 0;
cached/fetch-all transfers were 9/188, and texture creation/deletion was
46/46 and 225/225. Peak RSS was 1,634,611,200 bytes, temporary disk 111,731,954
bytes and total invocation 10.259359243999995 s under 8 GiB / 2 GiB / 600 s.
No scale-performance comparison between the control and authority is asserted.

The complete hosted log is the authority-verification record. It contains:

- `04:52:07.6699958Z`: resident-count 1M report OK.
- `04:52:15.4383105Z`: resident-count 100M report OK.
- `04:52:26.1970004Z`: colored-spill 1M host/kernel slice OK.
- `04:52:26.2719947Z`: same-source browser companion OK.
- `04:52:49.5281734Z`: colored-spill 100M host/kernel slice OK.
- `04:52:49.5902449Z`: same-source browser companion OK.

The source workflow and log show both colored verifiers used the actual
host report, external `--sha "$GITHUB_SHA"` where required, and hosted
`--artifact-root "$GITHUB_WORKSPACE"`. No authority verifier was run locally,
and no Actions environment was fabricated. The three control reports were
also checked locally in the actual local context with the historical verifier
scripts and external source SHA, without `--artifact-root` for unavailable
hosted binaries; commands/results are in `local-control-validation.json`.
`retention-verification.json` records the byte, metadata, source and hosted-log
checks. `metrics.json` contains the extracted observations and original units;
the six unmodified raw JSON reports remain authoritative.

This does not establish billion-row or out-of-memory-scale operation,
competitor comparisons, all chart families, natural browser latency,
publication readiness, final candidate artifacts or complete issue acceptance.
There were no observed run failures or missing outputs. The remaining limits
are evidence scope and the absence of independently retained hosted executable
binaries, physical GPU telemetry and an independent review of this retention
diff. No PR, issue, tag, release or publication was changed.

## Inspect and reproduce verification

From this directory, `sha256sum -c SHA256SUMS` checks every retained path. The
following additionally checks original decoded bytes and exact ZIP membership:

```python
import gzip
import hashlib
import json
import pathlib
import zipfile

root = pathlib.Path(".")
manifest = json.loads((root / "manifest.json").read_bytes())
for name, entry in manifest.items():
    data = (root / name).read_bytes()
    assert len(data) == entry["bytes"]
    assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    if "decoded_sha256" in entry:
        raw = gzip.decompress(data)
        assert len(raw) == entry["decoded_bytes"]
        assert hashlib.sha256(raw).hexdigest() == entry["decoded_sha256"]
with zipfile.ZipFile(root / "artifact-12547963402.zip") as archive:
    assert archive.testzip() is None
    for name in archive.namelist():
        assert archive.read(name) == gzip.decompress((root / (name + ".gz")).read_bytes())
```

To inspect provenance against the historic source, hash
`git show 885908f2799803c1f9d8f6482d091adbf2c94d76:<path>` bytes for every
`historical_file_sha256` entry in `source-bindings.json`; compare the report's
own source/harness dictionaries and recompute their compact sorted JSON hashes.
The original `source-workflow.yml` and full job log retain the exact execution
commands, resource bounds and verifier invocations. No redispatch is necessary
to inspect this evidence. `validation.txt` records the required pre-commit and
Ruff checks used before the retention commit.
