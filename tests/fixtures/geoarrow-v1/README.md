# GraphForge GeoArrow v1 fixtures

These producer-neutral fixtures are copied byte-for-byte from GraphForge
commit `8a44b9992cfa9b13933536717b4011e966f583fa` (`#823`). The adjacent
`SHA256SUMS` file pins the Arrow IPC stream and equivalent Parquet artifact.

GraphForge regenerates them with:

```bash
cargo run -p graphforge-cli --example generate_geoarrow_fixtures
```

XYG deliberately vendors the small conformance artifacts so its tests do not
depend on another checkout, a network request, GeoJSON conversion, or field
renaming. When the upstream contract changes, update the JSON contract, both
binary artifacts, their hashes, and the source commit here together.
