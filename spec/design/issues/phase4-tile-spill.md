# Tracked work: Phase 4 Tier-3 disk tile spill

**Tracked by [#5](https://github.com/CurateLabs/xyg/issues/5).**

Canonical acceptance checklist and roadmap:
[`tier3-phase4-roadmap.md`](../tier3-phase4-roadmap.md).

This file remains a stable in-repo pointer so specs can cite a path even if
issue numbers move; prefer linking `#5` in commits and PRs.

WP3 (#10) uses the [Rust-owned binary tile painter](../density-tile-painter.md);
its GPU texture bound and explicit coarsening are separate from CPU D3 pinning.
