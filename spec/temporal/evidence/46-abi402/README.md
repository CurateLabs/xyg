# Temporal catalog ABI402 fixture transition

The catalog adds one officially generated native ABI symbol. A pre-review
audit against `0a9847b4010c958333dc362505a10a6d8adf5deb` reproduced the existing
fixture-transition failures: current shared fixtures still carried ABI401,
and the historical negative list incorrectly treated current ABI402 as wrong.
The failure log and exact prior test source are preserved here.

All ten existing official Python/Node fixture producers were rerun with the
verified catalog native library. Only top-level `/abi_version` changes
401 → 402; complete packets, cases, hashes, styles, errors and every other
field remain identical. `abi401-predecessor/` retains exact Git predecessor
bytes. `fixture-transition.json` records the actual commands and both hashes.
The original ABI399→401 receipt and complete ABI399 predecessors are unchanged.

The transition test checks the historical 399→401 step against preserved
401 bytes, then the append-only 401→current step. Wrong-version negatives
derive from the authoritative generated ABI, while removed-case and
rechecksummed packet-bit mutations remain rejected. This uses the same
already-reviewed transition structure as the independent Filter Tier C
checkpoint; it changes no production policy or acceptance gate.

The first full Node run also exposed direct browser-global names in the new
HTML source template. The template now uses the same existing
`BROWSER_DOCUMENT` framing constant as ordinary exports. Browser code still
executes only in the emitted HTML; the Node module boundary test and all its
negative controls remain unchanged. Complete Node results and fresh offline
Node-export captures are recorded separately from the earlier failed run.

`checks.json` records fresh commands, exits, source/native bindings and
compressed/raw log hashes. `current-bindings.json` preserves the preceding
catalog and historical Core chains. These are CI compatibility corrections,
not new catalog behavior, scale, accessibility or #46/milestone completion.
Independent review and accepted-main integration remain required.
