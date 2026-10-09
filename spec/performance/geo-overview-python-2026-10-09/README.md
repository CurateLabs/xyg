# Internal Python overview transport evidence

The native bridge exercises actual Rust authority, source-authenticated temporal
counts and private asynchronous read/write loans. Six tests cover eight temporal
cases (including signed extrema), callback ticket mutation, malformed framing,
immutable old-owner use, lifetime copy/admission quotas, repeated cancellation,
terminal cancellation, cleanup retry and unreturned Data disposal after creation
or read. `validation.json` records the environment, exact input hashes and command.

Reproduce:

```sh
cargo build -p xyg-core --release
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
  uv run pytest tests/test_geo_overview.py -q
uv run ty check
make check-ownership
```

This internal adapter does not add a public chart surface, source-feature
membership, painter mounting, frozen export or massive-data performance evidence.
