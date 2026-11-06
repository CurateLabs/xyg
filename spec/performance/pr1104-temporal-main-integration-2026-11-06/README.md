# PR1104 temporal accepted-main integration

This normal merge joins producer 0768a35a377014066d27ba524e1a46004cfe61c7
and accepted main 885330e228b6ada9bff54ef1b903e5da2f79b45c. The prepared
local branch first fast-forwarded from its older ancestor to the producer.
There were no merge conflicts. No producer workspace was written.

Exactly four of the producer's 14,673 tracked paths change on integration:
engine and WASM temporal_graph.rs, the Node package test command, and
spec/design/temporal-graph.md. Each incoming index entry equals accepted main.
The other 14,669 producer entries remain identical, including symlink blobs.
Against reviewed 4c3c15f, 14,626 of its 14,632 entries remain identical; the
six exceptions are these four exact incoming main paths and the two previously
qualified consumer runner/spec repair paths.
The new Node temporal publication test and temporal receipts are exact incoming
main additions. The complete incoming path list and original producer blob
SHA256 manifest are bound by receipt.json. All cache, naming, consumer-repair,
original transcripts, issue snapshots, and historical receipts remain intact.
Exactly three frozen path/hash scanner exceptions and all gates are unchanged.
The 8 MiB raw slab/request bound plus explicit additional metadata, deterministic
linked LRU, immutable-file requirement, admission/page behavior and exact
provenance/cancellation contracts remain as specified in rust-engine §5.1a.

Fresh combined native, paint client, and wasm32 production artifacts are built
locally. The normal WASM packager enforces unchanged 1882 KiB raw and 768 KiB
Node22 gzip6 caps; receipt.json binds their actual bytes and hashes. The installed
consumer smoke builds and consumes wheel/npm artifacts from this checkout with
the unchanged repaired port runner. Its checkout HEAD is the precommit producer;
qualification source/artifact hashes bind the combined working tree actually
exercised. Temporary fixture versions imply no release cohort qualification.

The receipt binds commands, environment, focused cache/temporal/native/WASM
checks, contract/naming/Core real-CRLF checks, inventory, ownership, packaging,
installed consumer report and losslessly compressed logs by raw/archive hashes.
The first Node temporal attempt preceded the optimizer output and failed only
on the absent packaged WASM file; its raw log is retained alongside the passing
post-package rerun. The broad roughly 800-case CI mutation suite was deliberately stopped after
passing progress to scope this unchanged-workflow integration to the active
graph wiring and WASM-asset cases plus the actual workflow verifier. Its
interrupted exit143 is recorded, not claimed as a pass. No current Core-bound source changed; no inventory declaration drift occurred.
Broader unchanged proofs remain historical evidence; no hours-long full Python
suite, 100M run, or new benchmark/competitor win is claimed.

Reproduce with Rust1.96, Python through uv, Node22 and the supplied Chromium:

```sh
CARGO_BUILD_JOBS=2 cargo build --release
CARGO_BUILD_JOBS=2 cargo build --release --target wasm32-unknown-unknown -p xyg-wasm
node js/build.mjs
node js/package-wasm.mjs
uv run python scripts/verify_wasm_assets.py
uv run pytest tests/test_stale_names.py tests/test_graphforge_contract_corpus.py tests/test_release_inventory.py tests/test_verify_ownership.py tests/test_audit_python_host_core.py tests/test_consumer_smoke_ports.py tests/test_stage_node_packages.py -q
uv run python scripts/consumer_apps_smoke.py --chromium /home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Final full-index binary patches from main and producer, commit/tree identity,
and exact changed paths are emitted after commit to target/task-tmp/delivery/;
the handoff reports their hashes to avoid a self-referential receipt. Final
external integration/port review, push, remote CI and queue remain with parent.
#110/M7/larger-than-RAM/browser-WASM/full-host/100M/#111–113 acceptance stays open.
No publication, RC reservation, issue closure or GitHub mutation occurred.
