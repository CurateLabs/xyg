# Bounded GraphSession P1 local implementation

Base: `5840b4790660d8bafa59e9b5308b450c51f55713`; isolated branch
`t3/rust-graph-session-p1`. Existing S5a package/source and receipts are preserved.
This directory is append-only local evidence, not issue/scale acceptance.

Slice 1 adds complete selection/result-row projection to successful publication
replies. `selection-engine.log` records 127 passing interaction tests using:
`PATH=/home/ubuntu/.cargo/bin:$PATH CARGO_TARGET_DIR=target/task-tmp/p1 cargo test -p xyg-engine graphforge::interaction --lib`.
The first local test attempt needed Cargo's explicit PATH; a test initially
passed session-local refs to the transport-only encoder and was corrected.
Production semantics were not weakened.

The existing `WireSession` `(nodes+edges)*8192` charge alone exceeds the
384 MiB cap for 100k nodes/200k edges. Other existing charges make admission
stricter. No capacities increased; no scale acceptance claimed. Sparse
projection output does not solve this remaining source-residency limitation.

C ABI398, WASM35, Scene34 and painter17 remain unchanged. API inventory is
parent-owned and intentionally untouched; parent must refresh it after integration.
No widgets, channel/controller, Python policy or public host API is added here.
