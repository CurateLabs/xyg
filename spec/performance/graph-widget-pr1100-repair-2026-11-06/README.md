# PR1100 CI ownership and Greptile repairs

Parent correction of reviewed/pushed `948ab7f26bae89ff21d1e816874b9428291df2c8`
in the owned `t3-56fb3ea2` worktree. CI run42172989799 job127745491255 stopped
at the source ownership audit: the new Python notebook adapter and shared
TypeScript host adapter had no ledger rows. Two exact policy classifications
and their human ledger rows correct that omission. No source exclusion,
classification-policy or required-status change is made; downstream missing
uploads followed the early audit failure and are not credited as passes.

Greptile discussion4489624178 correctly found hidden traces/categories returning
on remount. Their state is separate from durable view ranges/selection. Native
Figure visibility now survives remount and is applied before replacement payload
compilation; private per-trace metadata restores the generic browser legend
maps, GPU flags/category filtering and row controls before paint ACK. Saved
Python/browser widget snapshots mirror legend changes, including after terminal
layout, so bootstrap does not resurrect hidden data. Append keeps that metadata.
Existing selection/layout/identity computation remains Rust-owned.

Discussion4489624186 correctly found an underpowered final-pointer proof. The
notebook records a fresh callback count after reset and before the final pointer
action; after that action the kernel must observe a strictly larger count and
the exact expected node identity. The harness records both counts and derives
its boolean from them. The report verifier rejects earlier callbacks even if
the old boolean is true. The fixture and harness keep normal five-node bounds.

Focused native widget, actual renderer/adapter, report/CI/ownership controls and
a fresh real JupyterLab/IPython/anywidget/Chromium journey supply correction
evidence. Raw logs/failures are losslessly compressed; source, package, image and
report hashes identify actual working bytes rather than the precommit HEAD.
The fresh notebook report uses corrected runtime sources, unlike the prior R4
normal report's explicitly preserved earlier Python snapshot. Current bindings
are append-only and preserve historical Core/notebook evidence by digest.

Reproduce with the repository Node22/Rust tools, uv environment, selected native
`XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so` and Playwright Chromium:

```sh
uv run python scripts/verify_ownership.py
node js/build.mjs
node --test js/test/graph-host-transport.test.mjs
uv run pytest -q tests/test_graph_widget.py tests/test_graph_notebook_report.py tests/test_verify_ownership.py
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome XYG_GRAPH_NOTEBOOK_REPORT=target/pr1100-corrected.json node scripts/graph_notebook_progressive_smoke.mjs
.venv/bin/python scripts/verify_graph_notebook_report.py target/pr1100-corrected.json
uv run --with dunamai pytest -q tests/test_graphforge_contract_corpus.py tests/test_graphforge.py tests/test_release_version.py tests/test_check_release_version.py tests/test_verify_release_cohort.py
uv run python scripts/verify_ci_workflow.py
uv run ty check
```

Prior R1–R4 failures, captures, fixtures and qualification records remain
unchanged. No ABI, native algorithm, timeout/resource/size allowance, tolerance
or fallback changes; no release candidate or publication. #1015/#35/#36/#108
remaining UUID, frontend/export and rendered scale acceptance stays open. Fresh
independent correction review, current-head CI and merge queue remain required.
