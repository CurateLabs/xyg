# Exact host-camera pan and continuation proof

This corrects the bounded 1k proof at `80933e83`; earlier reports and receipts
remain unchanged. The independent review found that the former success check
accepted a trusted button reply even if its camera did not move. The recorded
old run did move correctly, but the regression assertion was insufficient.

A shared assertion now requires the exact requested +12 x translation, all other
camera components unchanged, at least one later Rust continuation, that camera
on every subsequent frame, and its preservation in the final snapshot. The
fixture records each render event's actual camera. Ten unit cases include exact
success and rejection of no-op, wrong translation, corrupt camera, changed scale,
untrusted/terminal callbacks, missing continuation, and late/final resets. The
existing normal foundation command runs these unit cases and the live probe.

Both fresh actual packaged Worker/browser runs pass the stricter proof. The
focused run records translation 320→332 and 45 later continuation frames; its
final camera is unchanged. `checks.json` binds both complete captures and
screenshots, exact source inputs, reused shipping artifacts and raw logs.
No production controller, native kernel, renderer, ABI or budget changes here.
The native browser bundles/WASM are reused with unchanged producer inputs.

Trusted input is still the host button click calling public `refreshRender`;
this does not prove a canvas drag/pan gesture. Both 1k views use explicit 384 MiB
arenas, not the 16 MiB default. Default1k/ceiling10k refusals remain failures.
Disposal follows completion; unfinished cancellation, cold start, keyboard focus,
larger rendered rungs, notebook/frontends/exports/accessibility and all broader
#35/#36/#1015/M4 acceptance remain open. No timing or competitor win is claimed.
