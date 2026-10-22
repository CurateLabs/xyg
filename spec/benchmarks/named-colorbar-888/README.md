# Named-colorbar finite-domain comparison (#888)

This correctness probe compares XYG's Rust-owned named-colorbar Scene route
with released Matplotlib 3.11.0 `Normalize` and a real `ScalarMappable` colorbar.
It completes the comparison/environment obligation left by [#1048](https://github.com/CurateLabs/xyg/pull/1048).
The adjacent-domain choice remains **fail closed + document**, using XYCB v2;
there is no fraction-space wire extension.

## Results and capability boundary

| Authored domain | XYG canonical Scene + SVG + decoded PNG | Matplotlib 3.11.0 normalization | Matplotlib colorbar + SVG/PNG |
|---|---|---|---|
| `[0, 1]` | Exports all 11 named palette stops with exact endpoints | Endpoints map to `[0, 1]` | Exports, domain unchanged |
| `[0, 1.7e308]` | Exports the same complete palette and exact endpoints | Endpoints map to `[0, 1]` | Fails with `OverflowError: cannot convert float infinity to integer` |
| `[-1.7e308, 1.7e308]` | Exports the same complete palette and exact endpoints | Endpoints map to `[0, NaN]`, with overflow/invalid warnings | Fails with `ValueError: Axis limits cannot be NaN or Inf` |
| `[1, nextafter(1, +inf)]` | Rejects with `XYG_SCENE_UNSUPPORTED_COLORBAR` | Endpoints map to `[0, 1]` | Exports after changing the domain to `[0.9, 1.1000000000000003]` |
| `[2, 1]` (reversed-invalid) | Rejects with `XYG_SCENE_UNSUPPORTED_COLORBAR` | Rejects with `ValueError: minvalue must be less than or equal to maxvalue` | Exports after changing the domain to `[0.9, 2]` |

The two Matplotlib stages use independent fresh `Normalize` instances, so
colorbar mutation cannot conceal the scalar-normalization outcome. Successful
Matplotlib colorbars are exported through both SVG and Agg PNG at 320×240.
XYG exports a 320×240 scatter Scene with named `viridis` chrome; Matplotlib
uses a standalone colorbar on explicitly positioned axes. These are behavior
witnesses, not equal-layout or equal-pixel comparisons. XYG retains its existing
11-sample named palette; this evidence does not claim that its table is identical
to Matplotlib's 256-entry `viridis`. It does prove that the palette is unchanged
between admitted XYG domains, with strictly increasing stop values and bit-exact
finite endpoints. This probe uses ordinary Scene literal-band semantics, not
StaticDocument's separate 64-band pyplot interpolation override: its 11 canonical
XYCB stops require exactly 10 rendered intervals, each painted with its lower
stop's RGBA. The SVG band count and every paint must match those canonical stops
before the decoded PNG center pixels are checked against the same canonical
RGBA values. Tests corrupt real exported SVG/PNG pairs by omitting a band or
repainting every band one color; both renderers still agree at the remaining
band centers, but the canonical checks reject each pair.

This is a numeric correctness boundary, independent of source row count.
It makes no startup, timing, memory, interaction, or massive-data performance
claim. No conclusions about other plotting libraries or other Matplotlib
versions follow from this probe.

## Reproduce

Use CPython 3.12.15 and the exact dependency versions in
[`results.json`](results.json) to reproduce this environment. The report also
records the OS/architecture, source commit, probe hash, native-library hash,
ABI version, backend, exact input/output f64 hex values, errors, warnings,
canonical palette values/paints, SVG band geometry, artifact hashes, and decoded
RGBA pixel hashes. `NaN` is stored as the string `nan`, never an invalid JSON
number. The captured source commit is the product baseline; the separately
hashed probe is added by this evidence change.

From the repository root:

```bash
PATH="$HOME/.cargo/bin:$PATH" cargo build --release
XYG_SKIP_CARGO=1 XYG_SKIP_NODE=1 uv sync --group dev
uv pip install matplotlib==3.11.0 numpy==2.5.1 pillow==12.3.0 \
  contourpy==1.4.0 cycler==0.12.1 fonttools==4.67.0 kiwisolver==1.5.1 \
  packaging==26.3 pyparsing==3.3.3 python-dateutil==3.0.0 six==1.17.0 tzdata==2026.5
uv run --no-sync python scripts/compare_named_colorbar_domains.py --output /tmp/colorbar-888
uv run --no-sync pytest tests/test_scene_ir.py -k named_colorbar -q
uv run --no-sync pytest tests/test_named_colorbar_comparison.py -q
```

Compare semantic fields and decoded pixel hashes with the committed report.
Native binary hashes can differ with toolchains; OS/font differences can change
image bytes. The probe fixes Matplotlib's SVG hash salt and removes its SVG
timestamp; it strips trailing SVG line whitespace while recording both original
and retained byte hashes. Successful output artifacts are retained beside this report for
inspection; failed paths have exact errors and warnings instead of invented
output. Existing Node witnesses remain in
`packages/xy-node/test/scene.test.mjs` (the named-colorbar #888 case); #1048
already supplied the cross-host canonical/SVG/raster acceptance coverage.
