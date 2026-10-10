# Selected19 Worker provenance evidence

Bounded four-row actual Chrome155 Worker proof under strict CSP. All controls
passed with zero browser errors, external requests, or CSP violations.

Base: ef933a893ece21c71b55ed23425ec788d53d4014. All204 compiler inputs match the
pinned durable-recovery donor; no Rust/compiler change was made. Native donor
SHA256: 90139354a1a33d220a1b1bc67fd38db1b541882fa909823aafe9d237a0e62c37.
WASM SHA256: 29e82b1ae89e4ed116799ed6b2040a1c855647ade23119ab8e796827f91a2b49.
Artifact1505665 raw /618491 gzip6 is within unchanged1507328/622592 caps.

```sh
npm ci
node js/build.mjs
# Supply the exact verified donor WASM into ignored packages/xy-client/dist.
CHROMIUM='/path/to/chromium' XYG_SELECTED19_CAPTURE_REPORT=/tmp/report.json \
  node scripts/geo_selected19_capture_smoke.mjs
```

`browser.json` and `browser.txt` are verbatim raw proof. Compiler inputs and
source hashes bind the proof. Test fixture framing is not product policy. This
slice authenticates exact19/304 and47/272 original19 dispatches; it does not
implement public19 owner adoption or close M6 journey/performance gates.
