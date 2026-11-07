# Actual temporal Aggregate → Direct → Aggregate and frozen-render proof

Parent: `c4f16778fd2551c439a6883daf0e9891f9b2fc11`. This is a bounded regression
proof for live issue45, not issue or milestone closure. No shipping producer
source, ABI or package artifact changed. The separate fixture is discovered by
the ordinary full foundation command in the existing Release surfaces gate.

Four authored node UUIDs are repeated bytes1–4; x=[0,1,100,101], y=0;
valid-to=[40,10,20,30]. Six edge UUIDs are bytes11–16;
source=[0,0,1,2,0,3], target=[2,2,3,0,0,3]. Budgets2/8 are fixture inputs,
not altered product defaults. Camera=[1,1,30,60,240,180,1]. Initial cursor20
allows trusted ArrowRight/Enter setup and public pinFocused on canonical UUID4.
Captures at20,5,10,20,30,5 exercise Direct, Aggregate, Aggregate, Direct,
Direct, Aggregate. The final5 follows queued10/30/5 intents. UUID4 disappears
at30 and reappears at5 with the same selected/focus/pin state. The initial
frame-time state is empty while its later retained publication carries state;
these are separately asserted, not conflated.

At5 all six edges are temporally visible but only0–3 are represented at
Aggregate, with CSR [0,1,2],[3]. Loops4/5 are intentionally omitted there and
preserved at Direct20. The exact node CSR at10 is [0],[2,3]. Every half-open
visibility byte, source UUID, endpoint, CSR offset/member and tier is checked
against independent authored expectations. Missing/duplicate/stale expectation
controls fail; re-signed malformed retained CSR also fails Rust import.

Read-only Worker observation captures requests/replies without injecting or
changing publications. Native replay compares complete XYGR bytes, including
GPU planes, for every render/interaction. Native frame acquisition compares
source, time, visibility, interaction provenance, camera and full retained
publication against browser freeze. The opaque temporal instance token and
v2 browser presentation/context are intentionally not a native v1 byte claim.
All six Worker and native Scene/XYPB/SVG/PNG/HTML exports match byte-for-byte.
After later scrub and source disposal, all three artifact carriers recover the
exact original XYFG. Offline HTML uses the shipped ChartView with network
routes refused and pageerrors checked. Independent authored centers and live,
Rust raster and offline pixel samples pass, with shifted/stale picture controls.
This is finite center/interior coverage, not whole-image antialiasing parity.

Reproduce (Node22, explicit current native ABI405, locked dependencies and
verified generated artifacts required):

```bash
TMPDIR=/var/tmp XYG_NATIVE_LIB=/absolute/current/native405.so \
PYTHONPATH=$PWD/python XYG_CHROMIUM=/absolute/chromium \
node scripts/temporal_graph_aggregate_smoke.mjs /var/tmp/aggregate-proof
```

The full command is `node scripts/wasm_foundation_smoke.mjs`, with the same
environment and optional XYG_WASM_FOUNDATION_REPORT. No sleeps, host-side
filter/LOD implementation, private acquisition, caller-authored publication,
new renderer or policy/cap/default/deadline/tolerance changes were introduced.

`attempts/` preserves all development logs and failed-run raw archives; these are not
credited as final acceptance. Attempt1 tried to pin an aggregate focus and was
correctly refused. Attempts2/3 supplied an HTML-only client argument to Scene
export and were correctly refused; attempt4 corrected the harness. Attempt5
had an observational response-envelope decoding error; attempt6 corrected it.
Attempt7 added native acquisition and supersession checks. Initial focused
pytest omitted XYG_FROZEN_CHROMIUM and caught a stale current-bindings pointer;
its failed log is retained, with successor binding and explicit Chrome rerun.
Initial Ruff found closure bindings in the new pixel verifier and was fixed.
Final checks and source/artifact/capture digests are recorded alongside this file.

Unchanged producer inputs were byte-compared with the root checkout before
copying pinned native405, WASM and client assets. Dependency directories are
borrowed by symlink; explicit native path and PYTHONPATH avoid the old root
ABI403 library. Artifact pins and source equality are in producer-inputs.json.
No broad producer rebuild was needed; artifact size and symbol qualifications
are inherited only under those equal inputs, not newly measured here.

Remaining acceptance includes full GraphForge assertion/history corpus scope,
massive aggregate playback, broader accessibility, installed-host attachment,
and release-scale/platform/competitor evidence. Existing direct pointer,
keyboard,10k,GPU,filter and seven-shape export coverage is retained. The root
owns independent review, current-main reconciliation, PR, hosted CI and queue.
