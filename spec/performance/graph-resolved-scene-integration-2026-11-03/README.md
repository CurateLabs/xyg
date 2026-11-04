# Resolved Scene consumer: combined parent proof

Normal merge of independently reviewed child `a95f7e91d9f69787dc9aab98114dd968918e402f` into P1 parent `6997e767a01b97381f3334392c06d0c48ed17ae6`. All browser product sources match the child exactly. Native/WASM producer sources and package gates match the parent exactly. No native/WASM rebuild is needed or claimed. The new S5 roadmap wording records the actual accepted #1085 merge; the private S6 and later controller/host requirements remain unchanged.

The isolated R5 repair received completed independent reviews from `s5a_final_review` and `m4_defaults_audit`: whole diff SHA-256 `3a6b5fc202977e88301c6440dca97040290c60cf0ae78fed03a572b04adfdceb`, source diff `ba50b179cdcbb74c3f4cddc26c6630c9b8e96134f59ef6d99a12cb42b5fd5271`. They verified the three actual failing-before/passing-after CSS cases, historical preservation and honest remaining failures. This receipt separately proves the combined current P1 artifacts.

## Behavior

The resolved Scene consumer preserves Rust-final plot bounds instead of adding ordinary top/right gutters again. Resolved spines consume native centerlines and exact nonnegative widths as actual SVG strokes. The public HTML slot retains its CSS cascade; effects the narrow adapter cannot faithfully represent retain one HTML paint path. This includes pointer-enabled hit regions, motion paths and supported reflections as well as existing borders, gradients and other box effects. Ordinary host layout and axes remain unchanged. The earlier resolved SVG legend default-box repair is included.

No rounding, DPR offsets, new layout/force/LOD policy, mask, tolerance change, golden replacement, general CSS-to-SVG renderer or native export compensation is introduced. Endpoint caps, residual grid/serializer precision and exact-recapture limitations remain as recorded in the child receipts. This does not establish arbitrary exact native/SVG pixel equality.

## Fresh combined results

| Check | Result |
|---|---|
| Fresh native producers | 37 authored Scenes/ordinary payloads and slot/precision Scenes match historical canonical inputs exactly |
| Browser bundle build | PASS; index SHA-256 matches final reviewed R5 child |
| Production packager / paired assets | PASS with the unchanged P1 module and current bundle |
| Canonical matrix | 222 browser cases, 111 independent native-SVG plot checks and 276 spine checks PASS |
| Ordinary preservation | 111 records and 12 screenshots exactly unchanged |
| Pointer/motion/reflection | 12 cases and 12 switching records PASS; no skips; all 12 complete screenshot pairs exactly equal independent 188f baseline |
| Existing CSS slots | 144 cases and six switching runs PASS |
| Literal fractional width | .3 Rust width and authored CSS footprint at DPR 1 / 1.25 / 2 PASS |
| Nearby Python/security/dual-axis/chrome tests | 82 passed |
| Full strict-CSP foundation | PASS; six PNGs, zero external requests, artifactCommit null |
| Ownership / release preparation inventory | PASS; 504 classified files, 685 explicit gaps remain |

The initial producers ran alongside the short client build. `producer-preservation.json` explicitly verifies both generated native HTML documents embed the final standalone bundle, allowing only the three required HTML closing-tag escapes. Thus no stale bundle snapshot is used. All 149 matrix input files and fresh slot/precision exports match the historical canonical inputs exactly.

The actual production WASM module remains 1,881,508 raw / 768,134 gzip6 bytes, SHA-256 `717440524b63cf87e0127161c128c4f81efdca87e5112f9b05a42e820b456fde`. Current 1,838/751-KiB gates and headroom 604/890 are unchanged. The fresh packager invokes the production optimizer on the unchanged raw module. Native SHA-256 remains `6df9cb7ed06048d08d59ec8c068da0e0be9b5a3eb6b10d1b86f08527a8fd2485`. The fresh bundle index is `b2c2066b1d6ed2687a1a248c3f7e8eb1541d4bf6a39ae56a75a99968b5a13f6b`; its bytes equal the final child build despite the different current WASM artifact.

## Untouched whole-image acceptance helper

The existing property helper runs normally and **still exits 1**. Both WASM comparisons pass the unchanged mean <3.5 / fraction-over-96 <.01 limits, over every pixel:

| Comparison | Mean max-channel difference | Fraction over96 | Result |
|---|---:|---:|---|
| Light canonical / WASM browser | 1.4715736607 | .0039508929 | PASS |
| Dark canonical / WASM browser | 1.4738616071 | .0039620536 | PASS |
| Light canonical / initial native chart | 11.2721614583 | .0284635417 | unchanged FAIL |
| Dark canonical / initial native chart | 236.7134077381 | .9927752976 | unchanged FAIL |

Native chart versus its own export still passes. Exact identities, loops/parallel routes/heads, f64 positions, captions and legend/frame/swatch/text geometry checks remain green. These two separate initial-native presentation failures are retained, not removed from the helper or hidden by a diagnostic pass mode. The failing helper is not newly registered as a CI gate.

## Reproduction and evidence

`run.py` records exact argv, exits, elapsed time and raw/gzip log hashes. `reused-producers.json` pins pre-build native/raw/optimized identities. `module.json` records actual production output, and `capture.py` binds both parents' historical receipts, exact browser/native source ownership, artifacts, all command logs, foundation PNGs and expected remaining helper failures. `compression.json` records lossless copies of generated native HTML. Generated shipping bundles remain ignored and uncommitted.

Use fresh output directories when reproducing: run the matrix/slot producers, build the browser bundle, run the production WASM packager, then the unchanged browser harnesses shown in command records. The independent 188f baseline index is retained with hash `351fa5038800204a13a99ae9cb91612472e3368f6d7ecd4829d589e39b16acd7`. The canonical audit consumes existing historical native SVGs only after byte equality with the fresh producer is established. Pixel samples remain diagnostics, not masks or replacement image gates.

Required full-worktree hooks and Ruff pass (962 Python files formatted). Completed independent final integrated review by `s5a_final_review` approves the 17-path nonreceipt diff SHA-256 `59f09d003007f892df877b69ab8bca212961b58b1784ed865377ea54770a819a`, including exact child browser sources, 234 unchanged parent Rust files, actual current artifacts, logs, full proof and historical preservation. Fresh PR CI and parent landing remain required. No multi-hour full Python suite or comparative performance claim is made. Native/WASM signatures, ABI398/WASM35/Scene34/painter17, compiler/profile/optimizer/dependencies/exports/guards and runtime16/384-MiB bounds stay unchanged. S5b/S6/S7 public integration, massive-graph admission, native home-view/theme/caption parity, #934/#935/M4/#108 acceptance and publishing remain outstanding.
