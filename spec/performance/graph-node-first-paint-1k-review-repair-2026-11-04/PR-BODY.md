The current bounded 1k Node first-paint proof lives in
`spec/performance/graph-node-first-paint-1k-review-repair-2026-11-04/`.
Earlier proof and parent-sync receipts/runners remain immutable historical records.

The held inspector now drains each genuine intermediate UPDATE ACK with bounded
waiting and job/revision/step validation, and checks viewport reset on the first
replacement rather than assuming it is COMPLETE. Labelled scripted ACK tests
exercise initial -> UPDATE -> UPDATE -> COMPLETE, including the historical stall
and incorrect final-only viewport assertion. Synthetic updates are not cadence
or actual Rust callback evidence.

Fresh real 1k unheld/held runs use the existing Rust/Worker/painter path. Native
identity is observed from existing loaded-module exports inside the fixture and
inherited bridge/force Workers, independently hashed and ABI-bound by the runner.
Known-parent byte identity is separate from origin, which defaults to unknown.
Historical conventional-path hashes are not retroactively treated as attestation.
Normal platform-package/override precedence is unchanged; alternate-byte force
captures fail closed for this repair. Origin/rebuild/loader cases are explicit
labelled tests, not new build or performance claims.

Actual presented frames and timing bases remain in the new raw receipts. This is
partial 1k evidence only: no sustained cadence, unheld initial trusted response,
rest-of-ladder/public-host scheduling, notebook completion, competitor ranking,
M4/#108 or publication acceptance is claimed. Literal async-compose wording
remains open. Production files and all old receipts remain unchanged; current
spec links and official inventory provenance are updated with 685 gaps and
contracts/classifications/preparation-only freeze unchanged.

Final validation is recorded in the new checks receipt. Parent must complete a
new independent final-diff review and pre-push checks before pushing/updating
this PR or replying to/resolving either accepted P2 thread.
