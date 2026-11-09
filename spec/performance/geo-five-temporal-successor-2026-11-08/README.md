# Five automatic temporal hierarchy views: qualified successor

Parent4e2496892fe258f09f2911249005292be43bd5ad is preserved, including every
committed predecessor receipt and failure. This successor completes its bounded
functional dependency qualification. M6/#50/#39 remain open: this is neither
massive/performance nor complete milestone closure. No Root checkout, Git config,
remote, PR or other worker artifact is modified.

## Repairs and causal controls

The only shipped-code change is the existing shared renderer's Canvas2D
presentation creation: `alpha: true, willReadFrequently: false`. No shader,
DITHER/AA state, protocol, physics, data, tier, resource cap, deadline or pixel
assertion changes. This explicitly retains the accelerated copy preference.

The pre-edit diagnostic compares every byte of all five GPU and presentation
planes, with unchanged source, camera, shaders, uniforms and exact membership.
Raw GPU planes stay identical. Canvas2D changes four bytes by one LSB. Two reads
of a frozen copied canvas reproduce the difference without another GPU draw.
Fresh Canvas2D controls with explicit false or true remain stable; an omitted
preference changes on its second read. Disabling DITHER *after* GLHost reset
changes no GPU bytes; it is not the repair. Selected complete raw GPU/Canvas
planes, centers, shader/uniform/state snapshots and per-view full comparisons
are archived. Browser adaptive Canvas2D readback policy is the inferred internal
mechanism; the observed cause boundary is the copy/readback surface, not GLSL.

The final current harness on the immutable2afad9d7 baseline client fails its exact
idle RGBA assertion. The officially rebuilt df62465d client passes direct and
reduced cursor/range matrices without retries-to-match, masks, count-only
substitutes or tolerance. The stable reduced output equals the original first
paint (SHA25617a7c055...), not a newly rounded substitute. Existing modern CSS
color/lookup regression also passes, including zero repeated-frame byte changes.
This addresses the isolated readback defect. Historical AA, Worker/Jupyter,
timer and100k watchdog failures retain their recorded status; no blanket
reliability or cross-driver claim follows.

The initial broad Node588-pass/1-fail/1-skip result is retained unchanged in the
parent evidence. Kind4 is reproduced with one captured802f467a... request and
four complete1784-byte outputs. The borrowed64,631,776-byte conformance executable
(9ec80e9d...) differs from the pinned C ABI at offsets952–954 and1008–1010.
Its exact source/build provenance is unknown; an ABI label cannot qualify it.
A fresh64,641,208-byte executable built from this checkout (5d7f35c2...) matches
the pinned native and WASM outputs byte-for-byte (2697e57d...). All six artifact
hashes and the borrowed executable are archived. Building all conformance
executables from matching local source yields589 pass/zero fail/one skip in the
same broad590-test suite. No Rust code or oracle tolerance was changed. This is
an executable-input qualification correction, not a dismissed parity failure.

## Functional proof

Five explicit issued selected hierarchy lanes (original plus four forks) share
one original canonical Source and one Scope. Source-wide canonical/snapshot and
same-lane exclusions remain. Initial caller frames and Source owners are
explicitly disposed only after independent hierarchy/adapter retention.
Scope1 + lanes5 + accepted Data5 =11 native owners, with one transient twelfth
State/Query/Data.16 total handles, eight Data, one process staging slot and
128/384 MiB ledgers remain unchanged. No canonical source copies are introduced.

Four strict-CSP packaged Node22/native browser matrices cover direct/reduced
and cursor/range. Each verifies independent native ready handshakes, one held
actual43/44 candidate while1000 newer intents arrive, latest predicate, exact
full-u64 selection, native direct picks or all32769 original membership rows
(nine pages per view), and complete RGBA SHA256 equality. Half-open endpoint
predicates empty all five views and preserve authored selection; restoration
returns the exact original pictures. Trusted keyboard input creates five
independent cameras. Actual page failure preserves last good pixels, then a new
intent recovers. Five real releases and fresh realms remount without losing
camera/pixels. A genuine old completion is replayed against a newer active
request and cannot release it. Repeated cancellation retains correlation;
two lost Abort ACK replies block successors and retain the claim until explicit
exact drain retry. Linked native controller groups and independent controllers
update only their intended views. All positive ACKs come from the actual native
and existing browser lifecycle. No synthetic drain proves acceptance.

