# Stored formats, rebuilds, and migration for 0.6 preparation

This inventory distinguishes source data from caches and portable output. It
describes implemented readers; it does not freeze an unaccepted release or
provide a universal converter. The final #108 ledger must retain the accepted
reader versions, source identity, toolchains, and exact artifacts. The
[compatibility policy](compatibility-policy.md) governs public API changes.

## Retain the source of truth

| Data or format | Current reader and lifetime | Migration or rebuild path |
| --- | --- | --- |
| Canonical user columns, including disk-backed f64 data | Original source values and row identities are authoritative. Raw f64 files have no self-describing version/endianness header. | Retain the original source, schema, dtype/byte order, row identity, and ingest parameters. Reopen through the matching input API; never recover canonical precision from f32 GPU or spatial caches. |
| Ordered chunked columns, `XYGC` | Rust reads versions 1 and 2; the Rust writer emits 2. Version 2 adds the bounded overview. Python/Node `ChunkedColumns` retain explicit close ownership. | Keep the source artifact. Version 1 remains readable; an overview request cannot fabricate absent v2 overview data. For a rejected version, export/re-ingest canonical f64 columns using the producing reader and rebuild with Rust's `ChunkedColumns::create`. No Python/Node writer or standalone general conversion command exists; the public ingest/migration path remains part of #110. Never rewrite a header in place. |
| Retained geographic chunks/manifests, `XYGK` / `XYGI` | Version 1, under the [source contract](../design/geo-retained-source.md). A manifest becomes trusted only after canonical chunk authentication and summary recomputation. | Preserve the exact manifest, chunks, source generation, IDs, CRS, intervals, and scalar values. Rebuild a new manifest from validated canonical chunks; changing a summary or digest does not establish authority. Reject unsupported versions before pruning or querying. |
| Durable view-state JSON | `v: 1`, finite ranges and geometric selection, with strict unknown-key/axis rejection. [View state](../design/view-state.md) defines merge-patch behavior. | Restore through public state APIs on an equivalent authored chart. Preserve axis IDs and source/selection meaning. Arbitrary row selections and hover are not serialized snapshots. A future state version requires an explicit reader/migration; do not drop unknown fields silently. |
| Geographic frozen snapshot, `XYGX` | Envelope 2 ordinary, 3 selected-only, and 4 overview-only; all require the current Scene version. See [frozen export](../design/geo-frozen-export.md), [selected](../design/geo-selected-snapshot.md), and [overview](../design/geo-overview-painter-snapshot.md) contracts. | Keep the exported image/document and its exact companion snapshot. A snapshot preserves a frozen view, not a live source/query capability. If the embedded Scene is rejected, use the matching producing package to export it, or rebuild from canonical source and recorded camera/time/style/selection using the newer package. There is no general cross-Scene binary converter. |
| PNG, SVG, PDF, JPEG, WebP and self-contained HTML | User output, with format-specific contracts in [export](../api/export.md). Geographic exports may carry companion provenance. | Keep originals. Static output is not canonical chart data. Regenerate from original authoring inputs for new behavior. HTML embeds its producer client; update by re-exporting the chart rather than swapping one embedded JS/WASM file. |
| External Arrow/GraphForge IPC | External canonical input, validated by the owning reader. GraphForge result versions and exact qualified Core releases are declared separately. | Keep original IPC and its metadata. Use a declared-compatible Core/XYG pair or upgrade/re-export with the producer. Reject an unsupported result schema; do not rename metadata to bypass dispatch. |

The XYGC reader/writer authority is
[`chunked_columns.rs`](../../crates/xyg-engine/src/chunked_columns.rs).
Geographic snapshot admission is in
[`geo_snapshot.rs`](../../crates/xyg-engine/src/geo_snapshot.rs).
Public wrapper names and signatures belong to the [API inventory](api-inventory.md).

## Rebuildable and process-local state

