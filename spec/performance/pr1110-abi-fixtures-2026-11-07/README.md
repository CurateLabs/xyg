# PR1110 hosted CI ABI fixture repair

This receipt repairs the verified failures on run 42344574622, Test job
128319882763 and Python 3.11 job 128319882789. The scoped reproduction produced
15 failures, 376 passes and four existing Python-version skips; the exact hosted
GeoColumn Node command failed its golden ABI equality. Compressed logs retain
both failures. No product behavior, export signature, ABI number, WASM artifact,
budget, cap or gate changes here. Broader #110/#109/#113/M7 remains open.

Ten current cross-host fixtures were regenerated with their existing official
Python writers or Node producer scripts. `fixture-transition.json` records every
command, predecessor/current SHA-256 and every changed field: only the top-level
`/abi_version` changes 399 → 401. All cases, complete packet bytes and hashes,
descriptors, wire versions, styles, errors and output metadata compare identical.
`predecessor/` contains exact candidate Git blobs, not reconstructed JSON.
Node producer stdout has a literal trailing `\\n`; parsing that terminator and
serializing JSON with indent=2 and a final LF preserves the fixture convention.
The producers themselves are unchanged. The Python geo freshness test also runs
its official writer and confirms exact current bytes.

Graph-session tests, including both callback subprocesses, now require the
loaded core version to equal the authoritative generated ABI value. Existing
loader mismatch rejection and full live cross-host packet assertions remain.
The transition regressions reject stale 399, wrong 400/402, and removed product
cases even when ABI metadata is correct. The capability matrix failure came
from appending the scoped XYGC note outside its generator: the generator now
owns the same note, and official regeneration preserves the document exactly.

`provenance.json` records the accepted main/candidate/merge, native hash, complete
matching crate source hashes and added ABI declarations. All earlier symbols
compare unchanged. The candidate ABI401 native artifact was copied after hash
verification, with no source producer edits. Shipping WASM remains unchanged.
The successor `current-bindings.json` preserves all historical receipts and
refreshes current hashes; scoped LF rules and real Git CRLF checkout tests
protect hash-bound evidence. Core producers/captures/provenance are unchanged.

Validation uses actual CPython 3.11.17, Node 22.23.4, local native override,
command-scoped TMPDIR under this checkout's target, and read-only symlinks to
source Node dependencies. Exact commands, exits and log hashes are recorded in
`checks.json`. This is focused CI repair evidence, not a full-suite or hosted
rerun claim. Independent parent review and delivery remain outstanding; no push,
PR mutation, publication, issue closure or milestone acceptance is performed.
