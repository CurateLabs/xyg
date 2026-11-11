# Per-call UUID tooltip classification

This continuation optimizes Python transport classification without changing
Rust geometry, layout, LOD, admission, source identity, callback or wire policy.
It does not complete #1015, #36 or milestones 4–7.

A failed public 100k notebook profile identifies repeated semantic-row and
encoding work. The encoder already discovers canonical UUID text to select its
existing 16-byte representation. After discovering an exact builtin UUID string,
it now uses a local string classifier for that column. Other scalar columns
retain the original validator. Any later non-builtin string value, including
null or a compatible subclass, permanently restores the generic classifier for
the rest of the column. Each next column starts generically, and the local
function/cell reference is cleared before plane lowering. Unsafe integers,
heterogeneous values, sparse/null flags, dictionaries and complete bytes retain
their previous behavior. No source/epoch/UUID cache is introduced: in-place edits
are read again on the next encode.

The rejected broad text shortcut is retained. Its first private/mixed runs
looked promising, but the public 38-case comparison flagged tiny boolean and
numeric regressions. UUID-specific dispatch avoids charging ordinary scalar
columns. The intermediate helper still added cost to mixed-subclass columns;
per-column backoff restores the original path after the first such value.
Normal local-reference retirement is included in the final measured source.

The final unchanged-harness CodSpeed walltime pair is
[baseline6af44646b1273b04de9fbb93 → final6af4498ee07b2b940fc1561b](https://app.codspeed.io/CurateLabs/xyg/runs/compare/6af44646b1273b04de9fbb93..6af4498ee07b2b940fc1561b).
The baseline startup plugin loads the exact Git-parent encoder before collection;
fixture construction and assertions are unmeasured. Maximum rounds are five,
warmup is zero. All 62 cases pass their complete metadata/plane/padding oracles.
The six graph rows are classified as improvements; all 56 scalar, subclass,
null/missing and fallback controls are classified unchanged. All slower samples
are preserved too; these classifications are not confidence intervals or proof
of improvement for every input.

| Encoder work | Baseline | Final |
| --- | ---: | ---: |
| 100k node rows | 189.41 ms | 152.00 ms |
| 200k edge rows | 825.66 ms | 620.38 ms |

These measure encoding alone. No competitor, convergence, full-notebook speed or
process/GPU memory win is claimed. Normal CodSpeed discovery now collects 219
rows across the same nine modules, including 62 tooltip cases. All 163 previous
IDs survive; 56 scalar controls were added, none renamed or deleted. New type
controls include builtin-first mixed NumPy/subclass UUIDs and UUID columns
dominated by nulls or missing keys.

Fresh source checks include 180 Python 3.12 and 118 actual Python 3.11 contracts;
59 strengthened writer-observation guards were subsequently rerun on each
interpreter after a test-only improvement. Refused schemas must make zero writer
calls. The overly broad isinstance shortcut independently fails four targeted
subclass-identity cases. 49 complete predecessor comparisons pass per interpreter;
13 complete Node logical-column comparisons and bit-change negatives pass.
The benchmark oracles separately cover full aligned payload buffers. Scoped
Python typing passes. No earlier fixture or receipt is rewritten.

Actual stock JupyterLab4.6.5/CPython 3.12.15/Chromium149 uses the final source,
matching native405 and current browser client. The profiled 1k+1k journey passes
(CodSpeed 6af44a312c4189d7425a5688, one functional iteration). The profiled 100k
attempt FAILS: primary 17 remains live, but the 1k peer stops at 73 after its
unchanged wall deadline. Complete UUID selection, geometry populations and two
owner/two worker cleanup assertions pass. The raw failure and dropped sampling
events remain evidence, not a timing pass.

A distinct observer-effect control explicitly sets
`CODSPEED_PROFILER_ENABLED=false`, retaining CodSpeed walltime and the unchanged
stock journey, source, data, assertions and deadlines. That 100k+1k run PASSES
[CodSpeed 6af44afd2c4189d7425a56ae](https://app.codspeed.io/CurateLabs/xyg/runs/6af44afd2c4189d7425a56ae):
all 100k nodes/200k edges, trusted native UUID0 pick, exact selected masks, isolated
peer, no page errors or external requests, and three owner/four worker teardown.
At cancellation the primary is 9 with a pending build and the peer 137; neither
has converged. This is one bounded functional success under a different profiling
condition. It does not prove the original failure's cause, reliable deadline
acceptance, sustained interaction performance or a causal whole-notebook gain.
Earlier profiled and pre-retirement-source attempts remain preserved separately.

`checks.json` records commands, inputs, source/artifact pins, complete archived
logs/reports/captures and phase boundaries. All 324 compiled inputs, nine runtime
artifacts and six static copies remain Git-parent exact; no Rust, WASM or client
build is needed. The module remains 1,884,503 raw/786,337 Node22 gzip6 bytes
(95 gzip bytes spare), ABI405/WASM38, 551 native declarations and 68 WASM functions.
Budgets, defaults, timeouts and package caps remain unchanged.

The earlier full-foundation GPU context-loss failure remains unresolved; no new
full-foundation pass is claimed. Installed-host breadth, reliable 100k/large
ladders, complete performance/accessibility/exports, global budgets and competitor
acceptance remain open. Final independent review, current-main freshness,
hosted checks and the required merge queue govern delivery.
