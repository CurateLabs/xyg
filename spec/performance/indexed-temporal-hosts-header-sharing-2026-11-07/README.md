# Indexed mounted temporal hosts and bounded WASM header sharing

This follow-up starts from source checkpoint `1b26d471b5e456ddc046d57de63328627486ce09`.
That exact parent received independent bounded source approval. Its module
failed both shipping caps; that review did not approve shipping or broader
milestone acceptance.

The WASM change outlines only `put32` and `put64` in the geographic source and
snapshot protocols. Their slice-copy bodies are unchanged, and the attribute
applies only to wasm32. Native O3, WASM O2/inline50, fat LTO, one codegen unit,
stripping, Binaryen132 `-O3 --all-features`, all public declarations, and runtime
and artifact caps remain unchanged. No heap allocation or product policy is added.

With the same producer inputs apart from those four attributes, optimized size
changes from 1,940,915 raw /807,541 Node22 gzip6 bytes to **1,936,761 /805,269**:
4,154 raw and 2,272 gzip bytes saved. This remains **9,593 /18,837 bytes over**
the unchanged 1,927,168 /786,432 caps. The normal package command still exits1.
The new module is an explicitly unqualified test artifact, never installed as
packaged WASM. Native host tests use a fresh matched ABI405 library and paint
client; their validity does not certify the WASM package.

Fresh header-path controls compare actual WASM with explicit matched native405:
frame leases with direct and 40k reduced data, source/original disposal, exact
full-u64 identity, picking/membership/rows, independent copy quotas, frozen
snapshots, selected state, mixed raster/vector/source tiles and hierarchy.
The hierarchy module passes all18 tests. Complete normalized replies match on
every repetition of the additional small-source ABBA fixture. Its medians were
0.2010 /0.1826ms after warmup, with visible sample dispersion on this shared VM.
These observations establish neither a broad latency nor a competitor win.

The broader13-reader/writer experiment saved2,251 gzip bytes; its smaller
warmup timing sample was slower. Reader-only outlining grew gzip by57 bytes.
Only the four writer attributes are retained. Earlier index-sort, fixed Scene
writer, direct PNG Vec and SVG-number experiments were rejected and restored.
The code-attribution-only extra Binaryen passes were not adopted: function
merging grew compressed size despite reducing raw code, code folding grew the
actual module, and convergence saved only673 additional gzip bytes while still
failing the cap. Names-based layout measurements concern a separate diagnostic
build and are not production qualification or an adopted optimizer setting.

The mounted indexed-host implementation, Python selected-query birth retirement,
new fixture transport controls and final source-bound host evidence are recorded
in the completed receipt alongside this file. No fixed birth-bank, source, Data,
query, timeout, pixel tolerance or readiness gate is weakened.

Full combined-module fit and runtime qualification, final independent diff
review, accepted-main freshness, hosted CI and merge queue remain required.
Snapshot indexed binding, ordinary hierarchy/overview/mixed-tile automation,
all-host exports/accessibility, large-scale/five-view/resource and competitor
acceptance remain open. This receipt does not close #39/#50/M6, #45, #110–113 or
milestones4–7.

## Native mounted indexed continuation

Python and Node mounted binders admit the exact `GeoSpatialIndex` class together
with a matching caller-supplied initial frame. They reuse the existing Rust
18/33→36→19 lane and XYGH Prepare/CAS/RetireACK. Snapshot indexed binding remains
refused. Sources and storage callbacks remain caller-owned; explicit Rust
full-scan refusal never starts a hidden canonical fallback.

Repeated selected indexed replacements exposed Python's unreleased command36
query births after successful command19. The operation now confirms and releases
that exact birth, retains uncertain retirement for exact retries, and preserves
independent caller Data. The original failure at sequence15 is retained. The new
28-replacement regression crosses it without changing the16-entry bank or any
handle/Data/session cap. Lost-confirm/release controls preserve the binding claim
until actual settlement.

Fresh final implementation checks:101 Python and58 Node tests, ordinary/selected
native browser journeys, actual Python3.11.17 Jupyter/anywidget26-update journeys,
and VS Code1.103.2/embedded Node22.17 journeys. They cover half-open time/extrema,
ordered camera/time, delayed external-page supersession, refused/failed page
reads, accepted-paint preservation, exact identity, caller leases, close/remount,
source claims and native release. Selected and ordinary notebook pixels are
34→0→34 and70→0→70. Source/renderer/artifact pins stayed unchanged during the
sealed batch. Broader existing canonical selected and32769-row aggregate cases
also pass; the canonical aggregate case additionally rejects corrupted membership.
These native-host checks do not use or qualify packaged WASM.

The remount test exposed a fixture transport bug: an aborted HTTP long-poll could
consume the successor mount's reply. The fixture clears only the identical closed
response and rejects destroyed/ended destinations before posting. A deterministic
abort/queue/successor control fails on the old harness and passes after correction;
actual native readiness and release still follow the unchanged protocol. The
terminated90s and45s probes and earlier failed attempts retain their failure
status. Corrected capture-only notebook reruns scroll the real painter into view;
the earlier offscreen screenshots are not visual-presentation evidence.

All historical receipts remain byte-identical. The successor Core binding pins
current sources and the unchanged parent chain; the preparation API inventory
retains its explicit gaps and does not establish an exact-byte API freeze.
Independent review of this complete follow-up, matching full-module qualification,
hosted CI and merge queue remain pending. No issue or milestone closure is claimed.

## Follow-up metadata checks

Actual Python3.11.17 also passes all101 affected lifecycle/publication tests.
The ABI generators, capability matrix, ownership ledger and Python-floor checker
pass. The first root metadata command named a nonexistent test module and
collected nothing. The corrected aggregate initially passed41 tests but exposed
two unpinned files through real Git CRLF conversion. Exact LF pins for
`python/xyg/_geo_selected.py` and `tests/test_geo_indexed_host.py` repair that
metadata defect; the unchanged aggregate then passes all42 checks. Failures are
retained and receive no pass credit. The existing API preparation inventory
matches semantically, with two stale generation-time hashes explicitly reported;
it is not regenerated or described as an exact-byte freeze.

Final root gates pass: full-worktree pre-commit, Ruff check and format check,
the unchanged workflow validator and all776 `make check-ci` regression tests.
These local contract results do not qualify the over-cap shipping module or
replace final independent review and current-head hosted CI.
