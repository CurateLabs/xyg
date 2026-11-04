# Pointer sync with accepted controller main — 2026-11-04

Normal local merge parents:

- Approved pointer `207ebdbdaa2ec8b0360c571683eb0fa6165e02c0`.
- Actual accepted main `d6fcacfd482d425a731c5b1ebd492e32dc8a15b4`.

Worktree `/home/ubuntu/.t3/worktrees/xyg/t3-5009d7d3`, branch
`t3/graph-pointer-selection`; human author David Spencer. No root modification,
reset, rebase, force operation, cherry-pick, history discard, push, GitHub PR/
thread update, queue, issue or publication action accompanies this candidate.
No separate Rust experiment or Node1k task source/evidence is imported.

## Actual main identity and normal merge

The parent reports #1091 merged through the queue at2026-11-04T04:35:11Z as
`d6fcacfd482d425a731c5b1ebd492e32dc8a15b4`, with #1092 retargeted to main.
The child verifies the **entire accepted main tree**:
`4cde4a0ea4f24125d5c2bdafc2c1bde72cd263eb`, exactly the entire tree of already
reviewed controller `c3013b30bf97ce63b1f381a71d4ca1be38e75427`. This is local
object/tree verification; no new remote query or GitHub mutation is claimed.
The parent also reports completed independent s5a review of exact207 with69
actual journeys and m4defaults naming149+44 approval. Those parent-provided
review results establish the starting checkpoint; they do not replace new
independent review of this final sync. No absent parent review log is reconstructed.

`merge.command.json` retains actual
`git merge --no-commit --no-ff d6fcacfd482d425a731c5b1ebd492e32dc8a15b4`,
exit1. The squash history caused exactly10 conflicts:

- `js/src/63_graph_controller.ts`
- `js/src/63_graph_session_wire.ts`
- `js/test/graph-session-controller-wire.test.mjs`
- `scripts/graph_session_controller_wasm_smoke.mjs`
- `spec/api/browser-wasm.md`
- `spec/design/browser-wasm.md`
- `spec/design/graph-interaction.md`
- `spec/releases/0.6.0-api-inventory.json`
- `spec/releases/api-inventory.md`
- `tests/browser/graph_session_controller_page.mjs`

`conflict-stages.txt` retains actual stage blob IDs; `conflicts.json` binds each
raw conflict SHA256 and its losslessly compressed `*.conflicted.txt.gz` bytes.
All conflicts are first restored from the exact approved207 file. The
`pre-status-resolution.json` assertion verifies **all2799 approved nonreceipt
files**, including clean auto-merges, match207 before status changes. No parent
keyboard-only snapshot replaces the pointer source, codecs, native-coordinate
helpers, tests, naming policy or pointer contracts.

Only current status/roadmap prose then changes in graph-interaction and
browser-wasm design: #1091's base keyboard/GPU/companion attachment is now
accepted main at the actual timestamp/commit, while the independently reviewed
bounded pointer remains on the branch. #1092 main acceptance, new final sync
review and broader S5b/S6/S7/#35/#36/M4/#108 remain open. Historical property
FAIL/current6-pair PASS and #1089/#1090 main status are preserved.

The inventory is regenerated with the official generator. Only
`sourceProvenance` and `sourceSha256` differ from207; contracts, classifications,
capability metadata, naming policy and all685 preparation gaps remain exact.
The freeze remains **unaccepted**. `resolved-status-inventory.patch` is the
complete permitted nonreceipt delta against207: three files, status prose and
inventory provenance/body hashes only. `verify_sync.py` checks exact replacement
text for both prose files, rather than exempting their whole contents.

## Source, actual artifact and historical proof preservation

`before-sync.json` binds both complete parent trees, approved nonreceipt SHA256,
all301 qualified production input hashes and15 actual artifacts before merge.
`preservation.json` verifies2796 protected nonreceipt files remain byte-exact
and rejects any nonreceipt delta outside the three metadata paths. Production,
Rust/ABI/wire/Worker/GPU, build configuration, controller tests/runtime helpers,
capability source/generated matrix and precise naming guards/tests/spec remain
identical to approved207. No behavior, public API, tolerance, capacity, compiler,
profile, optimizer, package gate, arena, export or dependency change occurs.

Every historical performance file is checked against each parent's Git blob:

| Parent | Historical files preserved byte-exact |
| --- | --- |
| Approved207 pointer |9828 |
| Accepted main d6fc |9174 |
| Unique union |9828 |

