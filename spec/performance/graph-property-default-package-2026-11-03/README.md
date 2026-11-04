# Property-default functionality budget and combined shipping qualification

The actual combined production package passes the separately approved
**1,878-KiB raw / 765-KiB gzip6** gates. Native and WASM release targets were
recompiled, the reviewed CSS client rebuilt, and the normal shipping packager
produced complete paired assets, manifests and inline bootstraps. All fresh
shipping, foundation and unmasked property checks pass. This receipt does not
retroactively convert any historical failed producer into a shipping pass.

## Independent review and explicit parent decision

The parent reports completed `m4_defaults_audit` approval of source
`2ed544dcb85698f21d0f5db297320490ce26c8ee`, whole binary/full-index diff SHA-256
`c1b80e0baf630b813137d639e9c323aa0c927ce2f8b95fe5150d2da3d945073b`, with no
blocking source defects. The reviewed shared home/label behavior is retained;
no unsolicited optimization of generic label candidates or other product
algorithms is included here.

After that source review and independent package assessment, the parent
explicitly adopted the smallest whole-KiB gates, **1,923,072 raw / 783,360 gzip6
bytes**. The reviewed module is 1,922,561 / 783,148 bytes, leaving **511 / 212
bytes**. Growth over the accepted P1 module is **41,053 raw / 15,014 gzip6
bytes**. Shared native home/label policy is newly reachable on the property
WASM path; exact component attribution is unmeasured. Generic cartesian ticks
were already WASM-reachable, so the growth is not attributed solely to them.

The prior producer failed the then-current 1,882,112 / 769,024-byte gates by
40,449 / 14,124 bytes. That failure and rejected-candidate functional proof in
`graph-property-default-presentation-2026-11-03/` remain immutable historical
FAIL evidence. The new gates grant no automatic allowance for future growth.
Compiler, profile, toolchain, optimizer, dependencies, exports, validation and
16-MiB default / 384-MiB maximum runtime arenas are unchanged. Native ABI 399,
WASM ABI 35, Scene 34 and painter 17 remain unchanged. No performance win or
broad acceptance follows from this functionality decision.

`review-and-decision.json` records the parent instructions and verifies the
provided review hashes against local git objects. `guard-preservation.json`
proves the packager changes only its two size constants and decision comments;
all validation and publication ordering is exact to the reviewed predecessor.

## Reviewed CSS merge and source ownership

A normal merge of `78b4b69f76b955ab19bd365f0492711cc3c06c1f` into the original
`2ed544dc` branch produced merge commit `86249d6b`. Full hooks, Ruff check and
Ruff format check passed before the merge commit. No reset, rebase,
cherry-pick, history rewrite or remote action was used.

The parent reports completed `s5a_final_review` approval of that CSS source.
Its whole increment from `e768ce25` hashes to
`bbc98d31fde137452231604b95dbade3445212f5bb0402b5281150078a565a0d`, and its
nonreceipt increment hashes to
`22c3959e7b5ae164f2c6b4fc154aacc89925de7bd31c1a6cbf67938c74d4e24e`.
Browser TypeScript is byte-exact to `78b4b69f`; all Rust, Python and Node product
sources are byte-exact to the approved `2ed544dc` source. Only
`js/package-wasm.mjs` and `js/src/50_chartview.ts` differ among the 699 build
inputs compared with reviewed `2ed544dc`.

`historical-preservation.json` verifies every historical receipt blob from
both inputs: 7,229 paths from `2ed544dc` and 8,229 from `78b4b69f`, including all
shared history, are exact in the combined checkout. No historical receipt is
edited or deleted. The new final integrated diff still requires independent
parent review before PR, push or integration.

## Case-count erratum and preservation

The old README and current composition spec prose said 99 cases. The actual
raw comparison already recorded **101**. This receipt corrects the count;
`erratum.json` preserves the exact discrepancy and its disposition. The old
committed README and every historical receipt stay byte-identical. The current
normative composition spec now says 101 and links this erratum.

