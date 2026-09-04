# M2 close contract

**Status:** #731 close bar closed (2026-08-31). Host materialization retirement
(ABI 316–325) landed on `main` via PR [#852](https://github.com/CurateLabs/xyg/pull/852)
(`8752bd95a`, 2026-09-02). Children: [#732](https://github.com/CurateLabs/xyg/issues/732),
[#733](https://github.com/CurateLabs/xyg/issues/733).

Post-landing host-parity follow-on (adversarial review): tracker
[#855](https://github.com/CurateLabs/xyg/issues/855). In-repo pointer:
[`issues/m2-host-parity-findings.md`](../design/issues/m2-host-parity-findings.md).
The later stop-the-line release recovery is tracker
[#862](https://github.com/CurateLabs/xyg/issues/862), specified in
[`m2-stage0-recovery.md`](m2-stage0-recovery.md). Stage 0, including the
capacity-aware raster seam and cost-bounded density authority (#876/#877), is
closed on `main`; the remaining close work is tracked under #855.

In-repo pointer for the emit/pack contract: [`issues/m2-close.md`](../design/issues/m2-close.md).
Reproduce remaining Python core surfaces with
`python3 scripts/audit_python_host_core.py`.

## Contract

M2 **#731 close bar** required Python **emit** and **Scene pack** loops to
move into Rust with **both hosts calling the same kernel**. That bar is
**closed** (2026-08-31 orchestration; 2026-09-01 materialization retirement on
PR #853, stacked on PR #852's head branch; PR #852 then merged the combined
work to `main` on 2026-09-02). Python `_payload.py` and `_scene_v3.py` are
**marshal-only**: coerce host objects, call generated ABI 292–325, ship returned
buffers. Recorded Node stay-host TAP extras are inventory,
not an alternate close path.

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
documented compatibility fallback (follow-up #869; #59 covered the narrower
cutover). Reproduce with `make check-host-parity` (or
`python3 scripts/audit_host_parity_landing.py`); CI runs the same orchestrator in
the `test` job after `uv sync`.

The #858 inventory parses calls through imported Python `_native` / `kernels`
boundaries and Node `native.js` / `sceneBulkNative.js` boundaries, but #874's
adversarial review makes its limitation explicit: those are syntactic call
expressions, not executed calls or a call graph, and dead calls can inflate the
numbers. Count floors were removed. `verify_ownership.py` keeps the cheap
forbidden-pattern tripwires, while the versioned
[`host-delegation-corpus.json`](../design/host-delegation-corpus.json) now runs
the versioned default-palette byte contract, all admitted public marks, and the
payload/Scene/static/LOD/density/append journeys through generated ctypes and
Koffi trace hooks. Existing differential
assertions remain the output oracle; the deterministic exact-commit report is
written to `target/host-delegation-report.json` and uploaded by CI. New
keep-host tags still require file-specific code/spec evidence under the
ownership contributor rule; the policy's canned rationale is not evidence.

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

#860 kept the remaining copies visible. Follow-up
[#868](https://github.com/CurateLabs/xyg/issues/868) closes the palette residual
with one Rust-owned versioned contract (native ABI 360 / WASM ABI 25), while
`js/src/30_ticks.ts` remains `browser-scene-migration` under open follow-up
[#869](https://github.com/CurateLabs/xyg/issues/869); historical parent #59
closed a narrower delivered subset. The host-only close bar does not claim
that secondary/polar/unattached browser tick policy is closed. The executable
`default-palette` journey runs both dedicated host tests against
`tests/fixtures/default_palette_contract.json` and requires traces for the
version, row-count, UTF-8, and RGBA8 ABI entries on each host; removing either
host's Rust consumption therefore fails `make check-host-parity`.

The #856/#857 implementation admits Rust-resolved autorange for primary-axis
geometry and proves exact Python/Node Scene, SVG, and raster-command identity
for ordinary line, scatter, bar, and histogram figures in
`tests/test_static_export_cross_host.py`. The same proof pins browser CSS as an
explicit compatibility miss instead of widening the public route silently.
`scripts/audit_host_parity_landing.py` enumerates the Scene trace/chrome ABI
tests alongside the `test_*cross_host*.py` differentials, which now include
the static-export proof. The ChartView source-structure assertion runs under a
separate non-differential label; practical WASM evidence comes from the XYTS
cross-host fixture and browser foundation contract.

- Bump `ABI_VERSION` and run `python3 scripts/gen_abi_manifest.py --write` on
  signature change; never edit generated ABI declarations by hand.
- Required checks per push: `abi_smoke`, push-scoped pytest, Node npm test.
- Related: #24, #58, #59.
