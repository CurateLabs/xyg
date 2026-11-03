# Private Python GraphSession transport: parent integration

Normal merge of independently reviewed P0 commit
`322e4b951c5f7728ff75f66ed8f3107139facc5a` onto parent
`e91fe2f7531cc808987d0af0868c321c55e51066` (reviewed #1085 binding repair).
The private wrapper, tests and contract are byte-identical to the reviewed
child. Ownership records include the new thin Python byte transport alongside
all accepted Rust/Node ownership entries. No Rust, ABI, generated declaration,
JavaScript, packaged asset, public chart or widget/channel code changes.

Independent reviewer `m4_notebook_plan` approved cumulative child diff
`2de3b042eebff23630b44a40c4562f0a00fd0a6b5a480e9f669004483ba0a9fb`.
The original indexable-input deadlock and Python-buffer callback reentrancy are
fixed by conversion outside the non-reentrant lock and a second closed check
before FFI; native creation, whole exact-byte reply retries and disposal remain
serialized. This is private P0 transport only, not notebook attachment,
scheduling or #1015/M4/#108/publication acceptance.

Fresh integrated tests must use the parent's actual repaired ABI-398 library,
not the child's historical ABI-398 bytes. Those original receipts remain
unchanged. The already-built native/WASM/client assets may be reused only with
exact source and asset hash controls because this slice changes none of their
producers. New command and evidence records below bind actual integrated proof.

## Fresh parent proof

All 83 nearby tests pass using the repaired parent native library, SHA-256
`95c16daf37ce19af5a9d3b9d1f08a4d8e12580f522b2dfea90aab90f121f509e`. The targeted typecheck, ownership
(503 classified production files), public API preparation-inventory check and
673 native ABI smoke checks pass. No inventory declarations change or release
freeze is introduced. The unchanged producer control covers 296 Rust/JS/build
source files and all 13 actual parent assets. No rebuild or browser rerun is
needed for byte-identical producers/assets. The review covers private transport
correctness; no parallel-session throughput or public attachment is claimed.

The parent interaction-status table now distinguishes this private transport
from the still-planned public attachment. Full-worktree hooks and Ruff checks
pass with 933 Python files. Final independent integration review precedes the
merge commit and separate stacked PR; no issue closure is implied.

## Final independent integration review

`m4_notebook_plan` approved the six-path integrated nonreceipt diff
`916d18d9d4f24bc6eecd19ba61f33d041ea31fd5117d0d60fa098f3c093412e8`.
It verified exact child source, additive ownership, accurate private/public
status, actual parent native proof, source/log/asset hashes and 3,181 historical
receipt files unchanged. No blocking finding remains for this private slice.
The final merge commit will bind this proof before opening a stacked PR;
committed CI and the parent main merge remain pending.
