# png 0.18.1 shared encoder specialization

This is the existing image-rs/png 0.18.1 dependency, including its original
MIT/Apache-2.0 licenses. No dependency or compression algorithm is replaced.
`upstream-source-sha256.json` pins the unmodified cached registry source.

The only source changes are in `src/encoder.rs` and its `src/lib.rs` re-export.
A restricted `PlainRgb8Writer` exposes only image bytes and finish. Its constructor
creates a fresh RGB8, noninterlaced, nonanimated encoder with no ancillary
metadata, the existing `Compression::Fast` and `Filter::Up` settings used by XYG.
Both writer types invoke the same const-generic header and image implementation.
The restricted capability permits dead stripping unused options; the ordinary
writer keeps the complete original metadata, APNG, filtering and compression
branches. Fdeflate, the existing larger-than-stored fallback, CRC, IDAT chunking,
IEND and sequence validation remain unchanged. The private wrapper cannot be
converted to a mutable ordinary writer or supplied authored metadata.

XYG qualifies exact PNG byte equality against its immutable native producer,
plus ordinary native Scene, raster and text controls. This is a build-time
reachability change, not a second encoder or a different PNG output policy.
