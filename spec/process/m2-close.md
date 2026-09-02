# M2 close contract

**Status:** #731 close bar closed (2026-08-31). Host materialization retirement
(ABI 316–325) landed on `main` via PR [#852](https://github.com/CurateLabs/xyg/pull/852)
(`8752bd95a`, 2026-09-02). Children: [#732](https://github.com/CurateLabs/xyg/issues/732),
[#733](https://github.com/CurateLabs/xyg/issues/733).

Post-landing host-parity follow-on (adversarial review): tracker
[#855](https://github.com/CurateLabs/xyg/issues/855). In-repo pointer:
[`issues/m2-host-parity-findings.md`](../design/issues/m2-host-parity-findings.md).

In-repo pointer for the emit/pack contract: [`issues/m2-close.md`](../design/issues/m2-close.md).
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

**Landed on `main` (2026-09-02).** PR [#852](https://github.com/CurateLabs/xyg/pull/852)
merged at `8752bd95a` (includes host-parity landing gate in CI). Post-merge
verification: `make check-host-parity` green on `main`.
Disposition parity: 0 `python-scene-migration`, 0 `node-scene-migration`; honest
keep-host inventories for Python (~80 files) and Node (~30 files) in
`audit_python_host_core.py`. Browser: `49_wasm_ticks.ts` adapter + `30_ticks.ts`
documented compatibility fallback (#59). Reproduce with `make check-host-parity` (or
`python3 scripts/audit_host_parity_landing.py`); CI runs the same orchestrator in
the `test` job after `uv sync`.

**Post-landing follow-on ([#855](https://github.com/CurateLabs/xyg/issues/855)).**
Adversarial review after #852 showed the live payload/Scene compile seam is
marshal-only, but the default public static-export path for most ordinary
charts still runs Python `_export_*`, Node has no twin, inventory metrics are
lexical, and the landing gate does not cover SVG/PNG or Scene-byte ABI tests.
Children: [#856](https://github.com/CurateLabs/xyg/issues/856) (P0 autorange
admit), [#857](https://github.com/CurateLabs/xyg/issues/857) (P0 static
parity; blocked by #856), [#858](https://github.com/CurateLabs/xyg/issues/858)
(P1 inventory gates), [#859](https://github.com/CurateLabs/xyg/issues/859)
(P1 landing-gate proof; blocked by #857 for SVG/PNG),
[#860](https://github.com/CurateLabs/xyg/issues/860) (P2 spec/ledger leftovers).

- Bump `ABI_VERSION` and run `python3 scripts/gen_abi_manifest.py --write` on
  signature change; never edit generated ABI declarations by hand.
- Required checks per push: `abi_smoke`, push-scoped pytest, Node npm test.
- Related: #24, #58, #59.
