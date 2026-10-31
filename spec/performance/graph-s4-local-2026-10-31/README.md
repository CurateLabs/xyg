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
