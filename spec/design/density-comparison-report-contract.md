# Independent equal-window report contract

`scripts/verify_density_comparison_report.py` verifies evidence from
`benchmarks/bench_density_comparison.py`. It extends the
[live aggregation experiment](live-aggregation-comparison.md),
[benchmark methodology](../benchmarks/methodology.md), and dossier §§5, 12,
17, 28–29. It adds no product behavior, allocation authority, workflow, job,
capacity, dispatch, competitive acceptance gate, or performance winner.
The producer and its allocation guard remain unchanged.

## Invocation and result

```bash
python3 scripts/verify_density_comparison_report.py REPORT.json \
  --sha "$GITHUB_SHA" --artifact-root "$GITHUB_WORKSPACE" \
  --sizes 1000000,100000000,1000000000 \
  --arms xy-density,plotly-aggregate,datashader-aggregate
```

JSON and losslessly retained `.json.gz` are supported. The verifier is stdlib
only; it imports no producer, numerical library, native core, or browser code.
It reads at most 64 MiB of decoded report bytes, rejects duplicate JSON keys
and nonfinite JSON constants, and hashes existing artifacts in 1 MiB blocks.
It never generates, loads, maps, or rescans N source rows. Tests use retained
small browser measurements and mutated metadata; no hosted or browser run is
needed to exercise this contract.

`--sizes` and `--arms` independently specify the expected sets. Omitting either
checks internal coverage only and cannot detect an omitted target hidden by a
matching omission in the report declaration. Lists must be nonempty, unique,
and match exactly; ordering need not match. Every declared size × arm must
retain every repetition, numbered from zero, with exactly two or three
repetitions. No duplicate, unexpected, missing, or best-of-N cell is accepted.
`--sha` binds the recorded git commit to an external full SHA; it is mandatory
for hosted authority. Local dirty measurements remain exploratory.

Exit zero means structurally valid evidence. The summary always prints both
successful and failed cell counts and explicitly disclaims gesture latency,
kernel wins, and competitive acceptance. A complete report with six honest
failures can exit zero with **zero successful cells and six failed cells**.
A failed attempt is never promoted into a successful repetition. Malformed,
incomplete, mismatched, or unbound evidence exits one with a diagnostic.

## Independent policy bounds

These limits are constants/structural checks in the verifier, rather than
trust in limits supplied by a report:

| Scope | Actual rows | RSS cap per source/host/browser tree | Source disk cap |
| --- | ---: | ---: | ---: |
| Bounded local control | 5–1,000,000 | ≤2 GiB | ≤0.25 GiB |
| Existing manual main macOS M4 lane | ≤1,000,000,000 | ≤20 GiB | ≤20 GiB |

All limits must be finite and positive. Preparation/browser phases declare
at most 300 s; successful source creation and host preparation must fit that
phase deadline, with the host build subclock contained in preparation. Each
programmatic checkpoint declares at most 15 s; RSS polling
is 50 ms. Source-generation chunks are 1–1,000,000 rows. Actual source bytes
must fit the declared source disk cap. The verifier's **20 GiB hosted source
disk bound** is deliberately stricter than the producer guard's existing
200 GiB upper bound. This does not weaken or change that producer guard.
Root's optional existing-lane invocation uses `f64-memmap`, chunk 1,000,000,
20 GiB source disk, the existing RSS input capped at 20 GiB, 300 s phases,
15 s steps, and two repetitions. No new resource purchase is authorized.

Any report above one million rows, or claiming the hosted authority for a
smaller control, requires the verifier to run on actual `Darwin` / `arm64`
and to observe all of these ambient values:

- `GITHUB_ACTIONS=true`
- `GITHUB_EVENT_NAME=workflow_dispatch`
- `GITHUB_REF=refs/heads/main`
- `GITHUB_WORKFLOW=Interactive ceiling benchmark`
- `RUNNER_OS=macOS`
- `GITHUB_SHA` equal to externally supplied `--sha` and the clean report commit.

The report must also record matching platform/authority facts, at least
44 GiB system memory, and `f64-memmap`. Report self-claims do not grant
hosted authority. Test fixtures may inject metadata/context into the pure
validator; they never invoke the producer or allocate over one million rows.
A downloaded large report cannot be promoted on a local machine by its own
fields. This is authority-context validation, not a cryptographic attestation
of a runner or permission to dispatch one.

## Identity and successful-cell checks

The source must identify the exact versioned f32 or independent-stream f64
seeded generator, little-endian dtype, x/y names and file names, actual row
count, exact per-column bytes, column and x-then-y SHA256, finite extents,
bounded chunk size, authority and independent expected counts. Repeated
windows must retain identical counts. Host source metadata must equal the
shared manifest byte-for-byte in JSON value terms. Actual source files are
removed by the producer after measurement; the verifier checks retained
identity bindings and does not claim to reconstruct missing source bytes.

