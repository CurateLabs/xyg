# S4 GraphSession local implementation and validation

Status at the implementation checkpoint: **native/WASM wire implemented;
shipping package gate FAIL; final parent-base validation pending**. This is not
#36, milestone 4, #108, release, browser-controller or public-host completion.
The parent owns independent final review, PR/queue actions and publication.

The original implementation base is `6a42e73be1ae75effb847c875fa3d26ff2d0a4e6`.
Parent steering subsequently requests a normal merge of
`bd57eb7c692b658d9428109103f4da47dd5eb144` before final validation. Pre-merge
command records are retained transparently; they are not final merged-source
acceptance. Historical S1/S2/S3 receipt directories remain byte unchanged.

## Implemented contract

- Shared Rust `interaction/wire.rs` validates XYGI and serializes XYGR for real
  native and WASM exports. Exact result strings cross the fixed 56-byte ref
  record; absent IDs cannot alias empty strings or local table indexes.
- All mutation, publication, semantic result construction and serialization
  occur on an admitted speculative session under one authoritative temporal
  world access. No owner state/session/cache/sequence/delivery commit occurs
  when rendering, serialization or resource admission fails.
- Complete serialized retries, zero/short/exact native capacity, nonconsuming
  short polls, source flags, same-revision style/emphasis, bounded candidates,
  companion text, focus ring, summaries and position records are implemented.
- Native handles are monotonic and never reused, with at most 256 sessions and
  no global registry lock during bound work. Lock order is session -> temporal
  operation -> temporal state. Existing native temporal accesses follow it.
- WASM has one session per instance and a directly locked disposable temporal
  owner. Replacement/disposal/geographic acquisition revokes old ownership;
  an Arc never extends usable graph lifetime. Retained state, replies, staging
  and temporary work participate in conservative admission before mutation.
- Native ABI 397 / 537 symbols and WASM ABI 35 / 65 function exports are
  generated/current. Scene 34 and painter 17 are unchanged. The browser encoder
  has the missing DT.u32 branch; its actual module is tested against Node bytes.

