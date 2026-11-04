# Parent handoff: #35 bounded 1k rendered proof

Base production/non-receipt source: **207ebdbdaa2ec8b0360c571683eb0fa6165e02c0**.
Isolated branch `t3/node-first-paint-proof`, worktree
`/home/ubuntu/.t3/worktrees/xyg/t3-00534fdb`. The handoff commit contains the
new harness, spec corrections and evidence together; its full SHA is reported
in the final handoff message. No production files or prior receipts changed.
No GitHub write, PR, push, issue closure or publication was performed.

The [README](README.md) contains exact reproduction commands, timing bases,
measurements and limits. [Final unheld raw JSON](raw/unheld/result.json) binds
environment, exact native/client/executable/source hashes, checkpoints,
visible pixels, geometry, real pointer identity, heartbeat and resource facts.
[Held inspection JSON](raw/held/result.json) records initial trusted UUID/pan,
active invalid-ACK rejection and actual replacement-camera reset separately.
Source hashes for both preserved earlier instrumentation captures match their
archived files in `instrumentation-v1-source/`.

Actual final unheld first checkpoint **302.61 ms**, visible paint observation
**887.90 ms**, GPU node-hit readiness **966.80 ms**; these use distinct documented
host/browser clocks. Cold fixture **166.79 ms**, Chromium launch **134.72 ms**,
context/navigation **693.92 ms**; parent first-frame observation including that
serial startup **1,980.19 ms**. There were only initial step 1 and complete step
401 presentations, one **570.00 ms** interval and **zero update-phase frames**.
Instrumentation contributes to those values. This does not establish sustained
presentation cadence or unheld initial trusted interaction. All source/paint
bytes and screenshots for presented frames are retained.

Trusted final pointer UUID and pan, separate held initial pointer/pan,
wrong-step/wrong-job ACKs, wrong-job pick and real synthetic-event negative
checks succeeded. Cancellation returned `GF_LAYOUT_ABORTED`, disposed owners
returned `GF_LAYOUT_DISPOSED`, canvases were removed and all observed WORKER
resources balanced. No native-destructor, emergency-termination, complete
memory-accounting or VRAM-budget proof is claimed.

Validation: **8 focused tests pass**. All required full-worktree gates pass:

- `uv run --with pre-commit pre-commit run --all-files`
- `uv run ruff check .`
- `uv run ruff format --check .`

Their raw logs are adjacent. No full Python run was repeated. There is no new
CI/CodSpeed gate, arbitrary numerical acceptance budget, competitor ranking,
performance optimization or package qualification. The actual native artifact
was reused at the exact supplied SHA, ABI 399. No #36 target-size, hover,
point-mapper or module-gate changes were made.

Parent decisions/remaining #35 acceptance:

1. Keep the issue open. This is only the 1k rendered rung; 10k/100k/1M rendered
   first paint and interactivity across public hosts remain unproved.
2. Unheld initial trusted input and sustained progressive presentations remain
   unmeasured. Do not replace those with held-inspection times or checkpoint
   arrivals. Replacement resets the camera; any production repair is a separate
   parent decision.
3. Public browser progressive scheduling/attachment remains open. Retained
   Rust opcode 15 does not supply a public browser force-continuation API.
4. Python widget/notebook progressive delivery and rerender/dispose cancellation
   remain open (#1015); private byte seams or standalone schedulers are not
   acceptance evidence for that flow.
5. Explicitly clarify the literal async `composeGraphForge` criterion against
   the adopted synchronous metadata/static/batch API and default live
   Worker-backed `graphforgeWebviewPayload`. This receipt does not decide that
   wording or closure on the parent's behalf.

`host-parity.md` and the dual-host matrix now distinguish the implemented
live Worker path from that unresolved literal wording. The graph mark and Node
scheduling contract link this partial rendered proof and qualify older S5
wording against the separate explicit attachment. Historical receipts are
unchanged; preservation identities are in `identities.json`.

Parent owns external final-diff review, integration/PR, issue disposition and
all later M4/#108/release decisions. This test handoff supplies no independent
code-review approval and cannot satisfy the repository's external review gate
for its own implementation.
