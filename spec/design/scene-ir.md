# Canonical scene IR

Issue [#58](https://github.com/CurateLabs/xyg/issues/58) moves parity-affecting
scene and static-export decisions into `xyg-engine` in bounded vertical slices.
This document is the version contract for that migration.

## Ownership and versioning

`crates/xyg-engine/src/scene.rs` owns the canonical scene records.
`SCENE_VERSION` starts at 1 and is exposed as `xyg_scene_version`; hosts may
reject an unsupported scene version independently of the C `ABI_VERSION`.
Changing a record's meaning, units, ordering, or bounds requires a scene-version
bump. Adding a new record that old consumers never receive does not.

The IR is an in-process typed contract, not a JSON data path. Numeric arrays
cross the C ABI as bounded typed buffers and remain subject to the dossier's
§29 prohibition on JSON numbers on the browser wire.

## Version 1: built-in scatter scene

Version 1 contains a screen-space scatter scene with one record per mark:

- f64 center x/y and authored diameter;
- RGBA8 fill and stroke;
- optional validated constant CSS paint tokens, preserving authored SVG spelling;
- f64 stroke width;
- the stable built-in symbol code from the public symbol table; and
- an optional visibility byte.

Rust validates equal record counts, finite coordinates and sizes, non-negative
diameter/stroke width, and the `DIRECT_SOFT_CEILING` bound of 2,000,000 marks.
It then owns stroke-inclusive radius calculation, every built-in marker shape,
visibility, deterministic numeric formatting, and SVG fragment construction.
Unknown symbol codes fail closed to the circle shape, matching the existing
compatibility fallback.

Python calls this path from `_svg._scatter_marks`; Node exposes the same record
through `scatterSceneSvg`. Python remains responsible for ingest coercion,
public validation text, channel-to-RGBA resolution, scales, and polar projection
until those policies move in later slices. Authored arbitrary marker paths and
font glyph markers stay on the existing Python compatibility path because they
need separate bounded path/text records.

## Evidence and extension order

Rust unit tests pin schema validation and byte-deterministic SVG. Python tests
prove the public scatter exporter consumes the Rust scene and preserves its
custom-marker fallback. Node tests consume the same scene fixture and expected
fragment. ABI generation, parity, and version-first loading cover both hosts.

Next slices add scales/layout/ticks, line and area records, remaining mark
families, chrome/legend/annotation records, and finally native whole-scene SVG,
PNG, and PDF consumption. Browser DOM measurement and WebGL paint remain
environment-specific consumers with documented layout tolerances (§7 and §21).
