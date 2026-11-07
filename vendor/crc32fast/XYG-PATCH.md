# crc32fast 1.5.0 browser table representation

This is the existing png dependency, with original MIT/Apache-2.0 licenses.
The upstream source hashes are in `upstream-source-sha256.json`.

On wasm32 the baseline entry calls the existing `update_slow` byte-at-a-time
implementation. Only its first 256-entry IEEE CRC table is retained. The
remaining slicing-by-16 tables become unreachable const data. Native retains
the original table, fast baseline, SIMD selection, combine and public API.
No CRC polynomial, initialization, complement, chunk framing or PNG encoding
policy changes. Exact native/WASM PNG byte oracles include every chunk CRC.
The space tradeoff is a slower CRC loop on wasm32; no speed win is claimed.
