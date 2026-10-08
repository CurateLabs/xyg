# Native coverage unions for explicit Scene triangles

Geographic polygon tessellation emits explicit Triangle records. Independently
antialiasing each primitive makes internal shared edges partly transparent.
Adjacent visible triangles of one source feature and identical literal fill
therefore lower to one native coverage union when stroke width is zero and no
gradient is present. Invisible feature separators and all other record kinds
terminate the union. Distinct source features retain ordered alpha compositing.

Raster display-list opcode 19 contains a little-endian u32 triangle count,
four RGBA8 bytes, and six little-endian f32 coordinates per triangle. The
processor validates complete framing, finite coordinates, a nonzero count no
greater than 65,536, and at most 64,000,000 edge/subscanline visits before
allocating triangle or coverage arrays. Work is bounded by three edges per
triangle times four subscanlines per clipped device row. Rejection returns no
successful raster result; the caller must discard a failed output buffer.

Rust normalizes each triangle's winding and evaluates all contours together
with the existing nonzero-winding scanline coverage processor. Opposite copies
of shared edges use identical arithmetic. Coverage is blended once, including
when triangles overlap. Holes remain absent geometry from the upstream bounded
tessellator. SVG uses one nonzero-winding path with independent triangle
subpaths under the same grouping policy. Stroked or gradient primitives retain
the existing per-triangle rendering path.

The native regression fixtures check every interior pixel of a two-triangle
square at opaque and half alpha, both source windings, overlapping contours,
and malformed/nonfinite/count/work rejection. Browser rendering uses the
explicit fixed-triplet primitive contract and its existing WebGL coverage.
