# Camera retention across every post-reply frame

This corrects the independent review of `13b2a5be` without changing or relabeling
its evidence. The former verifier checked only frames with advancing Rust steps,
so a same-step camera reset followed by restoration could escape validation.
The verifier now checks camera equality on every frame after the reply and
separately requires at least one strictly advancing continuation.

The fixture records the frame count when refreshRender resolves. That ordinal
identifies subsequent frames without relying on clock precision; equal-clock
frames cannot evade validation. Sixteen unit cases cover the original camera
and continuation controls, same-step/regressed-step/equal-clock resets, and
invalid/missing ordinals. Existing normal foundation CI runs these unit checks
and the actual two-view 1k browser probe. The full command passes with the new
assertions; its report, captures and logs are bound in checks.json.

No product controller, algorithm, renderer, ABI, budget or public API changed.
Shipping artifacts are reused with unchanged producer inputs and exact hashes.
The earlier scheduling and camera reports remain immutable. This remains a
trusted host-button refreshRender route, not canvas dragging. Each Worker uses
explicit 384 MiB; default1k/ceiling10k refusals stay failures. Cold start,
keyboard focus, unfinished disposal, larger rendered rungs, frontend/export/
accessibility and whole #35/#36/#1015/M4 acceptance remain open. No timing or
competitor win is claimed. Independent re-review and delivery remain required.
