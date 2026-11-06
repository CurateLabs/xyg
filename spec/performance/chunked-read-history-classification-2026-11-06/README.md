# Frozen issue-history naming classification

PR1101 CI failed in the stale-identity-name step because two preserved GitHub
dependency responses quote old package paths and ABI locations. The underlying
chunk repair and original receipt bytes are unchanged. The failed gate prevented
subsequent steps; downstream missing-artifact uploads are not separate product
defects. CI run 42290594869, job 128144199643 identifies the failure.

The naming scanner now recognizes only two exact historical-response paths with
their original SHA-256-bound UTF-8/LF contents. Changed content and renamed/copied
files receive all ordinary checks. No directory or current product surface is
excluded; existing explicit compatibility rules remain unchanged. New negative
controls exercise both snapshots, changed contents and alternate paths, plus
platform newline normalization matching the scanner's existing text reader.

`checks.json` binds the correction sources, the original snapshot hashes, and
compressed/raw before/after evidence. The before control runs the original
checker on an isolated tree containing the same two complete snapshots; after
runs the corrected checker on those same bytes. The existing repository-wide
gate is also run without bypasses. All original chunk-read sources, specs,
receipts, artifacts, failure logs and the independent product approval remain
unchanged. This corrects classification of frozen history, not #110/M7 acceptance.

Commands:

```sh
uv run pytest tests/test_stale_names.py -q
python3 scripts/check_stale_names.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

No native/WASM rebuild or broad product-suite rerun is needed for this
checker-only correction. CI and final external review remain required.
