# S2 shared functionality budget and packaged validation

This is a new decision and passing package receipt after the retained failed
[S2 recovery](../graph-s2-recovery-2026-10-31/README.md) and
[two-candidate size repair](../graph-s2-size-repair-2026-10-31/README.md).
Neither failed receipt is changed or reclassified. #36, milestone 4 and final
release acceptance remain incomplete.

## Decision and measured cost

The repository requires a deliberate recorded decision for artifact growth.
S2 retains shared compound flag propagation and temporal state changes which
affect reachable WASM code. The session render implementation remains
Rust-only; this is not a new session WASM export or ABI allowance.

| Source | Optimized raw bytes | Node gzip6 bytes |
| --- | ---: | ---: |
| Reviewed S1 | 1,546,708 | 639,531 |
| Recovered S2 `5c3f51cd` | 1,547,915 | 640,615 |
| Retained forest repair `4515f482` | **1,547,779** | **640,527** |
| S1 limits | 1,547,264 | 640,000 |
| S2 limits | **1,548,288 (1,512 KiB)** | **641,024 (626 KiB)** |
| Remaining headroom | **509** | **497** |

Scratch-free forest validation saves 136 raw / 88 gzip bytes, preserving exact
first-error order and linear work. Forced outlining of the shared compound
helper saved no additional bytes and was reverted. No third candidate was
attempted. The retained S2 addition over S1 is 1,071 raw / 996 gzip bytes.
The new limits are the smallest next-KiB pair that admits this module, with
no reserved capacity for later slices. Rust 1.96.0, release O3/fat LTO/codegen1/
strip, inline threshold 100, pinned Binaryen 132 and `-O3 --all-features` remain
unchanged. No dependency, signature, validation or feature is removed; no
runtime speedup is claimed.

Independent policy/patch assessment `m4_s1_size_policy_review` reproduced the
actual Node 22 sizes and hashes, inspected the validator's error precedence
and O(n) retracing, and recommended this minimal pair after both experiments.
It found no further narrowly justified candidate with demonstrated sufficient
savings. This policy assessment does not replace final integrated review.

## Exact source and packaged result

The parent normally merged the reviewed S2 specification corrections and
accepted-main/S1 ancestry from `1bcf7f9e` into the retained repair. Rust inputs
remain byte-identical to `4515f482`; [source.json](source.json) binds all 287
producer, client, harness and affected preparation/specification inputs,
including the new packager. Validation ran before the containing commit;
the browser correctly records `artifactCommit: null` and source-dist scope.
There is no claim that its harness HEAD names uncommitted packaging metadata.

The actual Node **22.23.4** packager succeeds, writes the manifest and inline
payload, and copies assets into the browser package and Python static tree:

- Optimized module: **1,547,779 bytes**, SHA-256
  `27b922cb47294ebf8585a54be4d86d3fece91772a0bc7df432a34385fb26b678`.
- Node gzip6: **640,527 bytes**, SHA-256
  `c52977d626d8d7d048e964c1cf61d0bf0d0712b8f209f08694613f9a7c0aea96`.
- The optimized bytes exactly match the earlier retained repair candidate.
- Native ABI stays **396 / 529 symbols**; WASM ABI **34**, Scene **34** and
  painter **17** are unchanged.

[artifact.json](artifact.json) records sizes and both generations of limits.
[results.json](results.json) binds the source manifest, packaged manifest,
environment and ten exact command/raw/compressed-log records. Generated WASM,
inline payloads and client bundles remain ignored rather than committed.

## Executed verification

- Pinned release WASM build, actual packager and paired-asset verifier: passed.
- Actual Node 22 GraphForge/CoSE native-WASM parity, cross-host fixtures and
  Worker lifecycle checks: **51 passed, zero failures or skips**.
- Full original strict-CSP local-only Worker foundation: passed against these
  newly packaged source-dist assets. Cached Chromium **156.0.8078.4** was
  explicitly selected; there were no external requests. The report and six
  original no-refinement screenshots retain their own artifact/harness hashes.
- Cross-host golden and ABI manifest checks: passed.
- API preparation inventory regenerated and checked; only provenance metadata
  changed, with existing classification and acceptance gaps retained.

The preceding repair retains 1,878 Rust workspace tests, an independent
126,126-case first-error oracle tested before and after the repair, 100,000-node
forest fixtures, 134 Python tests, 136 native Node tests, Clippy, 673 ABI checks,
goldens and actual render/append smokes. Those historical results keep their
original source bindings. The final packaging decision changes no Rust source.
The original broad Node baseline diagnostics remain documented; a full Node
glob or multi-hour Python suite is not claimed green here.

Final independent review and CI must confirm this integrated diff and its
tight size headroom. This establishes no session browser/controller/host or
accessibility acceptance, interaction latency, competitor win, final release
artifact cohort, API freeze, registry publication or milestone completion.

## Reproduce

Use an actual Node 22 installation, the pinned toolchain and a local Chromium:

```bash
export PATH="/path/to/node22/bin:$HOME/.cargo/bin:$PATH"
cargo build --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
uv run python scripts/verify_wasm_assets.py
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
node --test --test-concurrency=2 --test-timeout=20000 \
  packages/xy-node/test/graphforge-wasm-parity.test.mjs \
  packages/xy-node/test/cose-wasm-parity.test.mjs \
  packages/xy-node/test/graphforge-cross-host.test.mjs \
  packages/xy-node/test/force-worker-lifecycle.test.mjs
XYG_CHROMIUM=/path/to/chromium node scripts/wasm_foundation_smoke.mjs
uv run python scripts/gen_graphforge_cross_host.py --check
python3 scripts/gen_abi_manifest.py --check
uv run python scripts/check_release_inventory.py
```

[commands.txt](commands.txt) retains the exact recorded commands. Raw output is
lossless `*.txt.gz`; use `gzip -dc FILE` to inspect it.
