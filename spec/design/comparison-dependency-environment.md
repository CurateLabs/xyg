# Manual comparison dependency environment

This contract repairs dependency drift in the existing manual ceiling lane.
It supplements [live aggregation comparison](live-aggregation-comparison.md),
[benchmark methodology](../benchmarks/methodology.md) §4, and dossier §12.
It does not qualify an actual comparison or satisfy #11/#108 publication gates.

## Hosted causal evidence

The retained originals at commit `82641839`, under
`benchmarks/results/live-aggregation-2026-10-24/hosted-main/`, bind hosted run
`40066499687` to source `a8b3e10801fa3c1b96eddd7b244a1d64e0778bad`.
Those bytes are immutable; the repair does not rewrite their report, log,
workflow, producer, hashes, or failure outcomes.

The job log proves this sequence:

1. Unqualified `uv venv` selected runner CPython **3.14.6**. This workflow did
   not contain a `setup-python` action.
2. `uv pip install --constraint benchmarks/requirements-ci.lock` installed
   **NumPy 2.4.6**, **Numba 0.66.0**, and the comparison stack.
3. The following native-backend check invoked `uv run python`. It downloaded
   NumPy, uninstalled 12 packages, installed 12 packages, and printed `native`.
   That assertion tested XYG's backend, not competitor importability.
4. The actual report records **NumPy 2.5.1** and **Numba 0.66.0**. All twelve
   competitor attempts (six Plotly aggregate, six Datashader aggregate) exited
   before `META`, with `ImportError: Numba needs NumPy 2.4 or less. Got NumPy 2.5.`

The source mechanism agrees with those observations: project `uv.lock` resolves
NumPy 2.5.1 for Python >=3.12; comparison constraints pin NumPy 2.4.6.
`uv pip install` applies the comparison constraints to that installation, while
subsequent ordinary project `uv run` synchronizes against the project lock.
Pinning Python to 3.12 alone would still select the incompatible project NumPy
if implicit synchronization remained. The NumPy constraint and Numba's import
check must remain intact.

Inspect the exact retained evidence without modifying it:

```bash
git show 82641839:benchmarks/results/live-aggregation-2026-10-24/hosted-main/job-120790765112.log.gz | gzip -dc
git show 82641839:benchmarks/results/live-aggregation-2026-10-24/hosted-main/density-comparison-a8b3e10801fa3c1b96eddd7b244a1d64e0778bad.json.gz | gzip -dc
git show a8b3e108:uv.lock
git show a8b3e108:benchmarks/requirements-ci.lock
```

## Execution contract

The existing workflow creates `.venv` with `uv venv --python 3.12`, matching
the Python target recorded in the comparison constraint file's generation
command. Existing setup-uv supplies interpreter discovery/download; no new
action is needed. The constraint file was compiled for Linux x86_64; selecting
the same Python minor does not prove macOS arm64 wheel compatibility, so the
actual hosted install and import checks remain required.

Every constrained install explicitly targets `.venv/bin/python`. Every later
workflow Python invocation uses that interpreter directly: native/dependency
preflight, both benchmark modes, comparison report verification, ceiling
summary, and both ceiling plots. None invokes a project resolver. Existing
source-generation and host children in `bench_density_comparison.py`, and
isolated children in `bench_ceiling.py`, already launch `sys.executable`;
therefore they inherit the controller's constrained interpreter. They do not
need producer changes or another environment.

Before either benchmark can generate source data, the unconditional
`Verify benchmark environment` step has a **two-minute** deadline. Dispatch
`INPUT_EXPERIMENT` and quoted `INPUT_ARMS` arrive through step environment bindings;
the quoted Python heredoc reads them as strings through `os.environ`. Neither
value is interpolated into shell/Python source or evaluated as code. The
preflight asserts Python 3.12, a known experiment and a nonempty selection
containing only that experiment's producer-supported arms. Ceiling parsing
matches its producer's trimmed, nonempty comma-separated tokens; comparison
parsing matches its producer's exact comma-separated tokens. Duplicate valid
arms remain accepted. Empty selections and unknown/mixed-experiment/injection
strings fail before dependency metadata queries, imports or source generation.
Tests read the producers' literal `ARMS` definitions with AST, without importing
them, to enforce the same supported sets.

Version queries and imports cover shared dependencies plus only the selected
arms' stacks:

- Both modes require NumPy, psutil, websocket-client and the native XYG backend.
  Density mode also requires Tornado, used by its controller/live hosts.
- Ceiling `xy` and `xy-exact`, and comparison `xy-density`, add no competitor
  stack.
- Ceiling `plotly` imports Plotly Express and pandas. Ceiling
  `plotly-resampler` imports Plotly graph objects, pandas and Plotly-resampler.
- Ceiling `matplotlib` imports WebAgg, Tornado and Pillow.
- Ceiling `datashader`, comparison `plotly-aggregate` and comparison
  `datashader-aggregate` import/check NumPy (shared), Numba, llvmlite,
  Datashader, pandas and Pillow. Plotly aggregate additionally imports
  Plotly offline; Datashader aggregate additionally imports hvPlot's pandas
  integration, HoloViews, Panel and Bokeh.

