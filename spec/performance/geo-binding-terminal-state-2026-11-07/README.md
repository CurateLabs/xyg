# Terminal cancellation, observer identity and snapshot isolation

This correction preserves reviewed candidate `7c11bc54` and all earlier receipts.
Independent final reviews found four defects: a reader-raised CancelledError
could poison every later close; snapshot charts shared mutable authoring values;
reentrant Node destruction dropped terminal notifications; Number/BigInt handle
representations used different observer keys. The pre-fix regressions reproduce
two Python failures and four Node failures.

The binding distinguishes source-owned cancellation counts, reader-originated
cancellation and genuine waiter cancellation. Source-owned requests are
acknowledged; caller cancellation still propagates. Last-good frames survive
failed reads. Cleanup never waits on an already terminal cancelled child, so
private-frame release and registration teardown remain available even inside a
caller's cancellation handler. Tests cover retry after reader cancellation,
repeated close, surviving leases, and the original thread/cancellation controls.

Python and Node copy authored query, camera and style values at bind time and
for every snapshot, retaining the actual opaque source object. Python borrowed
source-digest memoryviews become owned bytes rather than copying native owners.
Tests mutate authored and returned styles/queries/cameras and verify later
snapshots, future frames and ordinary SVG provenance validation remain correct.

Node observer maps normalize handles before lookup/publication/destruction.
A reentrant destroy preserves the captured terminal snapshot and subscriptions
until notification drains. Nested terminal destruction is guarded, and binding
construction that is refused during destruction rolls back source registration.
Callbacks remain synchronous notifications with isolated asynchronous rejections.

Initial development runs exposed a memoryview deepcopy failure and a replacement
fixture reusing its prior query sequence; both logs are retained without pass
credit. Native query sequencing was not relaxed. The replacement fixture authors
a new sequence after the previous binding's admitted query. Final commands,
source/artifact bindings and lossless logs are in `checks.json`. No native/WASM
or browser producer changed; artifacts are reused by verified digest.

Current-main integration is retained. Final independent re-review, hosted CI and
queue delivery remain pending. Mounted native replacement, mixed tiles, all-host
export/accessibility and scale/five-view/competitor acceptance are still open;
this does not close #50/#39/M6 or establish a release cohort.

Final fresh validation passes 157 Python tests and 38 Node tests, plus type
checking and semantic inventory checks. Snapshot byte isolation covers ordinary
Uint8Array, Node Buffer and SharedArrayBuffer-backed inputs. Built-in byte
constructors ensure owned copies; Buffer.slice and structuredClone of shared
backing stores would not suffice. Constructor refusal during terminal delivery
also proves source registration rollback. Original shipping artifacts remain
unchanged and are verified by digest; no rebuild or new browser run is claimed.
