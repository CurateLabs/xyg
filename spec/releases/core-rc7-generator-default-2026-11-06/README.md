# Core rc.7 generator default and current contract documentation

The dedicated rc.7 generator now defaults to `results-0.6.0-rc.7`, preserving
the older default `results` corpus, and its usage names the correct script.
This changes only CLI default/documentation; the prior generator execution and
its committed IPC/source/log bindings remain preserved without rewriting.
A fresh invocation against the same authentic published Core rc.7 addon used
an explicit ignored output directory, producing 112 fixtures and 96 contracts
with no failures. UUIDs are freshly minted; the new manifest records semantic
coverage rather than asserting repeated byte identity. The prior generation
receipt remains authoritative for the committed original fixture bytes.

The API schema-version table and host-parity contract now include the exact
rc.7 scope and original receipt link. Notebook/product and final artifact-cohort
acceptance remain open. `bindings.json` binds these changed source bytes and the
fresh reproduction manifest. No publication or external repository mutation.

The original generator bytes are retained as `original-generator.cjs`; their
SHA-256 equals the immutable original generation receipt. The provenance test
checks that producing snapshot plus every current corrected-source binding,
instead of incorrectly treating a later CLI revision as the old producer.
`producer-binding-before.log.gz` retains the expected source-mismatch failure.