Installed JupyterLab4.6.5/anywidget exercises five public widgets through real
binary comms: five ready handshakes, held native Prepare, burst supersession,
independent trusted keyboard cameras, five Output clears with real release ACKs,
redisplay and exact per-view full-canvas restoration, and final native-owner
cleanup. It runs on both one owning loop and two concurrent owning loops on
separate threads. Every cross-loop wait uses its owner; notification inbox and
product admission bounds are unchanged. Python3.11.17 and3.12.15 each pass120
native lifecycle tests, including failed foreign-loop constructor rollback that
must preserve the other four lane claims. Existing canonical, indexed and
hierarchy one-view packaged browser journeys also pass.

These are source-checkout tests in an installed Jupyter application and packaged
source-built browser client. They are not an installed XYG wheel, five-view
installed VS Code, performance/scale or competitor-win qualification.

## Provenance, failures and reproduction

Receipts record exact command arrays, environment inputs, exits, complete product
source hashes and content snapshots, and executable/runtime hashes before/after
execution. The final guardian includes all324 inherited compiled/config inputs;
all remain byte-identical to the qualified parent. Native1ac386f0.../ABI405 and
WASM4cd1e964.../ABI38 are inherited by exact hash, not freshly rebuilt.551 native
and68 WASM functions,1,895,719 raw/786,385 Node22 gzip6 bytes and47 spare remain.
Conformance executables are fresh matching-source builds. The client is a fresh
`node js/build.mjs` build, with both package and Python copies hash-bound.
Predecessor clients, source snapshots, runtime artifacts, raw logs, diagnostic
planes and screenshots are content-bound here; the external handoff binds the
final commit/tree/ordered parent and canonical binary Myers diffs.

New failed runs are also retained. The first notebook operator incorrectly
matched code text rather than output. The second issued later keys after a
paint replaced the focused canvas; the corrected driver refocuses each canvas
and observes each native retirement. The third observed native mount release
before the host had delivered its actual release ACK; it now waits for both
observations. These are explicit fixture fixes, not timer-based ownership
release or claims that an unrelated reliability failure disappeared. Initial
Ruff/notebook formatting diagnostics are retained. Early diagnostic receipts
predate the guardian; final source-bound controls are identified separately.

Use the exact Node/Chrome/interpreter paths in environment.json. Never sync a
borrowed Python environment. Representative commands, with TMPDIR=/var/tmp,
PYTHONPATH=python:tests and XYG_NATIVE_LIB pointing to the bound native library:

```
cargo build --offline -p xyg-wasm --bins
node js/build.mjs
python scripts/qualify_geo_five_temporal.py --name unique-name -- node --test packages/xy-node/test/geo-catalog-wasm-parity.test.mjs
XYG_GEO_AGGREGATE=1 node tests/browser/geo_five_temporal_test.mjs
XYG_GEO_RANGE=1 XYG_GEO_AGGREGATE=1 node tests/browser/geo_five_temporal_test.mjs
XYG_GEO_JUPYTER_PYTHON=/path/to/verified/python node scripts/geo_notebook_five_temporal_smoke.mjs
XYG_GEO_MULTILOOP=1 XYG_GEO_JUPYTER_PYTHON=/path/to/verified/python node scripts/geo_notebook_five_temporal_smoke.mjs
```

Receipts contain the complete exact variants and exits. The protected old-client
negative is expected to fail; the diagnostic mode is explicitly separate from
normal acceptance and never alters normal renderer state. Parent receipts are
historical, matching-runtime native/WASM results are inherited, and new local
application/browser/lifecycle results are fresh. Hosted CI, independent review,
combined integration and merge queue remain Root-owned. Massive/1B budgets,
full multi-chart performance/competitor matrix, mixed tiles, broader application
and browser/driver coverage, exports/accessibility and remaining issue criteria
still gate full M6/#50/#39 closure.
