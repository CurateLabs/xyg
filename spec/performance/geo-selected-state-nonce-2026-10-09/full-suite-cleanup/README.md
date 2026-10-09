# Full-suite owner cleanup correction

PR972 CI run37952292269 exposed a test-only Scope leak: the new saturation
control implicitly dropped its Scope before the canonical query fixture that
still retained it. Its RAII helper ignores failed disposal, so a later registry
capacity test encountered ResourceLimit before filling all16 slots.

The test now explicitly disposes the replacement State, query/source fixture,
Scope and pressure Scope in that order and asserts the registry handle count
returns to its starting value. Production code and release artifact inputs are
unchanged. `full-engine.txt` records all1439 engine tests passing together;
`ci-failure.txt` retains the preceding Linux failure evidence.

Reproduce: `cargo test -p xyg-engine --lib`.
