# Temporal/geographic subscription inventory correction

Independent review of `195e2339e4783c17a2783067da9774053cc63ac7`
found one missing preparation-inventory declaration: the public temporal
controller's `subscribeState` method. The official inventory generator now
records that already-reviewed method. Removing this sole new member from the
regenerated definitions yields exactly the previous contracts. No other API
contract, implementation, test assertion, dependency or stability classification
changes. The snapshot remains preparation-only, not a release freeze.

Generation also refreshes source hashes for earlier accepted body-only edits
and the generation-time base commit. These are provenance metadata, not
additional API changes; the inventory checker deliberately compares semantic
declarations. `semantic-delta.json` records the exact method and refreshed
source paths.

`checks.json` retains the failing pre-correction check, official `--write`,
post-correction validation and the complete inventory test module, with
compressed/raw log hashes. All original geographic binding sources, browser
results, artifacts, failed captures and receipt files remain byte-identical
to the independently reviewed candidate. No browser/native/WASM rebuild or
recapture is needed for this snapshot-only correction. The original review's
bounded behavioral evidence carries forward; no whole #50/#39/M6 acceptance
or publication claim is made.

Reproduction:

```sh
uv run python scripts/check_release_inventory.py --write
uv run python scripts/check_release_inventory.py
uv run pytest tests/test_release_inventory.py -q
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```
