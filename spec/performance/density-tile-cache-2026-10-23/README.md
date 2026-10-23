# Keyed density cache evidence

Initial scope: the source/native producer and generated browser bundle before a
release freeze. This is a 32,768-point correctness/resource/transport proof;
it makes no competitor or dedicated 100M latency claim. The separate #11
scale gate remains open.

The original reports below remain bound to their recorded source and assets.
Later review found bounded-viewport admission and resize-during-fade defects.
[The review follow-up](review-followup/README.md) records the corrected client,
new regressions, and updated source/browser validation. Do not treat the
original client hashes as the later client or an accepted release candidate.

[Browser raw results](browser.json) record R8 counts and premultiplied RGBA
means. Both cases use actual raw XYDC HTTP requests and native Rust XYDT
replies, then the real `renderStandalone` client and WebGL readback:

- First view uploads four tiles; an edge pan uploads two, and an in-cache
  pan uploads zero. A fetch-all oracle uploads four tiles at the same
  Rust-served level/framing/exposure.
- Cached and fetch-all pixels are identical. Nonblank density ink is checked
  against a disabled-density draw: 6,426 count pixels / 6,534 mean-color
  pixels, with matching cached/oracle SHA256 values.
- Both cases exercise a real L0→L1 fade. Rust inventory stays within the
  unchanged per-format eight-screen-texture byte ceiling.
- Forged retained format changes, malformed offsets and stale replies cause
  zero allocations and preserve pixels/inventory. Legacy overlay buffers
  retire at cache pruning and fade completion, shared sample buffers survive
  until trace disposal, and every tile texture is deleted at disposal.
- Mean-color categorical hover changes the image and restores it exactly
  without allocating another texture.

The focused Python/Node suites pin the same source-body SHA256
`410965db6e34b2143ebcb668edd99c35af3dd7caaade3e3eace7566cdb5486dd`.
Forced-spill SpatialIndex cases verify that binary tile observations preserve
legacy exact point and channelled exact-grid decisions and bytes. Socket.IO
checks actual binary input/output across the Reflex namespace.

[Provenance](provenance.json) records environment, source hashes and generated
artifact hashes. [The painter contract](../../design/density-tile-painter.md)
contains the exact binary layout, limits, quality/resource exceptions and
reproduction commands. Raw logs retain Rust8 / Python38 / Node14 / Reflex35,
673 ABI checks and the existing broad non-NumPy render smoke.

The Reflex suite used the isolated immutable-wheel environment's Reflex
runtime plus the checkout's test dependencies, with `PYTHONPATH` selecting
current source; it is a source transport test. Packaged Reflex acceptance is
recorded separately by the release coordinator.

[Broader source-browser validation](source-browser-validation/README.md)
retains the unmodified full foundation and isolated seven-scenario interaction
results, including the earlier unreproduced disposal error and timing overrun.