Each named distribution must be installed. If it has a pin in the unchanged
comparison constraints, its installed version must equal that pin. All selected
version checks precede selected imports, so NumPy 2.5.1 or Numba drift cannot
reach the aggregation path. The existing unpinned websocket-client version is
recorded without inventing a constraint. Unselected distributions are neither
queried nor imported merely because installed, so missing, broken or drifting
unused packages do not block a narrow run. This is an explicit check of shared
and selected primary packages, not a claim to independently validate every
transitive package; real stack imports still expose incompatible/missing
transitive dependencies.

The step prints interpreter identity, selected arms, checked package versions
and native backend as JSON in its log. It constructs no benchmark arrays,
maps, sources or browsers. Selected import/version failure stops the job before
large allocation. Kaleido is not used by either producer's selected paths here
and is never imported by this preflight; the existing constrained installation
commands remain unchanged.

The workflow remains manual-only with the same default ceiling experiment,
single job/status, actions and pins, Blacksmith macOS M4 runner, capacity,
720-minute job timeout, exact-SHA report binding, main-only comparison
allocation authority, and all source/memory/disk/phase/step budgets. No
dependency is added or widened. Failure cells and count/oracle acceptance
remain governed by their existing independent contracts.

## Review finding and disposition

Independent review of `4e84343d` identified an introduced narrow-arm regression:
that revision imported optional competitor stacks by experiment and checked all
installed constraint entries. Consequently ceiling `--arms xy` could fail on
unused Plotly-resampler's pre-existing missing `pytz`, and comparison
`--arms xy-density` could fail on unused competitors. The finding is accepted.
This follow-up passes arms to the preflight and makes both checks and imports
follow the selection. It preserves early failure when the broken stack is
actually selected; it does not add/widen dependencies to cure `pytz`.

## Regression proof and reproduction

`scripts/verify_ci_workflow.py` guards every executable command and the exact
preflight position, quoted heredoc, Python indentation, selected-stack map,
input environment and deadline. Mutation tests preserve the original guards
against implicit resynchronization, ambient interpreters, input interpolation,
changed budgets, authority, actions or report bindings. New mutations reject
hardcoded arms, weakened known-arm validation, unconditional stack selection,
removed aggregation checks and a restored all-installed version scan.

The actual extracted workflow Python is executed with controlled dependency
metadata and import failures. Tests demonstrate narrow XYG selections succeed
with unrelated missing/drifting packages and broken optional imports; selected
broken imports, missing distributions and version drift fail; shared NumPy
drift fails even for narrow XYG runs; aggregation arms require compatible
Numba/NumPy; invalid and injected arm strings remain data. Every supported arm,
combined selections and producer arm-set parity are covered without arrays,
benchmark producers, large sources or browsers.

```bash
mkdir -p target/comparison-dependency-tmp
TMPDIR="$PWD/target/comparison-dependency-tmp" uv run pytest tests/test_verify_ci_workflow.py -q -k ceiling
TMPDIR="$PWD/target/comparison-dependency-tmp" uv run python scripts/verify_ci_workflow.py
TMPDIR="$PWD/target/comparison-dependency-tmp" uv run --with pre-commit pre-commit run --all-files
TMPDIR="$PWD/target/comparison-dependency-tmp" uv run ruff check .
TMPDIR="$PWD/target/comparison-dependency-tmp" uv run ruff format --check .
```

Keep temporary mutated fixture source under ignored worktree `target/` so it
does not enter Ruff's full-worktree scan. Full CI-contract testing belongs to
the parent integration gate; this follow-up does not rerun the long
`make check-ci` suite.

Follow-up validation passes 158 focused ceiling/preflight/guard tests and the
production verifier across all workflows and the merge-queue ruleset. Real
preflight subprocesses in the same existing Linux x86_64 environment pass for
ceiling `xy`, comparison `xy-density`, and the combined two comparison
aggregation arms. Those checks use CPython 3.12.15, NumPy 2.4.6, Numba 0.66.0,
Datashader 0.19.1 and hvPlot 0.12.2, with the existing compiled native core.
Selecting Plotly-resampler in that environment fails on the genuine missing
`pytz`, confirming that selected failures remain early and visible.

For bounded real import validation, use an already constrained Python 3.12
environment directly, with `PYTHONPATH=python` and, when needed,
`XYG_NATIVE_LIB` pointing to its existing compiled core. This command executes
only the preflight's actual heredoc, without generating benchmark sources:

```bash
INPUT_EXPERIMENT=ceiling INPUT_ARMS=xy .venv/bin/python - <<'PY'
from pathlib import Path
workflow = Path(".github/workflows/ceiling-benchmark.yml").read_text()
block = workflow.split("      - name: Verify benchmark environment\n", 1)[1].split(
    "      - name:", 1
)[0]
body = "\n".join(line[10:] for line in block.split("        run: |\n", 1)[1].splitlines())
code = body.split(".venv/bin/python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
exec(compile(code, "ceiling-workflow-preflight", "exec"))
PY
```

Repeat with `INPUT_EXPERIMENT=density-comparison INPUT_ARMS=xy-density`, then
`INPUT_ARMS=plotly-aggregate,datashader-aggregate` for the aggregation stacks.
Selecting ceiling `INPUT_ARMS=plotly-resampler` in the existing optional
environment exposes its genuine `ModuleNotFoundError: pytz`; the narrow XYG
selections must pass in that same environment. No dependency is added to
repair the unrelated upstream import issue. These import checks cannot certify
macOS arm64 compatibility, actual-scale comparisons or publication acceptance;
no browser/hosted dispatch/retry is part of this follow-up.
