# Resolved axis synchronization with the updated P1 parent

Normal merge of the reviewed P1 synchronization
`60cee1e58bc93766b954d7343b90ec19d676a8de` into reviewed CSS repair
`78b4b69f76b955ab19bd365f0492711cc3c06c1f`, for stacked PR #1089.
The parent remains #1088; this does not merge either PR into a feature base.

The two conflicts retain the complete reviewed property-browser helper from
78b4b69f and use the parent's roadmap row recording #1087's actual main merge.
All 580 recorded producer/build/browser-test inputs match the reviewed CSS
head byte-for-byte. Both parents' historical performance receipts remain
unchanged (8,229 CSS-head files and 3,530 parent files). The imported P1
synchronization evidence retains its original scope and limitations.

The existing reviewed CSS proof is reused: both review findings reproduce
before and pass after the repair, 60 complete captures equal the independent
HTML reference, the canonical and ordinary preservation matrices pass, and
nearby tests plus full strict-CSP proof pass. Production native/WASM sources
and actual shipping artifacts remain unchanged. No stale local binary is used
for a new qualification claim. The two original native presentation failures
remain explicit; separate native work is not part of this synchronization.

Fresh declarations, ownership, Python types, preparation inventory and full
repository hooks/Ruff must pass before commit/push. `checks.py`, individual
records and compressed logs retain exact commands and hashes. The inventory
keeps 685 explicit gaps and refreshes provenance for the current working tree.
`preservation.json` records exact Git blobs for all preserved inputs and both
historical receipt sets. Independent final review is required before pushing.

Fresh PR CI is required. Keep #1089 stacked until #1088 actually lands, then
retarget to main and use the main merge queue after review and checks pass.
No package limit, runtime bound, ABI, compiler, optimizer, dependency, export,
guard, CSS contract, threshold or issue/release acceptance changes here.

Completed independent review by `s5a_final_review` approves the synchronization
with no blocking findings. Incremental nonreceipt binary/full-index SHA-256:
`0941542d96987bdb97372d77f9be72c56ba446b637943cb646f2943f4679a0c7`.
Whole-PR nonreceipt SHA-256 against updated parent 60cee1e5:
`447882c63d4f7552300d16ef828480da77ade1ba3418c8e79f18b5a39b1c5248`.
The review verified all 580 inputs, both historical receipt sets and nine
passing check/log pairs. Full-worktree Ruff reports 972 formatted files.
