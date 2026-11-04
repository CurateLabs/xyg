# Resolved axis synchronization with accepted main

Normal merge of accepted main `3c66580731dde0b10a1f18465c0d0df9e73f8862` into reviewed #1089 head `8a5922af4b33bfd67f2aefe71f613847d6fdcb08`. #1088 actually merged at `2026-11-04T00:40:06Z`; accepted tree `b9f1a546159ca949b62bb644f90e3139b58ba9fb` is exactly reviewed #1088 head `60cee1e58bc93766b954d7343b90ec19d676a8de`. #1089 has already been automatically retargeted to main. Its former 20 passing checks are historical, not fresh checks against main.

The existing bound worktree switched from `t3/fix-resolved-axis-css` to `t3/resolved-scene-consumer-20261103` only after verifying cleanliness and that the target was not checked out elsewhere. The old repair ref remains at `78b4b69f76b955ab19bd365f0492711cc3c06c1f`. The merge uses `git merge --no-commit`, with no reset, rebase, history discard, new worktree, push, PR update or queue action. Separate unmerged native property ABI399/#1090 and S5b controller work is not included.

## Resolution and preservation

The sole merge conflict was inventory provenance and the browser-spec body hash. The unchanged inspector regenerated the preparation inventory against the actual working tree with base provenance 8a. Its contracts, contract hash, classifications, preparation-only acceptance and all 685 explicit review gaps remain unchanged. The current S5 roadmap now records the actual #1088 landing and reviewed 1,838/751-KiB gates while keeping S5b controller/runtime/visual acceptance planned. Historical receipts retain their original wording, dates, results and scope.

`source-preservation.json` proves all 2,786 nonreceipt tracked files outside the two explicit metadata edits match 8a in Git blob identity and SHA-256, including every native/WASM producer, browser/worker source, host, build/configuration input, declaration, fixture and test. It separately checks the full previously reviewed 580-input producer/build/browser-test set. The complete property-browser helper is **20,079 bytes**, SHA-256 `a9cc95b2bc1958abfa5e7f8b4b20a67706d0742f088b6c219eb8d33f801ffef8`, exactly equal to both 78 and 8a. The older 14,976-byte helper is not restored. No production fix, policy change or test weakening is introduced.

Both parents' performance receipts are verified by their actual Git blobs and SHA-256: **8,276 files from 8a and 3,530 from accepted main**. Accepted-main history was already present through the earlier ordinary parent merge; every accepted-main receipt remains present and exact. New evidence is limited to this append-only directory. `evidence.json` records metadata and whole-PR nonreceipt binary/full-index diff hashes, parent/tree identities, source-manifest hashes and exact command/log bindings. The handoff separately provides both complete committed binary/full-index diff hashes, including this receipt, to avoid a self-referential digest.

## Qualified artifact and validation reuse

`artifact-manifest.json` reads and hashes 13 actual existing native/WASM/browser assets and verifies byte equality to the qualified78/8a shipping proof. Python package copies equal their host-neutral counterparts. This is **reuse of qualified artifacts and previous browser/runtime evidence because source identity is exact**, not a fresh native/WASM/browser build or a fresh stale-binary browser qualification run. No parent-root or other child's files/artifacts are modified.

- Native library: `6df9cb7ed06048d08d59ec8c068da0e0be9b5a3eb6b10d1b86f08527a8fd2485`.
- ESM: `3b194aebda9a2d8f30e0503f01310d944efb72edcca4701777a3c211803ddf70`.
- IIFE: `bdce4a092184e0feb745ea4ebfc57b3929b5ca795d5ec968f9a678e233efeea8`.
- Production WASM: `717440524b63cf87e0127161c128c4f81efdca87e5112f9b05a42e820b456fde`, **1,881,508 raw / 768,134 gzip6 bytes**. Node 22 remeasurement of the existing bytes matches the original production compressor and gzip hash `101e1394aff270699602a3945723971243c7bbe11e284372683b9203aa0012ae`.

ABI398/WASM35/Scene34/painter17 remain exact. Raw limit **1,882,112 bytes (1,838 KiB)** and gzip6 limit **769,024 bytes (751 KiB)** retain 604/890 bytes of headroom. Build/compiler/optimizer/dependency/export/guard policy and 16/384-MiB runtime bounds are unchanged.

The reused proof still establishes actual before-fix failures and 60 passing candidate captures matching independent browser-owned HTML, 222 canonical cases, exact native geometry/fractional widths, ordinary preservation, public CSS cases and full strict-CSP behavior. The untouched property helper still has exactly the two documented initial-native presentation failures; both WASM whole-image comparisons pass unchanged. This merge neither reruns nor fixes those separate native failures. Existing #935, controller, public-host, massive-graph and release acceptance limitations remain.

## Fresh metadata checks

- Inventory regeneration and comparison: PASS; unchanged contracts/classifications/acceptance and 685 explicit gaps.
- Ownership: PASS; 504 tracked production files classified.
- Native ABI declarations: PASS; 537 symbols, ABI398.
- WASM declarations: PASS; WASM35/Scene34/painter17.
- Python typing: PASS.
- Release inventory / ownership / WASM generator tests: **61 passed**.
- Mandatory full-worktree pre-commit, Ruff check and Ruff format check: PASS before commit, with exact argv/exits and losslessly compressed raw stdout/stderr retained.

Use `run.py <fresh-record-name> <argv...>` to reproduce individual checks. It refuses existing command names and sets skip-native/skip-browser-build flags for Python environment hooks. `preserve.py` and `artifacts.mjs` refuse to overwrite proof outputs; use a fresh receipt directory when reproducing. Command records include environment, elapsed time, exit, raw SHA-256 and gzip SHA-256. The merge's conflict exit is expected and retained. Two initial preservation attempts are retained: the first treated the `AGENTS.md` symlink as target content; the second detected a proof/command filename collision. The final `source-proof` handles symlink blobs correctly and writes the distinct `source-preservation.json`; neither attempt changed product files or historical evidence.

This is implementation/synchronization evidence, **not independent review**. The parent must obtain a new independent review of the final committed candidate before push, PR update or queue entry, and fresh main-target PR CI is still required. No remote mutations or push are performed by this task.
