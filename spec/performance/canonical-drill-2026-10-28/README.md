# Finite canonical-drill correctness observations

These original local outputs accompany implementation
`eddb7a9d981de2bb6a921bf37e98cd3e8e1ee469`, based on accepted main
`d005b0063d9909392786a18262ff1306e3e8f54c`. They are finite correctness
fixtures, not a scale benchmark, hosted authority, timing comparison,
competitive winner or complete #11/#108 acceptance.

- `native-query.json` retains exact IDs and overflow observations.
- `host-query.json` retains the 600,000-row canonical query and padding
  observations: 3,871 requested-view rows and 75,000 shipped canonical rows.
- Four `browser-*.json` files retain the final 262,144-row density → points →
  cached points → density journeys, including actual host replies, channels,
  opacity, draw observations, ownership and disposal. Each exact window has
  41,882 rows. Parameter order is pinned by the retained test source binding.
- Gzip files preserve original test/smoke output bytes. The workspace log
  covers Rust tests; the final Python log records 165 passed and one existing
  xfail; the final Node log records 25 passed. The ABI smoke and render/append
  smoke logs retain their actual results. `keyed-drill-baseline.log.gz` records
  the earlier real browser failure (`noHandoff: false`), before the TS fix.
- `provenance.json` binds every original output's encoded/decoded bytes, source
  commit, changed source files, product trees, environment and recorded
  generated artifact identities. Generated executable/client bytes are not
  included. These local bindings do not constitute independent run attestation.

The [contract and reproduction commands](../../design/canonical-drill.md)
describe query caps, completion/refusal, existing hysteresis, color and hover
identity, padding and lifecycle checks. Its sparse 80,000,001-candidate
preflight is a metadata-only refusal, not an ingested 80M/100M benchmark.
Unordered massive-source localization remains an explicit product gap.

From this directory, verify retained bytes with:

```bash
sha256sum -c SHA256SUMS
```

No original JSON or log bytes were rewritten. Gzip uses mtime zero; its decoded
hashes and lengths appear in `provenance.json`. Implementation source can be
compared with the named immutable Git blobs. The parent independently rebuilds
and tests the integrated source before opening its product PR.