| State | Compatibility and recovery |
| --- | --- |
| Native library and generated bindings | Match the generated C ABI exactly; reinstall all packages from one accepted cohort after a mismatch. Do not copy a library from an unrelated checkout into a published package. |
| Scene, XYPB painter, live wire, XYAG/XYAO and other packed request/reply records | Internal producer/consumer contracts, not durable chart interchange. Use the exact supported versions in the generated manifests and owning spec; regenerate from canonical authoring inputs after rejection. |
| Density pyramids, disk-spill `XYTS`, zone maps and derived spatial indices | Derived caches. Spill `XYTS` is native-endian process-scoped storage and is distinct from canonical typed-ingress framing also named `XYTS`. Free/close owners and rebuild from original f64 inputs. Preserve source files; delete only cache files identified by their owning implementation after all readers close. |
| Geographic spatial/hierarchy/overview pages | Derived from authenticated source chunks. Preserve immutable pages while any live root/result owns them; new pages or imported checksums alone do not confer trusted authority. Rebuild via the validated source and its existing build session when incompatible. |
| GPU resources, WASM arenas, LOD buffers, handles, registry tokens, workers and transport recovery receipts | Process/session-local. Never serialize these as user data or reuse a handle in another process. Dispose through the owning API and reconstruct from canonical data. Context recovery rebuilds caches and preserves canonical selection/identity under the owning contract. |

No automatic cache deletion is part of publication. Caches are replaceable;
source data, exports, source manifests, and historical release archives are
not. Unsupported or corrupt input must retain the prior valid view and the
documented failure where that contract requires it, rather than replacing it
with guessed data.

## Upgrade and rollback procedure

1. Record the installed Python/npm versions, qualified Core version, exact
   archive hashes, runtime/platform, input schema, and current durable outputs.
   Keep canonical source and authored chart configuration outside the upgrade.
2. Install the complete new cohort into an isolated environment/application.
   For a candidate, pin the exact Python spelling and every npm cohort member;
   do not infer availability from matching release suffixes. Use the final
   release ledger to compare downloaded archive hashes before execution.
3. Reopen canonical inputs through supported readers, rebuild derived state,
   and run the relevant host, numeric/visual, lifecycle, accessibility, and
   unsupported-input fixtures. Restore view state only through its public API.
   Keep the old environment and originals until these checks pass.
4. Switch the application to the verified environment. Stop and retain the
   old environment if an unsupported durable format has no validated migration
   or reconstruction path. Never overwrite the only copy of an input artifact.
5. For rollback, stop clients/workers, close native owners, restore the prior
   pinned complete environment and its qualified Core pair, and reopen original
   inputs. Newer caches are rebuilt. Data written only in a new unsupported
   canonical format requires an explicit conversion through its producing
   reader; installing an older package does not convert it.

Supported packages use `xyg` and scoped `@curatelabs/xyg*` names.
The removed `reflex_xy` namespace and `xyg[reflex]` extra have no compatibility
shim; migrate to the [supported application consumers](../design/application-consumers.md). There is no legacy `xy` import or `@xy/node`
compatibility alias. Port authoring code to the documented composition API;
the internal `Figure` object is not the public chart-building surface.
The corpus-defined `xyg.pyplot` shim has its own
[compatibility matrix](../matplotlib/compat-matrix.md); it does not promise
arbitrary Matplotlib or Plotly compatibility.

For code that built or imported a `Figure` directly, move authoring into the
public chart container and mark. Export from the returned `Chart`:

```python
from pathlib import Path
import xyg

chart = xyg.scatter_chart(
    xyg.scatter(x=[0.0, 1.0, 2.0], y=[2.0, 0.0, 1.0], color="#2563eb"),
    xyg.x_axis(label="x"), xyg.y_axis(label="y"), width=480, height=320,
)
Path("chart.svg").write_text(chart.to_svg(), encoding="utf-8")
Path("chart.png").write_bytes(chart.to_png())
Path("chart.html").write_text(chart.to_html(), encoding="utf-8")
```

This example was exercised with the installed CI wheel
`0.0.1.dev2875+cbf2c0eb` from source `cbf2c0eb` on Python 3.12, producing
native SVG/PNG and self-contained HTML. That development wheel is integration
evidence, not a version to install from PyPI or final candidate acceptance.

This procedure does not mark missing migrations complete. The final freeze
must list every additional persisted format discovered by the source inventory,
its accepted reader versions and reconstruction path, and fail acceptance for
an unsupported user-owned format without an explicit disposition.
