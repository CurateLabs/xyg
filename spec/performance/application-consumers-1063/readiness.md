# Pre-PR readiness (#1063)

Verdict: ready for PR to `main`; remote required checks and merge-queue admission
remain lifecycle gates. Workspace: `/home/ubuntu/.t3/worktrees/xyg/t3-700b2dca`,
branch `t3/streamlit-vanilla-ts-tests`, base
`cbf2c0eb3fdc2bb4f1ec8dd1cede8f3f73158342`.

Independent reviewer: `review_1063`. Completed final review with no blocking
findings. Reviewed implementation diff SHA-256:
`fab841105dfc4b681a7c260b780e7915c1a16e8ce0160b5b808a4d89955fa559`.
Reproduce from the base and accompanying implementation with binary git diff,
excluding `spec/performance/application-consumers-1063` to avoid a self-reference.

Findings and disposition:

1. Source-only consumer execution was insufficient. Resolved by verified wheel
   installation, staged/packed npm artifacts, fresh environments and checks that
   package/native/client paths resolve inside those installs.
2. Executable parent directories could expose the other runtime. Resolved by
   dedicated executable-only PATH directories and explicit absence checks.
3. Active notebooks/FastAPI examples retained old support claims. Resolved by
   framework-independent wording and preserving historical provenance only.

BDD mapping: Streamlit app/rerun/export, Node app/render/update/DOM-selection/
disposal and missing-WASM cases are in `report.json` and their named tests;
coverage retirement is in `coverage.md`; absence from shipped artifacts is
covered by clean import/native-path assertions and wheel/sdist validators;
required CI gates/evidence retention are covered by 578 workflow-contract tests.
Full local results, intentional skips and reproduction commands are in README.

No production telemetry, external data migration or authentication surface is
added. Consumers use bounded synthetic inputs and local assets. This is an
intentional breaking support removal, with no compatibility shim; rollback is
a revert before release. Related #40/#54/#886 host requirements were reconciled
with explicit supersession; remaining shared release qualification stays open.

## Python-floor collection follow-up

CI run 39898664731, job 120235386107, failed collecting the AppTest module in
its intended XYG-plus-pytest-only Python 3.11 environment. The AppTest module
now treats absent optional Streamlit as a module skip; the locked dev lane and
required real-app gate remain unconditional.

Reproduced with a clean CPython 3.11.17 environment installed using
`uv pip install --python <env>/bin/python -e . 'pytest>=8,<9'`:
whole-suite collection succeeded with 7,412 tests; focused floor checks passed
49 tests and skipped only the absent optional Streamlit module. The development
lane passed all 9 dependency/AppTest checks, including all 6 Streamlit cases.
Raw output is in `python311-collection.txt.gz`, `python311-focused.txt` and
`streamlit-dev-followup.txt`. No full Python-floor execution is claimed locally.

Independent reviewer `review_1063` found no blocking findings in the follow-up
against base `191f9df04bda7e990805e380c53f9969a03444a5`. Reviewed patch SHA-256:
`452dfd7b44157f03c6ce3f7f135ab18d08fa5d374cb35f4b957f4eadc3acbfc7`
(before these evidence-only additions).

## Framework dependency isolation follow-up

The Matplotlib reference job on `191f9df0` activated pandas for the first time
through Streamlit's new dev dependency. The prior lock did not contain pandas;
no code under `python/xyg/pyplot` changed in #1063. The three observed optional
pandas failures are reproducible with pandas 3.1: its default Series backend
passes period ordinals instead of timestamp arrays, and the existing Rust
static route rejects date axes with `XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS`. Those
broader interop/static-route gaps are documented in `spec/matplotlib/compat.md`
and remain visible in `pandas-activated-reproduction.txt.gz`; no pandas test was
modified, skipped by new test code, or marked xfail by this follow-up.

Streamlit now lives in a separate `consumers` test dependency group. The core
and Matplotlib-only environments retain their prior dependency scope. The
required installed consumer gate imports AppTest unconditionally, runs all six
AppTests against the wheel with no checkout conftest injection, rejects zero
executed tests or any skip/error/failure in its JUnit result, and then runs the
real browser checks against that same installed environment. Thus optional core
collection does not soften required application proof. The historical dev-group
validation above predates this isolation; direct AppTests now use
`uv run --group consumers pytest tests/test_streamlit_consumer.py`.

Validation: 1,296 Matplotlib-reference tests passed, 4 optional tests skipped,
41 existing expected failures and 4 existing non-strict unexpected passes;
65 dependency/local-verifier tests passed; 19 required-gate guards passed;
all 6 installed Streamlit AppTests and the clean installed browser gate passed
with zero skips. Framework absence in the ordinary dev environment was also
asserted directly. Hooks, Ruff and type checks passed. See the accompanying
`matplotlib-reference-isolated.txt`, `consumer-group-guards.txt`,
`installed-streamlit-app-tests.*`, `isolated-consumer-report.json` and
`isolated-gate-contracts.txt` for raw results.

