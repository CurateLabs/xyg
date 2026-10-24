# Colored-spill browser continuity and supervised companion (#11/#108)

`scripts/density_spill_browser_smoke.py` supplies the real-browser journey and
`benchmarks/bench_density_e2e.py --workload colored-spill
--colored-browser-report PATH --chrome CHROMIUM` opts into a separate companion
inside the existing supervised host worker. The existing host/kernel report
contract remains unchanged: `scope: host-kernel-only` and
`browser.status: not-run`. The default command remains host-only. Browser
continuity uses deterministic presentation cadence, with no FPS or end-to-end
latency claim. No actual 100M browser result is retained yet. The separately
accepted hosted 100M host report remains historical host-only evidence.

The standalone smoke remains a bounded control and refuses more than 1M rows.
This facility does not establish billion-row, larger-than-RAM, competitive,
publication, natural-cadence or whole-#11 acceptance. It changes no product
behavior, dependency or CI workflow. Parent-owned workflow wiring and actual
trusted authority execution remain separate work.

## Path and assertions

The harness imports the actual `benchmarks/_density_spill.py` generator, endpoint
colormap, mapped-pointer inventory, native frame parser, count/mean oracle and
24-pan/eight-zoom window generator. It builds the public
`scatter_chart(scatter(x, y, color=color, color_domain=(0, 1), colormap=...,
opacity=1, density=True, pyramid_spill=True)).figure()`. Each source is an f64
mapping, with file hashes checked against the generator's streaming hashes.
Borrowed pointers and absence of retained row-color caches are checked before
and after the journey. This reuses the actual workload rather than substituting
the separate fixture in `density_tile_smoke.py`.

Local admission is capped at 1M **before allocation**, and optimized Python is
refused. As in the host control, only Python lazy-pyramid eligibility is lowered
to one; the store is explicitly prewarmed, with adaptive base 2048 and native
tile budget 16 MiB. Production eligibility remains 2M. Native first-payload
policy stays unchanged: it truthfully emits `exact` / `bin2d` with a mean-color
plane. It does not advertise tile discovery below production eligibility.
Therefore the bounded browser receives one genuine public `density_view`
bootstrap reply with empty XYDC observations. Product XYDT admission enables
the client's normal tile-inventory requests; no fabricated `tiles` metadata,
fixture store, or success flag enables the path.

The actual generated standalone bundle paints the public initial payload. A
real chart resize gives a 512-square plot, matching the host workload. The
client schedules each shared window and sends its own binary XYDC observations
over loopback HTTP. The server forwards them to the same figure's
`density_view(..., tile_cache=...)`; actual Rust XYDT bytes and host reply
metadata go to the product `_onKernelMsg` receiver. Requests must match the
scripted windows exactly. Rust chooses levels, retained keys, gutters, tone,
color and texture budget. Every pan preserves its level; all eight zooms must
change the served level by exactly one without resource coarsening/refine debt.

The checks exercise dossier §§5/27/28/29/32b:

- **Actual WebGL allocation:** wrap real `createTexture`, `texImage2D` and
  `deleteTexture` calls, check RGBA8 dimensions, GL errors and `isTexture`, and
  reconcile every retained tile against native byte accounting and the eight
  screen budget. Reported instrumented peak bytes include the separate stitched
  oracle textures; they exclude first-payload textures allocated before the
  hooks. They are allocation accounting, not hardware VRAM telemetry.
- **Nonblank colored density:** read real framebuffer pixels, then draw the
  same chart with density drawing suppressed. Every frame must differ in over
  100 pixels and contain both red and blue density ink. Opaque chart background
  or an unchanged sample overlay cannot satisfy this comparison.
- **Cached/fetch-all pixels:** a second actual chart replays the seed and all
  32 windows with the product's empty-inventory diagnostic control. SHA-256 of
  every full RGBA framebuffer must match the cached run. Native active keys,
  tile hashes, geometry, level, generation, opacity and normalization also
  match independently. Cached transfers must be strictly fewer.
