# Desktop test collection in the minimal Python floor

Hosted run 42771601692 at ab625c5b failed Python 3.11 collection because the
PNG-report test module imported optional Pillow unconditionally. The original
failure remains recorded. Runtime dependencies and the minimal floor install
command intentionally exclude Pillow; their contract is unchanged.

The 15 cohort/installer/required-command cases move unchanged into a dependency-
light module. The 68 PNG-report cases use the established optional-oracle
module skip. A new child-interpreter regression explicitly removes Pillow and
checks all three boundaries: cohort imports, image-test collection skips, and
the unchanged required standalone desktop verifier fails. Both modules remain
in make check-ci. The required journey, verifier, CI steps and existing assertions remain unchanged.

A clean actual Python 3.11.17 environment uses the hosted dependency ranges and
an editable install with existing prebuilt-artifact flags. It reproduces the
parent missing-PIL collection error, then collects all 8,976 tests without an
error and passes 16 focused cases with one optional module skip. With Pillow,
all 84 cases pass on Python 3.11 and 3.12. Collection does not claim full suite
execution. Subsequent checks and their exact exits are recorded in checks.json.

All prior histories, runtime files and compiled inputs remain hash-bound and
unchanged. No Rust/client/native/WASM rebuild, package/default/cap or product
policy change. The named desktop and browser proofs inherit only over exact
source/artifact equality. Final independent review, new-head hosted CI and the
required merge queue remain delivery gates. Whole #1015 and milestones 4–7,
installed distributions, broader platforms/versions, geometric policy, scale,
accessibility, performance and global-budget acceptance remain open.
