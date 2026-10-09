# Shared pointer-capture follow-up

The Python3.11 floor gate identified direct pointer acquisition outside the
existing shared capture policy. The native host now imports and uses
`captureGesturePointer` from `50_chartview`, including its guarded acquisition
and release, capture-loss callback and trusted buttonless-move guard. The
stable host element owns capture across child painter replacement.

The updated real Chromium155 fixture activates capture, explicitly loses it,
then verifies that a continued primary-button move issues no camera request.
Its27 preparation requests and all earlier input/recovery checks still pass.
The existing five-view fixture passes;47 static client security checks and the
shared chart gesture capture-loss behavior test pass. The client was rebuilt,
with fresh hashes recorded here; native and WASM artifacts are unchanged from
the paired combined-input checkpoint. Independent source review is green.

Earlier evidence remains its original checkpoint. This change does not add
geometry policy or establish large-scale latency or new host journeys.
