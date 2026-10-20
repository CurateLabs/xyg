# StaticDocument colorbar style policy

M2 #873 adds opt-in static colorbar scale, endpoint-extension, and pyplot label
facts to XYST. The canonical Scene/XYCB wire is unchanged; ordinary Scene and
public Figure output retain the existing label position and linear-tick policy
unless the document explicitly requests an override. Numeric flag assignments
live in the XYST contract and the shared static-export support registry.

`SceneDocument::apply_static_colorbar_style(log_scale, extend, pyplot_label)`
validates the colorbar and installs these document-only facts. An override
without a colorbar fails. Extension bits are min=1 and max=2; other bits fail.
A logarithmic colorbar requires a strictly positive domain and authored major
values. These are native product decisions, not host-side transformations.

## Scale and tick positions

Absent majors select the existing Rust `log_ticks` algorithm for logarithmic
scales, or `linear_ticks` otherwise. The target remains the bounded Scene
colorbar target derived from axis length. Labels use the same native log/linear
formatter. Optional log minors subdivide each adjacent major interval into
five equal logarithmic intervals, rather than five equal data intervals.
The pyplot label override formats authored major values with shortest
round-trip decimal labels (scientific notation at magnitudes below `1e-4` or
at least `1e6`), preserving precision independently of the tick interval.
Ordinary Scene and automatic labels retain the existing formatter.
Automatic log candidates are filtered to the strict closed domain after tick
selection: the tick algorithm's inclusion tolerance must not place a label
outside a very narrow bar. Authored out-of-domain ticks remain invalid.
Log minors use relative `ln_1p`/`exp_m1` interpolation where finite, with a
difference-of-log fallback for extreme ratios. Rounding is bounded to adjacent
major endpoints; endpoint-collapsed or duplicate minor values are omitted when
the domain has too few representable interior values.

Log positions normalize `log(value / low) / log(high / low)`, evaluated with
`ln_1p` on relative differences where finite and a difference-of-log fallback
for extreme ratios. Domain endpoints pin to exactly zero and one. Every
returned label position must be finite before a renderer consumes it.

XYCB v2 still stores stop positions in data space. Named-colorbar packing for
adjacent-representable or extreme finite domains can therefore fail before the
renderer receives a valid Scene; it must not approximate or discard palette
stops. [Issue #888](https://github.com/CurateLabs/xyg/issues/888) tracks the
versioned fraction-space XYCB contract and every downstream consumer update.

The band table continues to describe normalized palette samples: its positions
remain linear fractions of the authored domain even when tick placement is
logarithmic. This matches the former pyplot named-colorbar convention in which
the palette ramp is uniform in normalized color space and tick positions follow
the selected normalization. For the pyplot static convention, Rust linearly
interpolates those samples into exactly 64 paint bands, including ties-to-even
RGBA rounding. SVG and raster consume the same resolved bands. Ordinary Scene
colorbars without the pyplot override retain literal authored-band semantics.

## Discrete bands

XYST v4 (#1035) adds panel flag 25 for matplotlib's discrete colorbars
(`BoundaryNorm` image/mesh colorbars and banded contour fills). It requires the
pyplot label bit (13) and a Scene colorbar. The canonical XYCB stops are the
band edges: `stops[i]` opens band `i` and paints it with `stops[i].1` (the last
stop only closes the final band), so the bar is the literal Scene stops with
no 64-band interpolation. The Scene contract bounds this to 16 stops, i.e. at
most 15 bands; pyplot reports the existing `XYG_SCENE_UNSUPPORTED_COLORBAR`
admission reason beyond that.

The flag's blob is `u32` flags (bit 0 uniform spacing, bit 1 an under-cap
RGBA8 follows, bit 2 an over-cap RGBA8 follows; other bits rejected), `u32`
label count, the present cap paints (under, then over), then each label as
`u32` byte length plus UTF-8. Panels consume the region sequentially; NUL and
invalid UTF-8 are rejected. It adds three facts:

- **Cap paints.** Each extended end (XYST extend bits min/max) carries exactly
  its own paint, matplotlib's colormap under/over color; the extension triangle
  uses it instead of the first/last stop. A paint without its extension, or an
  extension without its paint, fails closed in
  `apply_static_colorbar_discrete`, so a discrete bar can never paint a cap with
  an interior band color.

- **Spacing.** `1` is matplotlib's default `spacing="uniform"`: every band is
  an equal share of the bar and a value maps piecewise-linearly inside its
  band (`uniform_discrete_fraction`, shared by the bands and the tick
  positions, so SVG and raster agree). `0` is `"proportional"`: bands span
  their literal value interval, the ordinary linear layout.
- **Tick labels.** Zero labels keep Rust's authored-tick labels; otherwise
  exactly one label (at most 32 bytes) per authored major tick, drawn
  verbatim. This carries `colorbar(format=...)` on a banded bar without a host
  formatting pass over Rust's layout. pyplot keeps the formatter and
  re-evaluates it against the live ticks at each chart build, so labels never
  outlive a `set_ticks()`.

`apply_static_colorbar_discrete` fails closed (decoder `XYG_STATIC_DOCUMENT_PANEL`)
for a logarithmic scale, minor ticks, fewer than two stops, or authored labels
without authored ticks or of the wrong count. pyplot admits `band_colors`,
`boundaries`, `spacing` and `tick_labels` on the panel colorbar and marshals
them as literal Scene stops plus this blob; `tick_labels` without bands (a
formatted continuous ramp) stays rejected with the stable
`XYG_STATIC_UNSUPPORTED_PANEL_COLORBAR_TICK_LABELS` reason because the named
ramp has no literal bands to label. A discrete colormap without `BoundaryNorm`
boundaries (`get_cmap(name, n)`) still renders the continuous ramp, which is the
pre-existing behavior this change does not widen.

## Extensions and labels

Endpoint extension triangles use the first/last stop's literal RGBA paint.
Their depth is nine logical pixels. For a vertical colorbar, max extends above
the bar and min below; for a horizontal colorbar, max extends right and min
left. The same resolved three-point polygons feed SVG and raster commands.

With the pyplot label convention, vertical titles are centered beside the bar
at `(x + width + 38, y + height / 2)`, rotated -90 degrees. Horizontal titles
are centered below at `(x + width / 2, y + height + 22)`. Title size is the
existing pyplot colorbar default of 10 pixels. SVG emits the explicit transform;
the raster text command uses the shared counterclockwise anchor flag. The
resolved coordinate/anchor helper is shared, not duplicated between consumers.

Without that opt-in, the existing 11-pixel Scene title stays above a vertical
bar or at its existing horizontal baseline. No browser title or tick behavior
changes through these nonserialized static overrides.

An explicit pyplot `cax` sets XYST's fill-plot bit. Rust then uses the decoded
Scene plot rectangle as the complete colorbar body instead of allocating the
ordinary right/bottom gutter. This retains the authored axes rectangle for both
SVG and raster without host-side colorbar geometry.

## Evidence

`cargo test -p xyg-engine static_colorbar` pins major/minor log positions in
both orientations, the bounded 64-band continuous ramp, extension
endpoints/colors, shared SVG/raster title coordinates and rotation, and
rejection of invalid flags/domains. XYST
cross-host cases must separately exercise the decoder and public host adapters.
Retained pyplot tests must inspect native raster commands/output rather than
requiring calls into the retired Python `_raster._Cmd` implementation.
