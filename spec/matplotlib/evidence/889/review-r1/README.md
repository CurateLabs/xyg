# Rust/PDF review disposition for #889

The independent Rust/PDF/registry review requested changes on commit
`9487d791068cd1a51684f78f8eb469b0dcc5920b`:

1. Two concentric SVG clip children form a union, not a hole. PDF must not
   reinterpret that union as an even-odd ring. Scene now emits a single compound
   annular path using its existing exact circular-arc writer. PDF supports that
   path and rejects unsupported multiple-child clips.
2. Newly admitted clip rules and numeric geometry need validation. Unknown
   container rules are rejected before child dispatch, including when a child
   overrides the rule. Circle and rectangle clip coordinates reject nonfinite
   values. Negative tests cover NaN, infinity, invalid rules and multiple circles.

The SVG semantics are specified in
[SVG 1.1 section 14.3.5](https://www.w3.org/TR/SVG11/masking.html#EstablishingANewClippingPath).
The registered Python/Node annulus programs now include a diameter-crossing line
at a fixed radial domain. A separate active test checks a single even-odd path,
a clear center and painted ring on both panels, and PDF even-odd clipping.

The original candidate's reported full-diff checksum `57e09…98c` was incorrect.
The independently reproduced binary/full-index diff from base `74195403` to
`9487d791` is `a86feadc2bdabd696f65aa6f861015264dd6dda69772ec9514cdc5edc76b76ac`.
Original committed evidence is retained. That candidate is not approved and its
old result records do not qualify this repair. New native artifacts, affected
cross-host tests, registry/golden checks, and repository hooks must pass before
commit and new independent review. All native/Python/Node/host checks and unchanged WASM gates passed on the repair.
Mandatory commit hooks and Ruff passed; new independent review remains required.

Focused Rust PDF tests: 12 passed after the repair. No size budget, tolerance,
ABI, dependency or fallback-renderer change is authorized by this disposition.

The center-crossing witness additionally exposed Scene's missing native raster
annulus clip. Scene now emits the existing analytic annular-sector opcode for
marks and resets it before chrome, reserving its exact 25 command bytes. The
original implementation did not emit this opcode. The new witness requires a
white center and green ring in both independently authored panels.

Fresh validation: required pyplot 1184 passed / 163 skipped / 26 qualified
xfails; polar plus full document registry 236 passed / 17 qualified xfails;
host parity green with 1097 cross-host tests; Rust workspace and exact Clippy
all-targets with warnings denied pass. Native and WASM rebuilt from this tree,
unchanged size gates passed. Logs are archived losslessly with both raw and
archive SHA-256 in logs.json. The host suite's unrelated generated mark-fixture
ABI metadata diff is preserved as a patch; the tracked fixture was restored.
Prior completion evidence remains historical, not silently relabelled.
