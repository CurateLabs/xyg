# Resolved axis live CSS repair

Isolated browser repair from `e768ce25194bf3ebcc1a0de1df37696da3948295` for PR #1089. Parent owns integration, independent final review, PR updates and push. This receipt adds evidence without changing any historical receipt or native/WASM producer source, ABI, build configuration, budget or runtime resource bound.

## Findings and repair

- [Greptile r4461520935](https://github.com/CurateLabs/xyg/pull/1089#discussion_r4461520935): **reproduced and repaired**. Actual mouse enter changes the public background to red while the old SVG remains dark. Ancestor focus-within, mouse active and keyboard-active controls reproduce the same stale projection. Discrete input events now coalesce one frame to re-evaluate existing resolved public slots; they do not redraw chrome, replace those public elements or poll at idle. The existing mutation observer also handles direct public class/inline edits, ignoring private nodes and its own clip writes. Browser-owned HTML handles decorated states, including hover gradients/borders; leaving removes stale copies and restores SVG when eligible. Destroy cancels queued work and uses existing listener cleanup.
- [Greptile r4461520943](https://github.com/CurateLabs/xyg/pull/1089#discussion_r4461520943): **reproduced and repaired**. Both normal and important `svg line` rules suppress or recolor/widen the private line although the public box is correct. Inline important implementation styles reset only private SVG wrappers/lines, preserve literal coordinates/widths and copy authoritative public paint/opacity/visibility/stacking. They also keep the line pointer-transparent. No public slot reset or stylesheet parser is introduced.

`tests/browser/resolved_axis_live_css.mjs` records actual input, public computed styles, private attributes/computed styles and full screenshots at DPR 1, 1.25 and 2. After the initial authored slot setup it calls neither `refreshTheme()` nor draw; instrumentation fails the test if any such call occurs. The same public element must survive every state change. Public normal CSS, class `!important` and direct inline `!important` remain authoritative. The existing security guard was updated to recognize the mutation-record callback and its ancestor branch; geometry, native comparisons and image acceptance assertions are untouched.

## Fresh evidence

| Proof | Result |
|---|---|
| Final actual failing-before (`proof-before`) | EXIT 1, visible stale hover/focus/active and overridden SVG paint/width; 60 captures |
| Final actual candidate (`proof-after`) | 60 captures PASS, including automatic decorated fallback and restore |
| Independent browser-owned HTML (`html-reference`) | 60 captures PASS using pinned pre-adapter 188f asset |
| Whole screenshot comparison | All 60 candidate screenshots equal HTML reference at every pixel; required before states visibly differ at all three DPRs |
| Existing canonical matrix | 222 browser cases PASS; 111 independent native-SVG plot checks, 276 literal spine checks |
| Ordinary preservation | 111 records and 12 complete screenshots byte-identical to historical baseline |
| Existing public CSS | 144 cases and six switching runs PASS |
| Pointer/motion/reflection | 12 cases and 12 switches PASS, no unsupported-feature skips |
| Exact fractional widths | Unmodified `.3`/authored-footprint helper PASS at DPR 1 / 1.25 / 2 |
| Nearby security/dual-axis/chrome tests | 82 passed |
| Full strict-CSP foundation | PASS, source dist, zero external requests; six PNG captures retained |
| Historical receipts | 7,058 files hash-verified unchanged |

The controlled `html-diagnosis-fixed` run removes only the projection in a separate diagnostic page using the current Rust-final plot. Native width `.3` becomes HTML used width `.296875` at every DPR and the full screenshots differ. The literal-width acceptance helper was not weakened to accept this. This is why the narrow exact SVG path remains; no new layout policy, pixel snapping, rounding, tolerance, mask or general CSS-to-SVG renderer is added. Native round-cap versus SVG flat-cap and other previously recorded export precision limitations remain.

## Untouched full property helper

`property-browser-ready` runs the existing full helper without edits or a diagnostic pass mode and **exits 1 with exactly the two historical native presentation failures**. All-pixel WASM comparisons remain:

| Comparison | Mean max-channel difference | Fraction over 96 | Result |
|---|---:|---:|---|
| Light canonical / WASM | 1.4715736607 | .0039508929 | PASS |
| Dark canonical / WASM | 1.4738616071 | .0039620536 | PASS |
| Light canonical / initial native | 11.2721614583 | .0284635417 | known FAIL |
| Dark canonical / initial native | 236.7134077381 | .9927752976 | known FAIL |

Thresholds remain mean <3.5 and fraction <.01; native chart versus its own export, node/route identity and geometry, captions, labels and legend geometry remain passing. The parent separately owns native presentation. No whole-image native fix or independent final review is claimed here.

## Sources, artifacts and reproduction

`prepare.py` verifies 237 native/WASM source/build inputs against both the exact base commit and donor worktree before copying artifacts. `reused-producers.json` records the complete source hashes, donor HEAD, copy paths and artifact hashes. No native/WASM rebuild is used for proof. The pinned native library remains `6df9cb7ed06048d08d59ec8c068da0e0be9b5a3eb6b10d1b86f08527a8fd2485`. Production WASM remains `717440524b63cf87e0127161c128c4f81efdca87e5112f9b05a42e820b456fde`, 1,881,508 raw / 768,134 gzip6 bytes. ABI398/WASM35/Scene34/painter17 and existing 1,838/751-KiB gates are untouched.

The fresh candidate ESM hash is `3b194aebda9a2d8f30e0503f01310d944efb72edcca4701777a3c211803ddf70`; IIFE is `bdce4a092184e0feb745ea4ebfc57b3929b5ca795d5ec968f9a678e233efeea8`. Their Python package copies match. Before ESM is `b2c2066b1d6ed2687a1a248c3f7e8eb1541d4bf6a39ae56a75a99968b5a13f6b`; independent HTML reference is `351fa5038800204a13a99ae9cb91612472e3368f6d7ecd4829d589e39b16acd7`. Shipping bundles remain generated and uncommitted. `producer-preservation.json` verifies all 149 fresh matrix inputs and slot/precision exports equal canonical history and generated native HTML embeds the actual new standalone bundle.

Every command record retains exact argv, exit, elapsed time, raw log and deterministic gzip log hashes. Raw logs are committed losslessly as `.txt.gz`; decompression reproduces their original bytes, including compiler ANSI escapes and whitespace. Local `.txt` duplicates are ignored within this receipt. The final runner additionally records explicit environment, Node 22, cached Chromium, native-library path and skip-build flags. To reproduce use a fresh receipt directory: prepare pinned binaries/dependencies, build the browser, produce Scenes, run the four unmodified existing resolved-axis helpers and new live-CSS helper against before/candidate/reference assets, run pixel/canonical audits, then property and nearby/foundation gates as shown in `*.command.json`. `evidence-final.json` binds actual final sources, helper hashes, artifacts, historical preservation, command results and screenshots. Final full-worktree hooks and Ruff results are recorded separately.

Development attempts are retained rather than overwritten: the first `uv sync` unexpectedly invoked the editable-build Cargo hook and was terminated; the pinned library hash stayed unchanged and no native/WASM rebuild output is used. Later tooling sets both skip-build flags. A diagnostic server initially lacked favicon handling; one candidate build failed TypeScript's Node/HTMLElement narrowing, followed by an intentionally retained stale-artifact test failure. A keyboard control initially assumed Chromium propagated keyboard `:active` onto the ancestor; the final control selects the real active button through `:has()`. The first evidence capture used Python gzip instead of the production Node compressor; final measurement uses the unchanged Node 22 measurement helper and verifies the exact production gzip6 bytes/hash. Missing installed Node host dependencies and the obsolete observer source marker were corrected before final gates. Only `proof-before`, `proof-after` and `html-reference` bind the final same-source regression helper. Earlier runs are development evidence, not acceptance claims.

Stylesheet replacement and non-color-scheme media changes without an observed event retain the existing §36 `refreshTheme()` escape hatch. No multi-hour full Python suite, cross-browser conformance or comparative performance claim is made. Parent must obtain a new independent review of the final integrated diff before push/integration.
