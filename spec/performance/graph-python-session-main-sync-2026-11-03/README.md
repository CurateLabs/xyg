# Private Python transport: synchronize with accepted main

The parent S5a PR #1085 actually merged at6ffc1ad1e772338931b1dda998032af2841ae5e4 after the main merge queue. GitHub automatically retargeted #1087 to main. A normal merge of accepted main into reviewed3aea preserves the private Python transport and all native/browser producers byte-for-byte; the sole conflict kept the implemented private S6 transport status instead of reverting it to planned. The neighboring S5 status now records its actual accepted merge. No public host/notebook API or product behavior changes.

Accepted main also includes #1086's reviewed partial export proof. Its historical visual failures remain explicit; they are not acceptance or an issue closure. Original parent and accepted-main performance receipts remain unchanged.

preservation.json records exact sources and transport hashes. The original83 transport/ABI tests,673 ABI checks and actual e91 production/foundation validation are reused on identical producer bytes. This sync does not run against or claim a freshly qualified native binary. Fresh ownership503, native/WASM generated declarations, private transport typecheck and release preparation inventory checks pass; the inventory retains685 explicit gaps. Required full-worktree hooks/Ruff and completed independent final diff review precede commit/push. Fresh CI on the synchronized main base is required before main queue admission.

No WASM/package/runtime limit, compiler/profile/optimizer/dependency/export/guard or historical receipt changes. Public widget/channel/Node/VSCode attachment, massive graph admission, M4/#108 acceptance and publishing remain outstanding.

Completed independent review m4_notebook_plan approves the synchronized diff: incremental nonreceipt SHA-256 f71aa95a35370acac1f99521e37fa7709285eb0579191b53b379d3ebcdec298b and whole-PR nonreceipt SHA-256 versus accepted main f3cf6fb070bab28d6c9cbd27506ef3eefb925d166ca86a3a1a7ad780f6f8fc29. Transport bytes, historical receipts, inventory provenance and conflict resolution are verified; no blocking finding remains. Fresh main-base CI is still required.
