# Exact single-color interpolation, 2026-11-12

Parent: `e9ba6331b5ce284f3c527bfdc9a3e06086760844`. This bounded
continuation bypasses redundant interpolation for a one-stop colormap and
non-NaN scalar. Rust returns the authored RGB bytes and supplied alpha directly.
The general path remains authoritative for NaN, empty and multi-stop palettes.
In particular, NaN retains its previous zero-RGB/caller-alpha result. Clamping,
normalization, blend, density orientation, wire packets, budgets, compiler
configuration, ABI405 and WASM38 are unchanged.

The new Rust regression exercises 23,040 color/alpha/scalar combinations,
including signed zero, subnormals, infinities and three NaNs. Extracting the
actual function and regression into a std-only control passes; deleting the
NaN guard fails. The complete workspace reports 2,076 passing tests. Expanded
colormap/ABI/density/range-paint checks pass on Python 3.11 and 3.12; complete
native/shipping-WASM fixtures preserve their bytes. `checks.json` binds the
commands, logs, source inputs, historical evidence and runtime artifacts.

## Paired full-pipeline CodSpeed evidence

Only CodSpeed CLI walltime runs supply performance numbers. All four runs use
the original four benchmark IDs and measured calls, the same materialized
100M-row source, five 100-by-100 views, 346 active cells, explicit 256 MiB
session budget, shipping client, SwiftShader and `gl.finish`. Setup/index build
is excluded. Indexed serving reports tier 3 and zero canonical query-row reads.
The 6.4 GB source fits available RAM; this is not a beyond-RAM result.

| Run | Native | Full update best | CodSpeed comparison |
| --- | --- | --- | --- |
| `6af54b49bb61ce4a2e103902` | parent 1 | 30.88 ms | No Change against earlier baseline |
| `6af54b8cbb61ce4a2e10390e` | candidate 1 | 24.20 ms | Improvement, +27.6% throughput against parent 1 |
| `6af54bcebb61ce4a2e103918` | parent 2 | 30.54 ms | No Change against parent 1 |
| `6af54c12eaa685ef877f8ed9` | candidate 2 | 23.26 ms | Improvement, +31.3% throughput against parent 2 |

Query and density rows are **No Change** in both paired candidate comparisons.
The first candidate cached row is Improvement (8.21 to 7.02 ms); the second is
No Change (7.68 to 7.74 ms). Cached serving executes no native kernel, so that
first improvement is not attributed to this Rust change. All rows, including
the parent controls, remain in the archived comparisons. These best values do
not qualify 50 FPS, p95, hardware rendering, competitor leadership or arbitrary
pointer-endpoint indexed serving. All four runs report an environment-metadata
write failure; lost profile samples are respectively 164, 2, 123 and 0.

The setup-only Python hook redirects the original host driver to a private
copy to select parent/candidate native libraries. It preserves benchmark IDs,
operation bodies and data. That private copy records the actual explicit native
path/digest using `??`; the production metadata correction uses `||`. Every
measured override is a nonempty absolute path, so both choose the same artifact.
The metadata correction is outside the measured operation. The normal shipping
build profile is identical for both native variants. Frozen measurement input
hashes and complete CodSpeed raw profiles/results are archived.

Reproduction (substitute the archived inputs at the paths recorded in
`measurement-inputs.json`; keep its private setup hook on `PYTHONPATH`):

```bash
XYG_NATIVE_LIB=/absolute/verified/variant.so \
XYG_FILTER_NATIVE_COMPARE=1 TMPDIR=/var/tmp \
codspeed run -m walltime --repository CurateLabs/xyg --base PARENT_RUN \
  --profile-folder /absolute/result-profile -- \
  uv run --no-sync pytest -p native_redirect \
  benchmarks/test_codspeed_filter_dashboard.py -q --codspeed \
  --codspeed-warmup-time=1 --codspeed-max-time=8 --codspeed-max-rounds=100
```

The archived `measure.py` records the full environment and ordered ABBA commands.
CodSpeed MCP comparison tools were unavailable in this session; the retained
CLI comparisons and raw CodSpeed profiles are the measurement evidence.

## Investigation boundaries

A fresh symbol-bearing diagnostic native profile identified single-stop
interpolation among the density/update hot functions. Its build has a different
feature union/layout from shipping. An attempted address mapping to the shipping
binary failed and is retained; only fresh diagnostic samples are resolved with
that exact diagnostic symbol table. Its timing is not shipping optimization
evidence. `analysis.json` counts samples inside CodSpeed rounds, not walltime
shares. The selected function body is source-identical across those builds.

A separate private JavaScript count-copy experiment passed its correctness and
Worker controls but all four full-pipeline CodSpeed rows were No Change
(`6af547542ccb8b093378a964`). It was rejected and production decoder bytes remain
unchanged. A separate trusted pointer probe establishes that arbitrary brush
endpoints still use the exact fallback; author-aligned benchmark ranges do not
establish general row-independent pointer serving. Failed fixture/setup attempts
remain archived and receive no qualification credit.

## Shipping identities and remaining acceptance

The rebuilt single shipping module measures **1,875,559 raw / 785,836 Node22
gzip6 bytes**, leaving **596 gzip bytes** under unchanged caps. It has 68 function
exports, zero imports and WASM38. Native ABI405 retains 551 symbols. ESM,
standalone and Worker scripts remain parent-identical; native/module/inline
module/manifest copies change as recorded. Earlier receipts are unchanged.

Performance evidence is bounded to the authored full100M fixture. Global memory,
arbitrary brush throughput, 50 FPS across five views, massive/all-host/platform,
accessibility and competitor acceptance remain open. This receipt does not
complete #112 or milestones 4–7. Final independent review, current-head hosted
checks and the required merge queue remain separate delivery requirements.