Main's historical files are already a subset of the approved pointer tree.
`history-union-sha256.json` retains each actual file SHA256; its canonical
mapping digest is
`04a07e71f22db7cd6541cb25948fe89f6213cf089f1c036762e33ab16a382e5e`.
All original27/P1/motion/slot/native-input failures, failed naming audits, later
qualified proof and controller-main receipts remain immutable. Only this new
append-only sync receipt is added.

All301 production inputs and15 actual artifacts match qualified R5 bytes.
The preserved native-input receipt owns69 actual strict-CSP browser journeys,
the **fresh native-coordinate19-request/17-SelectAt** capture and complete
native/WASM/browser XYGR parity,26 wire/shipping tests,88 focused contracts and
full unfiltered strict-CSP foundation. Capture SHA256 stays
`3acfe244e7ebb0c24ee003b6a78268bc5c0ebadba8ca33c58e623d0a88fb1e16`.
Their helpers/tests/requests/replies/records remain exact. This sync reuses
proof only by exact source/artifact identity: **no fresh runtime/native/WASM/
browser build, execution or rerun claim** is made.

Actual reused binary SHA256:

| Artifact | SHA256 |
| --- | --- |
| Native core |`3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6` |
| Raw WASM |`3f53a4747010f6cfc9e7f308c73d35a81d68cd2f6ffecaafb1860aa3cf9053b0` |
| Optimized module |`6ebbdb7f7e6859ad9a08bd2c0237c62aaa6147df8c683b080959b42e7d2fb273` |

Current actual module is rehashed and Node22 gzip6 recomputed solely for
identity/size verification:1922723 raw /783181 gzip6, digest
`5ed44e4d8802ddcdfb48dbe0aded7206d8228e9f9970a868b2bb8aaec35e5d4a` for gzip.
Unchanged1878/765KiB hard gates (1923072/783360) leave349/179bytes.
ABI399/538 native symbols, WASM35/GPUv1/Scene34/painter17 remain unchanged.
Normal paired ESM/IIFE/Worker/module/inline manifests remain qualified actual
bytes; there is no diagnostic artifact substitute or fresh packaging claim.

## Fresh metadata validation and handoff

| Recorded command | Result |
| --- | --- |
| `merge` |Expected exit1/10 archived conflicts; normal merge resolved from207 |
| `inventory-write`, `inventory-check` |Official current provenance/body hashes;685 gaps unchanged |
| `capability-check` |Current official generated matrix passes, unchanged |
| `metadata-tests` |61 inventory/ownership/WASM-generator tests pass |
| `naming-tests` |Full149 naming tests pass, unfiltered |
| `naming-whole-repository` |Standalone whole-repository naming audit passes |
| `ownership` |508 tracked production files classified; pass |
| `native-declarations` |ABI399/538 symbols current |
| `wasm-declarations`, `typecheck` |WASM declarations/Python typing pass |
| `preservation` |Exact source/artifact/history/prose-whitelist proof passes |
| `hooks`, `ruff-check`, `ruff-format` |Mandatory full-worktree checks pass before commit |

Every command record includes exact argv/cwd/environment/timing/exit plus raw
combined/stdout/stderr hashes. `proof-inputs.json` binds final source/check
records and nonreceipt binary full-index diff hashes against both actual main
d6fc and approved207. The committed handoff also returns whole binary full-index
hashes against both parents. No receipt claims a self-referential whole hash.

Reproduce metadata checks with Node22 at
`/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin`
on PATH and exact recorded argv. Use fresh output labels/paths for repeats:

```bash
uv run python scripts/check_release_inventory.py
uv run python scripts/gen_capability_matrix.py --check
uv run pytest -q tests/test_release_inventory.py tests/test_verify_ownership.py tests/test_gen_wasm_abi.py
uv run pytest -q tests/test_stale_names.py
uv run python scripts/check_stale_names.py
uv run python scripts/verify_ownership.py
uv run python scripts/gen_abi_manifest.py --check
uv run python scripts/gen_wasm_abi.py --check
uv run ty check python
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The pointer contract remains native reported browser precision, strict public
effective zoom1, conservative inspectable-transform guards and exact Rust
selection identity. The historical Chromium156/software/small-fixture evidence
establishes no cross-browser/subpixel/scale/competitor win. SelectionTooLarge
remains a labelled pre-execution seam; the actual10001-source fixture reaches
initialization Budget. No hover/picked-target/gesture/public-host/broad S5b/S6/S7,
#35/#36/M4/#108, freeze or publication acceptance is added. Parent new independent
final sync review and pre-push hooks remain required before any root integration
or push to existing#1092; child performs neither.
