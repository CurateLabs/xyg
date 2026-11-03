# Property-default presentation repair (#934/#935)

The bounded presentation repair passes the unchanged full-image helper in both
themes, but **the production WASM package is rejected by the unchanged size
gates**. Parent integration and independent final review are still required.
No push, PR, remote merge, issue closure, publishing, or credential retrieval
was performed. Parent: `e768ce25194bf3ebcc1a0de1df37696da3948295`.

## Policy and implementation

The parent decision was recorded in `graphforge-compositions.md` §4.4a before
behavior edits: property-only, zero-result-layer canonical Scenes use the
existing public graph presentation. Rust's existing `graph_label_plan` and
`graph_home_domain` own caption priorities and the home view; the extracted
cartesian graph shell owns plot bounds, and unauthored axes are hidden.
Generic semantic Scenes and layered canonical compositions keep their prior
presentation. The seeded force call, seed, ticks, topology, source positions,
clipping, route and arrow implementations are unchanged. No supplied/preset
positions or new force/layout algorithm/pass is used to make the proof agree.

The canonical property fixture now paints `ada` and `00000005`, the two captions
visible under the existing public home plan. All five source captions retain
their text, order and identities in the document. Relationship types retain
priority −1 below caption priority 0; the shared plan, rather than a fixed
five-caption culler, decides visibility. Every source UUID, edge endpoint,
semantic class, direction/status and legend row remains exact.

The existing semantic chrome palette is extracted in Rust. A native-only,
allocation-free copy accessor returns its four RGBA8 rows. The property-only
Python and Node adapters mechanically map those bytes into existing chart
style slots before authored values. Layered host theme behavior is unchanged.
Native ABI 399 adds that accessor and generated bindings; WASM ABI 35, Scene 34,
and painter 17 stay unchanged. The compiler, profile, optimizer, dependencies,
WASM exports, guards and 16/384-MiB runtime limits are unchanged.

## Final functional results

`corrected-property/browser.json` is the unmodified helper result (the sole
browser-source edit is the required native ABI assertion, 398 → 399). All
comparisons use unmasked full 640×420 images at device scale 1, with the same
exclusive mean <3.5 and fraction-over-96 <.01 limits:

| Theme | Pair | Mean max-channel difference | Fraction over 96 |
|---|---|---:|---:|
| Light | Canonical / WASM browser | 0.7523251488 | .0025930060 |
| Dark | Canonical / WASM browser | 0.7003459821 | .0025372024 |
| Light | Native export / native browser | 2.6464880952 | .0089657738 |
| Dark | Native export / native browser | 3.1425372024 | .0098883929 |
| Light | Canonical / initial native browser | 2.8272842262 | .0087127976 |
| Dark | Canonical / initial native browser | 2.4920982143 | .0093452381 |

Every geometry check passes within .005 CSS px (unchanged .01 limit), including
caption text/anchors, node centers, route pieces, and legend frame, swatches
and text. Edge-piece counts by stable ID remain `3,3,5,3,3`, including distinct
parallel edges, the loop and arrow wings. Python/Node request/document/SVG/PNG
bytes match, default initial-native f64 positions equal canonical positions,
and repeated canonical/native exports are exact. Requests, exports, unmasked
screenshots and raw observations are retained in `corrected-property/`.

`corrected-preservation-comparison.json` compares all 99 cross-host cases
against the parent ABI398 library: every request and every document section
are identical except `scene.canonical` in `property graph + render`. This
includes exact source position bytes and every layered canonical Scene. Only
that property-render digest changes in `cross_host.json`. Ten other fixtures
change only their `abi_version` metadata; `abi-only-fixtures.json` proves all
other JSON values are exact. No image golden or pixel tolerance is replaced.

Completed focused checks (raw argv/exits/logs in the matching command files):

- `corrected-engine-tests`: 320 Rust graph tests pass.
- `corrected-autorange-tests`: 13 Rust autorange-related tests pass, including
  positive-bar zero-baseline preservation.
- `corrected-focused-python`: 181 pass, including graph home view, label plan,
  static export, unchanged visual goldens, GraphForge, semantic mapping/style,
  autorange, ABI parity, and native session/transport tests.
- `corrected-property-python`: both default property helper cases plus the
  new palette/authored-style/layered-preservation and ABI boundary cases pass.
- `corrected-node-tests`: 88 pass (graph, GraphForge, and cross-host).
- `abi-fixture-python`: 348 pass; `abi-fixture-node`: 148 pass. These prove the
  ABI-only metadata refresh against current product outputs in both hosts.
