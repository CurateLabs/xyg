# Progressive companion paging regression

Greptile discussion4484853565 on PR1098 correctly observed that the committed
browser controls never combine a nonzero companion page with progressive layout.
The earlier independent protocol-level page/step check did not fill that public
attachment coverage gap. This repair changes tests/specification/evidence only.

The shipping strict-CSP harness opens a 64-node ring using the existing explicit
384 MiB arena. Trusted Playwright Enter activation moves its companion to page1
while Rust layout is unfinished. A subsequent opcode15 is followed by opcode21
for that same page. Complete displayed cells, row ordering and aligned Rust refs
must match the originally paged publication after every captured continuation.
Trusted Enter activates its first row, and the selected ref must exactly equal
that page's aligned ref while Rust done remains false. No callback/ACK is held,
no timing threshold is relaxed, and no controller policy is mocked.

The final capture records8 paging publications (ticks25 through81), followed by
exact ref selection at tick81 with done=false, and zero held replies. All8
progressive harness cases pass, including default-arena refusal, 0/4/1k,
authored pins, concurrent attachments and stale/terminal/disposal controls.
The wire/GPU modules pass13 tests, zero skips. Earlier positive runs preceded
assertion/retry hardening; the final source/capture bindings supersede those
intermediate logs. The initial default-arena attempt refused with
GF_INTERACTION_BUDGET; its log is preserved. Explicit384 MiB uses the existing
allowance rather than changing any default or maximum.

Reproduce with Node22.23.4 and XYG_CHROMIUM pointing to the installed Chromium:

```bash
XYG_GRAPH_PROGRESSIVE_ONLY=1 XYG_GRAPH_SESSION_REPORT=/tmp/paging.json node scripts/graph_session_controller_wasm_smoke.mjs
node --test js/test/graph-session-controller-wire.test.mjs js/test/graph-session-gpu.test.mjs
```

Generated client/native/WASM bytes were reused unchanged from the independently
reviewed a062d9c0 candidate; no producer or binary regeneration was needed.
The prior69 legacy and full foundation results remain applicable to unchanged
product source. This is an automated manual browser harness, not a new required
CI status or a claim that the whole graph host matrix runs on every PR.
Broader35/36/1015/108, large rendered ladder and publication remain unaccepted.
Independent final repair review and new-head CI are required before merge.
