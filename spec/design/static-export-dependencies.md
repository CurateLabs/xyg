# Compatibility-renderer dependency retirement

M2 #873 removes imports of legacy renderer facades from production paths as
their consumers move to shared kernels. This is separate from proving that the
old rendering algorithms have been deleted; no import-only change establishes
ownership completion by itself.

`_payload_trace_materialize` constant heatmap paint now imports
`_paint.paint_rgba8` directly. Pyplot `_colors` colormap lookup and `_artists`
transformed-image colormap lookup import `_paint.colormap_lut` directly. The
former `_raster._parse_color` and `_svg._lut` names were exact aliases of these
same function objects. This changes dependency reachability, not numeric,
paint, or lookup behavior, and does not duplicate the implementation.

Remaining facade import sites must be eliminated or converted to bounded
native-query wrappers before compatibility-renderer deletion. A clean public
save path alone does not establish that the facades are unreachable from
payload construction, authoring, styling capability queries, or pyplot probes.