The verifier independently reconstructs the 24 overlapping/reversing
half-span pans and eight adjacent quarter/half-span zooms. Every successful
cell must retain all 32 ordered windows, the correct stable cold checkpoint,
and the separate outside-source zero-count/zero-lit-pixel control. Each
warm result must carry actual matching axes and a 512×512 plot area, adopted
output, explicit mode and fallback, actual raster domain/shape or covering
exact subset, expected count, RGBA stability hash and correct nonblank/empty
pixel observation. Successful RSS samples and peaks must fit declared caps.

Programmatic request start/return, axis adoption, output adoption, first
stable paint and stability confirmation must be finite and ordered in their
one browser clock, within the declared step deadline; successive requests
cannot precede prior stability confirmation. Cold preparation, source creation,
host build and navigation remain separate records. These are observed
adapter/probe/oracle clocks, never real-wheel input-to-pixel latency or pure
aggregation-kernel timings.

XYG density retains its actual visible count, reduction disclosure, requested
reply and rendered revisions. A retained raster with a different rendered
revision requires explicit equivalent-cache adoption and grid-value equality.
Exact fallback requires the actual clipped GPU count and covering subset,
with payload count recorded. Its rendered revision identifies the drill subset
and need not equal the density request sequence. Plotly retains its adopted
PNG hash/domain/revision and independent count/grid-mass oracle, matched to
host-served output. Bokeh retains its observed data/request revisions and the
actual backend grid hash, dimensions, domain and count conservation oracle.
Backend/empty checkpoints and retained column copy/mapping observations are
required. Mode, resolution, shading, oracle work and exact fallback may differ
between arms; those differences remain explicit and do not yield a raster-only
or mixed-mode ranking. XYG quantized raster evidence does not acquire an
invented independent per-cell conservation proof.

Transport totals must be nonnegative and internally sum correctly at each
checkpoint; cumulative counters cannot decrease and per-step deltas must
match checkpoints. They measure WebSocket application-message bodies only,
excluding HTTP/bootstrap, framing and network-stack overhead. Host/browser RSS
includes process-tree runtime and shared mappings, rather than allocation
deltas or physical GPU memory. Copy observations describe retained arrays;
false pointer sharing or mapping observations are allowed when explicitly
recorded, rather than relabeled as zero-copy.

## Failure evidence and artifact binding

Host preparation that is still alive without `META` at its deadline records
`timeout` in phase `host_prepare` with a reason; silent early exits retain
their return code and source mismatches retain an explicit diagnostic. These
cells must pass structural verification as failures after cleanup, even with
empty stderr. They do not acquire successful timing or output evidence.

New programmatic reports distinguish renderer launch requests from observations.
`browser_renderer_requested` and its legacy `browser_renderer` alias must match
the CLI's `--hardware` choice, irrespective of inherited environment flags.
The currently unmeasured actual renderer is null in `browser_renderer_observed`,
with `browser_renderer_scope: "launch-request; actual renderer not measured"`.
The verifier requires all four fields for nonhistorical reports and rejects
contradictory aliases or invented observed renderers. Only the exact pinned
historical raw archives may omit these newer fields under their original bindings.

Every failure requires a nonempty known producer status (including typed
browser supervisor failures), retained sampled guard observations, and a reason
or diagnostic. Timeout/memory-limit statuses themselves identify the guard
reason even when the producer emitted no stderr. Guard overshoot is permitted
in failed cells and never accepted in successful cells. Available failure
transport and RSS observations must remain nonnegative. Source failures may
lack source manifests but require the source RSS observation and complete
arm/repetition coverage; a later host/browser failure cannot replace missing
source identity. A failing oracle's observations are retained as diagnostics,
not subjected to a requirement that the failed oracle pass.

Provenance requires harness/lock SHA256, product tree identities, the built
client hash, the path/hash of the native binary actually loaded, and measured
Python/platform/browser/component/git environment. When a Linux build hash is
also present it must match the loaded binary. `--artifact-root` compares existing
harness/lock/client files, product trees (same path-plus-file-digest algorithm
independently implemented), and available native binary paths with the report.
Unavailable artifacts cannot be reconstructed; their recorded hashes remain
identity evidence rather than a claim that the verifier checked absent bytes.
A file/tree that exists and differs is an error.

The three retained equal-window archives have independently pinned decoded
SHA256 identities. Only exact original raw bytes select their historical
producer binding. With `--artifact-root`, their retained `f32-producer/` or
`current-producer/` text files must match the reported harness hashes. Current
product/client/native artifacts cannot establish historical correspondence and
are explicitly excluded from that historical check. The old f32 collector's
missing newer rendered-cache fields are admitted only for exact immutable
historical reports; its two failures remain failed. Recompression preserves
this binding because the digest covers decoded original bytes. Neither an
archive filename nor `historical_archive_commit` grants this exception.
The original real-wheel archive and all old raw reports remain immutable.

Verification:

```bash
TMPDIR="$PWD/.venv/verifier-tmp" uv run pytest tests/test_density_comparison_report.py -q
python3 scripts/verify_density_comparison_report.py \
  benchmarks/results/live-aggregation-2026-10-24/equal-window-v2/f32.json.gz \
  --artifact-root "$PWD"
```
