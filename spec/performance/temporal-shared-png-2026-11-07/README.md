# Shared retained PNG within the existing browser module

This functional continuation starts at approved `44bf73390b3d949797755d8637e3aeca0a60d7b5`
(parent `8d32c3dc5be0e6356c9bf88b3eac964a74a842df`, acquisition
`59b1c38a337925a8bad11333ed8d04aea76a03e0`). Historical receipts and producer bytes
remain unchanged. This candidate requires independent final review and later
combined-source/ABI integration by the parent. It does not close #45 or milestones4–7.

The single WASM36 module renders real retained PNG through the same Rust Scene,
raster coverage/compositor and png/fdeflate encoder as native ABI404. Python,
Node, the actual module Worker and the strict-CSP offline classic Blob Worker
share export/recovery. HTML still embeds Rust Scene/XYPB and uses the shipped
ChartView. No second painter/encoder, host raster fallback, optional module,
cap increase, geometry rebuild or new chart-building surface is introduced.

## Qualified artifacts and source

| Artifact | SHA256 / measurement |
| --- | --- |
| Native, new owned immutable pin | `1424331bd0569c3ecbab1e3e591022aa95adac0f2fce2c486e51909974cf2929` |
| Final WASM36 | `9dbd29f1d5f20ec49494a84562de6cd43096ab02ab276b95c05a8e9e77fbb646` |
| Final raw / Node22 default gzip6 | **1,886,125 / 784,655 bytes** |
| Unchanged caps | **1,927,168 / 786,432 bytes** |
| Raw / gzip6 headroom | 41,043 / 1,777 bytes |
| Approved prior module | `c99579a2f61e79cb180e92405f7ff8193464210d70304f2d0f2499babaf08a32`, 1,904,840 / 784,799 |
| Immutable prior native oracle | `ce420fd1ae0e52e19d3b3c20f359d968418d6ee87896743e35712dea7145d572` |

Native pin: `/home/ubuntu/.t3-owned/1cafa70d/png-next/qualified-native/libxyg_core.so`.
The prior `qualified-native-final` pin remains immutable. Build target is the
new owned `/home/ubuntu/.t3-owned/1cafa70d/png-next-target`; no shared temporary
native target or other producer's library is used. `native-source-fresh.log.gz`
checks the current source through Cargo and the build-target/pinned digests match.

`compiled-source-inputs.json` and `compiled-source.tar.gz` bind final Rust,
Cargo, checked-in vendor and toolchain inputs. `artifact-bindings.json` binds
those inputs to the native/module/client/capture artifacts. Full final Git
head/parents, exact changed paths and canonical binary patch digests are supplied
in the post-commit handoff. A receipt created before commit records the approved
parent as its harness commit; the input manifest and final Git export provide
the exact final source binding. No signature/authenticity claim is made.

## Reachability and representation

Retained canonical Scenes have literal marks and no text/axes/legend. The shared
Scene writer and raster dispatcher use const capability specialization, with
unexpected commands/decorations rejected before output/framebuffer allocation.
Full native Scene/text routes remain available. Every supported retained symbol,
focus band, status/epistemic layer, phased dash, head, pin and compound frame
continues through the existing primitive/SDF/alpha/order implementation.
A solid two-point butt shaft uses the existing box-coverage compositor without
materializing generic polyline/dash run vectors.

The existing png0.18.1 encoder is vendored with one generic implementation and a
restricted RGB8 writer. It fixes the exact prior Fast/Up configuration and leaves
the full writer's metadata/APNG/filter/compression options intact. Fdeflate,
its larger-than-stored fallback, IDAT framing and pixels are unchanged.

The decisive data attribution was the CRC slicing-by-16 tables: one new data
segment occupied18,578 bytes and gzip-compressed to17,844. The existing
crc32fast1.5.0 dependency now selects its existing byte-at-a-time update on
wasm32 and retains only the first256-entry IEEE table; native keeps its original
SIMD/fast/table behavior. This trades browser CRC speed for module space without
changing any PNG bytes. Original licenses and upstream source hashes are retained
with each dependency. No new encoder or compression policy is substituted.

