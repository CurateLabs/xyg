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

M2 closes only when remaining Python **emit** and **Scene pack** loops move
into Rust and **both hosts call the same kernel**. Recorded Node stay-host TAP
extras are inventory, not an alternate close path.

Python `_payload.py` and `_scene_v3.py` still assemble product output. Rust
already owns LOD tier, M4/visible indices, density kernels, and Scene
admit/encode slices (ABI 122, 204–205, 214–215, 218–256). Hosts still gather
columns, fill XYTC/XYTA envelopes, and ship keys. That duplicated policy is
the remaining M2 bar.

JSON `python-scene-migration` `follow_up_issue` stays **58** (policy template).
GitHub close work is **#731**. Extra notes belong in markdown disposition, not
in `ownership-audit.json` rationale fields.

## Children

Close independently. Parent #731 stays open until every child is closed with
differentials.

| Issue | Surface | Remaining loops |
| --- | --- | --- |
| [#732](https://github.com/CurateLabs/xyg/issues/732) | `python/xyg/_payload.py` live paint emit (`build_payload`, `_emit_*`, `_density_trace_spec`, `_axis_spec`, `_transition_entry`, `_ship_channels`); Node `figure.js` twin | Extra-column gather and ship. Index math is ABI 204/205; count budget is ABI 214; errorbar role expand is ABI 215. |
| [#733](https://github.com/CurateLabs/xyg/issues/733) | `python/xyg/_scene_v3.py` figure-to-record pack (`_pack_xytc` XYTC, `_pack_xyta` XYTA); Node `scene.js` twin | Pack loops. ABI 218–256 are admit/encode kernels, not the envelope assembly. |

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

- Bump `ABI_VERSION` and run `python3 scripts/gen_abi_manifest.py --write` on
  signature change; never edit generated ABI declarations by hand.
- Required checks per push: `abi_smoke`, push-scoped pytest, Node npm test.
- Related: #24, #58, #59.
