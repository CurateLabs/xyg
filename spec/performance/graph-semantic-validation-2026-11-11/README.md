# Exact semantic input validation

Parent: `968c5588bf5a0d92d96ec983f272e7a06c408daa`.

The failed public100k notebook profile identified repeated Python iteration
over semantic integer planes before native style and paint-layer resolution.
Python now uses complete integer minimum/maximum reductions for planes longer
than eight values. Tiny planes retain the original scalar checks. Integer
dtype/dimension validation, code range0..7, uint32 flag representation, error
precedence and all narrowing/copy operations remain unchanged. Rust continues
to own vocabularies, interaction bits, metric domains and actual paint policy.
This is neither sampling nor a changed LOD, cap, ABI or fallback policy.

## Measurements and rejected variant

Every timing run uses CodSpeed walltime. The committed
`benchmarks/test_codspeed_graph_semantic_validation.py` constructs fixtures
outside measurement and checks every returned plane byte afterward. Its
fourteen cases cover empty/tiny, 1k, 100k and200k contiguous and reversed,
strided, non-native-endian inputs. Existing CI discovers the benchmark through
its `test_codspeed_*.py` glob.

The final matched comparison uses five rounds, zero warmup, identical
benchmark cases and native artifact. A private pytest-session plugin loads
the exact predecessor function AST into the already loaded native binding
module for the baseline; fixture/oracle work and that load are unmeasured.
The final run uses the production function without the plugin.

| Rows/layout | Predecessor | Final |
| --- | ---: | ---: |
| 1k contiguous | 660.21 µs | 18.62 µs |
| 1k strided/endian | 665.53 µs | 28.19 µs |
| 100k contiguous | 64.14 ms | 200.58 µs |
| 100k strided/endian | 65.04 ms | 746.70 µs |
| 200k contiguous | 128.99 ms | 432.69 µs |
| 200k strided/endian | 130.33 ms | 1.65 ms |
| 8 contiguous | 13.55 µs | 13.93 µs |
| 8 strided/endian | 15.05 µs | 15.11 µs |

[Complete fourteen-case comparison](https://app.codspeed.io/CurateLabs/xyg/runs/compare/6af42feee07b2b940fc1524a..6af43046b38b19452e041bb2).
No final case is classified as a regression; all slower samples remain in the
raw results. Short measurements do not establish a confidence interval, an
end-to-end notebook win or competitor acceptance.

The first universal-reduction variant regressed empty and tiny planes. A
separate five-round crossover comparison covers0/1/8/16/32/64/128/256 rows and
places the observed crossover between8 and16. The retained scalar path resolves
that defect. Both rejected variants, comparisons and exact source snapshots
are preserved. An earlier run changed benchmark IDs between the private and
committed harnesses; its new/dropped rows receive no comparison credit. The
matched baseline/current runs above correct that setup error.

## Correctness and actual notebooks

The predecessor/current function controls compare311 cases byte for byte,
including integer widths, byte order, strides, empty planes, uint64 extremes,
negative/out-of-range codes and flags, NaN payload/signed-zero metric bits,
input immutability and exact error type/message/precedence. Public native tests
also verify complete style and paint-layer outputs under source permutation
for both themes and node/edge modes. Late invalid values must refuse before
narrowing. Native policy and existing visual oracles remain required.

Fresh final checks pass176 Python3.12 cases, including all three actual browser
semantic paint tests, and155 Python3.11 cases. The initial119-pass run had three
browser skips because Chromium was not explicitly selected; those skips receive
no browser credit, and the final explicit-Chromium run passes all three.
The first commit hook then rejected an unescaped dot in a new test's regex.
The assertion now requires literal dots; production code is unchanged. All140
ingress cases are rerun on each interpreter after that test-only correction;
the earlier complete affected-batch and browser logs remain separate evidence.

The actual JupyterLab4.6.5 1k+1k journey passes exact UUID selection, GPU masks,
peer isolation and native/thread cleanup. Its single CodSpeed round establishes
functional coverage only. **Public100k still fails its unchanged30-second peer
deadline**: primary step9 remains alive/building; peer step105 is failed.
Exact selection and cleanup of three owners/three workers pass. This state
sample is not a throughput comparison, and no failed timing receives pass
credit. The original harness, source sizes and assertions are unchanged.

The saved failed-run profile is Python-symbolicated. Its larger compiler thread
has13,031 inclusive compile samples,6,319 tooltip-encoder samples and2,278
`_kind` samples. These are diagnostic sample weights, not elapsed durations or
cross-run improvements. They direct the next investigation toward remaining
row/tooltip publication work instead of treating this narrow win as completion.

A separate independent read-only native lock audit confirms recurring graph
commands use per-entry locks. It records narrow duplicate-Open/document-copy
exceptions and conditional same-owner synchronous ACK retirement; none proves
the observed fresh-instance notebook cause. No native lock or retirement
behavior changes here.

## Reproduction and provenance

Use Node22.23.4, CPython3.12.15 or the existing3.11.17 environment without
synchronization, explicit `PYTHONPATH`, `XYG_NATIVE_LIB` and `TMPDIR=/var/tmp`.
Run the committed benchmark through `codspeed run -m walltime --base <run>
--profile-folder <precreated-folder> -- uv run --no-sync pytest --codspeed
--codspeed-mode=walltime --codspeed-warmup-time=0 --codspeed-max-rounds=5 -q
benchmarks/test_codspeed_graph_semantic_validation.py`. Add the archived
`historical_semantic_baseline` pytest plugin only to reproduce the predecessor.
Actual notebook checks use the unchanged `bench_graph_native_notebook.mjs`
through `codspeed exec`, explicit installed Jupyter/Chromium and a fresh report.
Exact commands, source/fixture snapshots, profiles, raw failures and public
captures are hash-bound by `checks.json`; private Jupyter runtime/auth files
and raw JIT dumps are excluded. Terminal JIT dumps remain locally preserved
with hashes.

The47-parent successor retains earlier receipts,324 unchanged compiled inputs,
nine runtime artifacts and six static copies. No native/WASM/client rebuild is
claimed. Native405/WASM38 and all declarations/exports remain unchanged;
WASM stays1,884,503 raw /786,337 Node22 gzip6 bytes,95 gzip bytes below the
unchanged cap. Full-worktree gates and independent final review remain explicit
commit/delivery requirements.

Public100k notebook acceptance, broader publication/renderer work, global
memory, all-host/scale/accessibility/export/competitor evidence and milestones
4–7 remain open. Current-head hosted CI and the required merge queue govern
delivery; this checkpoint claims no shipping qualification.
