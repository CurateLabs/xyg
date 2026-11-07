# Bounded trusted public Worker keyboard proof

Candidate only, based on 0a85b8da98ceb5dd0f2ef308f51c85a46f22460e;
accepted main remains 43c35f67b95ae4e78e3e96f200a0e6be8642199c.
No acceptance of pending PR1113 is presumed. Parent owns independent review.

The normal source-dist foundation gate invokes the unchanged two scheduling
cases and then a separate 7201/7202 pair of 1,000-node/1,000-edge cycles with
explicit 384 MiB arenas. The 16 MiB default still refuses 1k. The public Worker,
packaged client and WASM use unchanged default progressive load/scheduling.
No reply is held, layout frozen, or deadline increased. Real Playwright Tab
reaches the primary application through ordinary host DOM ordering.

ArrowRight focus and Enter Replace are required while native layout is
unfinished, with exact authored node UUID 01000000-0000-0000-0000-000000000000
and source index zero for selection. Each requires admitted trusted key events,
a command-count increase, default prevention and native stateChanged/outcomes.
All subsequent accepted publications, regardless of their progress count,
retain state up to the next intentional action; later Rust progress is required
separately. After convergence the journey verifies Toggle, Replace, Clear and
empty Escape. Empty Escape is admitted but does not prevent default or change
state. DOM focus remains on the application and polite text matches Rust's
summary. The peer remains untouched. Disposal leaves no attachment children or
late frames. Diagnostic reply copies are hashed then released; current replies
remain available for pixel/native-plane observations. The older cases' raw
records and oracles are unchanged.

Native GPU node state and native center planes correlate with actual 2D canvas
pixels near node zero. The host explicitly authors `--chart-focus: #ff00ff`;
initial unfocused pixels have no such color, focused publications must contain
it near the native center. This proves host-colored focus painting, not the
default theme. Native selected emphasis is separately required. Complete browser
XYGR digests replay against native and WASM; canonical requests retain all
1k source nodes/edges. The existing Rust viewport culling still applies to GPU
publications; no all-source-GPU-visibility claim is made.

Reproduction (Node 22, short disk-backed TMPDIR, supplied Chrome path):

```
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
node --test js/test/graph-progressive-camera.test.mjs js/test/graph-progressive-keyboard.test.mjs
XYG_GRAPH_SCHEDULING_REPORT=/var/tmp/keyboard-ci.json node scripts/wasm_foundation_smoke.mjs
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so node scripts/graph_session_public10k_replay.mjs /var/tmp/keyboard-ci.json.keyboard.json
uv run pytest tests/test_graphforge_contract_corpus.py -q
```

Producer inputs are byte-compared with the root's ABI401 build before artifact
reuse; `producer.json` binds those inputs and native/WASM bytes. No Rust changes
or shipping bundle commits. Logs preserve failed recorder attempts as failures:
the first attempt selected the Control modifier event rather than Enter; the
recorder was corrected. No controlled latency claim on this shared VM.

This advances only bounded keyboard proof. M4/#35/#36/#1015 remain open:
100k/1M, reliable simultaneous two-10k, latency/cold/peak RAM/GPU, full AA,
platforms, notebooks, exports and competitors are not qualified here. No API,
renderer, scheduler, LOD or semantic-selection implementation is added.

Open acknowledgements are compared browser/WASM; every Render and interaction
reply is compared in full across browser/native/WASM (the native Create ABI
returns a handle, not acknowledgement bytes). The initial replay count check
incorrectly required all source nodes in every GPU publication; the retained
failed log shows ordinary viewport culling, and the corrected check preserves
canonical request counts while retaining the original 10k GPU oracle.
The first full foundation attempt exposed the preceding removed host button
as the browser Tab starting point; the third case now reloads a fresh document
and orders its authored containers before trusted Tab, without product focus
changes. A second early verifier run rejected bigint source index zero against
a string expected value; numeric identity normalization corrected that harness
assertion. All failures remain in raw logs.

Qualified run: focus at Rust step 65 and Replace at step 105 are unfinished;
Toggle/Replace/Clear/empty Escape run after convergence at step 458. The focus
and first Replace publications contain 61 host-magenta pixels near the native
center. Both attachments reach step 458, with 66 primary / 60 peer commands.
The final verifier passes all 40 Node cases, and the qualified full foundation
command passes including existing temporal cases. Seven Core corpus tests pass,
including real autocrlf checkout. Full-worktree pre-commit, Ruff check and Ruff
format-check pass. No affected product/controller behavior changed, so the
unrelated 69-case legacy attachment branch and Rust builds were not repeated.
