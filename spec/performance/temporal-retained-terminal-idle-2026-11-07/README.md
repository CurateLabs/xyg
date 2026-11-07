# Retained temporal terminal failure settles idle waits

Independent review of `76aee55e9d64b0fd4fee2540c4f97a8b04501a87` found one remaining blocker: a terminal Worker failure prevented pending time intent from being consumed, leaving existing whenIdle calls pending until explicit disposal.

Terminal handling records the first terminal error, invalidates pending intent and late publication, unsubscribes from controller state, and wakes idle waiters. Existing and later idle calls reject with that terminal error. Normal recoverable native refusals retain their previous retry behavior. Explicit disposal remains idempotent; it is no longer required to settle idle after terminal failure.

The regression holds an ordinary render reply, queues cursor 20, starts an idle wait, and injects the actual Worker error handler. It requires that same idle wait to reject with the render's terminal code and verifies that later cursor 30 produces no graph commands. Before repair it fails its terminal-settlement watchdog assertion. After rebuilding the actual client, all ten retained temporal cases pass, including the nine previous cases. Full normal strict-CSP foundation also passes and discovers the regression. Reports, wire capture, images and lossless logs are retained.

The correction also refreshes current-source Core bindings without rewriting historical producer evidence. A fresh corpus check exposed three current paths changed by the original temporal candidate: capability generator, capability matrix and ownership Markdown. The failed check is preserved; binding-correction.json records those exact historical/current digests. The successor binding includes final correction inputs and real Git LF/CRLF verification. This is a provenance correction, not regeneration of authentic Core fixtures.

Prior complete review freshly passed 116 Python tests, eight native/WASM tests and the original browser journeys. This successor reruns relevant Core/inventory, wire, asset, build and full-foundation controls. Rust, ABI, native and WASM bytes remain unchanged; no rebuild of those unchanged artifacts or whole-suite rerun is claimed.

Independent re-review, PR/CI and queue delivery remain pending. Aggregate membership, frozen exports, scale, full accessibility, timezones and broader authoring-state ingress remain open. Nonzero load.pinned remains refused for temporal binding; pinFocused after readiness is the supported bounded route. No #45/M5 closure or publication qualification follows.
