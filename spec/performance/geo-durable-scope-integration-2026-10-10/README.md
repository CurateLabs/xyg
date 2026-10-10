# Combined durable recovery and hierarchy Scope credits

This fresh205-input build normally combines reviewed994fe1f029 and995967aac74 with the989/991/992 recovery layers already in integration993. The compiler manifest includes every tracked Rust/Cargo/vendor input and packaging configuration, including the new hierarchy boundary tests. All hashes match the integrated source. Artifact SHA256 and unchanged limits are recorded in artifacts.json; ABI383/WASM33, Scene32, painter15 and the O3/inline100 profile are unchanged.

The combined engine passes1494 tests and strict workspace/all-target/all-feature Clippy. The full default-feature `cargo test --workspace` run also passes (53 core,1494 engine,65 WASM and two single-test crates). The package contract passes. Native/WASM match all12 complete mutation packets,12 complete selected-publication packets and Snapshot-local binary controls. Nonce0 mutation/publication packets retain their archived baseline. All84 complete, unnormalized hierarchy native packets match the pinned old baseline exactly after validating creation issuer/publication bindings; the current capture is retained as deterministic gzip9/mtime0, and the baseline is in the parent hierarchy Scope-credit evidence.

Both independent actual Chrome155 Worker proofs pass under strict CSP with no external traffic or CSP errors. Accepted-binary controls include historical snapshots, lost allocation/retirement/Release replies, cloned dispatches, older genuine errors, sixteen capture contexts and twelve buffer-mutation schedules. Selected19 dispatcher controls include exact304-byte publication and272-byte47 confirmation, current-call rejection/success, modified replies, six nonmatching length/tag cases, literal u64 selection and scope cleanup. This dispatcher proof does not establish public19 host adoption.

Reproduce using the unchanged release builds and existing scripts:

```sh
cargo build --release -p xyg-core
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
node js/build.mjs
node --test js/test/package-wasm-contract.test.mjs
node js/package-wasm.mjs target/wasm32-unknown-unknown/release/xyg_wasm.wasm
cargo test --workspace
cargo clippy --workspace --all-targets --all-features -- -D warnings
# Set XYG_NATIVE_LIB to the platform cdylib before each paired script.
node scripts/geo_selected_mutation_recovery_conformance.mjs
node scripts/geo_selected_publication_recovery_conformance.mjs
node scripts/geo_snapshot_recovery_conformance.mjs
node scripts/geo_hierarchy_scope_credit_conformance.mjs
node scripts/geo_overview_binary_smoke.mjs
node scripts/geo_selected19_capture_smoke.mjs
```

Paired mutation/publication scripts accept XYG_SELECTED_MUTATION_BASELINE and XYG_SELECTED_PUBLICATION_BASELINE pointing to their archived legacy-baseline.json. Set XYG_SCOPE_PACKETS to capture complete hierarchy packets and compare them with the decompressed baseline-packets.json.gz. Browser scripts use Playwright Chromium, or an explicit XYG_CHROMIUM path; the recorded local run uses system Chrome155. Native-only Scene warnings in the no-raster WASM build are preserved verbatim; default-feature workspace Clippy is strict. Every raw log is base64 with exact byte length and SHA256.

The new selected19 Worker proof/report uses the existing direct-browser CI lane. No new job, cap or compiler setting is introduced. Exact-head CI, merge-queue and actual-main proof remain integration gates. Final public35/36 adoption from PR996 is normally integrated. On the final aggregate,39 Python and95 Node cases pass (one existing opt-in skip), all selected/overview generators and the client build pass, and the independent strict-CSP actual Worker/WebGL proof passes against the same205-input artifacts. The new proof/report extends the existing geographic browser CI lane. Public19 publication hosts, hierarchy43/44 recovery and broader linked interaction, spatial refinement, massive phase and competitor evidence remain separate M6 gates.