- `package-python-tests`: 78 pass; `package-guard-tests`: 7 pass.
- `corrected-native-abi-smoke`: passes against the actual release library.
- `rejected-production-foundation`: the full, unfiltered strict-CSP local-only
  browser foundation and Worker lifecycle smoke passes against the exact
  rejected production bytes; its report is retained separately.

The final full-worktree hooks and Ruff results are recorded in `hooks`,
`ruff-check`, and `ruff-format-check` command/log files. No full multi-hour
Python suite or comparative performance claim is made.

## Production package failure (not waived)

Both release targets and the client were built using the repository's actual
production commands. `corrected-wasm-package` invokes the unchanged shipping
packager and exits 1:

- Optimized WASM: **1,922,561 bytes**, SHA-256
  `e8011f779e70f58416a751f0067f279d1b9aa9515004c246e2f44c95af192651`.
- Gzip6: **783,148 bytes**, SHA-256
  `d447f4e3f63a0b189f962d53cba34336224df6cb84e4cd5be7fa430f7366120a`.
- Unchanged gates: 1,882,112 raw / 769,024 gzip6 bytes. Over by **40,449 /
  14,124 bytes**, respectively. Growth over the accepted parent's production
  module is 41,053 raw / 15,014 gzip6 bytes. This slice first makes the existing
  public graph home-domain authority reachable in the canonical WASM path.
- Release compiler output before the shipping optimizer: 2,120,065 bytes,
  SHA-256 `5ddb66a4244de26784b7eeae7a5e695b112967891181c7a02da57336d444434c`.
- Native release library: 6,108,248 bytes, SHA-256
  `e88b3f9458effea8f677d187e9e0e72fa4c3f26e43878c118aebf13494a37bad`.

`corrected-production-sizes.json` and `artifact-inventory.json` bind those
bytes to their production paths. `measure-candidate.mjs` uses the unchanged
shipping optimizer on the actual release compiler output and retains the
exact module losslessly in `corrected-production-candidate.wasm.gz`. It stages
those same rejected bytes only so the existing functional probes can run; it
does not invent a manifest, inline bootstrap, or package acceptance. This is
not an alternate diagnostic build. Package qualification remains failed:
`rejected-package-assets` also exits 1 because the rejected packager produced
no inline WASM or generated asset manifests. Native and WASM functional passes
must not be presented as a shipping package pass. No speculative size search,
budget increase, export deletion or unrelated feature removal was performed.

## Reproduction and provenance

Use Node `target/task-tmp/node-v22.23.4-linux-x64/bin/node`, project `uv`, Rust
1.96.0, and cached Chromium
`/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
`environment.command.json` and `environment.log` record the toolchain and host.
`corrected-build-inputs.json` hashes all tracked crate/Python/Node/client build
sources and the new Rust helper. Its canonical source SHA-256 is
`2268a29aaab52a747360a22023cfb96a86ab4b0f5f11bafd99bd63c88a491da4`;
`artifact-inventory.json` confirms those inputs still match and that staged
Python/client copies are exact. Client ESM and Worker bytes match the parent;
no browser source was changed. Historical receipts are untouched.

Raw stdout/stderr is stored losslessly as `*.log.gz`; `compression.json`
records raw and compressed SHA-256 values, and each command record verifies
the decompressed log. Original plaintext copies also remain in the worktree.
The `*.command.json` files contain exact argv, cwd, selected nonsecret
environment, UTC start/end, exits and log hashes. Reproduce into a new receipt
and property output directory, preserving this one. Build commands are
`cargo build --release -p xyg-core`,
`cargo build -p xyg-wasm --release --target wasm32-unknown-unknown`,
`node js/build.mjs`, and `node js/package-wasm.mjs`. The last command must
retain its size failure. For explicitly rejected-candidate functional checks,
run `measure-candidate.mjs` with a fresh output prefix, then:

```bash
XYG_GRAPH_PROPERTY_EVIDENCE=<new-output> uv run pytest tests/test_graphforge.py -k property_default_exports -q
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so XYG_CHROMIUM=<cached-chrome> node tests/browser/graph_property_default_export.mjs <new-output>
XYG_CHROMIUM=<cached-chrome> XYG_WASM_FOUNDATION_REPORT=<new-report> node scripts/wasm_foundation_smoke.mjs
```

All earlier attempts remain: missing-WASM prerequisite failures, test-authoring
mistakes, the corrected Node pointer call, and the autorange regression caught
and repaired by its existing zero-baseline test. `property/`, `final-property/`,
`production-*`, and earlier build/test logs are superseded by the corrected
results above; none is deleted or used to claim a final pass.

This slice does not close #935's intent/digest/safe-pair scope, #934, #36
S5b/S6/S7, M4, or #108, and authorizes no publishing. The parent must resolve the
production package failure and obtain independent review of the final diff.