Independent reviewer `review_1063` found no blocking findings against base
`c92bc645663020a01bd9090869b0b6cffe2b6b49`. Implementation patch SHA-256,
excluding this evidence directory:
`92b5c2f2b8eccde32508673c9b391dac0a1be3d1a9174002c619c542c7e781d0`.


## Browser review follow-up

Greptile reviewed `191f9df0` with three non-blocking findings: canvas removal
alone cannot prove resource cleanup, visible download buttons cannot prove
exports, and a success-only upload loses failure evidence. All three are fixed.
CodeRabbit skipped automatic review because repository auto-review is disabled;
its skipped message is not counted as review evidence.

The Node journey retains the outgoing tick-attached view and GL context and
observes actual Worker termination. It requires destroyed state, empty listener
records, cancelled draw work, detached tick ownership, released GL context and
terminated Workers before remounting. Fault injection also exposed that the
pinned Playwright implementation treats an async predicate's Promise as truthy;
all tick/disposal polls now read the live module namespace synchronously. The
runner defaults to a failed exit until the complete report has been written.

The Streamlit journey clicks both real download buttons, captures filenames and
bytes, parses SVG chart content, and decodes PNG chart paint at the public
scale-2 dimensions (1440 by 720). CI uploads available evidence with
`if: always()` while keeping the browser gate unconditional and fatal.

Validation: all six installed AppTests and the clean installed browser gate
passed with zero skips; `make check-ci` passed 583 workflow, release-surface,
WASM-asset and scheduled-evidence contracts. The final positive run and artifact
hashes are in `review-consumer-run.txt` and `review-consumer-report.json`; the
report identifies source head `313af60d` plus the reviewed working diff below.
`review-ci-contracts.txt` contains the full CI contract output.

Mutation proof used copies of the browser script against the same installed
hosts. Before disposal, replacing `globalThis.outgoingView.destroy` with a no-op
caused the required synchronous disposal poll to time out at 10 seconds.
Replacing the captured download bytes with `Buffer.from('broken')`, separately
for SVG and PNG, failed the parsed-SVG and PNG-signature assertions. Every
mutation returned a nonzero exit and produced no success report. Raw outputs
are retained as `review-negative-{missing-destroy,broken-svg,broken-png}.txt.gz`.
No example or product source was changed for these injections.

Independent reviewer `review_1063` completed review with no blocking findings.
Reviewed base: `313af60de25ac04ea34b5c5c6451b082292fb5ed`. Implementation diff
SHA-256 excluding this evidence directory:
`2ec504e6130fead235e886716ea9105987c319217ef30fd155855ac6a0c743fc`.


## Cold npm cache follow-up

CI run 39901218330 on `7b19fb3d` passed the full Python suite: 7,351 passed,
169 skipped, 114 expected failures and 4 non-strict unexpected passes. Its
consumer step then failed because `npm install --offline` required cached
Koffi registry metadata that this runner did not have (`ENOTCACHED`). The
Release surfaces aggregate correctly failed because its required test job
failed and its dependent wheel matrix was skipped. The other required
independent inputs, including Python floor and Matplotlib reference
compatibility, succeeded.

The clean consumer install now uses a new temporary npm cache and permits
registry fetches for the FFI dependency. All XYG packages still come from local
packed artifacts. A package override selects the exact Koffi version from the
existing Node host lockfile; post-install checks require that version and
resolve Koffi within the clean install. Scripts remain disabled and browser/app
runtime isolation is unchanged. The report records the Koffi version and fresh
cache proof. This avoids relying on a warm runner or broad dependency drift.

Reproduction with an empty npm cache and offline `koffi@3.1.4` installation
failed as observed in CI (`cold-npm-offline-reproduction.txt`). The repaired
full consumer gate passed all six installed AppTests, both browser journeys,
cleanup/download assertions and optional-WASM failure behavior with a fresh
cache and Koffi 3.1.4. Raw results and artifact hashes are in
`cold-npm-consumer-run.txt` and `cold-npm-consumer-report.json`. The report
identifies source head `7b19fb3d` plus the reviewed working diff below.

Independent reviewer `review_1063` found no blocking findings. Reviewed base:
`7b19fb3db4f71da7824295b7793e925819167f80`. Implementation diff SHA-256,
excluding this evidence directory:
`bceffadb6920129a7f92964a07ac76b7041bc2c4138f974b16f2e6931774fb02`.