Routine representation/status/pagination/retry decisions are normative in
[graph interaction §3](../../design/graph-interaction.md#3-abi--wasm).
The typed S1–S3 distinction between Some("") and None is preserved. Transport
identifier grammar rejects empty Some IDs; a typed-successful replacement that
cannot serialize is tested to leave the live wire session fully unchanged.
No S5 DOM/controller/ARIA/painter, S6 public wrappers, or S7 scale work is added.
This internal ABI slice introduces no new chart family or competitor speed lead;
existing chart capability/visual matrices and benchmark claims are unchanged.

## Evidence and reproduction

`*.command.json` contains exact argv, exit, elapsed validation wall time and
raw/compressed-log SHA256. New commands use `run.py`, which refuses duplicate
names and retains both `.txt` and deterministic `.txt.gz` logs. Exploratory
failures remain visible: early compile/test drafts, a stale-release diagnostic
comparison, and the temporary typed empty-ID regression were corrected and
rerun without relaxing assertions or historical goldens.

The pre-merge complete workspace and Clippy pass. The original geo transport
regression caught a missing staging clear in the new compatible temporal
adapter; the fix restores the old contract and its focused proof passes.
Fresh packaging still fails the unchanged 1,513/626-KiB gates. No budget,
profile, optimizer, dependency, toolchain, or export stripping is authorized or
performed to make it pass. `diagnostic_assets.mjs` materializes only a separate
`target/task-tmp/s4-diagnostic-assets` root; it retains thresholds and all
signature/import/version/worker checks, logs failed size gates, and never
publishes the product dist/static assets. Any functional use of those bytes is
explicitly diagnostic and cannot establish shipping acceptance.

Final artifact measurements, environment/source bindings, merged-base validation,
original full strict-CSP report and six PNGs will be appended after the normal
parent merge. Uncommitted proof uses `artifactCommit: null`.

## Final merged-source handoff

**Implementation and functional verification pass; shipping packaging remains
FAIL.** Checkpoint `b78bd804` contains the S4 implementation. Normal merge
`dfd1cac8cd1c39cb7010245b43b869db9f76605d` integrates the explicitly requested
parent `bd57eb7c692b658d9428109103f4da47dd5eb144`, preserving its approved
aggregate paint predicate (`output.tier`) and unchanged directed fallback.
Final source also reports aggregate Group/member summaries and admits the full
20,000-ref symmetric-difference result while keeping requests capped at 10,000.
There is no rebase, force operation, remote mutation, or publication.

Final evidence is `handoff-*` plus the unchanged merged client/manifest/golden
checks, `artifact.json`, `evidence.json`, `history.json`, and
`full-csp-diagnostic.json` with its six PNGs. Proof ran on the uncommitted final
source over the normal merge; **artifactCommit remains null** after commit.
`capture.py` binds exact changed source/spec/test hashes against the original
base, the integrated parent/merge, environment, native library, compiler module
and optimized diagnostic module. Receipt files are excluded from that source
inventory to avoid self-reference. Logs retain their original whitespace and
terminal escapes; the production/spec diff outside receipts is whitespace-clean.

| Validation | Final result |
|---|---|
| Complete Rust workspace, all tests serially | 1,937 unit/integration tests passed; 0 ignored (67 core, 1,793 engine, 72 WASM, 5 integration) |
| Graph interaction | 112 tests, including 9 shared-wire cases and the parent's 2 aggregate regressions |
| Native session seam | 9 tests, including 256-entry limit, stale/raced disposal, capacity/poll and temporal advancement |
| WASM session/temporal ownership | 2 session and 5 owner tests, plus existing temporal/geo regressions |
| Full workspace/all-target Clippy | passed with `-D warnings` |
| Native rebuild / real wasm32 build | passed |
| Focused Python actual-native seams | 185 passed, 4 browser tests deliberately deselected |
| Node actual-native regressions | 105 passed, none skipped |
| Actual native ABI / optimized real-WASM session bytes | 3 passed, none skipped; shared operations, exact IDs under different string-table indexes, malformed container/refs, capacity retries, same-revision emphasis, 20,000-ref result and real temporal bind/frame/replacement/disposal |
| Diagnostic WASM composition/CoSE/cross-host/force lifecycle | 51 passed, none skipped |
| Generated ABI/parity | 537 native symbols, v397; WASM manifest/declarations v35 current |
| ABI smoke | 673 checks passed |
| Client typecheck/shader/bundle + real browser u32 encoder | passed |
| Semantic/cross-host goldens | passed; historical fixtures unchanged |
| Non-NumPy render/append smokes | passed with explicit Chromium 156 |
| Original full strict-CSP foundation | passed on explicit diagnostic staging; actual report + six PNGs, artifactCommit null |
| Python type check / release inventory | passed; inventory is preparation only, not a release freeze |
| Historical receipts / build protections | 623 S1/S2/S3 files byte-equal to their accepted commits; compiler/profile/dependency/optimizer/gate inputs unchanged |

The first diagnostic Node staging used a source symlink, which defeated the
unchanged lifecycle test loader's exact parent-URL match (16 failures). Copying
byte-identical source files into the diagnostic root restores the real staged
path contract; all 51 pass with the original assertions. No product lifecycle
code or tests were weakened. Earlier failures remain in their original records.

### Package blocker and exact bytes

The real producer is `handoff-package-gate` (`npm run build:wasm`, actual Node
22.23.4): **exit 1**. It refuses the artifact before publishing any shipping
assets; the source checkout's paired shipping verifier consequently fails for
missing WASM assets. Diagnostic paired assets verify, but that is self-consistency
proof only, not shipping acceptance or a gate waiver.

- Optimized module: **1,852,594 raw / 755,339 gzip6 bytes**.
- SHA256: `ed4b5c9a0da268c0da1519d2f4bc0a4d8fae5b87351672d477662bb0884c598f`.
- Gzip6 SHA256: `53ae3b3e141f49749661358003bb0fcf503be4df1985dbfea935cbd14aa27cf9`.
- Existing gates: **1,549,312 / 641,024 bytes**; excess **303,282 / 114,315**.
- Accepted S3 baseline: **1,548,390 / 640,709**; increase **304,204 / 114,630**.
- Exactly 65 manifest function exports, no ambient imports, ABI/Scene/painter
  **35/34/17**; all producer signature/version/worker validation retained.
- Fresh native SHA256:
  `c4e5cb10351366e5037e1db934464d03ab1a5302e3bc33e5791dd7b64e662841`.

Parent action: independently review the complete final S4 diff and decide the
package-size policy or authorize further source work. No limit increase is
assumed. The parent retains PR/queue, CI, issue-closure and publication decisions.
No timing, competitor-speed, hardware, #36, M4 or #108 completion is claimed.

To reproduce, use each exact command vector in its `.command.json` with
`uv run python spec/performance/graph-s4-local-2026-10-31/run.py NEW-NAME COMMAND ...`.
Use a fresh receipt directory/name; the runner refuses to overwrite records.
The diagnostic materializer operates only under `target/task-tmp`; its normal
stdout inherits the producer's word “packaged” but every such path and both
failed-gate diagnostics explicitly identify the nonshipping staging root.

Final byte replay is recorded in `final-session-owner-byte-parity`: it also calls the
native bind export, advances both real temporal engines, rejects stale commands,
refreshes the bound world, rejects another WASM instance borrowing the owner,
and proves replacement/disposal invalidates the old binding before unbind recovery.
