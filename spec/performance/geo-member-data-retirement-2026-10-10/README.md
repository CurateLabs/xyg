# Known MemberData10 retirement proof

The host-only [contract](../../design/geo-member-data-retirement.md) recovers
lost-successful MemberData10 using a genuine current exact6 probe on the private
original publication sequence. Query45 retirement is not Data absence. Generic
callback producers retain their guard unless a strict10 succeeds.

The immutable donor pair is native `eac4795cc1fe9f4a574d97e7d1a40319c40e965f8cfa3ff6e5bbe4130e810f87`
and WASM `d8e0612406d65168aaf2393617d9b583737fe05dfd4d474b391eebbea1b3cc17`.
All206 compiler inputs match this checkout; all tracked crates/vendor Rust,
Cargo and build inputs are present. No Rust/ABI/artifact was changed or rebuilt.
Raw1505822 and gzip6 618706 bytes remain under1507328/622592. Browser-client
source was rebuilt locally for the actual genuine Worker proof.

- New focused tests:7 Python and5 Node native controls.
- Broader current/legacy tests:60 Python and123 Node native/raw-WASM controls.
- Genuine Chrome strict-CSP proof:16 controls, zero browser errors, external
  requests or CSP violations. This is not a raw callback fake Worker.
- Two independent reviewers reran7 Python,5 Node and the16 genuine Worker
  controls; their raw logs/reports are preserved with `root-` and `independent-`
  prefixes.
- Type checking and nonmutating canonical generator check pass.

Proofs cover successful10 reply loss/corruption after producer disposal, correct
liveData retry, wrong-publication-sequence saved genuine errors, forged public
attributes, canonical producer spoof rejection, Worker collisions, clone/latest
request provenance, synchronous scalar capture before microtasks,16 shared
contexts, failed MemberData read cleanup, and concurrent notebook close/cancel.
The existing callback/loan ACK and native/WASM member recovery suites remain
part of the broader checks. Inspection/backend copies retain the existing
four-wire profile; the purpose-specific probe adds no Data23 read or second
capture bank. Caller-retained inspection views remain application-owned.

```sh
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib uv run --no-sync pytest -q tests/test_geo_overview_member_retirement.py
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib node --test packages/xy-node/test/geo-overview-member-retirement.test.mjs
XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' XYG_MEMBER_RETIREMENT_REPORT=/tmp/member-retirement.json node scripts/geo_member_retirement_smoke.mjs
node scripts/gen_geo_overview_hosts.mjs --check
```

Use an equivalent portable Chromium path via `XYG_CHROMIUM`/`CHROMIUM`.
This proof does not establish selected overview membership, massive interactive
latency, a complete browser/GPU/OS resource ledger, or the M6 finish line.
