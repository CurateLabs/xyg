# Notebook identity ownership classification correction

Parent verification of candidate `0742df3381e20110584df8f39242a27aee4cfc0d`
reproduced the ownership gate failure for the new
`python/xyg/_graph_widget_identity.py` production module. This correction adds
exactly one Python-host entry and its human ledger row, using the existing
unchanged `python-host` policy. It introduces no exclusion or product changes.
The module transports Rust session requests and maps existing Rust-authored
identity/membership planes; independent semantic review remains required.

The prior identity receipt, notebook report, environment, artifacts, failed
captures and source bindings remain unchanged. `current-bindings.json` appends
a new current-source snapshot and preserves the historical chain including the
previous candidate's complete binding file. New receipt text is pinned to LF;
compressed logs remain binary. Existing real Git CRLF checkout tests verify the
new current bindings. This is an ownership metadata correction, not additional
notebook/scale evidence or closure of #1015/#35/#36/M4.

Verification commands:

```sh
uv run python scripts/verify_ownership.py
uv run pytest tests/test_graphforge_contract_corpus.py tests/test_graph_widget.py -q
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Raw output and compressed/decompressed hashes are retained in `checks.json`
and the adjacent gzip logs. Product bytes remain identical to the candidate
named above; its notebook and artifact receipt retain their original scope.

The before control replays the prior machine manifest against the corrected
human ledger, so it also reports that new row as extra. The initial parent
check on the unmodified candidate reported only the unclassified source.
The corrected audit classifies all 516 tracked production sources; the focused
widget/provenance/real Git checkout run passed 25 tests with the explicitly
selected native library recorded in `checks.json`.
