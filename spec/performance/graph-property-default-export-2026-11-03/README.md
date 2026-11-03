# Default property graph export: bounded partial proof, 2026-11-03

Acceptance is **not complete**. This receipt starts from clean accepted main
`030c79062138bb8287df2dc93ab6fdc0ecc8747b`, branch
`t3/graph-default-export-proof`, isolated worktree
`/home/ubuntu/.t3/worktrees/xyg/t3-45a7b1fc`. It excludes the parent's
uncommitted S5a changes. Production renderer, layout, identity, GPU/session
contracts, package budgets, compiler/dependencies and historical receipts are
unchanged. No issue, milestone, PR, publication or remote operation was performed.

## Contract and passing evidence

The existing synthetic `results/base-property-{nodes,edges}.arrow` fixture is
used without a result layer, layout override, authored style, or new public API.
`tests/fixtures/graphforge/property_default_export.json` records its input facts:
five exact node UUIDs, five relationship UUIDs, parallel pair, self-loop,
endpoints, caption precedence, relationship types and label legend. It contains
no output hashes or replacement layout oracle.

At 640×420, both light and dark, the Python and Node tests independently
compose twice and compare actual PNG and SVG bytes, for both the canonical
Scene and public native chart exports. The Python/Node request/document bytes,
canonical exports and public exports agree exactly across hosts. Native ABI 398
and the real packaged WASM ABI 35 return identical documents, including the
Scene, through direct invocation and through the packaged browser Worker.
All ten identities reach the browser's painter traces, including both parallel
relationships and the self-loop. Their type and exact endpoints round-trip.

The public native chart's default f64 node positions equal the canonical
positions exactly, with no supplied positions or independent test layout.
SVG routes distinguish the parallels, close the loop and contain two
nondegenerate arrow wings per relationship. The WASM browser's nodes and all
17 shaft/loop/arrow pieces match SVG geometry within 0.005 CSS px, under the
existing 0.01 px geometry tolerance (`tests/test_graph_static_export.py`).
Pieces retain stable edge IDs with counts 3, 3, 5, 3, 3. Caption anchors agree
within 0.004 px, including the same documented last-caption truncation; the
complete label legend text is present. The static Scene intentionally omits
relationship-type labels under the existing contract.

Final nearby suites: **23 Python tests passed; 38 Node tests passed, zero skips**.
These test totals include the existing semantic/compound and full composition
parity suites, not just the newly added bounded tests. The browser helper also
proves native tick readiness and records no page errors.

## Failed presentation acceptance

The normal browser helper invocation **exits 1** on the existing graph visual
limits: mean maximum RGB-channel difference <3.5 and fraction of pixels with
maximum difference >96 <0.01 (`graph-mark.md` §8). Full images include the
caption and legend. No mask, legend suppression, tolerance change, snapshot
refresh or diagnostic false-green mode is used.

| Comparison | Light mean / fraction >96 | Dark mean / fraction >96 | Result |
|---|---:|---:|---|
| Canonical PNG vs packaged WASM browser | 10.463013 / 0.016879 | 9.653229 / 0.015774 | fail |
| Public native PNG vs its HTML browser | 2.557716 / 0.009308 | 2.390472 / 0.008311 | pass |
| Canonical PNG vs initial native HTML browser | 11.272161 / 0.028464 | 236.713408 / 0.992775 | fail |

These are measured product gaps. Exact geometry/identity agreement does not
establish presentation parity. The WASM screenshot differs in background and
legend placement despite matching data geometry. The canonical Scene has axes
and five home captions; the native chart hides axes and shows two home
captions. A dark native chart request retains a white background, whereas the
canonical dark Scene is dark. The raw screenshots and DOM observations are
retained for parent diagnosis; this proof makes no production repair or claim
that these are the only causes of the pixel differences. The parent received
the presentation-gap handoff before any repair was attempted and directed that
repair be scoped separately after S5a.

#934, #935, M4 and #108 remain open. WASM relationship-type zoom gating and
keyboard/accessibility acceptance still depend on #36 S5–S7. This tiny local
fixture provides no scale/performance, competitor, notebook/application,
cross-driver or release-wide acceptance evidence. It makes no competitor win
claim. No full two-hour pytest run was attempted.

## Reproduction and raw evidence

Use the pinned repository toolchain and run from the repository root:

```bash
uv sync --group dev
/home/ubuntu/.cargo/bin/cargo build --release
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
PATH=/home/ubuntu/.cargo/bin:$PATH npm run build:wasm
python3 scripts/stage_node_platform_natives.py --lib target/release/libxyg_core.so
XYG_GRAPH_PROPERTY_EVIDENCE=/tmp/graph-property-final uv run pytest tests/test_graphforge.py tests/test_graphforge_semantic_evidence.py -q
XYG_NATIVE_LIB="$PWD/packages/xyg-node-linux-x64/libxyg_core.so" node --test packages/xy-node/test/graphforge.test.mjs packages/xy-node/test/graphforge-wasm-parity.test.mjs
XYG_NATIVE_LIB="$PWD/packages/xyg-node-linux-x64/libxyg_core.so" node tests/browser/graph_property_default_export.mjs /tmp/graph-property-final
```

The last command is expected to fail on this base and produces `browser.json`
with explicit failures before returning nonzero. It uses Playwright's installed
Chromium by default; set `XYG_CHROMIUM` for an installed system browser. The
documented `/usr/bin/google-chrome-stable` is absent on this machine; no browser
or dependency was downloaded for this proof. The actual executable/version and
toolchain are in `environment.json`. The source Node is v24.21.0 on this host;
this is not evidence for the repository's full supported-runtime matrix.

`commands.json` gives exact final argv, explicit environment, exit codes and
raw log paths. Setup/build outputs are `*.txt.gz`; the WASM packaging command
passed the unchanged 1,817 KiB raw / 742 KiB gzip gates. Native bytes are staged
into the existing exact-platform package and loaded explicitly, without an
implicit loader fallback. `artifacts.json` inventories native/client/WASM bytes,
manifest, exported documents/images and hashes, including the generated HTML
whose inline client is reproducible but not copied into this receipt.
`source.json` records base, source/contract hashes and the scoped source diff
hash before adding the receipt, avoiding a self-referential hash.

`outputs/` contains raw XYGQ/XYGF, canonical and public-native PNG/SVG,
unmasked browser PNGs, `observations.json` and `browser.json`. Images are proof
outputs, not blessed regression goldens. The helper compares each newly produced
export to newly captured browser paint; it never reads these committed images
as a passing oracle. Required full-worktree hook/Ruff logs are retained beside
the test logs. Parent owns independent review and integration.
