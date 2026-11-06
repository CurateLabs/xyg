# Public retained browser continuation — bounded #35 slice

Task workspace `/home/ubuntu/.t3/worktrees/xyg/t3-f18c1bda`, exclusive branch
`t3/browser-progressive-continuation`. Dispatch base `74195403`; accepted main
`5e00c6b9147b67f20046cdfa6bd77aa413c18474`, tree
`2bb6a0c3841d5cba19f6ed74b41524274d0a1ce7`, merged normally as `88a52156`.
The sync merge was made before the full-worktree hooks (a procedural miss);
all required hooks and Ruff checks passed subsequently on the final worktree.
No other checkout was edited. No push, PR, issue mutation or publication occurred.
Independent final-diff review belongs to the parent and remains required.

The existing experimental attachment now continues `load.progressive: true`
through retained Rust opcode 15 in its claimed WASM Worker. The initial picture
crosses a paint boundary before later work. Eight native steps per opportunity,
one outstanding UI command, a 30-second wall deadline, immediate reply admission
and no held ACK limit scheduling. No JavaScript force, done inference, source
position calculation, resource-limit change, or ABI change is introduced.
Nonzero companion pages coalesce a step with a same-state Rust Render to retain
aligned rows. No public update/supersede method is invented: disposal drains the
old lifetime before a new attachment reuses its Worker. Existing lifetime and
revision admission remains in the packaged lane.

`progressive.json` records genuine unheld render events, Rust ticks/done, pixel
observations, trusted four-node keyboard admission while unfinished, heartbeats,
commands, two independent Workers, dispose/recreate, stale/terminal fault injection
and disposal with a held in-flight reply. Holds occur only in that fault control.
Authored coordinates first paint without a report, pins remain fixed, and explicit
false performs no continuation. Empty sessions finish at zero ticks. Each nonempty
unheld rung presents many intermediate frames from tick 1 through Rust done at
458; render callbacks do not imply individual ticks. These are functional
observations on this VM, not accepted latency or competitor thresholds.

The 0/4-node runs use the unchanged 16 MiB default. The 1,000-node ring selects
the existing explicit 384 MiB arena ceiling; the default-arena refusal is also
asserted. No default or maximum was raised. The first attempted synthetic fixture
omitted required identity planes and used one-based endpoints; Rust refused it.
After fixture repair, a 1k focus probe on the initial viewport also returned
GF_INTERACTION_INVALID. The retained 1k run proves render/progress/heartbeat only;
trusted unfinished interaction is established by the four-node run. No 1k focus,
pointer or large-scale interaction claim follows. Legacy controls independently
cover trusted pointer/CSS/shadow/default-timing behavior.

`progressive.json.replay.json` contains the real four-node public command/reply
bytes. `uv run python spec/performance/graph-browser-continuation-2026-11-05/replay.py`
replays them through the existing native transport: progress planes match exactly,
paint centers match with absolute tolerance 1e-9 (no relative tolerance).
This is native/WASM checkpoint parity, not Python widget integration.
`legacy.json` records all 69 preexisting attachment journeys; `foundation.json`
records the full strict-CSP foundation/Worker scheduler controls. No generated
client bundle, native library or WASM module is committed; manifest hashes identify
the locally rebuilt test artifacts. Negative foundation screenshots are retained.

Reproduction from this workspace (Node 22.23.4):

```bash
export PATH=/home/ubuntu/.cargo/bin:/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
npm ci
uv sync --group dev
cargo build --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
XYG_GRAPH_PROGRESSIVE_ONLY=1 XYG_GRAPH_SESSION_REPORT=/tmp/progressive.json node scripts/graph_session_controller_wasm_smoke.mjs
node scripts/graph_session_controller_wasm_smoke.mjs
node scripts/wasm_foundation_smoke.mjs
node --test js/test/graph-session-controller-wire.test.mjs js/test/graph-session-gpu.test.mjs js/test/package-wasm-contract.test.mjs js/test/package-wasm-manifest.test.mjs
uv run python spec/performance/graph-browser-continuation-2026-11-05/replay.py
cargo test -p xyg-engine --lib graphforge::interaction::tests::wire::p1
uv run pytest tests/test_graph_session_abi.py tests/test_graph_session_python_transport.py -q
uv run pytest tests/test_release_inventory.py tests/test_wasm_ticks_chartview_contract.py tests/test_wasm_density_chartview_contract.py -q
uv run python scripts/check_release_inventory.py
uv run python scripts/gen_abi_manifest.py --check
uv run python scripts/check_public_api.py
uv run python scripts/verify_ownership.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The inventory was regenerated officially with `--write`; all 685 review gaps
remain explicit. Rust P1 controls: 14 passed; native transport: 38 passed;
contracts: 34 passed; JS wire/GPU/package: 20 passed. Client build includes the
TypeScript check. Full pytest, the rendered 10k/100k/1M ladder, all platforms,
Python notebook/widget progressive delivery/cancellation (#1015), broader #36,
and full #35/#108 acceptance remain outstanding. Literal Node async-compose
wording remains unresolved; this change leaves its synchronous/static contract
unchanged. No hover/picked-target (#1095) or version (#884) product code changed.
No package, competitor, milestone or publication qualification is claimed.
