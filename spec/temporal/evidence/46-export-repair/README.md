# Temporal catalog export corrections

This corrects the two findings from independent full review of
`8940c8777d0c6d6729b95f5f8df7c7951343da92`. All broader #46/M5/milestone
acceptance and accepted-main integration remain open.

Python temporal HTML now uses the ordinary export helpers for custom-CSS
validation, bundled-script escaping, title escaping and offline CSP. Unsafe
CSS rejects before any artifact is written. The normal pytest regression
rejects style/comment breakout inputs and uses the HTML parser with an actual
script-closing payload to distinguish bundled data from executable elements.
Fresh Chromium journeys render all six families with hostile bundled string
and title sentinels, verify that injected marker code never executes, retain
exact identity metadata, and dispose the ordinary painter.

Node static export now passes resolved width/height into temporal compilation
before framing the matching StaticDocument panel. The normal Node test covers
450×210 and 1200×600 SVG plus PNG scale 1 for all six families, and checks that
authoring dimensions and subsequent default Scene bytes remain unchanged.
PNG's existing default scale is unchanged.

The before regressions reproduce four Python failures with twelve passes and
one Node failure with six passes. Two intermediate after runs exposed test
assumptions: Node SVG is a byte array, and default PNG scale is two. Those
runs remain retained; the final test decodes SVG and explicitly requests PNG
scale 1. They are not additional product defects or passing runs.

`checks.json` binds final source/runtime identities, archived logs and
captures. `current-bindings.json` preserves both preceding catalog chains;
all original receipt files remain unchanged. Rust, native ABI402, WASM, browser
runtime sources and shipping artifacts remain unchanged. Actual output
security/size behavior is tested through public methods, with existing tests
and validation gates retained. Independent correction review is required
before PR delivery.