- **Seams:** independently stitch the actual native guttered RGBA planes into
  one test-only texture, checking every overlapping gutter byte and full cell
  coverage. Draw that monolithic texture through the same product density
  shader, removing tile clip boundaries without re-binning or recoloring.
  Compare framebuffer strips within two pixels of every visible internal
  boundary. Require nonempty strips, over 20 density pixels and maximum channel
  error at most two bytes. This tests tile assembly/clipping against continuous
  sampling; the separate chunked histogram/linear-light oracle tests native
  count conservation and color means.
- **Adjacent fades:** manually step presentation draws and freeze the existing
  clock at start, +70 ms and +210 ms. This keeps asynchronous network waits
  from painting a cached fallback ahead of reply adoption. The product chooses
  the outgoing frame and performs its normal fade; the harness never assigns
  density aliases or invents cache keys. All eight zooms must draw both actual
  adjacent tile levels at intermediate opacity, retain outgoing textures from
  the pre-reply inventory through the midpoint, produce changing/nonblank
  pixels, and retire the fade at completion. This is deterministic continuity
  evidence, not natural animation cadence, interaction latency or frame-rate
  evidence.
- **Lifetime:** destruction deletes every instrumented texture, clears tile
  ownership and ignores a real saved late reply without allocating. Chromium
  exits and its profile disappears. The HTTP thread stops; native store stats
  become unavailable; spill files disappear; mappings close; the old tile
  budget returns; the owned temporary tree is removed. Failed assertions raise
  and cannot emit an `ok` report.

## Retained 2026-10-24 control

Raw evidence lives in `spec/performance/density-spill-browser-2026-10-24/`:
`report.json.gz`, `pan.png`, `zoom.png`, `adjacent-fade.png`, and `SHA256SUMS`.
The compressed JSON preserves raw environment, source hashes, initial payload
hashes, native ABI/binary hash, full product source and harness manifests,
generated client/browser binary hashes, every window and native tile inventory,
binary client controls, framebuffer hashes, seam observations, fade observations,
allocation counts and cleanup. PNGs are framebuffer captures; the fade image
is taken at the actual midpoint. `validation.txt` records executed checks.

The 1M run on product base `71e48b67827709ed251ae05b90d010a8cef824eb` passed:
24 pans at level 1, eight alternating 0/1 zooms, eight adjacent crossfades,
33 cached/fetch-all framebuffer matches, minimum 3,172 density pixels,
minimum 30 density pixels in seam strips, maximum seam error **zero**, and
exact 1M count conservation with zero observed mean-color error. Cached journey
replies transferred **9 tiles**, versus **188** for fetch-all, excluding the
shared four-tile bootstrap. All 46 cached-run instrumented textures and all
225 fetch-all-run textures (including 33 monolithic oracles per run) were deleted.
Native spill size was 73,142,272 bytes. Cleanup passed.

Chromium 156 / ANGLE SwiftShader provided real WebGL2 texture allocation and
readback, using a software Vulkan device. This is not physical-GPU performance
or VRAM evidence. The report records the actual browser version and renderer.
Its generated client hash is
`8cb331481653b845d7e081d340c459a914115dddf8864095d502af5f9d664149`;
native ABI is 395 and the loaded binary hash is
`cc59e76471dea30c864aed3e183355dd5ba675f6ab47892dbae21add8da8cb6d`.
The report's base commit plus browser harness hash identify the uncommitted
harness used for execution; the product source manifest matches that base.

## Supervised integration contract

The opt-in guard runs in both public supervisor and internal worker entry points
before allocating source columns. It requires the colored-spill workload, an
executable Chrome/Chromium that successfully reports its version, and distinct,
writable host/companion output paths. The existing authority guard still admits
exactly 100M only with actual Actions scheduled/manual main context, run ID,
attempt, SHA and capability. In companion authority mode, the checkout must also
be clean at that SHA before allocation. Controls stay at most 1M. There is no
second source generation, figure creation or pyramid build for the companion.