The fresh `preservation.current.json` reruns every case against the actual
release native library. `preservation-comparison.json` proves all **101
requests** match the original baseline. Only `scene.canonical` in
`property graph + render` differs from that baseline; every other document
section is identical, including f64 positions, IDs, relationships, semantic
classes/statuses, source caption identities and legend. All current outputs
are byte-exact to the reviewed `2ed544dc` outputs. Generic semantic and layered
canonical presentation is preserved. Source caption visibility, routes,
clipping, loops, parallel edges and arrows are unchanged by this package slice.

## Fresh actual production artifacts

`native-build`, `wasm-build`, `client-build` and `shipping-package` are actual
producer invocations, all exit 0. Source mtimes were refreshed without changing
bytes to force release recompilation. The normal packager reads the ordinary
`target/wasm32-unknown-unknown/release/xyg_wasm.wasm` path, with no diagnostic
module or manually staged candidate. `paired-assets` then runs the repository
verifier successfully against both complete generated asset sets.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Native release core | 6,108,248 | `e88b3f9458effea8f677d187e9e0e72fa4c3f26e43878c118aebf13494a37bad` |
| Optimized shipping WASM | 1,922,561 | `e8011f779e70f58416a751f0067f279d1b9aa9515004c246e2f44c95af192651` |
| WASM gzip6 | 783,148 | `d447f4e3f63a0b189f962d53cba34336224df6cb84e4cd5be7fa430f7366120a` |
| Combined ESM client | 763,072 | `3b194aebda9a2d8f30e0503f01310d944efb72edcca4701777a3c211803ddf70` |
| Combined IIFE client | 763,103 | `bdce4a092184e0feb745ea4ebfc57b3929b5ca795d5ec968f9a678e233efeea8` |

Actual sizes are unchanged from the reviewed candidate; no further gate change
was needed. `shipping-artifacts.json` records all 15 actual files, including the
compiler output, paired worker/module/inline/manifest copies and classic
worker. The shipping packager validates raw signatures against all 65 manifest
functions and ABI/Scene getters before publication. The captured actual
module has no ambient imports and the same 68 total exports as the reviewed
module (65 functions plus memory/globals). Both inline bootstraps decode to the
exact shipping module and contain the exact generated classic worker. The
lossless `shipping-module.wasm.gz` is captured from the accepted shipping file;
`capture-shipping.mjs` only reads generated asset directories.

`build-inputs.json` records all 699 source hashes. Canonical source SHA-256:
`ab3ff61f3cd3769a89d5d1bbf31b28f99031a80e9d686a3ae93a8ee1fd134a53`.
`shipping-artifacts.json` verifies those source bytes still match, and
`build-environment.json` records unchanged build flags and configuration.

## Fresh qualification results

All normal commands, selected nonsecret environment, UTC times, exit codes and
raw log hashes are in `*.command.json`; raw stdout/stderr is stored losslessly
in `*.log.gz`, indexed by `compression.json`. The following are fresh results:

- `shipping-tests`: **13 pass, zero failures, zero skips**, against the actual
  default shipping WASM path, with `XYG_SESSION_WASM` explicitly unset. This
  includes real native/WASM session replay and package contract tests.
- `paired-assets`: complete Python/client copies, versions, manifests, inline
  payloads and classic worker validate successfully. No missing-manifest waiver.
- `foundation`: the **full, unfiltered** strict-CSP local-only foundation and
  Worker lifecycle smoke passes, with `XYG_WASM_FOUNDATION_ONLY` explicitly
  unset. `foundation.json` and its screenshots bind the generated assets.
- `inline-file-smoke`: the normal strict-CSP offline file-URL classic worker
  aggregate smoke passes against the actual generated inline bootstrap.
- `property-python`: both unchanged default property helper cases pass; repeat
  exports remain exact and default native f64 positions equal canonical ones.
