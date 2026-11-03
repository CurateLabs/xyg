# Persisted visualization intent

`@curatelabs/xyg-node/intent` owns `xyg.intent/v1` authoring documents and their
pure, native-free validation. A host resolves `result` and optional `base` local
references within its own project boundary. It passes original Arrow IPC to
GraphForge compositions, or explicitly bound columns to XYG chart/geographic
builders. Documents contain no scenes, buffers, renderer switches, callbacks,
credentials, remote providers, inferred joins, or computed layout positions.

The common fields are `format`, `name`, `kind`, `result`, and an explicit
`filters` array. Each filter names `column`, `operator` (`equals` or `contains`)
and `value`. The kinds are:

- `result-graph`: `graph.layout` (`cose`, `force`, `circle`, `grid`) and bounded
  `graph.iterations`. Optional analytical `intent` and `base` use the existing
  GraphForge composition API. Hosts must preserve generation identities and
  let Rust reject stale joins. Graph filtering belongs in the source query.
- `chart`: `chart.mark` (`scatter`, `line`, `bar`, `histogram`), `x`, optional
  `y` (required except for histograms) and optional `color` series field.
- `geospatial`: explicit longitude/latitude fields, optional paired target
  fields, source CRS 4326, projection 3857, center longitude/latitude and zoom.
  Hosts frame typed geographic source planes; Rust owns projection and geometry.
- `temporal`: explicit `timestamp` and `value` fields, optional `series`, UTC
  timezone, and `line`, `bar`, or `scatter` mark. Timestamps require an explicit
  offset; no host invents a timezone or an aggregation interval.

`isVisualizationIntent(value)` validates untrusted documents.
`createGraphForgeIntent({name,result,...})` records the ordinary explicit CoSE
request. These APIs only author and validate intent: the existing Rust APIs
remain the composition, layout, encoding and export authority. Invalid or
obsolete documents fail without conversion or alternate-renderer fallback.

Validation proof is `node --test packages/xy-node/test/intent.test.mjs`.
