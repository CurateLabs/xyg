# Independently authored StaticDocument corpus

`test_static_document_authored_cross_host.py` and
`packages/xy-node/scripts/static_document_authored_cross_host.mjs` are additive
evidence for #873 and the public-authoring work in #875. They complement the
existing raw-Scene replay tests; they do not claim those replay tests establish
independent authoring.

Python constructs `xyg.chart`, marks, axes, text, legends, and `xyg.facet_chart`
through their public composition APIs. Each output is requested through public
`to_image(..., engine=Engine.default)`. The test observes the XYST bytes passed
to Rust during that call. It does not alter trace identifiers, rewrite Scene
bytes, bypass public validation, or construct a replacement Python document.

The Node script receives no input and independently constructs the same literal
chart data and styles through the exported `Figure` constructor and mark /
annotation methods. It uses exported `staticDocumentEncode` and
`staticDocumentExport` to author and export the envelope. Panel chrome metrics,
annotation metrics, legend items, and document placement are explicit authored
fixture facts in this lower-level Node API. There is no test implementation of
Python's general projection or layout algorithm.

For each retained case the test compares every embedded Scene, the complete
XYST envelope, complete SVG text, and exact output length/SHA-256 for PNG, PDF,
JPEG, and WebP. SVG labels must be present, guarding against identical empty
outputs. The two-panel case independently authors data and per-panel titles in
each host and checks the title strip, gaps, and panel order through the complete
document comparison.

| Case | Python public authoring | Node public authoring |
| --- | --- | --- |
| Styled line | `chart(line(...), x_axis(...), y_axis(...))` | `Figure(...).line(...)` plus explicit XYST panel metrics |
| Outlined diamond scatter | `chart(scatter(...))` | `Figure(...).scatter(...)` plus explicit XYST panel metrics |
| Text annotation | `chart(line(...), text(...))` | `Figure(...).line(...).annotate(...)` plus explicit XYST annotation metrics |
| Anchored legend | Named line/circle scatter and `legend(...)` | Named line/circle scatter and authored XYST legend items |
| Continuous colorbar | `scatter(color=..., color_domain=...)` and `colorbar(...)` | `Figure.scatter(color=...)` and `setColorbar(...)` |
| Two-panel facets | `facet_chart(..., data=..., by="group")` | `facetChart({panels: [...]})` and authored XYST panel placement |

## Public contract boundaries

- Node `Figure` exposes `toScene`, `toSceneSvg`, `toScenePdf`, and
  `toSceneRasterCommands`; it does not expose a high-level equivalent of
  Python `Chart.to_image` that projects its authored styles to XYST.
  The explicit envelope route above must not be presented as proof that this
  missing ergonomic/product adapter exists.
- Node `facetChart` exposes `buildPayloads` but has no static-export method.
  The multipanel test proves independently authored public Figures and public
  XYST composition. It does not prove automatic Node facet static layout or
  export dispatch.
- Named non-circle scatter legends currently reject with
  `XYG_STATIC_UNSUPPORTED_FIGURE_LEGEND_STYLE`. The retained legend case authors
  circles explicitly; the separate scatter case still tests diamond geometry.
- The public continuous-colorbar probe records the actual native journey.
  Raw XYST colorbar support alone is insufficient evidence for public
  `chart(scatter(color=...), colorbar(...))` authoring.

The dashed-line cases deliberately retain an even-length dash array with
opacity, including in the named legend and annotation journeys. Each Node
case reports errors independently, so a failed constructor cannot hide the
other cases; any such report is a hard Python assertion failure, not an xfail.

## Recorded validation

All six authored cases pass against the rebuilt #873 development core: 30
exports total, with exact Scene, XYST, and output comparisons. This corpus
exposed and retains regression coverage for Node unaligned dashed-line
observation decoding, explicit hidden facet legends, named continuous
colorbars, and Python scatter legend swatches losing authored color/size.
Those failures were fixed in production; the fixtures were not rewritten to
accept fallback swatches or unsupported journeys.

The final combined run of this corpus and
`test_static_legend_fit_cross_host.py` passed 12 tests. The new Python corpus
also passes Ruff, Ruff format checking, and ty; the Node script passes
`node --check`. These focused checks are not a claim that the entire worktree
or release suite has passed.

Reproduce from a built checkout with both host dependencies installed:

```sh
uv run pytest tests/test_static_document_authored_cross_host.py -q
```

The Node child is launched with `XYG_NATIVE_LIB` set to the exact library loaded
by Python. Missing Node/koffi dependencies skip the cross-host portion; native
ABI mismatches and consumer failures are hard test failures. This corpus is
not yet registered in the host-delegation matrix; the parent integration task
owns that registry update after rebase.
