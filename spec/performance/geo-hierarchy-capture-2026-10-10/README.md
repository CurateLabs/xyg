# Hierarchy Worker capture evidence

Actual Chrome155 genuine Worker proof under strict CSP. All hierarchy controls
pass with zero browser errors, external requests, or CSP violations. The same
fixture before the dispatcher extension fails at `exact43 replay missing`.
The existing selected19 capture proof and full overview snapshot Worker smoke
also pass on the same artifact.

Base:46b19c08ca2eb8cef5b23c544efacfd57e04ee54. All206 compiler inputs match the
immutable donor; no Rust, compiler, ABI, quota, or package-cap change was made.
Verified native donor SHA256:
eac4795cc1fe9f4a574d97e7d1a40319c40e965f8cfa3ff6e5bbe4130e810f87.
WASM SHA256:
d8e0612406d65168aaf2393617d9b583737fe05dfd4d474b391eebbea1b3cc17.
WASM1505822 raw /618706 gzip6 remains within1507328/622592 caps. Native is
verified as the paired donor; this slice's execution evidence is browser/WASM.

```sh
npm ci
node js/build.mjs
# Copy the verified donor WASM into ignored packages/xy-client/dist.
CHROMIUM='/path/to/chromium' XYG_HIERARCHY_CAPTURE_REPORT=/tmp/report.json \
  node scripts/geo_hierarchy_capture_smoke.mjs
```

`browser.json`/`browser.txt` and `red.json`/`red.txt.gz` preserve verbatim proof (the raw failing log is compressed).
The fixed fixture uses exact lane creation sequence for cleanup. Source hashes
and all compiler-input hashes bind the checkpoint. No public hierarchy owner
recovery, native host journey, massive performance, or M6 completion is claimed.