After the host kernel samples, byte replay, count/mean oracle and host latency
checks finish, `run_existing` borrows the still-live host figure, its actual
native tile store, actual mapped x/y/color, original split payload and exact
production domain and 32 windows. It repacks only the bounded initial split
buffers for standalone paint. It never changes host timers or retimes a request.
The existing 24-pan p95 **<16 ms** and every-zoom **<50 ms** hard authority gates
remain enforced independently by the unchanged host verifier; controls are
advisory. Browser network, readback, seam or fade time never becomes a host
kernel sample. The helper itself refuses local scale above 1M and additionally
requires the authority worker to be its supervised process-group leader.

Production authority keeps normal eligibility and adaptive base 4096. Controls
explicitly lower lazy-pyramid eligibility and prewarm base 2048 as before.
Neither resource budgets nor windows nor assertions are relaxed for the larger
base. Resource-coarsening, a non-adjacent level jump, incomplete refinement or
lost fade source is a failure, including at base 4096. An actual authority run
must observe the outcome; a passing 2048 control cannot predict or replace it.

Chromium inherits the same worker process group. Its profiles and singleton
socket files remain inside the watchdog-owned tree. A short temporary alias
under the home directory points into that tree to avoid Unix socket path limits;
the supervisor removes the alias even after timeout, cancellation or worker
failure. The original process-group wall/RSS/disk watchdog remains in force:
**12 GiB / 4 GiB / 3600 s** hard maxima; configured lower limits stay binding.
All native, mapping, spill, browser-profile, HTTP-thread and process cleanup must
succeed. Browser launch/proof/validation failure fails the whole invocation.

The host JSON is finalized only after supervisor cleanup and host validation.
The separate companion then records SHA-256 of those **exact host-file bytes**,
source/row count, run context, product/harness/native/client identities, original
payload hashes, actual windows, supervisor resource/process observations and
cleanup. It never writes a browser-success flag or a companion hash into the
host report: the one-way immutable-host digest avoids circular hashing. Host
process-tree resource observations cover the complete optional invocation,
while kernel timing and `browser.status: not-run` retain their scoped meaning.
The companion stores PNG captures and their byte hashes as well as framebuffer
hashes. A failed/partial companion cannot pass as accepted evidence.

`scripts/verify_density_spill_browser_report.py --host-report PATH` requires the
actual matching host bytes and first invokes the independent host verifier.
It then pins identical point count, all three source hashes, environment,
provenance, native/client hashes, spill file, count/mean oracle, fixed limits,
actual supervisor-observed browser PID/group and cleanup. Authority additionally
requires externally supplied SHA and matching trusted ambient Actions context;
report fields cannot authorize themselves. Source/harness/native/client files
and the browser helper/verifier hashes can be checked with `--artifact-root`.
The browser executable hash is recorded; offline hash syntax and self-consistent
reports are not cryptographic runner attestation or proof of unavailable files.

For the shared bootstrap and every one of the 32 exact host windows, validation
requires native cached/fresh active-byte/geometry/exposure identity, genuine
hashed XYDC observations of prior ownership, actual WebGL allocation and
complete deletion, nonblank red/blue density ink, continuous-gutter seam checks,
and **33 cached/fresh framebuffer hash matches**. All **eight** zooms require
adjacent outgoing textures from the preceding active frame, retained keys,
source survival, actual intermediate draws at both levels, changed/nonblank
midpoint pixels and eventual retirement. Browser captures, controls, native tile
and pixel hashes remain inspectable. Deterministic cadence is the only
presentation claim; software WebGL allocation is not physical VRAM telemetry.

## Reproduction and integration control

