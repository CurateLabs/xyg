# Same-registry StaticDocument runtime proof

`test_static_document_registry_cross_host.py` and the matching Node script
consume the `document` subtree generated from the existing Rust
`static_export_registry.rs`. They do not establish a separate support list:
both hosts assert their builder names equal the registered 39 admitted cases
and 21 malformed-envelope mutations. Every admitted row declares all five
formats. The six existing independently authored fixtures are linked by an
exact name-set assertion against `authored_witnesses`.

Both programs independently author their Scene inputs through public chart
constructors, marks, axes, text, arrows, and named colorbars. The Node program
receives no stdin or Python Scene/document bytes. Both then author literal
XYST sidecar facts through their document packers; Node uses the public
`staticDocumentEncode`/`staticDocumentExport` APIs. Literal positions and
metrics are test authoring, not a replacement layout algorithm. This is not
proof of an automatic Node Figure/facet-to-XYST adapter.

Each admitted case compares embedded Scene bytes, XYST bytes, embedded Scene
raster commands, and complete SVG/PDF/PNG/JPEG/WebP bytes. PNG, JPEG, and WebP
are additionally independently decoded with Pillow: format, mode, dimensions,
and every RGBA pixel must match. Scale dimensions and bounded crop dimensions
are checked, and output must contain non-flat pixel data. SVG is parsed as
XML and required authored text/extension slots are checked. PDF receives byte
identity, container-signature checks, decompressed vector text checks, and
explicit Helvetica-Oblique/BoldOblique resources plus searchable authored text
for the seven italic cases. This is **not a rendered-page visual oracle**.
There is no exposed XYST raster-command API: the command comparison is only
for embedded Scenes; sidecar raster behavior is checked in decoded images.

Malformed cases start from independently authored valid documents in each
host and apply the same named corruption. The corrupted bytes must match,
and both consumers must reject each case in every format. There are no
xfails or retry renderers.

## Development before rebase

The default registry path is the generated fixture in this checkout. A missing
fixture or document subtree fails collection. Before #873 is rebased onto the
merged registry, use an explicit development override:

```sh
XYG_STATIC_EXPORT_REGISTRY=/home/ubuntu/code/xyg-m2-875/tests/fixtures/static_export_support_registry.json uv run pytest tests/test_static_document_registry_cross_host.py -q
```

After rebase, omit that variable. No CI fallback searches sibling worktrees.
The parent integration task owns decoder-mask linkage, registry generation,
and final gate registration. This corpus does not itself establish that the
production decoder imports the same registry masks.

## Recorded focused validation

Against the rebuilt ABI 362 core, the combined registry, legend query, label
query, and independently authored public corpus passes **196 tests**:
60 registry rows, 41 XYDL legend proofs, 89 XYDA label proofs, and six public
authoring cases. The 39 admitted registry documents exercise 195 format
exports per host; the 21 corruptions exercise 105 rejection attempts per host.
The legend/label query suites separately observe actual Python native query
calls and compare independently authored Node Scene, XYDD blocks, XYST, and SVG.

The seven italic PDF witnesses now require real Oblique/BoldOblique font
resources and exact searchable text, including escaped XML characters. The
corpus exposed the formerly rejected italic face, entity-semicolon leakage,
and malformed unrotated styled-label SVG quoting; production fixes retain the
strict assertions. This focused result is not a full-worktree/release verdict.
Rust-owned default title centering is also pinned on an odd-width 321px
document: raw title-x is canonical zero with the centering flag, while the
rendered title x is exactly 160.5. A nonzero raw slot under that flag rejects.
