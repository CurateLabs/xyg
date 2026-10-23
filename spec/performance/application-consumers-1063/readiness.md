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
