# M2 close contract

**Status:** closed (#731, 2026-08-31). Host materialization retirement (ABI 316–325) tracked in
[`m2-big-pushes.md`](m2-big-pushes.md) — **closed on branch #853**, pending merge to `main`.
Children: [#732](https://github.com/CurateLabs/xyg/issues/732),
[#733](https://github.com/CurateLabs/xyg/issues/733).
GitHub milestone 2 description matches this file.

In-repo pointer: [`issues/m2-close.md`](../design/issues/m2-close.md).
Reproduce remaining Python core surfaces with
`python3 scripts/audit_python_host_core.py`.

## Contract

M2 **#731 close bar** required Python **emit** and **Scene pack** loops to
move into Rust with **both hosts calling the same kernel**. That bar is
**closed** (2026-08-31 orchestration; 2026-09-01 materialization retirement on
branch #853). Python `_payload.py` and `_scene_v3.py` are **marshal-only**:
coerce host objects, call generated ABI 292–325, ship returned buffers. Recorded
Node stay-host TAP extras are inventory, not an alternate close path.

**Remaining M2 work (secondary §302 under [#58](https://github.com/CurateLabs/xyg/issues/58)) is closed** (2026-09-01): `_svg`/`_raster` compat paths, marks/_figure composition, channels label factorization, and `lod.py` cache wiring are keep-host re-export hubs. Reproduce inventory with `python3 scripts/audit_python_host_core.py`.

JSON `python-scene-migration` `follow_up_issue` stays **58** (policy template).
GitHub close work is **#731**. Extra notes belong in markdown disposition, not
in `ownership-audit.json` rationale fields.

## Children

Closed with differentials (2026-08-31 / 2026-09-01):

| Issue | Surface | Outcome |
| --- | --- | --- |
| [#732](https://github.com/CurateLabs/xyg/issues/732) | `python/xyg/_payload.py` live paint emit; Node `figure.js` twin | **Closed** — gather/ship registry + wire encode are Rust-owned (ABI 310–315); emit materialize is ABI 321 marshal-only |
| [#733](https://github.com/CurateLabs/xyg/issues/733) | `python/xyg/_scene_v3.py` figure-to-record pack; Node `scene.js` twin | **Closed** — pack dispatch is Rust-owned (ABI 305–309); trace/chrome materialize is ABI 317–325 marshal-only |

## Close when

- `_payload` emit orchestration and `_scene_v3` pack loops are Rust-owned.
- Python and Node only coerce host objects and call the generated ABI; they
  do not keep a second copy of which columns, flags, or density/errorbar/bar/
  transition keys ship.
- Cross-host payload and Scene-byte proof is green.
- Stay-host TAP diffs are either gone (kernel output) or explicit kernel
  fail-closes, not silent host omissions.

## Out of scope for this close bar

- Leftover cluster titles [#287](https://github.com/CurateLabs/xyg/issues/287)–[#313](https://github.com/CurateLabs/xyg/issues/313)
  and parents [#271](https://github.com/CurateLabs/xyg/issues/271)–[#283](https://github.com/CurateLabs/xyg/issues/283)
  stay closed. Historical inventory:
  [`m2-leftover-clusters.md`](m2-leftover-clusters.md).
- ChartView arrow math until WASM, `lod.py` cache wiring, and
  composition/`_fontmetrics.py` do **not** substitute for #731.
- Do not delete `_payload.py` or `_scene_v3.py` until Rust owns the path
  **and** differentials are green.
- Do not route pyplot through Scene.
- Do not treat Node omit-field extras as M2 complete.
- Do not silently make Node match Python.

## Landing

Orchestration era (ABI 218–315): one kernel twin per PR — **complete**.

Host materialization retirement: follow [`m2-big-pushes.md`](m2-big-pushes.md).
Each big push is one PR (Rust + both hosts + fixtures + spec). Do not resume
field-by-field stay-host slices for `_payload` grid compose or `_scene_v3` pack
walks.

**Branch landing readiness (2026-09-02, `cursor/m2-big-push-scene-trace-pack-7ce1`).**
PR [#852](https://github.com/CurateLabs/xyg/pull/852) is mergeable with green CI
on tip `be7960202` (Python 3.11 floor, Rust + Python + JS, WASM foundation).
PR #853 merged into stack base; #852 is green and mergeable to `main`.
Disposition parity: 0 `python-scene-migration`, 0 `node-scene-migration`; honest
keep-host inventories for Python (~80 files) and Node (~30 files) in
`audit_python_host_core.py`. Browser: `49_wasm_ticks.ts` adapter + `30_ticks.ts`
documented compatibility fallback (#59). Reproduce with `make check-host-parity` (or
`python3 scripts/audit_host_parity_landing.py`); CI runs the same orchestrator in
the `test` job after `uv sync`.
`python3 scripts/audit_python_host_core.py`, `uv run pytest tests/test_*cross_host*.py`,
and `uv run pytest tests/test_wasm_ticks_chartview_contract.py`.

- Bump `ABI_VERSION` and run `python3 scripts/gen_abi_manifest.py --write` on
  signature change; never edit generated ABI declarations by hand.
- Required checks per push: `abi_smoke`, push-scoped pytest, Node npm test.
- Related: #24, #58, #59.
