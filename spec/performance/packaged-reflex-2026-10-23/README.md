# Packaged Reflex and public HTML degradation evidence

This is bounded correctness and migration evidence for
[#886](https://github.com/CurateLabs/xyg/issues/886). Its application-host
requirements changed during this run:
[#1063](https://github.com/CurateLabs/xyg/issues/1063) retires Reflex and
retargets acceptance to Python/Streamlit and Node/vanilla TypeScript. The six
Reflex cases prove the pre-removal/current-main adapter; the two public Python
HTML cases remain applicable shared proof. **This report does not close the
amended #886 or qualify the #1063 replacement consumers.**

The original artifact is the Linux x64 wheel from main
`cbf2c0eb3fdc2bb4f1ec8dd1cede8f3f73158342`, CI run `39884110393`, artifact
`12472911324`. Its SHA-256 is
`557af3a526d969d3e9ad8cf815a3d1159e6423270a134e1b21a3c5ca61576082`.
It is an installed development wheel, not an accepted final RC cohort.

The original wheel fails a real live `XYChart` unmount: the DOM id
`packaged-density` remains in `window.__xy_views` after SPA navigation, even
though the view is destroyed, its GL/tick handles are cleared, its listener
count is zero, and its tick Worker has terminated. `baseline/` retains the
browser report, screenshots, and byte binding. The wrapper fix captures one
stable inspection-map key for payload replacement and unmount; React can clear
the DOM ref before effect cleanup.

The final worktree wheel passes all eight cases in
[`fixed/evidence.json`](fixed/evidence.json), on Python 3.12.15, Reflex 0.9.8
and Chromium 149.0.7827.55. Its SHA-256 is
`d8b67a1df77cabcc4dc967fdb64c7a6219200c465ea8cf7f4d09a2353da05f01`.
The complete 172-file installed package inventory matches that exact wheel.
`artifactSource` is `working-tree-build`; `sourceCommit` and `artifactCommit`
are null, with `cbf2c0eb...` recorded only as the base. The source ledger binds
680 source files and six prebuilt assets; three additional normative ABI
contract hashes are explicitly recorded after build. No producer bytes changed
during the final run.

The matching current
[full foundation report](../density-tile-cache-2026-10-23/source-browser-validation/xyg-tile-final-foundation.json)
passes six ESM/IIFE no-refinement cases, and all four of its client/worker/WASM
asset hashes match this wheel. It complements the actual Python HTML exports
without duplicating the broader browser aggregate.

| Amended #886 criterion | Evidence and disposition |
|---|---|
| Packaged Python/Node hosted ticks and vanilla TypeScript mounts | The six Reflex cases are pre-removal evidence only. Supported-consumer qualification remains owned by #1063. |
| Local assets, explicit CSP, no Python Node runtime | Proven on the tested app/export paths, including a Python-only compiled-app process tree; replacement-consumer coverage remains #1063 work. |
| Missing/invalid modules and unsupported density sources | Current shared ESM/IIFE cases plus two real Python HTML faults pass. The live unsupported-source journey is a pre-removal Reflex proof to account for in the #1063 coverage inventory. |
| Tick failure versus optional density degradation | Exact tick initialization errors, no admitted tick handle/positions, and retained density overview are asserted separately. Port applicable tick-host cases under #1063. |
| Screenshots, pixels, events, lifecycle, versions and hashes | Retained for all eight cases, with the original wheel regression and diagnostic history below. |
| Specification and evidence ledger | This ledger and browser-WASM spec explicitly record #1063 supersession and the remaining supported-consumer qualification. |

The reusable runner installs nothing and never imports XYG from the checkout.
It checks the installed distribution version and native/client/worker/WASM/
wrapper hashes against the supplied wheel before compiling the actual Reflex
application fixture. It also checks the compiled app's linked assets against
those exact installed bytes.

| Case | Required observations |
|---|---|
| Primary Cartesian ticks | Packaged local worker/module, Rust tick cache and labels, public navigation admits a newer Rust revision, nonblank canvas |
| Secondary ticks | `x`, `y`, and `y2` all use the Rust cache before and after public navigation |
| Polar ticks | Angular/radial axes both use the Rust cache; public radial navigation admits a newer revision |
| Live unsupported density source | Actual Python split payload declares `XYG_WASM_SOURCE_UNSUPPORTED`; attempted WASM dispatch retains the initial Rust overview and leaves native kernel refinement available |
| Missing/corrupt hosted tick module | Real worker fetch returns 404 or bytes `00 01 02 03`; `XYG_WASM_INIT_FAILED`, no fabricated tick positions, data marks remain visible |
| Public HTML missing inline module | Actual installed-wheel `Chart.to_html()` output; optional bootstrap withheld; `XYG_WASM_UNAVAILABLE`, exact grid/texture/home pixel retention, distinct nonblank zoom, exact home restoration, no fallback Worker |
| Public HTML corrupt inline module | Same unmodified generated file; valid classic worker/bootstrap framing with only WASM base64 replaced by bytes `00 01 02 03`; actual `WebAssembly.compile` rejection, retained overview, failed Worker terminated and URL revoked |

Each Reflex case also navigates to a chart-free route and requires removal of
the supplied DOM id from the inspection map, zero live owned Workers, released
GL and tick handles, and zero listeners. The original live case makes this a
regression test for ref-clearing cleanup rather than a source-text assertion.

The browser rejects every HTTP origin except the local Reflex app. The probe
adds an explicit nonce CSP to the served documents; `script-src-attr 'none'`,
same-origin Workers/connections, and no external fallback remain enforced. The
probe grants Chromium's `local-network-access` permission to that one loopback
origin because intercepted documents otherwise block the actual app websocket.
This is a recorded test permission, not a product change. File exports retain
their own generated CSP and prohibit all HTTP requests.

Both probes record the repository's established SwiftShader launch arguments.
Pixel reads happen once after a bounded presentation wait; unexpected blank,
stale, lost-context, or identical zoom pixels fail. Shared-host mode reads the
chart's presented 2D canvas; dedicated mode uses synchronous GL readback because
its drawing buffer is not preserved. Screenshots show the resulting charts and
tick labels. This is software-renderer correctness evidence, not GPU timing.

The first frozen-wheel HTML attempt failed to complete presentation; it did
not yet retain GL-state diagnostics. A diagnostic replay against the same
export bytes passed unchanged pixel assertions and the same eight-draw bound;
no root cause or product fix is claimed. The replay report and screenshots are
in [`diagnostics/`](diagnostics/README.md). A subsequent combined run exposed
an incorrect strict-null test oracle: initial failed attachment leaves the
tick slot undefined, not installed. The final run records `typeof undefined`
and no own property, accepts only null/undefined absence, and still requires
exact `XYG_WASM_INIT_FAILED`, zero tick positions, terminated Workers and
strict-null cleanup after destruction. Its earlier red report is retained.

To reproduce against another wheel, provision an isolated environment first:

```bash
uv venv /tmp/xyg-reflex-proof/venv
uv pip install --python /tmp/xyg-reflex-proof/venv/bin/python \
  '/absolute/path/xyg-wheel.whl[reflex]' 'reflex==0.9.8'
npm install --prefix /tmp/xyg-reflex-proof/tooling bun@1.3.14 --no-audit --no-fund
```

Run the complete proof with one command (the native Bun path avoids an npm
postinstall shim on hosts that disable dependency install scripts):

```bash
REFLEX_USE_SYSTEM_BUN=1 \
PATH=/tmp/xyg-reflex-proof/tooling/node_modules/@oven/bun-linux-x64/bin:$PATH \
uv run python scripts/packaged_reflex_ticks_smoke.py \
  --python /tmp/xyg-reflex-proof/venv/bin/python \
  --wheel /absolute/path/xyg-wheel.whl \
  --source-commit FULL_ARTIFACT_SOURCE_SHA \
  --work-root /absolute/path/on-disk/temporary-apps \
  --output /tmp/xyg-reflex-proof/evidence.json
```

Playwright and its Chromium installation are repository test prerequisites.
`--work-root` chooses disk-backed temporary app storage when a memory-backed
`/tmp` user quota cannot fit Bun's frontend dependency tree; the runner removes
only its own temporary application after the run.
The Python package consumes its prebuilt assets; Node/Bun are frontend compile
tools and the browser test driver. After compilation, the runner rejects a
Node/Bun process in the actual Python app's process tree. Build/runtime logs,
frontend dependency manifest/lock, complete Python distribution inventory,
browser/renderer versions, screenshots, events, lifecycle diagnostics, exact
wheel/assets/harness hashes, and the public HTML export SHA/size are retained
beside the report. Generated HTML embeds the client bundle, so its compressed
bytes stay local under dossier §33 and can be reproduced from the exact wheel.
The original baseline's raw report lists that local file; `RETENTION.json`
records its intentional omission from Git. A worktree build declares
`artifactSource: working-tree-build`, leaves the artifact commit unset, and
records its base commit and a separate source-file hash ledger; it cannot
stand in for an immutable final candidate.

Reflex 0.9.8's npm-only production build currently rejects its own direct
`postcss` version/override combination (`EOVERRIDE`). The reproduction uses
Reflex's supported system Bun 1.3.14 path without modifying Reflex or XYG.
This does not claim that building a Reflex frontend requires no Node tools.

This slice covers one Linux x64 wheel, one Reflex version, Chromium, small
static routes and one live density route. `SOURCE_UNSUPPORTED` belongs to the
real live split payload here; public packed HTML intentionally omits that
descriptor, so its two failures do not invent an unsupported-source flag.
The amended supported-consumer acceptance in #886 remains open through #1063;
this historical adapter proof does not replace that work. The full #54 final
platform/cohort matrix, #885 authoring/aggregate work, massive-scale acceptance,
refreshed hosted performance interpretation and final RC artifact reuse also
remain separate gates.
