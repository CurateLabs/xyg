# Tracked work: M2 post-#852 host-parity findings

**Tracker:** [#855](https://github.com/CurateLabs/xyg/issues/855).

**Children:**

| Issue | Priority | Role |
| --- | --- | --- |
| [#856](https://github.com/CurateLabs/xyg/issues/856) | P0 | Admit autoranged literal geometry into the Rust public exporter |
| [#857](https://github.com/CurateLabs/xyg/issues/857) | P0 | Python/Node static SVG/PNG parity (blocked by #856) |
| [#858](https://github.com/CurateLabs/xyg/issues/858) | P1 | Replace lexical host-inventory counters with native-call measurement |
| [#859](https://github.com/CurateLabs/xyg/issues/859) | P1 | Expand `check-host-parity` proof (blocked by #857 for SVG/PNG) |
| [#860](https://github.com/CurateLabs/xyg/issues/860) | P2 | Spec/ledger leftovers (palette copies, `30_ticks.ts`) |
| [#868](https://github.com/CurateLabs/xyg/issues/868) | P1 | Move the default palette bytes to one Rust/ABI authority |
| [#869](https://github.com/CurateLabs/xyg/issues/869) | P1 | Complete secondary/polar/unattached ChartView tick cutover |
| [#873](https://github.com/CurateLabs/xyg/issues/873) | P0 | Retire the Python compatibility static-export engine into Rust |
| [#874](https://github.com/CurateLabs/xyg/issues/874) | P1 | Replace source counts with executable delegation evidence |
| [#875](https://github.com/CurateLabs/xyg/issues/875) | P1 | Exhaustive admitted-shape static-export cross-host proof (blocked by #873) |

#860 bounds rather than erases two residuals: default-palette copies have
follow-up [#868](https://github.com/CurateLabs/xyg/issues/868), and
`js/src/30_ticks.ts` remains `browser-scene-migration` under open follow-up
[#869](https://github.com/CurateLabs/xyg/issues/869); historical parent #59
closed a narrower subset. Neither is described as a closed browser-policy
cutover.

Canonical write-up: [`m2-close.md`](../../process/m2-close.md) (post-landing
follow-on section). Prior emit/pack contract stays [#731](https://github.com/CurateLabs/xyg/issues/731)
(closed; do not reopen).

This file remains a stable in-repo pointer so specs can cite a path even if
GitHub issue numbers move; prefer linking `#855` / child `#N` in commits and PRs.

Release-train failures found after this review were owned by Stage 0 tracker
[#862](https://github.com/CurateLabs/xyg/issues/862), children #863–#867 plus
later findings [#876](https://github.com/CurateLabs/xyg/issues/876) and
[#877](https://github.com/CurateLabs/xyg/issues/877), with the executable close
matrix in [`m2-stage0-recovery.md`](../../process/m2-stage0-recovery.md). That
gate is closed on `main`; closing #855 still requires the remaining #868/#869/
#873/#874/#875 dependency chain rather than bypassing it.
