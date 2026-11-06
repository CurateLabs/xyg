# PR1095 integration with accepted #889 main

Owned workspace `/home/ubuntu/.t3/worktrees/xyg/t3-05a35a31`, branch
`t3/integrate-picked-target-receipt`, initially clean at
`74195403ccd18c760e3d20a18f024daab95d711a`. This candidate fast-forwards normally
to preserved R10 `24ab68045c98ea50055061191759c25479ddedcd`, then normally merges
live accepted main `5e00c6b9147b67f20046cdfa6bd77aa413c18474` without textual
conflicts. Its entire tree equals independently reviewed #889 tree
`2bb6a0c3841d5cba19f6ed74b41524274d0a1ce7`. No reset, rebase or force operation
occurs. The old implementation and orchestration root are read-only inputs.
No root TASKS.md was present in the old implementation when inspected.

The merge retains both histories and their disjoint product changes. No new
product feature or public hover integration is added. The official inventory
generator refreshes generation-time provenance and changed #889 source hashes;
ABI399/538 symbols, WASM35, GPU-v1, Scene34 and painter17 remain unchanged.
Ownership, ABI and capability checks require no generated declaration edits.
The existing R9 Clippy fixes and active golden-migration workflow entry remain
exact. The current browser-WASM spec links this integration and preserves the
explicit prior 1882/768-KiB picked-target decision. Main's older 1878/765 limits
are historical at this combined tip; no cap is raised by this integration.

## Protection and artifact provenance

`verify-protection.py` and `protection-final.json` verify all inherited R10
performance/evidence files (11,182) and accepted-main performance/evidence files
(10,574) by Git blob identity. They also verify the union of product, build,
test, script and CI files: existing picked-target changes remain R10-exact;
all other incoming paths remain accepted-main-exact. `protection.json` is the
initial successful subset proof; final proof additionally checks new R10 paths.
The initial verifier classification failure is retained in
`initial-protection-failure.txt`; it was a verifier mistake, not a source change.
No historical failed gate, capture, fixture, patch or receipt is rewritten.

`artifacts.json` verifies all 15 R10 artifact hashes against the read-only old
worktree and records each freshly produced combined hash. Old native SHA256
`0deea9029e4a328dc15aa2d86873a203f12b8911e1c89c274f14270b31a3f880`
and optimized WASM SHA256
`e3ef33b58820675f4c201a2b81ad23b3665090442210aa22fcee28a269884a96`
remain historical identities, not claims about the new producer. The combined
shipping optimized module SHA256 is
`0ba71b670ceae0459935ca04f6004670bac327a3c05cea4e99e7dca89ff538b7`.
`production-inputs.json` accounts for all 285 recorded producer inputs: only
`pdf.rs`, `scene.rs` and `static_export_registry.rs` differ, all accepted #889
changes. Normal native release, client and wasm32 release producers and pinned Binaryen132
packaging were executed in the owned worktree. These runs occurred with the merge staged but uncommitted, so harness Git HEAD
fields name R10 `24ab6804`; source and artifact hashes here identify the actual
combined working bytes rather than claiming that R10 alone produced them.
No source settings, dependencies,
arenas, validation, tolerances or gates were relaxed. No build binary is added
to Git. `size.json` records Node22.23.4 gzip6: 1,926,555 raw / 785,542 gzip bytes,
613/890 bytes headroom under unchanged 1,927,168/786,432-byte caps.

## Fresh validation and reproduction

`run.py` preserves exact argv, selected environment, cwd, timestamps, exit and
raw log SHA256 and refuses overwrites. Each `*.command.json`/`.log` pair records
an actual run. `checks.json` collects their exits and hashes. Run commands from
the owned root with Cargo1.96 and Node22.23.4 on PATH and
`XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so`; browser runs use
`XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
The command records preserve explicit fresh output paths and no diagnostic
session-module override.

- Native release and wasm32 release builds, normal client/package production,
  Python native-backend assertion, complete Rust workspace tests (1,982 passed) and exact
  `cargo clippy --workspace --all-targets -- -D warnings` pass.
- Exact existing command `node --test packages/xy-node/test/graph-session-wire.test.mjs js/test/graph-picked-golden-migration.test.mjs`:
  8 passed, zero skips, complete XYGR migration and shipping replay comparisons.
- Package/manifest/controller-wire/GPU contracts: 19 passed, zero skips.
  Paired shipping assets, full browser session journeys and inline-file startup
  pass against the rebuilt combined module (69 browser journeys, no page errors),
  with fresh captures retained here. Full WASM foundation and strict-CSP local-only
  worker lifecycle checks also pass.
- Combined #889 Python Scene/polar/registry/cross-host/rejection suite:
  267 passed, one qualified xfail. Node Scene tests: 131 passed, one existing skip.
- Official ownership/inventory/capability/native ABI/WASM ABI checks, whole-tree
  naming, 226 metadata regressions, 770 CI workflow contract tests and type checking
  are recorded in their command receipts, along with mandatory full-worktree
  pre-commit and Ruff gates.

The historical `graph-picked-receipt-shipping.mjs` pins R2 native/WASM hashes;
it is preserved as historical qualification and is not claimed as a fresh run
on this changed artifact. The current migration/wire command, complete Rust
suite, shipping contracts and browser checks supply fresh scoped proof. No
whole Python suite or complete release/platform matrix was run locally.

`source-vs-main.patch` is the binary/full-index diff versus accepted main with
all performance receipt paths excluded; `source-diff.json` binds its command,
size and SHA256. The parent handoff additionally reports the SHA256 of the
complete final binary/full-index diff versus accepted main, including receipts,
after commit (stored under ignored target to avoid a self-referential hash).

This is a local integration candidate. Independent final combined-diff review,
parent push, fresh remote CI, required merge queue and any acceptance/closure
remain parent-owned. No external review is claimed here. #36/M4/#108 and the
685 preparation gaps remain open and baseline freeze remains UNACCEPTED. There
was no GitHub mutation, push, watch, tag or npm/PyPI publication. Release108
publication must wait for all acceptance; these scoped results do not establish
whole-release completion.
