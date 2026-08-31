# M2 big pushes — host materialization retirement

**Status:** active (2026-08-31). Replaces the field-by-field stay-host TAP cadence for
the remaining #731 residuals. Orchestration kernels ABI 218–315 are landed; this
document tracks **execution retirement** only.

Reproduce inventory: `python3 scripts/audit_python_host_core.py`.

## Why big pushes

Hundreds of one-field Node/Python parity PRs cleared stay-host inventory but left
~26k lines of **host materialization** (_payload bin2d/pyramid compose,
_scene_v3 field-byte walks). Each slice paid review/CI overhead without moving
the retirement needle. The remaining work is **cohesive subsystems**, not isolated
keys.

## Push sequence

| Push | Surface | ~Lines retired (cross-host) | New ABI | Exit criteria |
| --- | --- | ---: | --- | --- |
| **1** | `_payload` density grid materialize (bin2d / pyramid / sample / encode) | ~800 | **316** `xyg_payload_density_grid_materialize` | `_density_trace_spec` grid body is plan → materialize → ship; density cross-host grid SHA green |
| **2** | `_scene_v3` XYTC + XYTA trace pack | ~1,100 | **317–318** `xyg_scene_xytc_trace_pack`, `xyg_scene_xyta_trace_pack` | `_pack_xytc` / `_pack_xyta` marshal inputs only; `figure_scene_v3.json` SHA matrix green |
| **3A** | Scene chrome / annotation / figure-support pack | ~1,500 | **319** bulk XYAF/XYCF/XYFS packers | Scene-byte cross-host proof closed (#731 blocker) |
| **3B** | Payload geometry gather + channel materialize | ~950 | **320** column gather offset ship + channel materialize | `_emit_*` bodies and `channels.ship_registry_attach` execution retired |

Push **3A** closes Scene parity; push **3B** closes payload parity. Order 3A vs 3B
is negotiable; do not interleave with field slices.

## Landing rules (override `m2-close.md` for pushes 1–3)

- One push = one PR versus `main` touching Rust + Python + Node + fixtures + spec.
- Bump `ABI_VERSION` once per push; run `python3 scripts/gen_abi_manifest.py --write`.
- Required checks: `abi_smoke`, push-scoped pytest, `packages/xy-node` npm test.
- Do not split a push across stacked PRs unless CI forces a hard ABI break mid-push.

## Out of scope (unchanged)

Secondary §302 (`_svg`, `_raster`, `marks`, `lod` cache, `_figure` hub) stays out
of these pushes — see `m2-close.md` out-of-scope section.
