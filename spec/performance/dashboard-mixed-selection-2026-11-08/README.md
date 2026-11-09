# Mixed-family dashboard selection restoration

Bounded follow-up to #111 at parent `6ad7cb76d1a02f3df759cffc4218baf26ab1378e`.
This is not whole-issue or milestones 4–7 acceptance.

A real 32-view dashboard reproduced a durable-selection defect: after whole-chart
GPU eviction/readmission, the brush geometry and count remained but the rebuilt
trace had no active mask. Context restoration now uses the existing local mask
restoration path before the first replacement paint. The kernel preview keeps
its scatter-only universe; standalone restoration matches its original local
selection universe. No new selection callback, link broadcast, host request or
history entry is emitted. Row-index selection remains non-durable.

## Fresh evidence

- All ten existing shared-host tests pass, including the preserved original
  scatter allocation journey and a new 32-view mixed-family journey in its normal
  browser-enabled pytest gate. Four view-state/republish/row-selection cases pass.
- The mixed dashboard contains line, scatter, histogram, grouped-bar and heatmap
  compositions. Actual GPU readback matches authored box/lasso masks `[1,1,0]`.
  Every presentation pixel and saved eviction stand-in matches before/after
  readmission and shared-context restoration. Selected line/scatter use authored
  saturated red/blue. This is not default-palette antialiasing qualification.
- Real Tab navigation and seven trusted keys activate canonical scatter row 1,
  then resume at row 2 after restoration. Trace identity, durable state, focus,
  peer isolation and event counts remain correct. All 32 views are evicted by a
  zero per-chart grant. Partial pressure and recovery use real Rust decisions.
- The independent GL-call oracle matches the production logical storage ledger
  at every checkpoint; teardown leaves zero actual buffer/texture allocations.
  This checks requested storage at checkpoints, not every transient driver peak,
  physical VRAM, RSS, Canvas2D or total process memory.
- The complete browser foundation passes, retaining default-1k/keyboard,
  temporal/line-window, filter/GPU, seven Worker freezes, aggregate membership,
  native/WASM export parity and offline recovery coverage.
- Seven Core/provenance tests pass, including real Git LF/CRLF conversion. The
  original complete sixty-view shader-cache probe remains byte-identical.
- Client build/type checking and full-worktree hooks/Ruff pass. Rust/native/WASM,
  ABI declarations, package profile, caps and policies are parent-identical;
  their compilation evidence is inherited after source/digest checks.

## Controls and failed attempts

The final mixed assertions against the digest-verified parent standalone client
fail at `rebuilt selection has an active GPU mask`. The original small public
reproduction independently records the absent mask after successful readmission.
Neither failure is counted as a pass.

Initial setup omitted module/Worker CSP origins; it failed before the probe.
Initial keyboard setup omitted authored click opt-in, then correctly enabled it
through the public composition. The first default-palette line comparison found
two one-LSB blue differences after context rebuild; this remains unqualified,
not a renderer repair or relaxed comparison. The final fixture explicitly authors
saturated line/scatter paint and still compares every RGBA byte exactly.
Two superseded diagnostic runs were stopped after an accidentally quadratic
pixel-difference formatter; the linear diagnostic and full assertions are used
in the final probe. A mixed-only diagnostic passed its browser assertions but
failed report collection because it intentionally omitted the original journey's
captures; it receives no full-command pass. Initial Core checkout validation
found an unpinned `view-state.md`; the explicit LF pin repairs that provenance gap.
All retained failures remain failures.

## Reproduction

Use Node 22.23.4, the recorded explicit native405 library, a disk-backed TMPDIR and
Chromium. Build the client once with `node js/build.mjs`, then:

```sh
TMPDIR=/var/tmp XYG_NATIVE_LIB=/absolute/native405.so PYTHONPATH="$PWD/python" \
  XYG_CHROMIUM=/absolute/chrome uv run --no-sync pytest -q tests/test_shared_glhost.py
TMPDIR=/var/tmp XYG_NATIVE_LIB=/absolute/native405.so PYTHONPATH="$PWD/python" \
  XYG_CHROMIUM=/absolute/chrome node scripts/wasm_foundation_smoke.mjs
```

`checks.json` binds the environment, logs, complete reports/captures and runtime
artifacts. Unchanged artifacts reference their immutable parent archives;
changed clients are archived here. `current-bindings.json` preserves its parent
history and binds this source delta. Independent final review, current-main
freshness, hosted CI and merge queue remain pending.

CPU/source/WASM/global budgets, default budget choice, massive mixed LOD/tile/graph
pressure, latency, WebKit/all-host/installed-host accessibility and competitors
remain open. No public100k/1M, all-palette or performance-win claim follows.