- `property-browser`: **all six full-image pairs pass**, with no masks,
  supplied layout, preset positions, modified helper or tolerance change.
- `scoped-crosshost-python`: 21 pass; `scoped-crosshost-node`: 31 pass.
  Python/Node request, document, canonical/native SVG and PNG bytes match.
- `focused-package-contracts`: 86 pass, including asset verification failure
  contracts, inline contract and the combined static-client CSS/security tests.
- `native-abi-smoke`, `generated-native-contract` and
  `generated-wasm-contract`: pass; native declarations remain 538 symbols at
  ABI 399 and WASM declarations stay unchanged.

| Theme | Unmasked full-image pair | Mean max-channel difference | Fraction over 96 |
|---|---|---:|---:|
| Light | Canonical / WASM browser | 0.7523251488 | .0025930060 |
| Dark | Canonical / WASM browser | 0.7003459821 | .0025372024 |
| Light | Native export / native browser | 2.6464880952 | .0089657738 |
| Dark | Native export / native browser | 3.1425372024 | .0098883929 |
| Light | Canonical / initial native browser | 2.8272842262 | .0087127976 |
| Dark | Canonical / initial native browser | 2.4920982143 | .0093452381 |

The unchanged exclusive limits are mean <3.5 and fraction-over-96 <.01.
`property/browser.json` retains the exact numbers and configuration. Every
geometry check passes within .005 CSS px against the unchanged .01 limit,
including node centers, caption text/anchors, routes, arrows and legend
frame/swatch/text. Fresh 640×420 screenshots at device scale 1, requests,
documents, exports and observations are retained under `property/`.

`reuse-scope.json` explains reuse of the independently reviewed 2ed graph/home/
label/static/golden/authored-preservation results and the exact reviewed 78
nearby canonical-axis/CSS evidence. Neither the multi-hour full Python suite
nor unrelated performance experiments were repeated. No product optimization
was added to obtain the package pass.

## Reproduction and remaining limits

Use the Node 22.23.4 toolchain at
`target/task-tmp/node-v22.23.4-linux-x64/bin/node`, project `uv`, Rust 1.96.0 and
cached Chromium
`/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
Reproduce into a new receipt/output directory; do not overwrite this one.
`run.py` supports `XYG_PACKAGE_RECEIPT=<new-receipt>` and refuses overwrites.
The command records give the exact final argv and environment. Core producers
and normal qualification invocations are:

```bash
cargo build --release -p xyg-core
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
python3 scripts/verify_wasm_assets.py
env -u XYG_SESSION_WASM node --test packages/xy-node/test/graph-session-wire.test.mjs js/test/package-wasm-contract.test.mjs js/test/package-wasm-manifest.test.mjs
XYG_GRAPH_PROPERTY_EVIDENCE=<new-property> uv run pytest tests/test_graphforge.py -k property_default_exports -q
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so XYG_CHROMIUM=<cached-chrome> node tests/browser/graph_property_default_export.mjs <new-property>
XYG_CHROMIUM=<cached-chrome> XYG_WASM_FOUNDATION_REPORT=<new-report> env -u XYG_WASM_FOUNDATION_ONLY node scripts/wasm_foundation_smoke.mjs
XYG_CHROMIUM=<cached-chrome> node scripts/inline_wasm_file_smoke.mjs
```

No fresh qualification failures remain. Full-worktree hooks, Ruff check and Ruff format check pass before the final
local commit (`final-hooks`, `final-ruff-check`, `final-ruff-format-check`),
with raw results recorded here. Parent **new independent
final integrated review** remains required before PR, push or integration.
The 511/212-byte package headroom does not authorize later growth. This slice
does not close #935 intent/digest/safe-pair scope, #934, #36 S5b/S6/S7, M4 or
#108, and establishes no performance win, broad acceptance or publication.
No GitHub mutation, issue closure, remote push or publishing was performed.
