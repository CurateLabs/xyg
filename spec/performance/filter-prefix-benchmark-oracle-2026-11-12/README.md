# Linked-density benchmark storage oracle correction

Parent: reviewed `b63d2edc41db48ce0a7169a8d9e3bc723b8e1a37`.
This correction changes benchmark assertions and provenance only. Production,
runtime artifacts, measured calls, budgets, quality, ABI and workflow gates
remain unchanged.

Hosted run 43146773138 on reviewed prefix-storage head 5989 failed nine cases
in `CodSpeed benchmark oracles (pytest, no timing)`: 218 passed, 4 skipped.
The aggregate Release surfaces check consequently failed. Those failures are
preserved; this correction does not credit that run as green.

The nine assertions still expected 51,632 index bytes, the old u64 prefix
allocation. The current exact u32 prefix obeys the existing row-count limit.
For the unchanged five 8×8 passive grids and 17 active cells, the independent
authored-shape oracle is:

```text
C = 16 cuts + 1 = 17
W = 1 selected-total channel + 5*8*8 passive bins = 321
4*(C+1)*W + 16*W + 16*C = 28,520 bytes
```

The helper derives C/W from the authored active/view inputs rather than a Rust
implementation constant or the reported result. The memory checks remain exact
equalities. Zero canonical reads, tier/fallback, selected totals, 642 prefix
reads, five complete count planes, masked intent and all other assertions
remain intact. All231 collected benchmark IDs and every measured call retain
their parent identities.

The exact hosted command is `pytest benchmarks/test_codspeed_*.py -q`, without
`--codspeed`: each correctness body runs once; no timing qualification follows.
The preserved uncorrected local run independently reproduces 9 failures,
218 passes and 4 skips against current native bytes. Corrected runs pass 227
cases with 4 explicit manual-source skips on actual Python 3.12 and 3.11.
The final assertions also reject the immutable pre-prefix native library in
all nine affected cases: it correctly reports 51,632 bytes. This two-sided
control proves the new expectation distinguishes the storage representations.

The first borrowed Python 3.11 environment lacked the CodSpeed fixture plugin,
so all 227 benchmark bodies failed at setup and receive no pass credit. The
corrected run supplies the existing pytest-codspeed 5.0.3 dependency through a
temporary `uv run --with` overlay; it does not synchronize or modify that base
environment. No benchmark is instrumented or timed in either invocation.

Source, historical bindings, compiled inputs, parent evidence and all eight
runtime artifacts remain hash-bound in `checks.json`. The range-and-paint
parent's completed independent review is archived there. Its runtime, browser,
100M and CodSpeed qualification is inherited only after identity verification;
no new browser, Rust build, performance measurement or whole-suite execution is
claimed for this correction.

Independent final-diff review, new-head hosted CI and the required merge queue
remain outstanding delivery gates. #112 and milestones 4–7 remain open. No
policy, test weakening, skip, tolerance or CI-gate change is introduced.
