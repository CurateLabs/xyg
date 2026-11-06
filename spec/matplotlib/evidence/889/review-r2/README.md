# Python and acceptance review corrections for #889

Both reviews requested changes on immutable candidate 9487d791. The Python
review found NullLocator still produced automatic labels: bulk chrome packing
collapsed a supplied empty array into absent/automatic. The initial pointer-presence approach failed two established host-parity tests
that require empty major arrays to remain automatic, and was discarded. No
FFI/host marshaller changes are retained. The pyplot adapter instead authors
zero major tick/grid style and Rust's existing off label strategy, retaining
separately authored minor ticks. Null minor locators author zero minor style.
NullFormatter uses the existing off strategy so it hides labels while retaining
tick marks. Actual rendered SVG tests check the absence of y labels/marks and
retention of x marks, including independent Python/Node registry witnesses.

The acceptance review found a copied categorical-coordinate scenario and an
unanchored regex did not prove the original test body. That copied test is
removed. The original function is now an active inventory case, with exact
equality including its pyplot panel context and stable XYG reason. A regression
test checks all #889 xfail functions against the actual original-body inventory.
The marker receipt is regenerated from those sources. The pre-correction marker
receipt and results are preserved here. The historical Rust summary mislabeled
five integration tests as doctests; the corrected record states zero doctests.
No raw historical logs were rewritten. Independent Rust repair approval for
3a912365 remains limited to that unchanged Rust/PDF/registry implementation.

Focused results: rendered NullLocator regression 1 passed; all active pyplot
rejection/coverage checks 36 passed; independent-host hidden-tick registry rows
2 passed. Full required gates, new artifact hashes, hooks and re-review remain
required for this new repair.

Final validation: required pyplot 1186 passed / 163 skipped / 26 qualified
xfails; host parity green with 1097 cross-host tests; Rust workspace, exact
Clippy all-targets with warnings denied, and type checking passed. The final
receipt-consistency assertion was separately verified by all 36 rejection/
coverage checks. Two NullLocator/minor regression cases, two independent-host
registry rows, and all 26 existing empty-array/secondary-axis contract tests pass.
Lossless logs.json binds raw and archived output. The failed pointer-presence
experiment is retained as failure evidence; no FFI, ABI or core change survives.
The generated mark fixture side effect was preserved as a patch and restored.
Mandatory commit hooks and Ruff passed; new independent reviews remain required.