```bash
PATH="$HOME/.cargo/bin:$PATH" cargo build --release --offline
npm ci && node js/build.mjs
uv sync --group dev
mkdir -p target/t target/integration-control
TMPDIR="$PWD/target/t" PATH="$HOME/.cargo/bin:$PATH" \
  uv run python benchmarks/bench_density_e2e.py --workload colored-spill \
  --points 1000000 --chunk-points 262144 --timeout 600 \
  --max-rss-gib 8 --max-disk-gib 2 \
  --chrome /home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome \
  --temp-root target/t --output target/integration-control/host.json \
  --colored-browser-report target/integration-control/browser.json
uv run python scripts/verify_density_spill_report.py \
  target/integration-control/host.json --artifact-root "$PWD"
uv run python scripts/verify_density_spill_browser_report.py \
  target/integration-control/browser.json \
  --host-report target/integration-control/host.json --artifact-root "$PWD"
TMPDIR="$PWD/target/t" PATH="$HOME/.cargo/bin:$PATH" \
  XYG_TEST_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome \
  uv run pytest tests/test_density_spill_browser.py \
  tests/test_density_spill_browser_report.py tests/test_density_spill_report.py \
  tests/test_density_spill_harness.py tests/test_density_e2e_report.py -q \
  --basetemp=target/pytest-integrated-final
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Use an installed explicit Chrome path on other machines. No browser download is
required. Use worktree-backed `TMPDIR` here because the shared `/tmp` quota is
limited. The standalone `scripts/density_spill_browser_smoke.py` command still
accepts only <=1M; it cannot invoke authority or promote its old raw artifact.
The new focused suite adds independent companion mutations, malformed/invalid
preallocation guard rejection, actual supervised bounded execution, timeout,
cancellation during Chromium execution, launch failure and fatal verifier
failure. Optimized Python remains refused. No local test allocates 100M or
forges Actions context to execute an authority workload.

The existing daily control and weekly/manual main authority commands include
`--colored-browser-report` and `--chrome`, then run both verifiers on their
distinct artifacts. Authority adds `--authority
--points 100000000 --timeout 3600 --max-rss-gib 12 --max-disk-gib 4`; each verifier
receives `--sha "$GITHUB_SHA" --artifact-root "$GITHUB_WORKSPACE"` in that same
trusted job. The existing unconditional colored-spill PR control also requests
the companion at 16,384 rows, within its unchanged 180-second/4-GiB/1-GiB
ceilings. Exact workflow-command guards and mutation tests reject omitted
companion output/verification, a different host report, or an unbound SHA.
Both hosted companion filenames fit the existing exact-SHA upload glob.
There is no separate workflow, job, status or second 100M generation.
Actual 100M browser execution remains pending reviewed landing on main.

### Retained integration control (2026-10-24)

[`integration-control/`](../performance/density-spill-browser-2026-10-24/integration-control/)
retains the supervised **1M** host/companion pair, exact commands, raw hashes and
three captures. It passed 33 cached/fresh framebuffer matches and all eight
adjacent fades; minimum density ink was 3,172 pixels, minimum seam ink 30,
maximum seam error zero. Cached/fresh transfers were 9/188 and all 46/225
instrumented textures were deleted. The supervisor observed Chromium inside
its worker group, 2,001,313,792-byte peak RSS, 111,269,917-byte peak temporary
disk and 21.048 seconds total invocation time under the configured 8 GiB/2 GiB/
600-second limits. All cleanup passed. Host kernel timings are advisory.

The immutable uncompressed host report SHA-256 is
`3673f7423277138e86c9a4a324f8eabbbf8735f0a313f67220ca9e8340a1c77b`;
the uncompressed companion is
`c9973ae1a61db81859119a97bedacd2fb59bf7648d5268e66c1698cedc708b00`.
Both independent verifiers passed with `--artifact-root`; the focused suite
passed **241 tests** in 55.46 seconds. The report records base commit `bc3ad8fa`
and dirty integration edits, with exact harness manifests. This evidence uses
the existing host worker's actual 1M columns/store; it does not attach the old
standalone control or the historical 100M host report as colored-browser proof.
Actual 100M production-base-4096 browser execution remains outstanding.