WASM also shares standard-library stable-sort bodies per record type and
callback-independent graph transaction/instance dispatch. Native comparator and
callback specialization remains. The sorting algorithm, stable order,
allocations, lock/validation sequence and product policy remain unchanged.
The reviewed target-only O2/inline50 profile (nativeO3), Rust1.96, Node22.23.4 and
Binaryen132 `-O3 --all-features` are unchanged. Gzip9 is never used for the gate.
Final code/data section payloads are1,763,122 /116,972 bytes; the approved O2
baseline had1,789,448 /109,892. Named diagnostic traces showed font machinery
absent after explicit dispatcher guards. No prior exported capability is removed.

## Fresh qualification

- **1,859 engine unit tests** and **74 native adapter tests** passed. These include
  ordinary raster/text, shared Scene, retained PNG byte equality with the full
  renderer, unsupported decorations and malformed/capacity/resource checks.
- The native Python/static/packaging run passed265 tests with one existing xfail;
  its new offline Worker test initially exposed the missing classic dispatch.
  The corrected targeted public Worker test passed. No assertion or timeout was
  relaxed. Both complete logs are retained instead of claiming that the initial
  combined run was green.
- **207 Node tests passed**, with one unchanged skip for ordinary heatmap opacity
  (#889). Real frozen PNG succeeds at scales1/2; duplicate/truncated/empty/tampered
  carriers and resource refusals leave subsequent exports usable.
- Full normal **foundation** passed on the final module: seven actual public
  Worker freezes, scales1/2, accepted computed CSS capture, camera/DPR, selection,
  focus, pins, compound frames, all six glyphs, heads/layers/dash phase, exact
  native/WASM Scene/XYPB/SVG/HTML/PNG bytes, recovery after scrub/disposal, fixed
  independent vectors/pixels, and offline ChartView HTML. The same gate now also
  executes public PNG/import/recovery from a strict-CSP single file and Blob
  Worker, rejects pending PNG on disposal, and exports identically via a fresh
  Worker. Classic and module Workers share one thin XYFX byte-staging helper.
- **14 final-module PNGs** are byte-identical to the immutable prior native
  producer, with exact imported XYFG recovery. The final foundation also compares
  the new native producer. Diagnostic PNG byte matches alone were never used as
  proof that an over-cap probe shipped.
- **673 native ABI checks**, official ABI generators, **546-symbol ABI404 parity**,
  WASM36 export signatures/import guard, official packaging and paired/inline
  asset verification passed. No ABI signature or generated declaration changed.
- **98 Core/current/history tests** passed, including Git's actual LF→CRLF
  checkout conversion and every retained predecessor transition. The current
  binding is a successor; historical bindings/producer artifacts are unchanged.
- Full-workspace/all-target Clippy passed with warnings denied. Native acquisition
  has an explicitly documented transport-argument lint annotation; the frozen
  export definition was moved before the test module without changing its ABI.
- Ownership and normal preparation API inventory checks passed. Inventory still
  reports existing release classification gaps; strict classification was not
  claimed. Full-worktree hooks and Ruff are recorded separately before commit.

The local ABBA control used identical generated Arrow/geometry requests at100,
10,000 and100,000 rows. All14 admitted old/new outputs were byte-identical; the
100,000-row interaction resource refusal was identical. All slower cases remain
in `profile-abba.json`; ratios range0.839–1.033 on a shared VM. A second run
with21 explicit shared-VM activity samples (`profile-shared-vm.json.gz`) retains
all14 admitted byte matches and the same refusal, with ratios0.953–1.065. This is a bounded
compatibility/runtime observation, not a comparative speed win, hosted benchmark
or proof of the future combined module's fit.

## Honest failed attempts

Every diagnostic remains distinct from the shipping module. Earlier immutable
probe/history receipts retain their original scope. New measured sizes (raw /
Node22 default gzip6) include:

| Probe | Bytes | Disposition |
| --- | --- | --- |
| Explicit retained dispatcher | 2,045,148 /853,781 | over cap |
| Encoder inlining | 2,021,955 /842,627 | over cap |
| Shared fixed encoder capability | 1,985,844 /830,308 | over cap;14 PNG matches |
| Extra filter inlining | 1,986,604 /832,139 | over cap; not adopted |
| Shared typed section writer | 1,982,531 /829,119 | over cap |
| Graph/Scene stable sorts | 1,954,629 /820,715 | over cap |
| Extra policy outlining | 1,954,308 /820,752 | ineffective; removed |
| Shared solid shaft / vendor | 1,937,853 /814,247 | over cap;14 PNG matches |
| Extra reader outlining | 1,938,005 /814,351 | ineffective; removed |
| Shared kernel stable sorts | 1,919,370 /805,237 | raw passes, gzip fails |
| Shared callback dispatch | 1,902,493 /801,779 | gzip fails |
| Single CRC table | 1,885,955 /784,749 | both pass; precursor |
| Cleaned and lint-corrected final | 1,886,125 /784,655 | qualified final |

Logs preserve the initial optimizer `/tmp` quota failure and correction to the
owned short disk TMPDIR, initial mutable-reborrow compile failure, test helper
opcode omission, module-wide declaration-budget test setup failure, classic
Worker's missing dispatch, ownership ledger corrections, lint attempts, and
inventory CLI/classification checks. The Windows test caught generated LF rules
that incorrectly classified historical binary receipts as text; those rules
were removed, original `-text` attributes retained, and the actual checkout test
passed. Producer file bytes were never rewritten. Pinned upstream Cargo.lock
files matching their own ignore rules are force-tracked; the checkout test
reproduces the actual tracked set before testing filters, retaining all byte
and unpinned-control assertions.

The first dispatcher/inline/capability diagnostic artifacts lack complete
contemporaneous producer source snapshots; their raw files/logs and source
fragments remain diagnostic, with no exact-final-source qualification claim.
Later source archives/manifests are retained. The first failed offline page
was a pytest temporary file and was subsequently removed by pytest retention;
its raw failure/debug logs and the old/new classic dispatch sources remain,
but no original failed-page artifact is claimed. Files named `final-source.*` from
an earlier diagnostic helper also carry an unused EXTERNAL-PROBE tree; only
`compiled-source.*` describes the qualified final build without an external
Cargo override. The complete final Git export is authoritative for review.

## Reproduction and remaining acceptance

Use explicit candidate-native paths, Node22 and short disk TMPDIR. The exact
commands, versions, artifact/capture hashes and raw stdout+stderr are retained
in `commands.jsonl.gz`, `environment.json`, per-command logs and artifact bindings.
From the final Git export, with ordinary dependencies available:

```sh
export TMPDIR=/var/tmp/pg45-1c CARGO_BUILD_JOBS=2
export CARGO_TARGET_DIR=/path/to/new-owned-target
cargo build -p xyg-core --release --locked
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown --locked
node js/build.mjs
node js/package-wasm.mjs "$CARGO_TARGET_DIR/wasm32-unknown-unknown/release/xyg_wasm.wasm"
export XYG_NATIVE_LIB="$CARGO_TARGET_DIR/release/libxyg_core.so"
export XYG_CHROMIUM=/path/to/chromium
node scripts/wasm_foundation_smoke.mjs
uv run pytest tests/test_temporal_graph_frozen.py -q
```

The unchanged384MiB per-instance/operation ceiling, default16MiB Worker refusals,
checked export reservations and owned lifetimes remain. Global process and
caller-retained budgets remain #111. Full #45 aggregate/scale/accessibility and
whole-milestone acceptance remain open. This standalone module fit does not
certify future combined-source/ABI integration. The parent owns independent
exact-diff review, accepted-main reconciliation, PR/CI/queue and delivery.
