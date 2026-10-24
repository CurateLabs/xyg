# Supervised 1M integration control

`host.json.gz` and `browser.json.gz` preserve exact raw JSON bytes. Decompress
before CLI validation; the companion pins the uncompressed host file SHA-256:
`3673f7423277138e86c9a4a324f8eabbbf8735f0a313f67220ca9e8340a1c77b`.
The uncompressed companion SHA-256 is
`c9973ae1a61db81859119a97bedacd2fb59bf7648d5268e66c1698cedc708b00`.
The retained PNG bytes match `browser.capture_sha256` in the companion.
`SHA256SUMS` covers retained compressed files, PNGs and validation notes.

The base checkout was `bc3ad8fad3e4a8d8d2a0af759b2e536555d8aa0f` with the
integration edits present (dirty is explicitly recorded). Raw manifests identify
the exact product and harness files, native/client binaries and browser helper.
The browser helper hash is
`59543501df84458db2e5200ec0ec1e245217cf0e24cac62e6703e8d93c1b0e9a`;
verifier hash is
`a0d6c27fbd3bce5ba58728d97c3ede48af4c0e28584fc93d0efd3b812fdea179`.
This is bounded integration evidence, not the separate historical 100M host
report, actual 100M browser authority, end-to-end latency or FPS evidence.

To validate retained bytes from the matching checkout:

```bash
mkdir -p target/retained-browser-control
gzip -dc spec/performance/density-spill-browser-2026-10-24/integration-control/host.json.gz > target/retained-browser-control/host.json
gzip -dc spec/performance/density-spill-browser-2026-10-24/integration-control/browser.json.gz > target/retained-browser-control/browser.json
uv run python scripts/verify_density_spill_report.py target/retained-browser-control/host.json --artifact-root "$PWD"
uv run python scripts/verify_density_spill_browser_report.py target/retained-browser-control/browser.json --host-report target/retained-browser-control/host.json --artifact-root "$PWD"
```

See `validation.txt` for execution commands and results and
[`spec/design/density-spill-browser-evidence.md`](../../../design/density-spill-browser-evidence.md)
for the contract and remaining authority work.
