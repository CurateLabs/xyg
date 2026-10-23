# Retained candidate density no-refinement evidence

This report proves six bounded browser scenarios against the retained
`0.6.0-rc.1` browser package from commit
`12ee3abf83fa627455032ec163608dba9d373058`. It is preparation evidence for
[#886](https://github.com/CurateLabs/xyg/issues/886), not final acceptance of
[#54](https://github.com/CurateLabs/xyg/issues/54) or publication approval under
[#108](https://github.com/CurateLabs/xyg/issues/108).

The browser tarball SHA-256 is
`9d5ca327da4a1c0a517c012bf90f555c10f56a62a33e6a1a3b585fe20bbd79b9`.
`no-refinement.json` records the runtime, source identity, exact asset and
harness hashes, CSP, observed events, presented-pixel hashes, resource teardown,
and six screenshot hashes. The report's `harnessCommit` identifies the checkout
base; its per-file hashes identify the modified harness that produced this
evidence. Screenshot paths are relative to the report.

Both the ESM and standalone IIFE entries exercise missing inline artifacts,
malformed inline bootstrap rejected before Worker allocation, and missing
retained source. The packaged Rust/WASM Worker generates the aggregate
overview. Each chart keeps that overview through unavailable-refinement
transitions, paints changed pixels when zoomed, restores identical home
pixels, and releases its listeners and GPU resources on disposal.

Reproduce from a checkout containing the recorded harness:

```bash
candidate_dir=$(mktemp -d)
gh release download xyg-v0.6.0-rc.1 --repo CurateLabs/xyg --pattern curatelabs-xyg-0.6.0-rc.1.tgz --dir "$candidate_dir"
sha256sum "$candidate_dir/curatelabs-xyg-0.6.0-rc.1.tgz"
tar -xzf "$candidate_dir/curatelabs-xyg-0.6.0-rc.1.tgz" -C "$candidate_dir"
XYG_BROWSER_DIST="$candidate_dir/package" \
XYG_WASM_FOUNDATION_ONLY=density-no-refinement \
XYG_RELEASE_COMMIT=12ee3abf83fa627455032ec163608dba9d373058 \
XYG_WASM_FOUNDATION_REPORT="$candidate_dir/no-refinement.json" \
node scripts/wasm_foundation_smoke.mjs
```

Compare the downloaded tarball digest above before executing its contents.
The draft release requires authorized GitHub access. The harness verifies the
package's asset manifest before loading the local assets.

The complete foundation gate remains the default when
`XYG_WASM_FOUNDATION_ONLY` is absent. Running that full gate with current source
fixtures and the old retained package fails painter parity for
`all_marks_reversed_domain`; this mixed-source result is not current-candidate
acceptance. The focused mode does not run that fixture suite and labels its
scope explicitly.

This evidence does not prove a real packaged Reflex application, validly framed
but corrupt inline WASM, unsupported tick-family behavior, complete platform and
host coverage, performance at scale, or the Phase 4 product requirements. Those
remain governed by the existing release issues and specifications.

## Rebuilt current-source foundation

`current-foundation.json` and its six screenshots retain the subsequent
successful **full** foundation run against current rebuilt source assets on
2026-10-23. Its `scope` is `full-foundation` and `artifactSource` is
`source-dist`; the default painter-parity and lifecycle suite ran alongside
the six density cases. The complete current run passes, resolving the
mixed-source parity failure above without narrowing the default gate.

```bash
node js/build.mjs
npm run build:wasm
uv run python scripts/verify_wasm_assets.py
XYG_WASM_FOUNDATION_REPORT=/tmp/current-foundation.json node scripts/wasm_foundation_smoke.mjs
```

The report's asset and harness hashes bind the tested bytes. `harnessCommit`
identifies the checkout base and `artifactCommit` is unset; this working-tree
verification is not an immutable
candidate build or an installed-package platform/host acceptance result. The
source assets include the ledger version 2 schema changes and measured WASM
size cleanup described in [the size record](../../benchmarks/graphforge-compatibility-size-local.json).
