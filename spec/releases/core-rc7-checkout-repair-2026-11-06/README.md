# CRLF-safe current Core qualification bindings

Independent review of `6ef69c56` reproduced raw-source hash failures on Git
CRLF checkouts. The checkout regression now derives its complete current-source
path set from this correction's bindings and tests actual Git checkout filters
with `core.autocrlf=true` and `core.eol=crlf`. An unpinned control still converts
to CRLF. Before the LF pins, this extended test reproduces all four omitted source paths plus the new correction receipt; its failure is retained losslessly in `before.log.gz` with both hashes.

Explicit LF attributes now cover `.gitattributes`, the API/host-parity Markdown
files, and the corpus test. The correction receipt is pinned too. The rc.5 test
again checks only its own immutable producer evidence; the accidental duplicate
rc.7 current-source checks were removed from it. The rc.7 test retains complete
current-source binding checks, frozen original producer SHA, authentic tarball
provenance and all 112 IPC byte hashes.

The R1/R2 receipts and original IPC/generator snapshots remain untouched; their
source bindings describe their recorded producing revisions. This append-only
correction binds current source bytes. No runtime, corpus, supported-version,
artifact, ABI, resource, tolerance, or publication policy changes. Independent
re-review and remote CI/queue acceptance remain required.

Fresh focused qualification: 177 passed, zero skips with `uv run --with dunamai pytest -q tests/test_graphforge_contract_corpus.py tests/test_graphforge.py tests/test_release_version.py tests/test_check_release_version.py tests/test_verify_release_cohort.py`. The earlier no-extra-dependency run (171 passed, six skipped) is retained separately.
