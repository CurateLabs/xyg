# Issue #884 local implementation proof

This is a fixture packaging smoke, not a release selection or paired-artifact
qualification. It preserves earlier receipts. No registry upload, tag creation,
issue mutation or related-repository write was performed.

The host assigned `/home/ubuntu/.t3/worktrees/xyg/t3-a51e1a65`, branch
`t3/issue884-release-version-contract`, exclusively to this task. Initial head,
merged accepted `origin/main`, and integration head are in `environment.json`.
The normal merge created a merge commit before the mandatory full-worktree
hooks were run (an execution error); all three gates subsequently passed on
the integration tree and are rerun before the implementation commit.

## Verification

```bash
/home/ubuntu/.cargo/bin/cargo build --release
uv run --with dunamai pytest -q tests/test_release_version.py \
  tests/test_check_release_version.py tests/test_stage_node_packages.py \
  tests/test_stage_browser_package.py tests/test_publish_node_packages.py \
  tests/test_verify_release_cohort.py tests/test_graphforge_contract_corpus.py \
  tests/test_xyg_package_identity.py
UV_DYNAMIC_VERSIONING_BYPASS=0.6.0rc42 XYG_SKIP_CARGO=1 \
  uv build --sdist --wheel --out-dir .artifacts/issue884
python3 scripts/verify_sdist.py .artifacts/issue884/xyg-0.6.0rc42.tar.gz
python3 scripts/verify_wheel.py \
  .artifacts/issue884/xyg-0.6.0rc42-py3-none-linux_x86_64.whl --expect-native
```

The final focused run passes 217 tests, zero skips. The initial run lacked a
native core and failed the package example; after building locally it passes.
The six optional dunamai tests pass when that build dependency is supplied.
Both archive verifiers pass. The fixture override bypasses Git tag discovery;
existing dunamai tests independently check canonical tag normalization. This
is not a claim of a real tagged release build. The local Linux wheel is not a
manylinux/platform-matrix certification.

Node smoke uses `parse_tag('xyg-v0.6.0-rc.42').npm`, `stage_platform` for
`linux-x64` from that wheel, and `stage_facade` with the generated
`packages/xy-client/dist/standalone.js`, under `.artifacts/issue884`.
Run `npm pack --json --ignore-scripts --pack-destination <absolute-output>` in
each staged tree. Both real archives report `0.6.0-rc.42`; native bytes come
from the same wheel, facade pins all five platform packages exactly, and the
pack inventory is retained in `npm-pack.log`. No install or publish occurs.
Browser manifest/assets staging is covered by the focused tests; this smoke
does not build or qualify an actual WASM/browser release cohort.

`artifacts.json` records local archive hashes/sizes; binaries remain generated
and untracked. Raw successful command output is adjacent. Full-tree hooks and
Ruff output are recorded after the final edits.

## Remaining acceptance

The authentic declaration still supports only Core 0.5.2 and rc.5. New
matched fixtures check these real declared identities; mismatches include
rc.7 and final 0.6.0, and release-candidate numbers deliberately differ between
products. Corpus tests verify the authentic evidence hashes. The optional
`--core-version` cohort input checks the declaration and records the requested
identity on success; it does not inspect or execute an actual Core artifact.

Core #1095/#1096 distinguish published rc.7 at `f871a2a1c` from the later packed
candidate at `aaf0448293`; the latest handoff says final 0.6.0 is unpublished.
See the linked sources in `../../../process/production-readiness.md` (the
release process specification is `spec/process/production-readiness.md`).
An actual selected pair needs new authentic Core qualification under #936 and
exact selected artifact/source evidence. #884 remains open on that gap;
#108 retains the complete candidate/matrix/freeze and product prerequisites.
No capability/API gap is dispositioned by these checks.
