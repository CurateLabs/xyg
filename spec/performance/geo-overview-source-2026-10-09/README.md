# Issued overview source ownership evidence

This checkpoint proves typed private ownership and static density composition;
it is not a massive-data timing benchmark or #50/#39 closure. The executable
contract is [geo-overview-hosts](../../design/geo-overview-hosts.md).

`source-sha256.json` binds the complete current Rust/Cargo source and the relevant
canonical and generated host sources. `environment.json` identifies the fresh
native383/WASM33 pair and current combined checkpoint. The borrowed parent
artifact source freeze is byte-identical to this checkpoint for all Rust/Cargo
sources; these exact file hashes bind the host proof.
`pre-membership-checkpoint/` preserves the original reviewed adapter proof before
the parent membership engine merge. The current tests rerun on the combined pair.
No Rust or ABI signature was changed by this slice. Build outputs are ignored.

`node-native-wasm.txt` records 24 actual tests. The shared typed owner runs against
both native C ABI and the real packaged wasm32 module. Faults occur after real
allocation and behind the captured producer callback. Test-only receipt observers
clean otherwise-unknown owners for isolation; product code does not gain that
authority. Five-view tests keep five tiny two-row views live and publish their queries
sequentially. They preserve independent snapshots with one replacement candidate
within unchanged handle/Data caps; they do not prove five simultaneous
replacement publications. Eleven baseline owners plus five Queries exhaust
the sixteen-handle cap, so legacy29 cannot allocate a seventeenth Data owner.
Native Node composition additionally exports all six formats. Python's 25 tests
include the new owner, ordinary overview, typing and selected-ingress controls;
the new owner tests cover notebook-loop synchronous export and asynchronous
admission/cleanup settlement. `hooks.txt` records the required repository hooks.

Reproduce from this worktree with the commands in the design contract, plus:

```sh
cargo build -p xyg-core --release
cargo build -p xyg-wasm --target wasm32-unknown-unknown --release
node js/build.mjs
node js/package-wasm.mjs
node scripts/gen_geo_overview_hosts.mjs --check
uv run ty check
python3 scripts/verify_ownership.py
```

The exact unknown26/27/28/29 allocation guards, explicit native overview
host/widget rejection, nonfinal data-domain counts and unsupported feature-level
membership remain visible. Browser public Worker paint/controller evidence is
owned by the separate controller slice; it is not inferred from these Node tests.
