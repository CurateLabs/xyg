# Native trace blob alignment

The trace-observation materializer returns a bounded byte blob with UTF-8
sections and little-endian f64 sections at explicit offsets. These offsets
are byte offsets, not an eight-byte alignment promise. In particular, a line's
kind/name strings can leave its numeric dash pattern at any byte alignment.

Both host wrappers must decode the exact packed representation without adding
padding or interpreting byte offsets as typed-array element offsets. Node uses
bounded `DataView.getFloat64(offset, true)` reads for these raw f64 sections;
it must not create a `Float64Array` view at an unaligned blob offset. This is
transport decoding only: dash validation and materialization remain Rust-owned.
No ABI signature or wire format changes are required.

M2 #873's independently authored styled-line export exposed the previous Node
alignment exception. Reproduce every preceding name-byte alignment and public
named/unnamed/Unicode dashed-line SVG exports with:

```sh
XYG_NATIVE_LIB=/absolute/path/to/libxyg_core.so node --test packages/xy-node/test/scene-blob-alignment.test.mjs
uv run pytest tests/test_static_document_authored_cross_host.py -q
```

The cross-host corpus compares independently authored Scene/XYST bytes and all
five native document outputs; the focused Node regression pins `[5, 3]` dash
values and the public SVG dash/opacity attributes.
