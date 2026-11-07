# PR1104 installed-consumer port allocation

The reviewed cache/main integration is3069881d49ebe59c2e4d01940fa39d69610b6a46,
with normal parents reviewed4c3c15f and acceptedmain9a75c4c0. This subsequent
runner correction addresses actual CIjob128184209481 on PRhead4c3c15f.

The consumer runner independently chose and released four ephemeral ports.
CI assigned59615 to both Streamlit and Node. Node logged EADDRINUSE; the
browser opened the Streamlit host where it expected the Node app and failed
reading its absent status element. The browser exception is a consequence, not
the cause. Original selector/assertion/timeout and isolation checks stay intact.

The runner now binds all allocation sockets simultaneously, reads their
distinct assigned ports, then closes them before launching the consumers.
This prevents reuse within its own batch. It does not provide an exclusive
lease through packaging/startup; unrelated later bind races remain failures.
Every socket closes if partial binding fails. No product, ABI, cap, package
version policy, retry, timeout or release-gate relaxation is introduced.

The deterministic allocator model represents a valid OS that immediately
reuses any closed port: the original helper selects the same port four times.
Fresh tests require four distinct ports and complete cleanup on success and
partial failure. The installed wheel/npm browser journey exercises the actual
runner and retains all original chart, selection, export, isolation and disposal
assertions. Results and precise environment/source/artifact/log bindings are
in checks.json. The first local attempt correctly refused missing packaged
WASM assets in the fresh integration worktree; its failure remains preserved.
Those required assets were then produced normally without changing gates.

Reproduce with Node22/Rust1.96 and the normal packaged assets:

```sh
uv run pytest tests/test_consumer_smoke_ports.py tests/test_stage_node_packages.py -q
cargo build --release --target wasm32-unknown-unknown -p xyg-wasm
node js/package-wasm.mjs
uv run python scripts/consumer_apps_smoke.py --chromium /home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Earlier integration/cache/history receipts remain unchanged. The integration
receipt's complete reviewed-file manifest still binds unchanged cache/native
product sources; only the smoke runner and its normative application-consumer
prose differ among its pre-existing files. The new regression file is test-only.
The smoke report Git field identifies its checkout base, while final runner
source hashes identify the exercised correction. Temporary fixture package
identities prove no accepted release cohort, selected-Core/platform or #108
qualification.

Independent final integration/correction review, push/current-head CI and queue
remain required. #110/M7 and larger-than-RAM/browserWASM/full-host/100M/#111–113
acceptance remain open. No release or milestone closure is claimed.
