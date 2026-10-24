from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

# Actions are pinned to full commit SHAs (`@<40-hex> # vX`) per the org policy,
# so fixtures strip a step by its action *path*, not a version tag — a SHA bump
# must not silently turn these negative tests into no-ops.
_UPLOAD_ARTIFACT_USES = re.compile(r" *- uses: actions/upload-artifact@\S+.*\n")
_NODE24_ACTION_PINS = {
    "actions/cache": "55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "actions/setup-node": "820762786026740c76f36085b0efc47a31fe5020",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "astral-sh/setup-uv": "11f9893b081a58869d3b5fccaea48c9e9e46f990",
}


def _load_verify_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_ci_workflow.py"
    spec = importlib.util.spec_from_file_location("verify_ci_workflow", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify_ci_workflow = _load_verify_module()

# The exact source line carrying the PyPI upload gate in publish.yaml. Fixtures
# mutate this line, so it must stay a verbatim copy of the workflow's own
# spelling (the fork opt-in variable plus the manual dry-run switch, #13).
RELEASE_PUBLISH_GATE_LINE = (
    "        if: vars.XYG_ALLOW_NPM_PUBLISH == 'true' && vars.XYG_ALLOW_PYPI_PUBLISH == 'true' && "
    "startsWith(github.ref, 'refs/tags/xyg-v') && "
    "(github.event_name != 'workflow_dispatch' || github.event.inputs.dry_run != 'true')\n"
)


def test_ci_workflow_accepts_current_gates() -> None:
    assert verify_ci_workflow.validate_workflow() == []
    assert verify_ci_workflow.validate_ci_workflow() == []


@pytest.mark.parametrize(
    ("command", "gate"),
    [
        ("npm test --prefix packages/xy-node", "complete Node host suite"),
        (
            ".venv/bin/python benchmarks/bench_dual_host_graph.py --sizes 1000",
            "graph/kernel ceilings",
        ),
        (
            ".venv/bin/python benchmarks/bench_parity_kernels.py --sizes 100000 --no-baseline",
            "graph/kernel ceilings",
        ),
        (
            ".venv/bin/python benchmarks/bench_scale_all_charts.py --profile smoke",
            "graph/kernel ceilings",
        ),
        (
            "node benchmarks/bench_scale_all_charts_node.mjs --profile smoke",
            "graph/kernel ceilings",
        ),
        (".venv/bin/python benchmarks/bench_tier3_pyramid.py", "graph/kernel ceilings"),
        ("node benchmarks/bench_tier3_pyramid_node.mjs", "graph/kernel ceilings"),
        (
            'python3 scripts/verify_tier3_pyramid_report.py "$RUNNER_TEMP/tier3-python.json"',
            "graph/kernel ceilings",
        ),
        (
            'python3 scripts/verify_tier3_pyramid_report.py "$RUNNER_TEMP/tier3-node.json"',
            "graph/kernel ceilings",
        ),
    ],
)
@pytest.mark.parametrize("replacement", ["# {command}", "echo {command}", "{command} || true"])
def test_ci_workflow_requires_active_graph_suite_commands(
    tmp_path: Path, command: str, gate: str, replacement: str
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    candidates = [
        line
        for line in workflow.splitlines(keepends=True)
        if line == f"          {command}\n" or line.startswith(f"          {command} ")
    ]
    assert len(candidates) == 1
    original = candidates[0]
    command = original.strip()
    path.write_text(
        workflow.replace(original, f"          {replacement.format(command=command)}\n", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any(gate in error for error in errors)


def test_ci_workflow_rejects_missing_release_surface_aggregate(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace("  release_surfaces:\n", "  release_surfaces_removed:\n"),
        encoding="utf-8",
    )
    errors = verify_ci_workflow.validate_ci_workflow(path)
    assert any("release_surfaces" in error for error in errors)


def test_ci_workflow_rejects_skippable_release_surface_job(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "    if: github.event_name != 'pull_request' || "
            "needs.release_surface_changes.outputs.required == 'true'\n",
            "    if: github.event_name != 'pull_request'\n",
            1,
        ),
        encoding="utf-8",
    )
    errors = verify_ci_workflow.validate_ci_workflow(path)
    assert any("classifier condition" in error for error in errors)


def test_ci_workflow_requires_classifier_from_trusted_base(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            'git show "$base:scripts/classify_release_surface.py" > "$classifier"',
            'cp scripts/classify_release_surface.py "$classifier"',
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("release-surface change classifier" in error for error in errors)


def test_ci_workflow_rejects_commented_trusted_base_fetch(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            'if git show "$base:scripts/classify_release_surface.py" > "$classifier"; then',
            'if cp scripts/classify_release_surface.py "$classifier"; then\n'
            '              # git show "$base:scripts/classify_release_surface.py" '
            '> "$classifier"',
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("trusted-base release-surface classifier execution" in error for error in errors)


@pytest.mark.parametrize(
    "old,new",
    (
        (
            "      required: ${{ steps.classify.outputs.required }}",
            "      required: ${{ 'false' }}",
        ),
        ("        id: classify", "        id: detached"),
        (
            "        shell: bash",
            "        env:\n          PYTHONPATH: ${{ github.workspace }}\n        shell: bash",
        ),
    ),
)
def test_ci_workflow_binds_classifier_output_and_environment(
    tmp_path: Path, old: str, new: str
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(workflow.replace(old, new, 1), encoding="utf-8")

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("release-surface classifier" in error for error in errors)


def test_ci_workflow_rejects_extra_classifier_job_step(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "      - name: Classify changed paths\n",
            "      - name: Poison classifier path\n"
            '        run: echo "$GITHUB_WORKSPACE" >> "$GITHUB_PATH"\n'
            "      - name: Classify changed paths\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("only the pinned checkout" in error for error in errors)


def test_ci_workflow_requires_quoted_path_fail_safe(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            '            if grep -q \'^"\' "$changed"; then\n'
            '              echo "required=true" >> "$GITHUB_OUTPUT"\n'
            "            elif git show",
            "            if git show",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("trusted-base release-surface classifier execution" in error for error in errors)


def test_classifier_git_diff_quotes_unusual_paths_for_fail_safe(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=XYG Test",
            "-c",
            "user.email=xyg@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        cwd=tmp_path,
        check=True,
    )
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    source = tmp_path / "python"
    source.mkdir()
    (source / "mañana.py").write_text("release_surface = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "python/mañana.py"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=XYG Test",
            "-c",
            "user.email=xyg@example.invalid",
            "commit",
            "-qm",
            "unicode",
        ],
        cwd=tmp_path,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    changed = subprocess.run(
        ["git", "-c", "core.quotePath=true", "diff", "--name-only", base, head],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert changed and all(path.startswith('"') for path in changed)


def test_ci_workflow_rejects_top_level_classifier_function_override(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "jobs:\n",
            "env:\n"
            '  "BASH_FUNC_python3%%": \'() { echo "required=false" >> '
            '"$GITHUB_OUTPUT"; }\'\n'
            "jobs:\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("top-level environment" in error for error in errors)


def test_milestone_governance_requires_recorded_human_approval(tmp_path: Path) -> None:
    spec = tmp_path / "contributing.md"
    spec.write_text("Agents may reorganize milestones automatically.\n", encoding="utf-8")
    errors = verify_ci_workflow.validate_milestone_governance(spec)
    assert any("explicit human approval" in error for error in errors)


def test_milestone_governance_rejects_legacy_autonomous_closers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflows = tmp_path / ".github" / "workflows"
    scripts = tmp_path / "scripts"
    workflows.mkdir(parents=True)
    scripts.mkdir()
    workflow = workflows / "m2-wave-c-close.yml"
    script = scripts / "m2_wave_c_close.sh"
    workflow.write_text("permissions:\n  issues: write\n", encoding="utf-8")
    script.write_text("gh api -X PATCH milestones/2 -f state=closed\n", encoding="utf-8")
    contributor_spec = tmp_path / "contributing.md"
    contributor_spec.write_text(
        "Creating, renaming, closing, or deleting a milestone requires "
        "explicit human approval recorded in a GitHub issue or pull request; "
        "automation must not execute it before that approval. Repository automation "
        "must not reopen, close, rename, create, or reassign milestones.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_ci_workflow, "ROOT", tmp_path)
    errors = verify_ci_workflow.validate_milestone_governance(contributor_spec)
    assert any("m2-wave-c-close.yml" in error for error in errors)
    assert any("m2_wave_c_close.sh" in error for error in errors)


def test_ci_workflow_requires_locked_development_environment(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "uv sync --locked --group dev --group codspeed",
            "uv sync --group dev",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("uv sync --locked --group dev --group codspeed" in error for error in errors)


def test_locked_development_environment_must_be_in_named_install_step(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    required = "          uv sync --locked --group dev --group codspeed"
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            required,
            "          uv sync --group dev\n\n"
            "      - name: Unrelated example\n"
            f"        run: {required.strip()}",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Install package + dev deps" in error for error in errors)


def test_locked_development_environment_cannot_be_commented_out(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    required = "          uv sync --locked --group dev --group codspeed"
    path = tmp_path / "ci.yml"
    path.write_text(workflow.replace(required, f"          # {required.strip()}"), encoding="utf-8")

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Install package + dev deps" in error for error in errors)


def test_locked_development_environment_cannot_hide_in_step_env(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    required = "uv sync --locked --group dev --group codspeed"
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            "        env:\n"
            f"          FAKE_GATE: {required}\n",
        ).replace(f"          {required}", "          uv sync --group dev"),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Install package + dev deps" in error for error in errors)


def test_locked_development_environment_requires_an_exact_command_line(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    required = "uv sync --locked --group dev --group codspeed"
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(f"          {required}", f"          echo '{required}'"),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Install package + dev deps" in error for error in errors)


def test_locked_development_environment_cannot_be_heredoc_data(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    required = "uv sync --locked --group dev --group codspeed"
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            f"          {required}",
            "          cat <<'EOF'\n"
            f"          {required}\n"
            "          EOF\n"
            "          uv sync --group dev",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Install package + dev deps" in error for error in errors)


def test_locked_development_environment_cannot_be_folded_echo_data(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    required = "uv sync --locked --group dev --group codspeed"
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            f"        run: |\n          {required}",
            f"        run: >\n          echo ignored\n          {required}",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Install package + dev deps" in error for error in errors)


def test_locked_development_environment_cannot_be_folded_comment_data(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    required = "uv sync --locked --group dev --group codspeed"
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            f"        run: |\n          {required}",
            f"        run: >\n          # disabled\n          {required}",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Install package + dev deps" in error for error in errors)


def test_locked_development_environment_step_must_be_a_hard_gate(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    bypasses = (
        "if: false",
        "shell: echo {0}",
        "continue-on-error: true",
        "working-directory: decoy",
        '"if": false',
        "'shell': echo {0}",
        '"continue-on-error": true',
        "'working-directory': decoy",
        '"working\\u002ddirectory": decoy',
        "!!str working-directory: decoy",
        "&guard_key working-directory: decoy",
        "<<: *step_defaults",
        "? working-directory\n        : decoy",
        "?\n          working-directory\n        : decoy",
    )

    for index, bypass in enumerate(bypasses):
        path = tmp_path / f"ci-{index}.yml"
        path.write_text(
            workflow.replace(
                "      - name: Install package + dev deps\n",
                f"      - name: Install package + dev deps\n        {bypass}\n",
            ),
            encoding="utf-8",
        )

        errors = verify_ci_workflow.validate_ci_workflow(path)

        assert any("Install package + dev deps" in error for error in errors)


def test_locked_development_environment_job_must_be_a_hard_gate(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    bypasses = (
        "if: false",
        "continue-on-error: true",
        "defaults:\n      run:\n        shell: echo {0}",
        'container: { image: "ubuntu:24.04", env: { BASH_ENV: noop } }',
        "needs: skipped-prerequisite",
        "strategy:\n      matrix:\n        shard: []",
        '"if": false',
        "'continue-on-error': true",
        '"defaults":\n      run:\n        shell: echo {0}',
    )

    for index, bypass in enumerate(bypasses):
        path = tmp_path / f"ci-job-{index}.yml"
        path.write_text(
            workflow.replace(
                "  test:\n",
                f"  test:\n    {bypass}\n",
            ),
            encoding="utf-8",
        )

        errors = verify_ci_workflow.validate_ci_workflow(path)

        assert any("Install package + dev deps" in error for error in errors)


def test_locked_development_environment_rejects_workflow_shell_override(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "jobs:\n",
            "defaults:\n  run:\n    shell: echo {0}\n\njobs:\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("hard-gate run steps" in error for error in errors)


def test_locked_development_environment_rejects_quoted_workflow_shell_override(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "jobs:\n",
            '"defaults":\n  run:\n    shell: echo {0}\n\njobs:\n',
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("hard-gate run steps" in error for error in errors)


def test_hard_gates_reject_shell_init_environment_overrides(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    mutations = (
        (
            "jobs:\n",
            "env:\n  BASH_ENV: .github/noop-shell-init\n\njobs:\n",
        ),
        (
            "  test:\n",
            "  test:\n    env:\n      BASH_ENV: .github/noop-shell-init\n",
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            "        env:\n"
            "          'ENV': .github/noop-shell-init\n",
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            "        env: { BASH_ENV: .github/noop-shell-init }\n",
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            '        env: { "ENV": .github/noop-shell-init }\n',
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            '        env: { "BASH\\u005fENV": .github/noop-shell-init }\n',
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            '        env: { "BASH\\x5fENV": .github/noop-shell-init }\n',
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            "        env: &shell_env { BASH_ENV: .github/noop-shell-init }\n",
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            "        env: { !!str BASH_ENV: .github/noop-shell-init }\n",
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            "        env:\n"
            "          !!str BASH_ENV: .github/noop-shell-init\n",
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            "        env:\n"
            "          &shell_key BASH_ENV: .github/noop-shell-init\n",
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            "        env:\n"
            "          ? BASH_ENV\n"
            "          : .github/noop-shell-init\n",
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            "        env:\n"
            "          ?\n"
            "            BASH_ENV\n"
            "          : .github/noop-shell-init\n",
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            "        env:\n"
            '          "\\u0045NV": .github/noop-shell-init\n',
        ),
        (
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n"
            "        env:\n"
            "          PATH: .github/fake-bin\n",
        ),
    )

    for index, (old, new) in enumerate(mutations):
        path = tmp_path / f"ci-shell-init-{index}.yml"
        path.write_text(workflow.replace(old, new), encoding="utf-8")

        errors = verify_ci_workflow.validate_ci_workflow(path)

        assert any("shell-init environment variables" in error for error in errors)


def test_hard_gates_reject_persistent_environment_file_writes(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "      - name: Install package + dev deps\n",
            "      - name: Persist shell setup\n"
            "        run: |\n"
            "          printf 'BASH_ENV=%s\\n' noop >> \"$GITHUB_ENV\"\n\n"
            "          printf '%s\\n' fake-bin >> \"$GITHUB_PATH\"\n\n"
            "      - name: Install package + dev deps\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("shell-init environment variables" in error for error in errors)


def test_multiline_quoted_env_value_does_not_create_a_sibling_key() -> None:
    text = 'env:\n  SAFE: "start\n  BASH_ENV: harmless"\njobs:\n  test:\n    steps: []\n'

    assert not verify_ci_workflow._has_shell_init_environment(text)


def test_protected_step_requires_exactly_one_direct_run_key(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    required = "          uv sync --locked --group dev --group codspeed\n"
    duplicate_run_keys = (
        "        run: echo bypassed\n",
        '        "run": echo bypassed\n',
        "        'run': echo bypassed\n",
        '        "r\\u0075n": echo bypassed\n',
        "        !!str run: echo bypassed\n",
        "        &run_key run: echo bypassed\n",
        "        <<: *run_defaults\n",
        "        ? run\n        : echo bypassed\n",
        "        ?\n          run\n        : echo bypassed\n",
    )

    for index, duplicate in enumerate(duplicate_run_keys):
        path = tmp_path / f"ci-duplicate-run-{index}.yml"
        path.write_text(workflow.replace(required, required + duplicate, 1), encoding="utf-8")

        errors = verify_ci_workflow.validate_ci_workflow(path)

        assert any("Install package + dev deps" in error for error in errors)


def test_shell_init_key_text_in_a_comment_is_not_a_mapping_key(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "jobs:\n",
            '# Documentation example only: { BASH_ENV: unsafe, "ENV": unsafe }\n'
            "# Mentioning GITHUB_ENV in a YAML comment is harmless.\n\n"
            "jobs:\n",
            1,
        ),
        encoding="utf-8",
    )

    assert verify_ci_workflow.validate_ci_workflow(path) == []


def test_shell_init_flow_mapping_on_an_indented_value_line_is_rejected() -> None:
    text = "env:\n  { BASH_ENV: .github/noop-shell-init }\n"

    assert verify_ci_workflow._has_shell_init_environment(text)


def test_sequence_mapping_sibling_after_block_scalar_is_still_checked() -> None:
    text = (
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - run: |\n"
        "          echo harmless\n"
        "        env:\n"
        "          BASH_ENV: .github/noop-shell-init\n"
    )

    assert verify_ci_workflow._has_shell_init_environment(text)


def test_anchored_steps_value_does_not_hide_step_environment() -> None:
    text = (
        "jobs:\n"
        "  test:\n"
        "    steps: &test_steps\n"
        "      - name: Protected\n"
        "        env:\n"
        "          BASH_ENV: .github/noop-shell-init\n"
        "        run: true\n"
    )

    assert verify_ci_workflow._has_shell_init_environment(text)


def test_plain_scalar_content_cannot_hide_a_later_shell_init_mapping() -> None:
    prefixes = (
        "name: Don't\n",
        'name: Say "hello\n',
        'run-name:\n  -"unterminated\n',
        'run-name:\n  name:"unterminated\n',
        'run-name:\n  CONFIG: plain\n    "unfinished\n',
    )

    for prefix in prefixes:
        text = prefix + "env: { BASH_ENV: .github/noop-shell-init }\n"
        assert verify_ci_workflow._has_shell_init_environment(text)


def test_scalar_contents_and_github_expressions_are_not_mapping_keys() -> None:
    harmless_yaml = (
        "matrix:\n"
        "  script:\n"
        "    - |\n"
        "      BASH_ENV: documentation\n"
        "anchored: &script |\n"
        "  ENV: documentation\n"
        "tagged: !!str >-\n"
        "  BASH_ENV: documentation\n"
        'quoted: "documentation starts\n'
        "  ENV: documentation\n"
        '  documentation ends"\n'
        'run-name:\n  &label "CI: run"\n'
        "condition: ${{ !cancelled() }}\n"
    )

    assert not verify_ci_workflow._has_shell_init_environment(harmless_yaml)


def test_unrelated_actions_env_fields_are_not_environment_mappings() -> None:
    text = (
        "run-name: Inspect GITHUB_ENV behavior\n"
        "jobs:\n"
        "  test:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        env: [py311, py312]\n"
        "    steps:\n"
        "      - uses: example/action@0123456789abcdef\n"
        "        with:\n"
        "          env: production\n"
    )

    assert not verify_ci_workflow._has_shell_init_environment(text)


def test_url_like_scalar_values_are_not_mapping_keys() -> None:
    scalars = (
        "run-name:\n  ENV:https://example.com\n",
        "run-name:\n  !!str https://example.com\n",
        "run-name:\n  &label https://example.com\n",
    )

    for text in scalars:
        assert verify_ci_workflow._yaml_mapping_keys(text) == [(0, "run-name", False)]


def test_plain_scalar_continuation_cannot_hide_duplicate_run(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    required = "          uv sync --locked --group dev --group codspeed\n"
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            required,
            required
            + "        env:\n"
            + "          NOTE: This is\n"
            + '            "unfinished\n'
            + "        run: echo bypassed\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Install package + dev deps" in error for error in errors)


def test_top_level_scalar_cannot_replace_the_real_job_block(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    original_test = verify_ci_workflow._job_blocks(workflow)["test"]
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace("  test:\n", "  test:\n    if: false\n", 1)
        + "\nrun-name: |2\n"
        + original_test
        + "\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Install package + dev deps" in error for error in errors)


def test_job_scalar_cannot_replace_the_real_named_step(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    original_step = verify_ci_workflow._named_step_blocks(
        verify_ci_workflow._job_blocks(workflow)["test"]
    )["Install package + dev deps"]
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "      - name: Install package + dev deps\n",
            "      - name: Install package + dev deps\n        if: false\n",
            1,
        ).replace(
            "  browser_conformance:\n",
            "    name: |2\n" + original_step + "\n\n  browser_conformance:\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Install package + dev deps" in error for error in errors)


def test_reference_gate_commands_must_be_in_the_named_step(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    command = "        run: .venv/bin/pytest -q -rs tests/pyplot\n"
    # Leaving the old verifier's needle elsewhere in the job must not satisfy
    # the structural step-local check.
    path = tmp_path / "ci.yml"
    path.write_text(workflow.replace(command, "") + f"\n# {command.strip()}\n", encoding="utf-8")
    errors = verify_ci_workflow.validate_ci_workflow(path)
    assert any("reference test commands" in error for error in errors)


def test_generated_abi_check_must_execute_in_its_named_step(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    command = "        run: python3 scripts/gen_abi_manifest.py --check\n"
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            command,
            "        run: echo skipped # python3 scripts/gen_abi_manifest.py --check\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("ABI artifact freshness check" in error for error in errors)


def test_reference_gate_commands_cannot_hide_in_inline_comments(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    command = ".venv/bin/pytest -q -rs tests/pyplot"
    workflow = workflow.replace(f"run: {command}", f"run: echo ignored # {command}")
    path = tmp_path / "ci.yml"
    path.write_text(workflow, encoding="utf-8")

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("reference test commands" in error for error in errors)


def test_reference_gate_commands_cannot_be_heredoc_data(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    command = ".venv/bin/pytest -q -rs tests/pyplot"
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            f"        run: {command}\n",
            f"        run: |\n          cat <<'EOF'\n          {command}\n          EOF\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("reference test commands" in error for error in errors)


def test_reference_job_runs_the_whole_pyplot_suite_not_a_file_list(tmp_path: Path) -> None:
    """#1035: matplotlib-dependent pyplot tests outside the corpus must gate merges."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    start, end = _job_span(workflow, "matplotlib_reference")
    assert "timeout-minutes: 30" in workflow[start:end]
    narrowed = workflow.replace(
        "run: .venv/bin/pytest -q -rs tests/pyplot\n",
        "run: .venv/bin/pytest -q -rs tests/pyplot/test_reference_corpus.py\n",
        1,
    )
    assert narrowed != workflow
    errors = _wasm_errors(tmp_path, narrowed)
    assert any("reference test commands" in error for error in errors), errors


def test_reference_job_and_steps_must_be_hard_gates(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    mutations = (
        (
            "      - name: Run the full tests/pyplot suite against matplotlib 3.11.0\n",
            "      - name: Run the full tests/pyplot suite against matplotlib 3.11.0\n"
            "        if: false\n",
        ),
        (
            "      - name: Run the full tests/pyplot suite against matplotlib 3.11.0\n",
            "      - name: Run the full tests/pyplot suite against matplotlib 3.11.0\n"
            "        continue-on-error: true\n",
        ),
        (
            "      - name: Run the full tests/pyplot suite against matplotlib 3.11.0\n",
            "      - name: Run the full tests/pyplot suite against matplotlib 3.11.0\n"
            "        shell: echo {0}\n",
        ),
        (
            "      - name: Run the full tests/pyplot suite against matplotlib 3.11.0\n",
            "      - name: Run the full tests/pyplot suite against matplotlib 3.11.0\n"
            "        working-directory: decoy\n",
        ),
        ("  matplotlib_reference:\n", "  matplotlib_reference:\n    if: false\n"),
        (
            "  matplotlib_reference:\n",
            "  matplotlib_reference:\n    continue-on-error: true\n",
        ),
        (
            "  matplotlib_reference:\n",
            "  matplotlib_reference:\n    defaults:\n      run:\n        shell: echo {0}\n",
        ),
    )

    for index, (old, new) in enumerate(mutations):
        path = tmp_path / f"ci-reference-hard-gate-{index}.yml"
        path.write_text(workflow.replace(old, new), encoding="utf-8")

        errors = verify_ci_workflow.validate_ci_workflow(path)

        if index == 4:
            assert any("matplotlib_reference" in error for error in errors)
        else:
            assert any("Run the full tests/pyplot suite" in error for error in errors)


def test_codspeed_workflow_accepts_current_gates() -> None:
    assert verify_ci_workflow.validate_codspeed_workflow() == []


def test_final_coderabbit_policy_accepts_current_gates() -> None:
    assert verify_ci_workflow.validate_final_review_policy() == []


def test_ci_pr_lane_policy_rejects_filters_required_skips_and_breadth_prs(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    mutations = (
        ("  pull_request:\n", '  pull_request:\n    paths-ignore: ["docs/**"]\n'),
        (
            "  test:\n    name: Test (Rust + Python + JS)\n",
            "  test:\n    name: Test (Rust + Python + JS)\n"
            "    if: github.event_name != 'pull_request'\n",
        ),
        (
            "  matplotlib_reference:\n    name: Matplotlib 3.11 reference compatibility\n"
            "    needs: [release_surface_changes, wasm_assets]\n"
            "    if: github.event_name != 'pull_request' || "
            "needs.release_surface_changes.outputs.required == 'true'\n",
            "  matplotlib_reference:\n    name: Matplotlib 3.11 reference compatibility\n"
            "    if: github.event_name == 'push' || github.event_name == 'workflow_dispatch'\n",
        ),
        (
            "  benchmark_methodology:\n    name: Benchmark methodology suites\n    needs: wasm_assets\n"
            "    if: github.event_name == 'push' || github.event_name == 'workflow_dispatch'\n",
            "  benchmark_methodology:\n    name: Benchmark methodology suites\n    needs: wasm_assets\n",
        ),
    )
    for index, (old, new) in enumerate(mutations):
        path = tmp_path / f"ci-pr-policy-{index}.yml"
        path.write_text(workflow.replace(old, new), encoding="utf-8")

        errors = verify_ci_workflow.validate_ci_workflow(path)

        assert errors


def test_ci_merge_queue_policy_rejects_missing_trigger_and_canceling_runs(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    trigger = "  merge_group:\n    types: [checks_requested]\n"
    cancel = "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n"
    assert trigger in workflow and cancel in workflow
    mutations = (
        (trigger, "", "must report required checks for merge_group"),
        (trigger, "  merge_group:\n    types: [destroyed]\n", "must handle checks_requested"),
        (
            trigger,
            "  merge_group:\n    types: [checks_requested]\n    types: [destroyed]\n",
            "must handle checks_requested",
        ),
        (cancel, "  cancel-in-progress: true\n", "must cancel only superseded pull_request"),
        (
            cancel,
            "  cancel-in-progress: ${{ github.event_name != 'merge_group' }}\n",
            "push runs on main must complete",
        ),
    )
    for index, (old, new, message) in enumerate(mutations):
        path = tmp_path / f"ci-merge-queue-{index}.yml"
        path.write_text(workflow.replace(old, new, 1), encoding="utf-8")

        errors = verify_ci_workflow.validate_ci_workflow(path)

        assert any(message in error for error in errors), (index, errors)


def test_ci_rejects_non_main_automatic_push_branches(tmp_path: Path) -> None:
    cases = ((Path(".github/workflows/ci.yml"), verify_ci_workflow.validate_ci_workflow),)
    for index, (source, validate) in enumerate(cases):
        workflow = source.read_text(encoding="utf-8")
        path = tmp_path / f"push-branches-{index}.yml"
        path.write_text(
            workflow.replace('branches: ["main"]', 'branches: ["main", "claude/**"]', 1),
            encoding="utf-8",
        )

        errors = validate(path)

        assert any("push trigger" in error and "branches" in error for error in errors)


def test_final_coderabbit_policy_rejects_auto_review_and_workflow_bypasses(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/final-coderabbit.yml").read_text(encoding="utf-8")
    config = Path(".coderabbit.yaml").read_text(encoding="utf-8")
    cases = (
        (workflow.replace("  workflow_dispatch:\n", "  pull_request:\n", 1), config),
        (workflow.replace("      pull-requests: write\n", "      pull-requests: read\n"), config),
        (
            workflow.replace(
                "        run: python3 scripts/request_final_coderabbit.py",
                "        run: echo python3 scripts/request_final_coderabbit.py",
            ),
            config,
        ),
        (workflow, config.replace("enabled: false", "enabled: true", 1)),
    )
    for index, (mutated_workflow, mutated_config) in enumerate(cases):
        workflow_path = tmp_path / f"final-review-{index}.yml"
        config_path = tmp_path / f"coderabbit-{index}.yaml"
        workflow_path.write_text(mutated_workflow, encoding="utf-8")
        config_path.write_text(mutated_config, encoding="utf-8")

        errors = verify_ci_workflow.validate_final_review_policy(workflow_path, config_path)

        assert errors


def test_final_coderabbit_policy_rejects_missing_idempotency_marker(tmp_path: Path) -> None:
    workflow_path = Path(".github/workflows/final-coderabbit.yml")
    config_path = Path(".coderabbit.yaml")
    source = Path("scripts/request_final_coderabbit.py").read_text(encoding="utf-8")
    script_path = tmp_path / "request_final_coderabbit.py"
    script_path.write_text(
        source.replace("has_existing_request(comments, head)", "False", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_final_review_policy(
        workflow_path, config_path, script_path
    )

    assert any("exact-head idempotent" in error for error in errors)


def test_final_coderabbit_policy_requires_release_surface_aggregate(tmp_path: Path) -> None:
    workflow_path = Path(".github/workflows/final-coderabbit.yml")
    config_path = Path(".coderabbit.yaml")
    source = Path("scripts/request_final_coderabbit.py").read_text(encoding="utf-8")
    script_path = tmp_path / "request_final_coderabbit.py"
    script_path.write_text(source.replace('    "Release surfaces",\n', "", 1), encoding="utf-8")

    errors = verify_ci_workflow.validate_final_review_policy(
        workflow_path, config_path, script_path
    )

    assert any("Release surfaces aggregate" in error for error in errors)


def test_final_coderabbit_policy_rejects_self_status_dependency(tmp_path: Path) -> None:
    workflow_path = Path(".github/workflows/final-coderabbit.yml")
    config_path = Path(".coderabbit.yaml")
    source = Path("scripts/request_final_coderabbit.py").read_text(encoding="utf-8")
    script_path = tmp_path / "request_final_coderabbit.py"
    script_path.write_text(
        source.replace('status.get("context") != "CodeRabbit" and ', "", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_final_review_policy(
        workflow_path, config_path, script_path
    )

    assert any("own status context" in error for error in errors)


def test_final_coderabbit_policy_rejects_bot_authored_review_command(tmp_path: Path) -> None:
    workflow_path = Path(".github/workflows/final-coderabbit.yml")
    config_path = Path(".coderabbit.yaml")
    source = Path("scripts/request_final_coderabbit.py").read_text(encoding="utf-8")
    script_path = tmp_path / "request_final_coderabbit.py"
    script_path.write_text(source + '\nCOMMAND = "@coderabbitai review"\n', encoding="utf-8")

    errors = verify_ci_workflow.validate_final_review_policy(
        workflow_path, config_path, script_path
    )

    assert any("bot-authored command" in error for error in errors)


def test_final_coderabbit_policy_rejects_idempotency_before_validation(tmp_path: Path) -> None:
    workflow_path = Path(".github/workflows/final-coderabbit.yml")
    config_path = Path(".coderabbit.yaml")
    source = Path("scripts/request_final_coderabbit.py").read_text(encoding="utf-8")
    skip = """        if has_existing_request(comments, head):
            print(f"final CodeRabbit review already requested for PR #{number} at {head}")
            return 0
"""
    script_path = tmp_path / "request_final_coderabbit.py"
    script_path.write_text(
        source.replace(skip, "", 1).replace(
            "        head = validate_candidate(\n", skip + "        head = validate_candidate(\n", 1
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_final_review_policy(
        workflow_path, config_path, script_path
    )

    assert any("skip must follow candidate validation" in error for error in errors)


def test_all_workflows_accept_current_gates() -> None:
    assert verify_ci_workflow.validate_all_workflows() == []


def test_density_authority_workflow_is_main_only_and_cost_bounded() -> None:
    assert verify_ci_workflow.validate_density_workflow() == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            "        if: github.event_name == 'workflow_dispatch' || github.event.schedule == '43 5 * * 0'\n",
            "",
        ),
        ('          XYG_DENSITY_100M_AUTHORITY: "1"', '          XYG_DENSITY_100M_AUTHORITY: "0"'),
        ("--points 100000000 --authority", "--points 1000000"),
        (
            "--timeout 3600 --max-rss-gib 12 --max-disk-gib 4",
            "--timeout 7200 --max-rss-gib 24 --max-disk-gib 8",
        ),
        ('--sha "$GITHUB_SHA" --artifact-root "$GITHUB_WORKSPACE"', ""),
        ("        env:\n", "        continue-on-error: true\n        env:\n"),
    ],
)
def test_colored_authority_cannot_relax_its_guard_or_evidence(tmp_path, old, new):
    source = verify_ci_workflow.DEFAULT_DENSITY_WORKFLOW.read_text()
    at = source.index("      - name: Run weekly/manual 100M colored spill authority")
    assert old in source[at:]
    path = tmp_path / "density.yml"
    path.write_text(source[:at] + source[at:].replace(old, new, 1))
    assert verify_ci_workflow.validate_density_workflow(path)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("--points 16384 --chunk-points 4096", "--points 100000000 --authority"),
        (
            '"$RUNNER_TEMP/density-spill-pr.json" --artifact-root "$GITHUB_WORKSPACE"',
            '"$RUNNER_TEMP/density-spill-pr.json"',
        ),
        (
            "      - name: Colored spill harness contract (small scale only)\n",
            "      - name: Colored spill harness contract (small scale only)\n        if: false\n",
        ),
    ],
)
def test_colored_pr_control_cannot_run_authority_or_skip_verification(tmp_path, old, new):
    source = verify_ci_workflow.DEFAULT_CI_WORKFLOW.read_text()
    assert old in source
    path = tmp_path / "ci.yml"
    path.write_text(source.replace(old, new, 1))
    assert verify_ci_workflow.validate_ci_workflow(path)


def test_density_authority_rejects_pull_request_and_unguarded_100m(tmp_path: Path) -> None:
    source = verify_ci_workflow.DEFAULT_DENSITY_WORKFLOW.read_text(encoding="utf-8")
    source = source.replace("  workflow_dispatch:\n", "  pull_request:\n  workflow_dispatch:\n")
    source = source.replace("    if: github.ref == 'refs/heads/main'\n", "")
    path = tmp_path / "density.yml"
    path.write_text(source, encoding="utf-8")

    errors = verify_ci_workflow.validate_density_workflow(path)

    assert any("only schedule and workflow_dispatch" in error for error in errors)
    assert any("refs/heads/main" in error for error in errors)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda source: source.replace(
            "permissions:\n  contents: read", "permissions: write-all", 1
        ),
        lambda source: source.replace(
            "  cancel-in-progress: false", "  cancel-in-progress: true", 1
        ),
        lambda source: source.replace(
            "      - name: Run weekly/manual 100M end-to-end authority\n",
            "      - name: Run weekly/manual 100M end-to-end authority\n"
            "        continue-on-error: true\n",
            1,
        ),
        lambda source: source.replace(
            "      - name: Upload exact-SHA raw reports\n",
            "      - name: Upload exact-SHA raw reports\n        continue-on-error: true\n",
            1,
        ),
        lambda source: source.replace(
            "          persist-credentials: false", "          persist-credentials: true", 1
        ),
        lambda source: source.replace(
            "      - name: Upload exact-SHA raw reports\n",
            "      - name: Unreviewed command\n        run: echo bypass\n"
            "      - name: Upload exact-SHA raw reports\n",
            1,
        ),
        lambda source: source + "\n  bypass:\n    runs-on: ubuntu-latest\n    steps: []\n",
    ],
)
def test_density_authority_rejects_structural_and_policy_bypasses(tmp_path: Path, mutation) -> None:
    source = verify_ci_workflow.DEFAULT_DENSITY_WORKFLOW.read_text(encoding="utf-8")
    path = tmp_path / "density.yml"
    path.write_text(mutation(source), encoding="utf-8")

    assert verify_ci_workflow.validate_density_workflow(path)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda source: source.replace("--points 250000", "--points 100000000 --authority", 1),
        lambda source: source.replace(
            "--timeout 180 --max-rss-gib 4 --max-disk-gib 1",
            "--timeout 3600 --max-rss-gib 12 --max-disk-gib 4",
            1,
        ),
        lambda source: source.replace(
            "          python3 scripts/verify_density_e2e_report.py \\\n"
            '            "$RUNNER_TEMP/density-e2e-pr.json" --sha "$GITHUB_SHA"\n',
            "",
            1,
        ),
        lambda source: source.replace(
            "      - name: Density end-to-end harness contract (small scale only)\n",
            "      - name: Density end-to-end harness contract (small scale only)\n"
            "        continue-on-error: true\n",
            1,
        ),
    ],
)
def test_ci_rejects_weakened_or_unverified_pr_density_contract(tmp_path: Path, mutation) -> None:
    source = verify_ci_workflow.DEFAULT_CI_WORKFLOW.read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(mutation(source), encoding="utf-8")

    assert verify_ci_workflow.validate_ci_workflow(path)


@pytest.mark.parametrize(
    "mutation",
    [
        # Dropping the SHA link, the verifier, or the step, or making it
        # non-blocking must all fail the CI workflow check (#33).
        lambda source: source.replace(' --expect-commit "$GITHUB_SHA"', "", 1),
        lambda source: source.replace(
            "          .venv/bin/python scripts/verify_benchmark_report.py \\\n"
            '            "$RUNNER_TEMP/graph-scale-pr.json" --kind graph-scale --expect-commit "$GITHUB_SHA"\n',
            "",
            1,
        ),
        lambda source: source.replace("--profile smoke", "--profile smoke --no-browser", 1),
        lambda source: source.replace(
            "      - name: Graph scale harness contract (small and medium tiers)\n",
            "      - name: Graph scale harness contract (small and medium tiers)\n"
            "        continue-on-error: true\n",
            1,
        ),
    ],
)
def test_ci_rejects_weakened_or_unverified_graph_scale_contract(tmp_path: Path, mutation) -> None:
    source = verify_ci_workflow.DEFAULT_CI_WORKFLOW.read_text(encoding="utf-8")
    mutated = mutation(source)
    assert mutated != source
    path = tmp_path / "ci.yml"
    path.write_text(mutated, encoding="utf-8")

    assert verify_ci_workflow.validate_ci_workflow(path)


def test_workflows_reject_normalized_top_level_overrides(tmp_path: Path) -> None:
    cases = (
        ("ci", Path(".github/workflows/ci.yml"), verify_ci_workflow.validate_ci_workflow),
        (
            "codspeed",
            Path(".github/workflows/codspeed.yml"),
            verify_ci_workflow.validate_codspeed_workflow,
        ),
        (
            "release",
            Path(".github/workflows/publish.yaml"),
            verify_ci_workflow.validate_release_workflow,
        ),
    )

    for label, source, validate in cases:
        workflow = source.read_text(encoding="utf-8")
        for key, value in (("jobs", "  bypass: {}"), ("on", "  workflow_dispatch:")):
            path = tmp_path / f"{label}-{key}.yml"
            path.write_text(workflow + f'\n"{key}":\n{value}\n', encoding="utf-8")

            errors = validate(path)

            assert any(f"top-level '{key}' key" in error for error in errors)


def test_ci_workflow_requires_block_style_top_level_on(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    # Keep every trigger-shaped line as a decoy under another top-level key.
    path.write_text(workflow.replace("on:\n", "on: {}\ntrigger_decoys:\n", 1), encoding="utf-8")

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("block-style top-level 'on' key" in error for error in errors)


def test_codspeed_trigger_checks_ignore_decoy_mapping(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace(
            "on:\n",
            'on:\n  schedule:\n    - cron: "0 0 * * *"\ntrigger_decoys:\n',
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any("only schedule and workflow_dispatch triggers" in error for error in errors)
    assert any("exactly the nightly main cron" in error for error in errors)


def test_codspeed_workflow_rejects_pr_and_push_triggers(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    for index, trigger in enumerate(("pull_request", "push")):
        path = tmp_path / f"codspeed-trigger-{index}.yml"
        path.write_text(
            workflow.replace("  schedule:\n", f"  {trigger}:\n\n  schedule:\n", 1),
            encoding="utf-8",
        )

        errors = verify_ci_workflow.validate_codspeed_workflow(path)

        assert any("only schedule and workflow_dispatch triggers" in error for error in errors)


def test_codspeed_workflow_rejects_drifted_cron_or_concurrency(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    mutations = (
        ('    - cron: "17 7 * * *"', '    - cron: "0 * * * *"'),
        ("  group: codspeed-main", "  group: codspeed-${{ github.ref }}"),
        ("  cancel-in-progress: true", "  cancel-in-progress: false"),
    )
    for index, (old, new) in enumerate(mutations):
        path = tmp_path / f"codspeed-schedule-{index}.yml"
        path.write_text(workflow.replace(old, new), encoding="utf-8")

        errors = verify_ci_workflow.validate_codspeed_workflow(path)

        assert errors


def test_codspeed_workflow_rejects_detector_gate_and_permission_bypasses(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    mutations = (
        ("permissions: {}", "permissions:\n  contents: write"),
        ("      actions: read", "      actions: write"),
        ("      should_run: ${{ steps.changed.outputs.should_run }}", "      should_run: true"),
        ("    needs: detect", "    needs: []"),
        ("    if: needs.detect.outputs.should_run == 'true'", "    if: always()"),
        ("      id-token: write", "      id-token: read"),
        (
            "        run: python3 scripts/codspeed_should_run.py",
            "        run: echo python3 scripts/codspeed_should_run.py",
        ),
    )
    for index, (old, new) in enumerate(mutations):
        path = tmp_path / f"codspeed-gate-{index}.yml"
        path.write_text(workflow.replace(old, new), encoding="utf-8")

        errors = verify_ci_workflow.validate_codspeed_workflow(path)

        assert errors


def test_ci_workflow_rejects_normalized_duplicate_required_job(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "  browser_conformance:\n",
            '  "test":\n    runs-on: ubuntu-latest\n    steps: []\n\n  browser_conformance:\n',
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("exactly one unambiguous 'test' job" in error for error in errors)


def test_workflows_use_consistent_node24_action_pins() -> None:
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(Path(".github/workflows").glob("*.yml"))
    )

    for action, sha in _NODE24_ACTION_PINS.items():
        uses_lines = [line for line in workflow_text.splitlines() if f"uses: {action}@" in line]
        assert uses_lines, f"expected at least one {action} use"
        assert all(f"uses: {action}@{sha}" in line for line in uses_lines), uses_lines


def test_setup_uv_cache_is_only_enabled_intentionally() -> None:
    for path in sorted(Path(".github/workflows").glob("*.yml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if "uses: astral-sh/setup-uv@" not in line:
                continue
            step_indent = len(line) - len(line.lstrip())
            boundary_indent = step_indent - 2 if line.lstrip().startswith("uses:") else step_indent
            block: list[str] = []
            for following in lines[index + 1 :]:
                indent = len(following) - len(following.lstrip())
                if following.strip() and indent <= boundary_indent:
                    break
                block.append(following)
            setting = "\n".join(block)
            assert "enable-cache:" in setting, f"{path}:{index + 1} relies on auto cache mode"


@pytest.mark.parametrize(
    "job",
    ["benchmark_vs", "benchmark_methodology", "benchmark", "matplotlib_reference", "test"],
)
def test_ci_workflow_rejects_advisory_continue_on_error_on_any_job(
    tmp_path: Path, job: str
) -> None:
    """The main benchmark evidence is hard (#1008); only scheduled workflows are advisory."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "continue-on-error" not in workflow
    start = workflow.index(f"\n  {job}:\n") + 1
    header_end = workflow.index("\n", workflow.index("    name:", start)) + 1
    mutated = workflow[:header_end] + "    continue-on-error: true\n" + workflow[header_end:]
    path = tmp_path / "ci.yml"
    path.write_text(mutated, encoding="utf-8")

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("must not use continue-on-error" in error for error in errors)


def test_ci_workflow_rejects_regrouped_expensive_cross_library_adapters(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace("          - name: plotly-svg\n", "", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("benchmark_vs" in error and "plotly-svg" in error for error in errors)


def test_ci_workflow_rejects_substring_preserving_adapter_regrouping(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "            libraries: plotly_svg\n",
            "            libraries: plotly_svg,bokeh_canvas\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any(
        "matrix entry 'plotly-svg'" in error
        and "must exactly equal" in error
        and "plotly_svg,bokeh_canvas" in error
        for error in errors
    )


def test_ci_workflow_rejects_unconditional_cross_library_browser_setup(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "      - name: Install Chromium (Playwright)\n        if: matrix.browser\n",
            "      - name: Install Chromium (Playwright)\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any(
        "Install Chromium (Playwright)" in error and "matrix.browser" in error for error in errors
    )


def test_ci_workflow_rejects_unconditional_cross_library_native_build(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "      - name: Build native core\n        if: matrix.xy\n",
            "      - name: Build native core\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Build native core" in error and "matrix.xy" in error for error in errors)


def test_ci_workflow_rejects_missing_cross_library_job_timeout(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "  benchmark_vs:\n"
            "    name: Cross-library benchmark (${{ matrix.name }})\n"
            "    if: github.event_name == 'push' || github.event_name == 'workflow_dispatch'\n"
            "    runs-on: blacksmith-4vcpu-ubuntu-2404\n"
            "    # The slowest group (native-and-webgl) takes about 5 minutes when installs are\n"
            "    # healthy; leave room for install retries and a slow runner, not a hang.\n"
            "    timeout-minutes: 25\n",
            "  benchmark_vs:\n"
            "    name: Cross-library benchmark (${{ matrix.name }})\n"
            "    if: github.event_name == 'push' || github.event_name == 'workflow_dispatch'\n"
            "    runs-on: blacksmith-4vcpu-ubuntu-2404\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("benchmark_vs" in error and "timeout-minutes: 25" in error for error in errors)


def test_ci_workflow_rejects_unlocked_competitor_install(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "            --constraint benchmarks/requirements-ci.lock ${{ matrix.packages }}\n",
            "            ${{ matrix.packages }}\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any(
        "Install selected competitors" in error and "requirements-ci.lock" in error
        for error in errors
    )


def test_ci_workflow_rejects_benchmark_upload_that_skips_after_failures(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(workflow.replace("        if: always()\n", ""), encoding="utf-8")

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("benchmark" in error and "if: always()" in error for error in errors)


def test_ci_workflow_rejects_benchmark_upload_that_fails_on_missing_report(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(workflow.replace("          if-no-files-found: warn\n", ""), encoding="utf-8")

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("benchmark" in error and "if-no-files-found" in error for error in errors)


def test_ci_workflow_rejects_missing_line_benchmark_verification(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "          .venv/bin/python scripts/verify_benchmark_report.py line.json --kind line-decimation\n",
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("benchmark" in error and "line-decimation" in error for error in errors)


def test_ci_workflow_rejects_missing_install_benchmark_verification(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "          .venv/bin/python scripts/verify_benchmark_report.py install.json --kind install-footprint\n",
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("benchmark" in error and "install-footprint" in error for error in errors)


def test_ci_workflow_rejects_stale_no_rust_import_identity(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace("          assert xyg.__version__\n", "          assert xy.__version__\n"),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("no-Rust" in error and "assert xyg.__version__" in error for error in errors)


def test_ci_workflow_rejects_benchmark_job_without_native_backend_assertion(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    block = (
        "      - name: Verify native benchmark backend\n"
        "        run: |\n"
        "          .venv/bin/python - <<'PY'\n"
        "          import xyg.kernels as k\n"
        '          assert k.BACKEND == "native", f"benchmark job requires native backend, got {k.BACKEND!r}"\n'
        "          PY\n"
    )
    path = tmp_path / "ci.yml"
    path.write_text(workflow.replace(block, ""), encoding="utf-8")

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("benchmark" in error and "native backend" in error for error in errors)


def test_ci_workflow_rejects_benchmark_job_without_required_native_install(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            '        env:\n          XYG_REQUIRE_CARGO: "1"\n'
            "        run: |\n          uv venv .venv\n"
            "          scripts/ci_retry.sh 3 uv pip install -p .venv/bin/python \\\n"
            "            --constraint benchmarks/requirements-ci.lock -e .\n",
            "        run: |\n          uv venv .venv\n"
            "          scripts/ci_retry.sh 3 uv pip install -p .venv/bin/python \\\n"
            "            --constraint benchmarks/requirements-ci.lock -e .\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("benchmark" in error and "XYG_REQUIRE_CARGO" in error for error in errors)


def test_codspeed_workflow_rejects_missing_native_backend_assertion(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    block = (
        "      - name: Verify native benchmark backend\n"
        "        run: |\n"
        "          .venv/bin/python - <<'PY'\n"
        "          import xyg.kernels as k\n"
        '          assert k.BACKEND == "native", f"CodSpeed requires native backend, got {k.BACKEND!r}"\n'
        "          PY\n\n"
    )
    path = tmp_path / "codspeed.yml"
    path.write_text(workflow.replace(block, ""), encoding="utf-8")

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any("CodSpeed benchmarks job" in error and "native backend" in error for error in errors)


def test_codspeed_workflow_rejects_non_strict_native_install(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace(
            '        env:\n          XYG_REQUIRE_CARGO: "1"\n'
            "        run: |\n          uv venv .venv\n"
            "          uv pip install -p .venv/bin/python -e . --group dev --group codspeed\n",
            "        run: |\n          uv venv .venv\n"
            "          uv pip install -p .venv/bin/python -e . --group dev\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any(
        "CodSpeed benchmarks job" in error and "XYG_REQUIRE_CARGO" in error for error in errors
    )


def test_codspeed_workflow_rejects_missing_authored_scene_node_native_path(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace(
            "          XYG_NATIVE_LIB: ${{ github.workspace }}/target/release/libxyg_core.so\n", ""
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any(
        "Generate and measure four-size authored-Scene first paint" in error
        and "native library" in error
        for error in errors
    )


def test_codspeed_workflow_rejects_missing_hosted_density_evidence(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace(
            '          .venv/bin/python scripts/verify_inline_density_benchmark.py "hosted-density-browser-${{ github.sha }}.json" --sha "${{ github.sha }}"\n',
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any(
        "changed-main authored-Scene browser evidence" in error
        and "verify_inline_density_benchmark" in error
        for error in errors
    )


def test_codspeed_workflow_rejects_missing_shell_safe_density_chromium_lookup(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace(
            '          XYG_CHROMIUM="$(node -e \'process.stdout.write(require("playwright").chromium.executablePath())\')"\n',
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any(
        "changed-main authored-Scene browser evidence" in error and "XYG_CHROMIUM" in error
        for error in errors
    )


def test_codspeed_workflow_rejects_scoped_authored_scene_node_native_path_duplication(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace(
            "          XYG_AUTHORED_SCENE_DIR: authored-scenes\n",
            "          XYG_NATIVE_LIB: ${{ github.workspace }}/target/release/libxyg_core.so\n"
            "          XYG_AUTHORED_SCENE_DIR: authored-scenes\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any("only to the authored-Scene measurement step" in error for error in errors)


def test_codspeed_workflow_rejects_missing_native_kernel_benches(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace("cargo install cargo-codspeed --locked --version 4.6.0\n", "")
        .replace(
            "        run: cargo codspeed build -m simulation --bench kernels --bench aggregate --bench typed_series\n",
            "",
        )
        .replace(
            "            cargo codspeed run --bench kernels --bench aggregate --bench typed_series\n",
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any("CodSpeed benchmarks job" in error and "cargo-codspeed" in error for error in errors)


def test_codspeed_workflow_rejects_walltime_build_for_simulation_action(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace(
            "cargo codspeed build -m simulation --bench kernels --bench aggregate --bench typed_series",
            "cargo codspeed build --bench kernels --bench aggregate --bench typed_series",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any("Build Rust kernel benchmarks" in error for error in errors)


def test_codspeed_workflow_requires_fail_fast_before_rust_action(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(workflow.replace("            set -euo pipefail\n", "", 1), encoding="utf-8")

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any("Run benchmarks" in error and "exact action commands" in error for error in errors)


def test_codspeed_workflow_rejects_nonfatal_rust_action(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace(
            "      - name: Run benchmarks\n",
            "      - name: Run benchmarks\n        continue-on-error: true\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any("Run benchmarks" in error and "exact action commands" in error for error in errors)


def test_codspeed_workflow_binds_simulation_mode_to_rust_action(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace("          mode: simulation\n", "          mode: walltime\n"),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any("Run benchmarks" in error and "exact action commands" in error for error in errors)


def test_codspeed_workflow_rejects_duplicate_action_run_key(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace(
            "          run: |\n            set -euo pipefail\n",
            "          run: |\n            set -euo pipefail\n"
            "          run: |\n            cargo codspeed run --bench kernels\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any("Run benchmarks" in error and "exact action commands" in error for error in errors)


def test_codspeed_workflow_rejects_intervening_artifact_rebuild(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace(
            "      - name: Run benchmarks\n",
            "      - name: Replace benchmark artifact\n"
            "        run: cargo codspeed build --bench kernels\n\n"
            "      - name: Run benchmarks\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any("immediately followed" in error for error in errors)
    assert any("exact build/run command pair" in error for error in errors)


def test_codspeed_workflow_rejects_extra_codspeed_run_command(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace(
            "      - name: Build Rust kernel benchmarks\n",
            "      - name: Decoy benchmark run\n"
            "        run: cargo codspeed run --bench kernels\n\n"
            "      - name: Build Rust kernel benchmarks\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any("exact build/run command pair" in error for error in errors)


def test_codspeed_workflow_requires_dedicated_hosted_runner(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/codspeed.yml").read_text(encoding="utf-8")
    path = tmp_path / "codspeed.yml"
    path.write_text(
        workflow.replace(
            "    runs-on: codspeed-macro\n",
            "    runs-on: blacksmith-4vcpu-ubuntu-2404\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_codspeed_workflow(path)

    assert any("dedicated codspeed-macro runner" in error for error in errors)


def test_ci_workflow_rejects_missing_interaction_stress_smoke(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            '          .venv/bin/python scripts/interaction_stress_smoke.py "$CHROME"\n',
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("test job" in error and "interaction_stress_smoke" in error for error in errors)


def test_workflow_policy_rejects_github_hosted_runner_and_playwright_apt(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "bad.yml").write_text(
        "jobs:\n"
        "  browser:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: npx playwright install --with-deps chromium\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("ubuntu-latest" in error for error in errors)
    assert any("must not use --with-deps" in error for error in errors)


def test_ci_workflow_rejects_unbounded_wasm_chromium_install(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "      - name: Install Chromium\n        timeout-minutes: 10\n        run: |\n",
            "      - name: Install Chromium\n        run: |\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Install Chromium" in error and "timeout-minutes: 10" in error for error in errors)


def test_ci_workflow_binds_exact_wasm_target_build(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "cargo build -p xyg-wasm --release --target wasm32-unknown-unknown",
            "cargo build -p xyg-wasm --release --target x86_64-unknown-linux-gnu",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("exact fail-closed wasm32 build" in error for error in errors)


def _job_span(workflow: str, job: str) -> tuple[int, int]:
    start = workflow.index(f"\n  {job}:\n") + 1
    following = re.search(r"\n  [a-z_]+:\n", workflow[start:])
    return start, start + following.start() + 1 if following else len(workflow)


def _mutate_job(workflow: str, job: str, old: str, new: str) -> str:
    start, end = _job_span(workflow, job)
    block = workflow[start:end]
    assert old in block, f"{old!r} not in job {job}"
    return workflow[:start] + block.replace(old, new, 1) + workflow[end:]


_WASM_FETCH_STEP = (
    "      - name: Fetch packaged WASM assets from the wasm_assets producer\n"
    "        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1\n"
    "        with:\n"
    "          name: wasm-assets\n"
    "          path: .\n"
)
_WASM_VERIFY_STEP = (
    "      - name: Verify packaged WASM assets (missing or stale fails here)\n"
    "        run: python3 scripts/verify_wasm_assets.py\n"
)
_WASM_CONSUMERS = (
    "test",
    "wasm_foundation",
    "python_floor",
    "matplotlib_reference",
    "benchmark_methodology",
    "wheels",
    "sdist",
)


def _verify_step(job: str) -> str:
    # The Windows wheel leg has no `python3` shim; every other consumer uses it.
    return _WASM_VERIFY_STEP.replace("python3 ", "python " if job == "wheels" else "python3 ")


def _wasm_errors(tmp_path: Path, workflow: str) -> list[str]:
    path = tmp_path / "ci.yml"
    path.write_text(workflow, encoding="utf-8")
    return verify_ci_workflow.validate_ci_workflow(path)


def test_ci_workflow_accepts_single_wasm_producer_with_every_consumer_wired() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    for job in _WASM_CONSUMERS:
        start, end = _job_span(workflow, job)
        block = workflow[start:end]
        assert "needs:" in block and "wasm_assets" in block, job
        assert "name: wasm-assets" in block, job


@pytest.mark.parametrize("job", _WASM_CONSUMERS)
def test_ci_workflow_requires_every_wasm_consumer_to_depend_on_the_producer(
    tmp_path: Path, job: str
) -> None:
    """BDD: a consumer whose producer was skipped/failed cannot start (#1005)."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    start, end = _job_span(workflow, job)
    block = workflow[start:end]
    needs = re.search(r"\n    needs: .*\n", block)
    assert needs is not None
    # Drop the dependency (keeping other needs, e.g. the release-surface classifier).
    replacement = (
        "\n    needs: release_surface_changes\n"
        if "release_surface_changes" in needs.group(0)
        else "\n"
    )
    mutated = workflow[:start] + block.replace(needs.group(0), replacement, 1) + workflow[end:]
    if job == "wheels":
        mutated = mutated.replace("needs: [release_surface_changes, test]", "")
    errors = _wasm_errors(tmp_path, mutated)
    assert any(f"WASM consumer {job!r} must list wasm_assets in needs" in e for e in errors)


@pytest.mark.parametrize("job", _WASM_CONSUMERS)
@pytest.mark.parametrize("which", ["fetch", "verify"])
def test_ci_workflow_requires_wasm_consumers_to_download_and_verify(
    tmp_path: Path, job: str, which: str
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    step = _WASM_FETCH_STEP if which == "fetch" else _verify_step(job)
    errors = _wasm_errors(tmp_path, _mutate_job(workflow, job, step, ""))
    assert any(
        f"WASM consumer {job!r} must download then verify the packaged WASM assets" in e
        for e in errors
    )


@pytest.mark.parametrize("job", _WASM_CONSUMERS)
def test_ci_workflow_rejects_verify_before_download_and_hidden_asset_steps(
    tmp_path: Path, job: str
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    swapped = _mutate_job(
        workflow,
        job,
        _WASM_FETCH_STEP + _verify_step(job),
        _verify_step(job) + _WASM_FETCH_STEP,
    )
    assert any("must download before it verifies" in e for e in _wasm_errors(tmp_path, swapped))

    hidden = _mutate_job(
        workflow,
        job,
        "        run: "
        + ("python " if job == "wheels" else "python3 ")
        + "scripts/verify_wasm_assets.py\n",
        "        continue-on-error: true\n        run: "
        + ("python " if job == "wheels" else "python3 ")
        + "scripts/verify_wasm_assets.py\n",
    )
    assert any("asset steps must be unconditional" in e for e in _wasm_errors(tmp_path, hidden))


@pytest.mark.parametrize(
    "command",
    [
        "npm run build:wasm",
        "node js/package-wasm.mjs",
        "cargo build -p xyg-wasm --release --target wasm32-unknown-unknown",
    ],
)
def test_ci_workflow_rejects_a_second_wasm_producer(tmp_path: Path, command: str) -> None:
    """Hand-rolled packaging in a consumer could ship stale residue as the real artifact."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    mutated = _mutate_job(
        workflow,
        "benchmark_methodology",
        "      - name: Install JS build toolchain\n        run: scripts/ci_retry.sh 3 npm ci\n",
        "      - name: Install JS build toolchain\n        run: |\n"
        f"          scripts/ci_retry.sh 3 npm ci\n          {command}\n",
    )
    errors = _wasm_errors(tmp_path, mutated)
    label = (
        "cargo build -p xyg-wasm --target wasm32-unknown-unknown"
        if command.startswith("cargo")
        else command
    )
    assert any("must consume wasm-assets" in e and label in e for e in errors)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "          if-no-files-found: error\n          retention-days: 7\n",
            "          retention-days: 7\n",
            "if-no-files-found",
        ),
        (
            "  wasm_assets:\n    name: Packaged WASM assets (single producer)\n",
            "  wasm_assets:\n    name: Packaged WASM assets (single producer)\n    continue-on-error: true\n",
            "job-level 'continue-on-error'",
        ),
        (
            "  wasm_assets:\n    name: Packaged WASM assets (single producer)\n",
            "  wasm_assets:\n    name: Packaged WASM assets (single producer)\n    if: false\n",
            "job-level 'if'",
        ),
        (
            "        run: python3 scripts/verify_wasm_assets.py\n      - name: Upload packaged WASM assets\n",
            "        run: echo skipped\n      - name: Upload packaged WASM assets\n",
            "verify_wasm_assets.py",
        ),
        (
            "          npm run build:wasm\n      - name: Verify packaged WASM assets\n",
            "          echo packaged\n      - name: Verify packaged WASM assets\n",
            "single packaging command",
        ),
    ],
)
def test_ci_workflow_rejects_weakened_wasm_producer(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    errors = _wasm_errors(tmp_path, _mutate_job(workflow, "wasm_assets", old, new))
    assert any("wasm_assets" in e or "packaging command" in e for e in errors), errors
    assert any(message in e for e in errors), errors


@pytest.mark.parametrize("job", ["wheels", "sdist"])
def test_ci_workflow_requires_distribution_builds_to_require_wasm(tmp_path: Path, job: str) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    errors = _wasm_errors(
        tmp_path, _mutate_job(workflow, job, '          XYG_REQUIRE_WASM: "1"\n', "")
    )
    assert any(f"{job} job must build with XYG_REQUIRE_WASM" in e for e in errors)


def test_ci_workflow_requires_worker_before_wasm_payload(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    errors = _wasm_errors(
        tmp_path,
        _mutate_job(
            workflow,
            "python_floor",
            "          node js/build.mjs\n",
            "          npm run build:wasm\n          node js/build.mjs\n",
        ),
    )
    assert any("must consume wasm-assets" in error for error in errors)


def test_ci_workflow_rejects_commented_wasm_chromium_install(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "          # Keep Chromium artifact installation cached and browser-specific.\n"
            "          npx playwright install chromium\n",
            "          # Keep Chromium artifact installation cached and browser-specific.\n"
            "          # npx playwright install chromium\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("active bounded browser-only Playwright" in error for error in errors)


def test_ci_workflow_rejects_duplicate_wasm_foundation_job(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "  wasm_foundation:\n",
            '  "wasm_foundation":\n'
            "    runs-on: blacksmith-4vcpu-ubuntu-2404\n"
            "    steps: []\n\n"
            "  wasm_foundation:\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("exactly one unambiguous 'wasm_foundation' job" in error for error in errors)


def test_workflow_policy_accepts_blacksmith_and_matrix_runners(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "good.yml").write_text(
        "jobs:\n"
        "  browser:\n"
        "    runs-on: blacksmith-4vcpu-ubuntu-2404\n"
        "    steps:\n"
        "      - run: npx playwright install chromium\n"
        "  wheels:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        os:\n"
        "          - blacksmith-4vcpu-ubuntu-2404\n"
        "    runs-on: ${{ matrix.os }}\n",
        encoding="utf-8",
    )

    assert verify_ci_workflow.validate_workflow_hosting_policy(workflows) == []


def test_workflow_policy_rejects_quoted_matrix_alias_and_continued_with_deps(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "bypasses.yml").write_text(
        "jobs:\n"
        "  wheels:\n"
        "    strategy:\n"
        "      matrix:\n"
        '        os: ["blacksmith-4vcpu-ubuntu-2404", "ubuntu-latest"]\n'
        "    runs-on: ${{ matrix.os }}\n"
        "    steps:\n"
        "      - run: |\n"
        "          npx playwright install \\\n"
        "            --with-deps chromium\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("GitHub-hosted runner alias" in error for error in errors)
    assert any("must not use --with-deps" in error for error in errors)


def test_workflow_policy_rejects_arbitrary_matrix_runner(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "matrix.yml").write_text(
        "jobs:\n"
        "  wheels:\n"
        "    strategy:\n"
        "      matrix:\n"
        '        os: ["blacksmith-4vcpu-ubuntu-2404", "arbitrary-runner"]\n'
        "    runs-on: ${{ matrix.os }}\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("matrix.os must be a static list" in error for error in errors)


def test_workflow_policy_rejects_unapproved_blacksmith_label(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "invented.yml").write_text(
        "jobs:\n  test:\n    runs-on: blacksmith-arbitrary-runner\n    steps: []\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("approved Blacksmith runner" in error for error in errors)


def test_workflow_policy_allows_only_oidc_npm_publish_on_github_host(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "publish.yaml").write_text(
        "jobs:\n"
        "  publish-npm:\n"
        "    runs-on: ubuntu-latest\n"
        "    environment: npm\n"
        "    permissions:\n"
        "      id-token: write\n"
        "    steps: []\n",
        encoding="utf-8",
    )
    assert verify_ci_workflow.validate_workflow_hosting_policy(workflows) == []

    (workflows / "publish.yaml").write_text(
        "jobs:\n"
        "  publish-npm:\n"
        "    runs-on: ubuntu-latest\n"
        "    environment: npm\n"
        "    permissions:\n"
        "      id-token: write\n"
        "    steps: []\n"
        "  unrelated:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: []\n",
        encoding="utf-8",
    )
    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)
    assert any("approved Blacksmith runner" in error for error in errors)

    (workflows / "publish.yaml").write_text(
        "jobs:\n"
        "  publish-npm:\n"
        "    runs-on: ubuntu-latest\n"
        "    permissions:\n"
        "      contents: read\n"
        "    steps: []\n",
        encoding="utf-8",
    )
    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)
    assert any("approved Blacksmith runner" in error for error in errors)

    invalid_fields = [
        "    # environment: npm\n    permissions:\n      id-token: write\n",
        "    environment: npm\n    permissions:\n      # id-token: write\n      contents: read\n",
        "    permissions:\n      id-token: write\n",
        "    environment: npm\n    permissions:\n      contents: read\n",
    ]
    for fields in invalid_fields:
        (workflows / "publish.yaml").write_text(
            "jobs:\n  publish-npm:\n    runs-on: ubuntu-latest\n" + fields + "    steps: []\n",
            encoding="utf-8",
        )
        errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)
        assert any("approved Blacksmith runner" in error for error in errors), fields


def test_workflow_policy_allows_codspeed_host_only_in_codspeed_workflow(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    content = "jobs:\n  benchmarks:\n    runs-on: codspeed-macro\n    steps: []\n"
    (workflows / "codspeed.yml").write_text(content, encoding="utf-8")

    assert verify_ci_workflow.validate_workflow_hosting_policy(workflows) == []

    (workflows / "ci.yml").write_text(content, encoding="utf-8")
    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)
    assert any(
        "ci.yml" in error and "dedicated CodSpeed hosted runner" in error for error in errors
    )


def test_workflow_policy_rejects_quoted_runs_on_third_party_runner(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "quoted.yml").write_text(
        'jobs:\n  test:\n    "runs-on": arbitrary-third-party-runner\n    steps: []\n',
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("arbitrary-third-party-runner" in error for error in errors)


def test_workflow_policy_rejects_quoted_job_and_runner_keys(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "quoted.yml").write_text(
        'jobs:\n  "test":\n    "runs-on": arbitrary-third-party-runner\n    steps: []\n',
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("arbitrary-third-party-runner" in error for error in errors)


def test_workflow_policy_rejects_quoted_dynamic_matrix_runner(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "quoted.yml").write_text(
        "jobs:\n"
        "  test:\n"
        '    "runs-on": ${{ matrix.os }}\n'
        "    strategy:\n"
        "      matrix:\n"
        "        os: ${{ fromJSON(vars.RUNNERS) }}\n"
        "    steps: []\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("matrix.os must be a static list" in error for error in errors)


def test_workflow_policy_restricts_codspeed_runner_to_benchmark_job(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "codspeed.yml").write_text(
        "jobs:\n"
        "  benchmarks:\n"
        "    runs-on: codspeed-macro\n"
        "    steps: []\n"
        "  unrelated:\n"
        "    runs-on: codspeed-macro\n"
        "    steps: []\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("job unrelated" in error and "codspeed-macro" in error for error in errors)


def test_workflow_policy_rejects_noncanonical_job_structures(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    cases = [
        '"jobs":\n  test:\n    runs-on: arbitrary-third-party-runner\n    steps: []\n',
        "jobs:\n  test: { runs-on: arbitrary-third-party-runner, steps: [] }\n",
        "jobs: { test: { runs-on: arbitrary-third-party-runner, steps: [] } }\n",
    ]
    for index, content in enumerate(cases):
        path = workflows / f"encoded-{index}.yml"
        path.write_text(content, encoding="utf-8")
        errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)
        assert errors
        path.unlink()


def test_workflow_policy_rejects_quoted_dynamic_axis_with_include_decoy(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "dynamic.yml").write_text(
        "jobs:\n"
        "  test:\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    strategy:\n"
        "      matrix:\n"
        '        "os": ${{ fromJSON(vars.RUNNERS) }}\n'
        "        include:\n"
        "          - os: blacksmith-4vcpu-ubuntu-2404\n"
        "    steps: []\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("matrix.os must be a static list" in error for error in errors)


def test_workflow_policy_rejects_explicit_and_tagged_job_keys(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    cases = [
        "jobs:\n  ? evil\n  :\n    runs-on: arbitrary-third-party-runner\n    steps: []\n"
        "  good:\n    runs-on: blacksmith-4vcpu-ubuntu-2404\n    steps: []\n",
        "jobs:\n  !!str evil:\n    runs-on: arbitrary-third-party-runner\n    steps: []\n"
        "  good:\n    runs-on: blacksmith-4vcpu-ubuntu-2404\n    steps: []\n",
    ]
    for index, content in enumerate(cases):
        path = workflows / f"unsafe-{index}.yml"
        path.write_text(content, encoding="utf-8")
        errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)
        assert errors
        path.unlink()


def test_workflow_policy_rejects_flow_include_runner_override(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "flow-include.yml").write_text(
        "jobs:\n"
        "  wheels:\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    strategy:\n"
        "      matrix:\n"
        "        os: [blacksmith-4vcpu-ubuntu-2404]\n"
        "        include: [{ os: arbitrary-third-party-runner }]\n"
        "    steps: []\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("matrix.os must be a static list" in error for error in errors)


def test_workflow_policy_rejects_quoted_include_runner_override(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "quoted-include.yml").write_text(
        "jobs:\n"
        "  wheels:\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    strategy:\n"
        "      matrix:\n"
        "        include:\n"
        '          - "os": arbitrary-third-party-runner\n'
        "    steps: []\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("arbitrary-third-party-runner" in error for error in errors)


def test_workflow_policy_preserves_hash_in_quoted_matrix_runner(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    cases = [
        '        os:\n          - "blacksmith-4vcpu-ubuntu-2404#arbitrary-third-party-runner"\n',
        "        include:\n"
        '          - "os": "blacksmith-4vcpu-ubuntu-2404#arbitrary-third-party-runner"\n',
    ]
    for index, matrix in enumerate(cases):
        path = workflows / f"quoted-hash-{index}.yml"
        path.write_text(
            "jobs:\n"
            "  wheels:\n"
            "    runs-on: ${{ matrix.os }}\n"
            "    strategy:\n"
            "      matrix:\n"
            f"{matrix}"
            "    steps: []\n",
            encoding="utf-8",
        )
        errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)
        assert any("matrix.os must be a static list" in error for error in errors)
        path.unlink()


def test_workflow_policy_rejects_multiline_matrix_runner_scalar(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "multiline.yml").write_text(
        "jobs:\n"
        "  wheels:\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    strategy:\n"
        "      matrix:\n"
        "        os:\n"
        "          - blacksmith-4vcpu-ubuntu-2404\n"
        "            arbitrary-third-party-runner\n"
        "    steps: []\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("matrix.os must be a static list" in error for error in errors)


def test_workflow_policy_rejects_quoted_flow_include_runner(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "quoted-flow.yml").write_text(
        "jobs:\n"
        "  wheels:\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    strategy:\n"
        "      matrix:\n"
        "        include:\n"
        '          - { os: "blacksmith-4vcpu-ubuntu-2404}arbitrary-third-party-runner" }\n'
        "    steps: []\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("matrix.os must be a static list" in error for error in errors)


def test_workflow_policy_rejects_inline_matrix_axis(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "inline-axis.yml").write_text(
        "jobs:\n"
        "  wheels:\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    strategy:\n"
        "      matrix:\n"
        '        os: ["blacksmith-4vcpu-ubuntu-2404,blacksmith-4vcpu-ubuntu-2404"]\n'
        "    steps: []\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("matrix.os must be a static list" in error for error in errors)


def test_workflow_policy_rejects_nested_quoted_runner_scalars(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    cases = [
        "        os:\n          - '\"blacksmith-4vcpu-ubuntu-2404\"'\n",
        "        include:\n          - os: '\"blacksmith-4vcpu-ubuntu-2404\"'\n",
    ]
    for index, matrix in enumerate(cases):
        path = workflows / f"nested-quote-{index}.yml"
        path.write_text(
            "jobs:\n"
            "  wheels:\n"
            "    runs-on: ${{ matrix.os }}\n"
            "    strategy:\n"
            "      matrix:\n"
            f"{matrix}"
            "    steps: []\n",
            encoding="utf-8",
        )
        errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)
        assert any("matrix.os must be a static list" in error for error in errors)
        path.unlink()


def test_workflow_policy_rejects_dynamic_matrix_with_unrelated_os_decoy(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "dynamic.yml").write_text(
        "jobs:\n"
        "  test:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        os: ${{ fromJSON(vars.RUNNERS) }}\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    steps:\n"
        "      - run: true\n"
        "        env: { os: blacksmith-4vcpu-ubuntu-2404 }\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("matrix.os must be a static list" in error for error in errors)


def test_workflow_policy_rejects_dynamic_axis_even_with_approved_include(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "mixed.yml").write_text(
        "jobs:\n"
        "  test:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        os: ${{ fromJSON(vars.RUNNERS) }}\n"
        "        include:\n"
        "          - os: blacksmith-4vcpu-ubuntu-2404\n"
        "            feature: x\n"
        "    runs-on: ${{ matrix.os }}\n",
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow_hosting_policy(workflows)

    assert any("matrix.os must be a static list" in error for error in errors)


def test_ci_workflow_rejects_unbounded_or_missing_webkit_dependencies(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    start = workflow.index("      - name: Install WebKit runtime libraries\n")
    end = workflow.index("npx playwright install-deps webkit\n", start) + len(
        "npx playwright install-deps webkit\n"
    )
    step = workflow[start:end]
    path = tmp_path / "ci.yml"
    for mutated in (
        "      - name: Install WebKit runtime libraries\n        run: true\n",
        # Without the needrestart guard the step hangs after installing.
        step.replace("$nrconf{restart} = 'l';", "true;"),
    ):
        assert mutated != step
        path.write_text(workflow.replace(step, mutated, 1), encoding="utf-8")

        errors = verify_ci_workflow.validate_ci_workflow(path)

        assert any("WebKit dependency install" in error for error in errors)


def test_ci_workflow_rejects_missing_dashboard_reliability_smoke(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    block = (
        "      - name: Browser dashboard reliability smoke (Chromium)\n"
        "        run: |\n"
        "          CHROME=$(node -e \"console.log(require('playwright').chromium.executablePath())\")\n"
        "          .venv/bin/python benchmarks/bench_dashboard.py \\\n"
        '            --chart-counts 10,20,50,60 --chromium "$CHROME" --json dashboard-smoke.json\n'
        "          .venv/bin/python scripts/verify_benchmark_report.py \\\n"
        "            dashboard-smoke.json --kind dashboard-browser\n\n"
    )
    path = tmp_path / "ci.yml"
    path.write_text(workflow.replace(block, ""), encoding="utf-8")

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("test job" in error and "dashboard reliability" in error for error in errors)


def test_ci_workflow_rejects_dashboard_reliability_smoke_without_sixty_charts(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            '--chart-counts 10,20,50,60 --chromium "$CHROME" --json dashboard-smoke.json',
            '--chart-counts 10,20,50 --chromium "$CHROME" --json dashboard-smoke.json',
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("test job" in error and "--chart-counts 10,20,50,60" in error for error in errors)


def test_ci_workflow_rejects_methodology_dashboard_without_sixty_charts(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            '--chart-counts 10,20,50,60 --chromium "$CHROME" \\\n'
            "            --json dashboard.json | tee -a docs/benchmark_ci.md",
            '--chart-counts 10,20,50 --chromium "$CHROME" \\\n'
            "            --json dashboard.json | tee -a docs/benchmark_ci.md",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any(
        "benchmark_methodology job" in error and "--chart-counts 10,20,50,60" in error
        for error in errors
    )


def test_ci_workflow_rejects_missing_app_lifecycle_smoke(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            '          .venv/bin/python scripts/app_lifecycle_smoke.py "$CHROME"\n',
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("test job" in error and "app_lifecycle_smoke" in error for error in errors)


def test_ci_workflow_rejects_missing_visual_regression_smoke(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            '          .venv/bin/python scripts/visual_regression_smoke.py "$CHROME"\n',
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("test job" in error and "visual_regression_smoke" in error for error in errors)


def test_ci_workflow_rejects_missing_cross_browser_conformance(tmp_path: Path) -> None:
    text = verify_ci_workflow.DEFAULT_CI_WORKFLOW.read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        text.replace(
            '        run: xvfb-run --auto-servernum --server-args="-screen 0 1280x720x24" '
            "node scripts/browser_conformance.mjs\n",
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("browser_conformance" in error and "conformance gate" in error for error in errors)


def test_ci_workflow_rejects_missing_node_xyts_cross_host_conformance(tmp_path: Path) -> None:
    workflow = verify_ci_workflow.DEFAULT_CI_WORKFLOW.read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "          node --test packages/xy-node/test/xyts-conformance.test.mjs\n",
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("test" in error and "xyts-conformance.test.mjs" in error for error in errors)


def test_ci_workflow_rejects_disabled_node_xyts_cross_host_conformance(tmp_path: Path) -> None:
    workflow = verify_ci_workflow.DEFAULT_CI_WORKFLOW.read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "      - name: Node XYTS cross-host conformance\n        run: |\n",
            "      - name: Node XYTS cross-host conformance\n        if: false\n        run: |\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Node XYTS cross-host conformance" in error for error in errors)


def test_ci_workflow_rejects_unexported_node_xyts_native_library(tmp_path: Path) -> None:
    workflow = verify_ci_workflow.DEFAULT_CI_WORKFLOW.read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            '          export XYG_NATIVE_LIB="$GITHUB_WORKSPACE/target/release/libxyg_core.so"\n',
            '          XYG_NATIVE_LIB="$GITHUB_WORKSPACE/target/release/libxyg_core.so"\n',
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("Node XYTS cross-host conformance" in error for error in errors)


@pytest.mark.parametrize(
    ("step", "needle"),
    [
        ("Restore WebKit runtime packages", None),
        ("Restore WebKit runtime packages", "restore-keys: "),
        ("Restore WebKit runtime packages", "-${{ github.run_id }}"),
        ("Install WebKit runtime libraries", 'APT::Keep-Downloaded-Packages "true";'),
        (
            "Install WebKit runtime libraries",
            'sudo cp "$HOME"/.cache/xyg-webkit-debs/*.deb /var/cache/apt/archives/',
        ),
        ("Install WebKit runtime libraries", "sudo apt-get autoclean -y"),
        (
            "Install WebKit runtime libraries",
            "cp /var/cache/apt/archives/*.deb ~/.cache/xyg-webkit-debs/",
        ),
        ("Install WebKit runtime libraries", 'echo "changed=true" >> "$GITHUB_OUTPUT"'),
        ("Save WebKit runtime packages", None),
        ("Save WebKit runtime packages", "if: steps.webkit-deps.outputs.changed == 'true'"),
    ],
)
def test_ci_workflow_rejects_a_broken_webkit_package_cache(
    tmp_path: Path, step: str, needle: str | None
) -> None:
    text = verify_ci_workflow.DEFAULT_CI_WORKFLOW.read_text(encoding="utf-8")
    start = text.index(f"      - name: {step}\n")
    end = text.index("      - name: ", start + 1)
    block = text[start:end]
    if needle is None:
        mutated = ""  # the whole step
    else:
        assert needle in block
        mutated = block.replace(needle, "", 1)
    path = tmp_path / "ci.yml"
    path.write_text(text[:start] + mutated + text[end:], encoding="utf-8")

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any(step in error for error in errors), errors


def test_ci_workflow_rejects_missing_playwright_browser_cache(tmp_path: Path) -> None:
    text = verify_ci_workflow.DEFAULT_CI_WORKFLOW.read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        text.replace(
            "      - name: Cache Playwright browsers\n"
            "        uses: actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0\n"
            "        with:\n"
            "          path: ~/.cache/ms-playwright\n"
            "          key: playwright-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('package-lock.json') }}\n",
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    # Two pinned caches share the job, so the rule is per step.
    assert "missing required CI step 'Cache Playwright browsers'" in errors
    assert any("browser_conformance" in error and "ms-playwright" in error for error in errors)


def test_ci_workflow_rejects_missing_regression_gate(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "          python3 scripts/check_regressions.py --scatter scatter.json --kernel kernel.json \\\n"
            "            --transport transport.json --emit-md spec/benchmarks/metrics.md\n",
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("test job" in error and "check_regressions" in error for error in errors)


def test_ci_workflow_rejects_missing_transport_regression_probe(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "          .venv/bin/python benchmarks/bench_transport.py --n 1e6 --reps 15 \\\n"
            '            --browser-reps 12 --chromium "$CHROME" --require-browser --json transport.json\n',
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("test job" in error and "bench_transport" in error for error in errors)


def test_ci_workflow_rejects_missing_kernel_benchmark_verification(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "          python3 scripts/verify_benchmark_report.py kernel.json --kind kernel-native\n",
            "",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("test job" in error and "kernel-native" in error for error in errors)


def test_ci_workflow_rejects_missing_regression_benchmark_upload(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    # Strip the whole step up to its next sibling, independent of the pinned
    # upload-artifact SHA. Explicit boundaries avoid regex backtracking on
    # adversarially long workflow text.
    step_start = workflow.index("      - name: Upload regression benchmark report\n")
    next_step = workflow.index("\n      - ", step_start)
    broken = workflow[:step_start] + workflow[next_step + 1 :]
    assert "regression-benchmark-report" not in broken
    path = tmp_path / "ci.yml"
    path.write_text(broken, encoding="utf-8")

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("test job" in error and "regression-benchmark-report" in error for error in errors)


def test_ci_workflow_rejects_regression_upload_that_skips_after_failures(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "      - name: Upload regression benchmark report\n        if: always()\n",
            "      - name: Upload regression benchmark report\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("test job" in error and "if: always()" in error for error in errors)


def test_ci_workflow_rejects_delegation_upload_that_skips_after_failures(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            "      - name: Upload executable host-delegation evidence\n        if: always()\n",
            "      - name: Upload executable host-delegation evidence\n",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("host-delegation evidence" in error and "if: always()" in error for error in errors)


def test_ci_workflow_rejects_missing_wheel_upload(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(_UPLOAD_ARTIFACT_USES.sub("", workflow), encoding="utf-8")

    errors = verify_ci_workflow.validate_workflow(path)

    assert any("wheels" in error and "upload-artifact" in error for error in errors)


def test_release_workflow_accepts_current_gates() -> None:
    assert verify_ci_workflow.validate_release_workflow() == []


def test_release_workflow_rejects_duplicate_plain_python_smoke(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    marker = "      - name: Prove plain Python wheel needs no optional host framework\n"
    start = workflow.index(marker)
    end = workflow.index("      - uses: actions/upload-artifact@", start)
    step = workflow[start:end]
    path = tmp_path / "publish.yaml"
    path.write_text(workflow[:end] + step + workflow[end:], encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("exactly one active named plain-Python" in error for error in errors)


def test_release_workflow_rejects_unconditioned_plain_python_smoke(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    marker = "      - name: Prove plain Python wheel needs no optional host framework\n"
    start = workflow.index(marker)
    condition = "        if: matrix.native\n"
    condition_start = workflow.index(condition, start)
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow[:condition_start] + workflow[condition_start + len(condition) :],
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("exact if: matrix.native" in error for error in errors)


def test_release_workflow_rejects_plain_python_command_hidden_in_heredoc(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    command = '          cp scripts/plain_python_smoke.py "$RUNNER_TEMP/plain-python-smoke.py"\n'
    hidden = (
        "          python - <<'PY'\n"
        '          cp scripts/plain_python_smoke.py "$RUNNER_TEMP/plain-python-smoke.py"\n'
        "          PY\n"
    )
    path = tmp_path / "publish.yaml"
    path.write_text(workflow.replace(command, hidden, 1), encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("exact isolated installed-wheel commands" in error for error in errors)


def test_release_workflow_rejects_inherited_upstream_tag_trigger(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(workflow.replace('["xyg-v*"]', '["v*"]', 1), encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("xyg-v*" in error for error in errors)


def test_release_workflow_rejects_branch_dispatch_real_publish(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace(
            "            refs/tags/xyg-v*) ;;\n",
            "            refs/heads/*) ;;\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("real-publish tag guard" in error for error in errors)


def test_release_workflow_requires_changelog_gate_on_real_dispatch(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    gate = "        if: github.event_name == 'push' || github.event.inputs.dry_run != 'true'\n"
    # Mutate the second occurrence, which belongs to check_release_version.
    first, separator, rest = workflow.partition(gate)
    assert separator and gate in rest
    path.write_text(
        first + separator + rest.replace(gate, "        if: github.event_name == 'push'\n", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("real-publish changelog gate" in error for error in errors)


def test_release_workflow_requires_post_publish_github_release(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace("          gh release create ", "          echo ", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("GitHub Release" in error and "gh release create" in error for error in errors)


def test_release_workflow_requires_browser_package_gate(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace("          npm run build:wasm\n", "", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("single packaging command" in error for error in errors)


def test_github_release_flattens_downloaded_wheel_for_attachment(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    prefix, separator, release_block = workflow.partition("  github-release:\n")
    assert separator and "          merge-multiple: true\n" in release_block
    release_block = release_block.replace("          merge-multiple: true\n", "", 1)
    path = tmp_path / "publish.yaml"
    path.write_text(prefix + separator + release_block, encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("GitHub Release" in error and "merge-multiple" in error for error in errors)


def test_github_release_cannot_run_for_dry_or_untagged_build(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    job_gate = f"    if: {verify_ci_workflow.GITHUB_RELEASE_GATE}\n"
    release_header = (
        "  github-release:\n    name: Create GitHub Release\n    needs: [publish, publish-npm]\n"
    )
    target = release_header + job_gate
    assert target in workflow
    path.write_text(
        workflow.replace(target, release_header + "    if: always()\n", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("GitHub Release job must use" in error for error in errors)


def test_release_workflow_rejects_missing_native_wheel_verifier(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace(
            '          python scripts/verify_wheel.py "$whl" --expect-native --require-wasm\n', ""
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("release wheels job" in error and "verify_wheel" in error for error in errors)


def test_release_workflow_requires_node_clean_install_matrix(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace("  node-clean-install:\n", "  removed-node-clean-install:\n", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("node-clean-install" in error for error in errors)


def test_release_workflow_rejects_nonblocking_native_wheel_matrix(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace(
            "    runs-on: ${{ matrix.os }}\n",
            "    runs-on: ${{ matrix.os }}\n    continue-on-error: true\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("wheels job must block publishing" in error for error in errors)


def test_release_workflow_rejects_unpinned_pyodide_runtime_contract(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace('            RUSTFLAGS="-C panic=abort"\n', "")
        .replace("          CIBW_BUILD: cp314-pyodide_wasm32\n", "")
        .replace('          CIBW_PYODIDE_VERSION: "314.0.0"\n', "")
        .replace(
            "          CIBW_BEFORE_BUILD_PYODIDE: >-\n"
            "            cargo build --release --target wasm32-unknown-emscripten\n",
            "",
        )
        .replace(
            "        uses: pypa/cibuildwheel@294735312765b09d24a2fbec22660ce817587d55 # v4.1.0\n",
            "",
        )
        .replace("          npm i --no-save pyodide@314.0.0\n", ""),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any(
        "release wasm job" in error
        and "panic=abort" in error
        and "cibuildwheel" in error
        and "pyodide@314.0.0" in error
        for error in errors
    )


def test_release_workflow_rejects_nonblocking_pyodide_probe(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace(
            "    runs-on: blacksmith-4vcpu-ubuntu-2404\n",
            "    runs-on: blacksmith-4vcpu-ubuntu-2404\n    continue-on-error: true\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("wasm job must block publishing" in error for error in errors)


def test_release_workflow_rejects_broad_wasm_permissions(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace(
            "    permissions:\n      contents: read\n    steps:\n",
            "    steps:\n",
            1,
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("release wasm job" in error and "contents: read" in error for error in errors)


def test_release_workflow_rejects_pyemscripten_artifact_outside_pypi_batch(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace(
            "          name: dist-pyemscripten\n", "          name: pyemscripten-wheel\n"
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("release wasm job" in error and "dist-pyemscripten" in error for error in errors)


def test_ci_workflow_rejects_missing_sdist_rust_smoke(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    moved = workflow.replace(
        "      - name: Build sdist\n",
        '      - name: Build sdist\n        env:\n          XYG_REQUIRE_CARGO: "1"\n',
        1,
    ).replace(
        "      - name: Build and load native core from sdist\n"
        "        shell: bash\n"
        "        env:\n"
        '          XYG_REQUIRE_CARGO: "1"\n',
        "      - name: Build and load native core from sdist\n        shell: bash\n",
    )
    path.write_text(moved, encoding="utf-8")

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any(
        "Build and load native core from sdist" in error and "XYG_REQUIRE_CARGO" in error
        for error in errors
    )


def test_release_workflow_rejects_missing_sdist_rust_smoke(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    moved = workflow.replace(
        "      - name: Build sdist\n",
        '      - name: Build sdist\n        env:\n          XYG_REQUIRE_CARGO: "1"\n',
        1,
    ).replace(
        "      - name: Build and load native core from sdist\n"
        "        shell: bash\n"
        "        env:\n"
        '          XYG_REQUIRE_CARGO: "1"\n',
        "      - name: Build and load native core from sdist\n        shell: bash\n",
    )
    path.write_text(moved, encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any(
        "Build and load native core from sdist" in error and "XYG_REQUIRE_CARGO" in error
        for error in errors
    )


def test_ci_workflow_rejects_missing_coreless_sdist_xyg_import(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    prefix, smoke = workflow.split("      - name: Verify coreless sdist imports xyg\n", 1)
    path = tmp_path / "ci.yml"
    path.write_text(
        prefix
        + "      - name: Verify coreless sdist imports xyg\n"
        + smoke.replace("          import xyg\n", "          import removed_xyg\n", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any(
        "Verify coreless sdist imports xyg" in error and "import xyg" in error for error in errors
    )


def test_release_workflow_rejects_missing_coreless_sdist_xyg_import(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    prefix, smoke = workflow.split("      - name: Verify coreless sdist imports xyg\n", 1)
    path = tmp_path / "publish.yaml"
    path.write_text(
        prefix
        + "      - name: Verify coreless sdist imports xyg\n"
        + smoke.replace("          import xyg\n", "          import removed_xyg\n", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any(
        "Verify coreless sdist imports xyg" in error and "import xyg" in error for error in errors
    )


def test_release_workflow_rejects_missing_trusted_publishing(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace("      id-token: write", "      id-token-removed: write"),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("release publish job" in error and "id-token" in error for error in errors)


def test_release_workflow_rejects_pypi_token_publish(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace(
            "      id-token: write",
            "      id-token: write\n      api-token: ${{ secrets.PYPI_API_TOKEN }}",
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("trusted publishing" in error and "token" in error for error in errors)


def test_release_workflow_rejects_missing_dry_run_input(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(workflow.replace("      dry_run:\n", "      dry_ran:\n"), encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("dry-run input" in error for error in errors)


def test_release_dry_run_rejects_inline_or_unsafe_duplicate_trigger(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    marker = "\n# Limit build jobs to repository reads."
    assert marker in workflow
    duplicates = (
        '  "\\u0077orkflow_dispatch": {}\n',
        "  !!str workflow_dispatch: {}\n",
    )
    for index, duplicate in enumerate(duplicates):
        path = tmp_path / f"release-duplicate-trigger-{index}.yml"
        path.write_text(workflow.replace(marker, f"\n{duplicate}{marker}", 1), encoding="utf-8")

        errors = verify_ci_workflow.validate_release_workflow(path)

        assert any("dry-run input" in error for error in errors)


def test_release_workflow_rejects_false_dry_run_default_hidden_by_comment(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace("        default: true\n", "        default: false # default: true\n", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("dry-run input" in error for error in errors)


def test_release_workflow_rejects_ungated_pypi_publish_step(tmp_path: Path) -> None:
    """A sibling step's `if:` (the dry-run summary) must not mask a missing
    gate on the actual PyPI upload step — regression for a bug where the
    checker's own regex matched across step boundaries under re.DOTALL."""
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace(RELEASE_PUBLISH_GATE_LINE, ""),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("is not gated by the dry-run predicate" in error for error in errors)


def test_release_workflow_rejects_duplicate_pypi_publish_condition(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    gate = RELEASE_PUBLISH_GATE_LINE
    path = tmp_path / "publish.yaml"
    path.write_text(workflow.replace(gate, gate + '        "if": always()\n', 1), encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("is not gated by the dry-run predicate" in error for error in errors)


def test_release_job_scalar_cannot_decoy_the_publish_step(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    gate = RELEASE_PUBLISH_GATE_LINE
    decoy = "\n    name: |2\n      - uses: pypa/gh-action-pypi-publish@decoy\n" + gate
    path = tmp_path / "publish.yaml"
    path.write_text(workflow.replace(gate, "", 1) + decoy, encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("is not gated by the dry-run predicate" in error for error in errors)


def test_release_workflow_rejects_missing_fork_repository_guard(tmp_path: Path) -> None:
    """The publish job's own `if:` is what keeps any other repository slug —
    including forks/mirrors of this fork — away from the PyPI upload (#13)."""
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    guard = "    if: github.repository == 'CurateLabs/xyg'\n"
    assert guard in workflow
    path = tmp_path / "publish.yaml"
    path.write_text(workflow.replace(guard, ""), encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("fork repository guard" in error for error in errors)


def test_release_workflow_rejects_missing_fork_publish_guard_step(tmp_path: Path) -> None:
    """The guard step is the configuration-independent stop: it must fail any
    real publish attempt while still refusing upstream's `xy` name (#13)."""
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    step = "      - name: Fork publish guard (refuse upstream's PyPI package name)\n"
    assert step in workflow
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace(step, "      - name: Renamed away from the guarded step\n"),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("release publish job" in error and "Fork publish guard" in error for error in errors)


def test_release_workflow_rejects_missing_publish_opt_in_variable(tmp_path: Path) -> None:
    """Dropping the XYG_ALLOW_PYPI_PUBLISH opt-in from the upload condition
    reverts to publish-on-tag, which this fork must never do (#13)."""
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    opt_in = "vars.XYG_ALLOW_PYPI_PUBLISH == 'true' && "
    assert opt_in in workflow
    path = tmp_path / "publish.yaml"
    path.write_text(workflow.replace(opt_in, ""), encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("is not gated by the dry-run predicate" in error for error in errors)


def test_release_publish_job_keeps_checkout_read_permission(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    prefix, separator, publish_and_after = workflow.partition("  publish:\n")
    assert separator and "      contents: read\n" in publish_and_after
    publish_and_after = publish_and_after.replace("      contents: read\n", "", 1)
    path = tmp_path / "publish.yaml"
    path.write_text(prefix + separator + publish_and_after, encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("publish job" in error and "contents: read" in error for error in errors)


def test_release_workflow_rejects_non_retryable_pypi_publish(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(workflow.replace("          skip-existing: true\n", ""), encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("release publish job" in error and "skip-existing" in error for error in errors)


def test_release_workflow_rejects_shallow_checkout(tmp_path: Path) -> None:
    """A depth-1 checkout fetches no tags, and the version is derived from them.

    That failure is silent — the build succeeds at the 0.0.0 fallback and
    publishes it — so the checker has to catch it instead of the release.
    """
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(workflow.replace("          fetch-depth: 0\n", ""), encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("fetch-depth: 0" in error and "0.0.0" in error for error in errors)


def test_ci_workflow_rejects_shallow_checkout(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(workflow.replace("          fetch-depth: 0\n", ""), encoding="utf-8")

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("fetch-depth: 0" in error for error in errors)


def test_ci_workflow_decodes_quoted_checkout_uses_key(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    uses_keys = ('"uses"', '"\\u0075ses"')
    for index, uses_key in enumerate(uses_keys):
        mutated = workflow.replace(
            "      - uses: actions/checkout@",
            f"      - {uses_key}: actions/checkout@",
            1,
        ).replace("          fetch-depth: 0\n", "", 1)
        path = tmp_path / f"ci-quoted-checkout-{index}.yml"
        path.write_text(mutated, encoding="utf-8")

        errors = verify_ci_workflow.validate_ci_workflow(path)

        assert any("fetch-depth: 0" in error for error in errors)


def test_workflows_reject_fetch_depth_hidden_in_scalar_input(tmp_path: Path) -> None:
    cases = (
        (Path(".github/workflows/ci.yml"), verify_ci_workflow.validate_ci_workflow),
        (Path(".github/workflows/codspeed.yml"), verify_ci_workflow.validate_codspeed_workflow),
        (Path(".github/workflows/publish.yaml"), verify_ci_workflow.validate_release_workflow),
    )
    for index, (source, validate) in enumerate(cases):
        workflow = source.read_text(encoding="utf-8")
        path = tmp_path / f"workflow-{index}.yml"
        path.write_text(
            workflow.replace(
                "          fetch-depth: 0",
                "          decoy: |\n            fetch-depth: 0",
            ),
            encoding="utf-8",
        )

        errors = validate(path)

        assert any("fetch-depth: 0" in error for error in errors)


def test_release_workflow_rejects_always_conditioned_pypi_publish(tmp_path: Path) -> None:
    # `if: always()` is *a* condition but gates nothing: a mere has-an-if
    # check would accept it and let a manual dispatch publish unconditionally.
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    gate = RELEASE_PUBLISH_GATE_LINE
    assert gate in workflow
    path.write_text(workflow.replace(gate, "        if: always()\n"), encoding="utf-8")

    errors = verify_ci_workflow.validate_release_workflow(path)

    assert any("is not gated by the dry-run predicate" in error for error in errors)


# ---------------------------------------------------------------------------
# Release surfaces aggregate: hard/advisory inventory, applicability, ruleset (#1008)
# ---------------------------------------------------------------------------

_HARD_JOBS = (
    "test",
    "wasm_assets",
    "wasm_foundation",
    "python_floor",
    "browser_conformance",
    "sdist",
    "wheels",
    "install_without_rust",
    "authored_scene",
    "matplotlib_reference",
    "benchmark_vs",
    "benchmark_methodology",
    "benchmark",
)


def test_release_inventory_matches_the_workflow_contract_constants() -> None:
    inventory = verify_ci_workflow.release_inventory
    assert tuple(sorted(inventory.HARD_JOBS)) == tuple(sorted(_HARD_JOBS))
    assert {
        *_HARD_JOBS,
        "release_surface_changes",
        "release_surfaces",
    } == verify_ci_workflow.REQUIRED_CI_JOBS


def test_ci_workflow_requires_every_job_to_be_classified(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    extra = "  unclassified_extra:\n    runs-on: blacksmith-4vcpu-ubuntu-2404\n    steps:\n      - run: true\n\n"
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace("  release_surfaces:\n", extra + "  release_surfaces:\n", 1),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any(
        "'unclassified_extra' is neither a hard release gate nor listed advisory" in e
        for e in errors
    )


@pytest.mark.parametrize("job", _HARD_JOBS)
def test_ci_workflow_requires_aggregate_to_depend_on_every_hard_job(
    tmp_path: Path, job: str
) -> None:
    """A hard job that is not an aggregate input could fail while Release surfaces passes."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    needs_line = f"      - {job}\n"
    start = workflow.index("  release_surfaces:\n")
    block_end = workflow.index("    runs-on:", start)
    block = workflow[start:block_end]
    assert needs_line in block
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow[:start] + block.replace(needs_line, "", 1) + workflow[block_end:], encoding="utf-8"
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any(
        "Release surfaces must need exactly the classifier and every hard job" in e for e in errors
    )


@pytest.mark.parametrize("job", _HARD_JOBS)
def test_ci_workflow_requires_aggregate_command_to_pass_every_hard_result(
    tmp_path: Path, job: str
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    line = re.search(
        rf'            --job "{job}=\$\{{\{{ needs\.{job}\.result \}}\}}"( \\)?\n', workflow
    )
    assert line is not None
    mutated = workflow.replace(line.group(0), "", 1)
    if job == "benchmark":  # last argument: keep the previous line's continuation valid
        mutated = mutated.replace(
            '--job "benchmark_methodology=${{ needs.benchmark_methodology.result }}" \\\n',
            '--job "benchmark_methodology=${{ needs.benchmark_methodology.result }}"\n',
            1,
        )
    path = tmp_path / "ci.yml"
    path.write_text(mutated, encoding="utf-8")

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any(
        "must pass --job NAME=${{ needs.NAME.result }} for every hard job" in e for e in errors
    )


def test_ci_workflow_rejects_aggregate_passing_another_jobs_result(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow.replace(
            '"wheels=${{ needs.wheels.result }}"', '"wheels=${{ needs.sdist.result }}"', 1
        ),
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("must pass --job NAME=${{ needs.NAME.result }}" in e for e in errors)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('            --event "${{ github.event_name }}" \\\n', ""),
        ('            --required "${{ needs.release_surface_changes.outputs.required }}" \\\n', ""),
    ],
)
def test_ci_workflow_requires_aggregate_to_receive_event_and_classifier(
    tmp_path: Path, old: str, new: str
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert old in workflow
    path = tmp_path / "ci.yml"
    path.write_text(workflow.replace(old, new, 1), encoding="utf-8")

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("--event and the classifier --required output" in e for e in errors)


@pytest.mark.parametrize(
    ("job", "old", "new", "scenario"),
    [
        # Applicable but not run: the aggregate would wait for a skipped job (or, worse, a
        # future edit could drop the job from the workflow and keep the aggregate green).
        (
            "matplotlib_reference",
            "    if: github.event_name != 'pull_request' || needs.release_surface_changes.outputs.required == 'true'\n",
            "    if: github.event_name == 'push' || github.event_name == 'workflow_dispatch'\n",
            "merge_group",
        ),
        (
            "benchmark_vs",
            "    if: github.event_name == 'push' || github.event_name == 'workflow_dispatch'\n",
            "    if: github.event_name != 'pull_request'\n",
            "merge_group",
        ),
        (
            "sdist",
            "    if: github.event_name != 'pull_request' || needs.release_surface_changes.outputs.required == 'true'\n",
            "    if: github.event_name == 'push'\n",
            "merge_group",
        ),
    ],
)
def test_ci_workflow_applicability_must_match_what_the_workflow_runs(
    tmp_path: Path, job: str, old: str, new: str, scenario: str
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    path = tmp_path / "ci.yml"
    path.write_text(_mutate_job(workflow, job, old, new), encoding="utf-8")

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any(
        (scenario in e and "differs from the jobs the workflow runs" in e)
        or f"hard job {job!r} uses an unrecognized if condition" in e
        for e in errors
    ), errors


def test_aggregate_propagation_self_test_rejects_a_weakened_aggregate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The self-test itself must go red when the aggregate swallows a failure."""
    inventory = verify_ci_workflow.release_inventory
    real = inventory.verify

    def lenient(*, required: bool, results: dict[str, str], event: str = "pull_request"):
        return [
            e
            for e in real(required=required, results=results, event=event)
            if "matplotlib" not in e and "benchmark_vs" not in e
        ]

    monkeypatch.setattr(inventory, "verify", lenient)
    errors = verify_ci_workflow._aggregate_propagation_errors({name: name for name in _HARD_JOBS})

    assert any("matplotlib_reference=failure" in e for e in errors)
    assert any("benchmark_vs=failure" in e for e in errors)


def test_aggregate_propagation_self_test_accepts_the_real_aggregate() -> None:
    assert (
        verify_ci_workflow._aggregate_propagation_errors({name: name for name in _HARD_JOBS}) == []
    )


def _ruleset() -> dict:
    import json

    return json.loads(Path(".github/merge-queue-ruleset.json").read_text(encoding="utf-8"))


def _write_ruleset(path: Path, ruleset: dict) -> Path:
    import json

    path.write_text(json.dumps(ruleset), encoding="utf-8")
    return path


def test_merge_queue_ruleset_accepts_the_checked_in_contract() -> None:
    assert verify_ci_workflow.validate_merge_queue_ruleset() == []


def test_merge_queue_ruleset_rejects_drift_and_duplicate_required_statuses(tmp_path: Path) -> None:
    def mutate(fn) -> list[str]:
        ruleset = _ruleset()
        fn(ruleset)
        return verify_ci_workflow.validate_merge_queue_ruleset(
            _write_ruleset(tmp_path / "r.json", ruleset)
        )

    assert mutate(lambda r: r.update(enforcement="evaluate"))
    assert mutate(lambda r: r.update(target="tag"))
    assert mutate(lambda r: r["conditions"]["ref_name"].update(include=["refs/heads/*"]))
    assert mutate(lambda r: r["conditions"]["ref_name"].update(exclude=["refs/heads/main"]))
    assert mutate(lambda r: r["rules"][0]["parameters"].update(merge_method="MERGE"))
    assert mutate(lambda r: r["rules"][0]["parameters"].update(max_entries_to_build=5))
    assert mutate(lambda r: r["rules"].clear())
    assert mutate(lambda r: r["rules"].append(r["rules"][0]))
    assert mutate(lambda r: r["rules"].append({"type": "deletion"}))
    duplicate = {
        "type": "required_status_checks",
        "parameters": {
            "required_status_checks": [{"context": "Release surfaces"}, {"context": "Test"}]
        },
    }
    assert mutate(lambda r: r["rules"].append(duplicate))
    single = {
        "type": "required_status_checks",
        "parameters": {"required_status_checks": [{"context": "Release surfaces"}]},
    }
    assert mutate(lambda r: r["rules"].append(single)) == []
    assert verify_ci_workflow.validate_merge_queue_ruleset(tmp_path / "missing.json")


def test_live_readback_compares_ruleset_and_branch_protection() -> None:
    local = _ruleset()
    protection = {"required_status_checks": {"contexts": ["Release surfaces"]}}

    def fetcher(live: dict, protected: dict):
        def fetch(path: str):
            if path == "rulesets":
                return [{"id": 7, "name": local["name"]}]
            if path == "rulesets/7":
                return live
            assert path == "branches/main/protection"
            return protected

        return fetch

    assert verify_ci_workflow.validate_live_readback(fetcher(local, protection)) == []
    drifted = {**local, "enforcement": "disabled"}
    assert any(
        "enforcement" in e
        for e in verify_ci_workflow.validate_live_readback(fetcher(drifted, protection))
    )
    extra = {"required_status_checks": {"contexts": ["Release surfaces", "Test"]}}
    assert any(
        "branch protection" in e
        for e in verify_ci_workflow.validate_live_readback(fetcher(local, extra))
    )
    assert verify_ci_workflow.validate_live_readback(lambda path: [] if path == "rulesets" else {})


# ---------------------------------------------------------------------------
# Release workflow carries the same packaged-WASM contract (#1005) and the hardened
# post-merge benchmark jobs (#1008)
# ---------------------------------------------------------------------------

_RELEASE_WASM_CONSUMERS = ("wheels", "wasm", "browser-package", "sdist")
_RELEASE_FETCH = (
    "      - name: Fetch packaged WASM assets from the wasm-assets producer\n"
    "        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1\n"
    "        with:\n"
    "          name: wasm-assets\n"
    "          path: .\n"
)
_RELEASE_VERIFY = (
    "      - name: Verify packaged WASM assets (missing or stale fails here)\n"
    "        run: python scripts/verify_wasm_assets.py\n"
)


def _release_errors(tmp_path: Path, workflow: str) -> list[str]:
    path = tmp_path / "publish.yaml"
    path.write_text(workflow, encoding="utf-8")
    return verify_ci_workflow.validate_release_workflow(path)


def _release_job_span(workflow: str, job: str) -> tuple[int, int]:
    start = workflow.index(f"\n  {job}:\n") + 1
    following = re.search(r"\n  [a-z-]+:\n", workflow[start:])
    return start, start + following.start() + 1 if following else len(workflow)


def _mutate_release_job(workflow: str, job: str, old: str, new: str) -> str:
    start, end = _release_job_span(workflow, job)
    block = workflow[start:end]
    assert old in block, f"{old!r} not in release job {job}"
    return workflow[:start] + block.replace(old, new, 1) + workflow[end:]


@pytest.mark.parametrize("job", _RELEASE_WASM_CONSUMERS)
def test_release_workflow_requires_wasm_consumers_to_need_the_producer(
    tmp_path: Path, job: str
) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    errors = _release_errors(
        tmp_path, _mutate_release_job(workflow, job, "    needs: wasm-assets\n", "")
    )
    assert any(f"WASM consumer {job!r} must list wasm-assets in needs" in e for e in errors)


@pytest.mark.parametrize("job", _RELEASE_WASM_CONSUMERS)
@pytest.mark.parametrize("step", [_RELEASE_FETCH, _RELEASE_VERIFY])
def test_release_workflow_requires_wasm_consumers_to_download_and_verify(
    tmp_path: Path, job: str, step: str
) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    errors = _release_errors(tmp_path, _mutate_release_job(workflow, job, step, ""))
    assert any(f"WASM consumer {job!r} must download then verify" in e for e in errors)


@pytest.mark.parametrize("job", ["wheels", "sdist", "browser-package", "wasm"])
def test_release_workflow_requires_client_build_before_wasm_verification(
    tmp_path: Path, job: str
) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    start, end = _release_job_span(workflow, job)
    block = workflow[start:end]
    build = re.search(
        r"      - name: Build (?:render|browser) client\n        run: .*?(?=\n      - )",
        block,
        re.S,
    )
    assert build is not None
    mutated = workflow[:start] + block.replace(build.group(0) + "\n", "", 1) + workflow[end:]
    errors = _release_errors(tmp_path, mutated)
    assert any(f"{job!r} must run node js/build.mjs before verifying" in e for e in errors)


@pytest.mark.parametrize(
    ("job", "old", "message"),
    [
        (
            "wheels",
            '          XYG_REQUIRE_WASM: "1"\n',
            "wheels job must build with XYG_REQUIRE_WASM",
        ),
        (
            "sdist",
            '          XYG_REQUIRE_WASM: "1"\n',
            "sdist job must build with XYG_REQUIRE_WASM",
        ),
        (
            "wheels",
            " --expect-native --require-wasm",
            "wheels job must build with XYG_REQUIRE_WASM",
        ),
        ("sdist", " --require-wasm", "sdist job must build with XYG_REQUIRE_WASM"),
        ("wasm", " --expect-native --require-wasm", "wasm job must verify --require-wasm"),
    ],
)
def test_release_workflow_requires_distributions_to_enforce_wasm(
    tmp_path: Path, job: str, old: str, message: str
) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    new = " --expect-native" if "expect-native" in old else ""
    errors = _release_errors(tmp_path, _mutate_release_job(workflow, job, old, new))
    assert any(message in e for e in errors), errors


def test_release_workflow_rejects_second_producer_and_weakened_producer(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    second = _mutate_release_job(
        workflow,
        "browser-package",
        "      - name: Build browser client\n        run: |\n          npm ci\n",
        "      - name: Build browser client\n        run: |\n          npm ci\n          npm run build:wasm\n",
    )
    assert any("must consume wasm-assets" in e for e in _release_errors(tmp_path, second))
    weak = _mutate_release_job(workflow, "wasm-assets", "          if-no-files-found: error\n", "")
    assert any("if-no-files-found" in e for e in _release_errors(tmp_path, weak))
    missing = workflow.replace("  wasm-assets:\n", "  wasm-assets-renamed:\n", 1)
    assert any("wasm-assets" in e for e in _release_errors(tmp_path, missing))


@pytest.mark.parametrize(
    ("job", "step", "needle"),
    [
        ("benchmark_vs", "Install selected competitors", "scripts/ci_retry.sh 3 "),
        ("benchmark_vs", "Install XYG", "scripts/ci_retry.sh 3 "),
        ("benchmark_vs", "Install Chromium (Playwright)", "scripts/ci_retry.sh 3 npx playwright"),
        ("benchmark_methodology", "Install JS build toolchain", "scripts/ci_retry.sh 3 "),
        ("benchmark_methodology", "Install XYG + competitors", "scripts/ci_retry.sh 3 "),
        ("benchmark_methodology", "Install Chromium (Playwright)", "scripts/ci_retry.sh 3 npx"),
    ],
)
def test_ci_workflow_requires_install_retries_in_hard_benchmark_jobs(
    tmp_path: Path, job: str, step: str, needle: str
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    start, end = _job_span(workflow, job)
    block = workflow[start:end]
    step_at = block.index(f"      - name: {step}\n")
    step_end = block.index("\n      - ", step_at + 1)
    mutated_step = block[step_at:step_end].replace("scripts/ci_retry.sh 3 ", "")
    assert mutated_step != block[step_at:step_end]
    path = tmp_path / "ci.yml"
    path.write_text(
        workflow[:start] + block[:step_at] + mutated_step + block[step_end:] + workflow[end:],
        encoding="utf-8",
    )

    errors = verify_ci_workflow.validate_ci_workflow(path)

    assert any("install retry" in e for e in errors), errors


@pytest.mark.parametrize(
    ("job", "old", "new"),
    [
        ("benchmark_vs", "    timeout-minutes: 25\n", "    timeout-minutes: 10\n"),
        ("benchmark_vs", "    timeout-minutes: 25\n", ""),
        ("benchmark_methodology", "    timeout-minutes: 45\n", ""),
    ],
)
def test_ci_workflow_requires_realistic_benchmark_timeouts(
    tmp_path: Path, job: str, old: str, new: str
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    errors = _wasm_errors(tmp_path, _mutate_job(workflow, job, old, new))
    assert any("timeout-minutes" in e for e in errors), errors


def test_ci_workflow_runs_the_painter_admission_wasm_parity_gate(tmp_path: Path) -> None:
    """Hard gate for the #1007 test; the file lands with that PR, so merge this after it."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    line = "          node --test packages/xy-node/test/painter-admission-wasm-parity.test.mjs\n"
    assert line in workflow
    errors = _wasm_errors(tmp_path, workflow.replace(line, "", 1))
    assert any("painter-admission-wasm-parity" in e for e in errors)


def test_ci_retry_script_retries_then_succeeds_or_returns_the_last_status(tmp_path: Path) -> None:
    import os
    import subprocess

    script = Path("scripts/ci_retry.sh").resolve()
    counter = tmp_path / "count"

    def run(*argv: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(script), *argv],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "CI_RETRY_DELAY": "0", "COUNTER": str(counter)},
        )

    flaky = 'n=$(cat "$COUNTER" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$COUNTER"; [ "$n" -ge 3 ]'
    ok = run("3", "bash", "-c", flaky)
    assert ok.returncode == 0 and counter.read_text().strip() == "3"
    counter.unlink()
    failed = run("2", "bash", "-c", flaky)
    assert failed.returncode == 1 and counter.read_text().strip() == "2"
    assert "failed after 2 attempt(s)" in failed.stderr
    assert run("0", "true").returncode == 2
    assert run("x", "true").returncode == 2
    assert run("3").returncode == 2


# ---------------------------------------------------------------------------
# Round-3 gates: PR-visible benchmark oracles, per-run concurrency, pipefail, Pyodide env,
# flag-order-tolerant producer guard
# ---------------------------------------------------------------------------

_ORACLE_COMMANDS = (
    "cargo bench -p xyg-engine --bench kernels -- --test",
    "cargo bench -p xyg-wasm --bench aggregate -- --test",
    "cargo bench -p xyg-wasm --bench typed_series -- --test",
)
_PYTEST_ORACLE = ".venv/bin/python -m pytest benchmarks/test_codspeed_*.py -q"


@pytest.mark.parametrize("command", [*_ORACLE_COMMANDS, _PYTEST_ORACLE])
@pytest.mark.parametrize("replacement", ["# {command}", "echo {command}", "{command} || true", ""])
def test_ci_workflow_requires_benchmark_oracles_on_pull_requests(
    tmp_path: Path, command: str, replacement: str
) -> None:
    """The stale-oracle root cause of #1007: assertions only ran in scheduled CodSpeed."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    line = f"          {command}\n" if command in _ORACLE_COMMANDS else f"        run: {command}\n"
    assert line in workflow
    prefix = "          " if command in _ORACLE_COMMANDS else "        run: "
    new = prefix + replacement.format(command=command) + "\n" if replacement else ""
    errors = _wasm_errors(tmp_path, workflow.replace(line, new, 1))
    assert any("benchmark oracles" in e for e in errors), errors


def test_ci_workflow_requires_the_codspeed_plugin_group_for_the_pytest_oracles(
    tmp_path: Path,
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    errors = _wasm_errors(
        tmp_path, workflow.replace(" --group dev --group codspeed", " --group dev", 1)
    )
    assert any("pytest-codspeed plugin" in e for e in errors)


@pytest.mark.parametrize("job", ["test", "python_floor"])
def test_unused_wasm32_toolchain_targets_stay_removed(job: str) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    start, end = _job_span(workflow, job)
    assert "targets: wasm32" not in workflow[start:end]


@pytest.mark.parametrize(
    "group",
    [
        "ci-${{ github.ref }}",
        "ci-${{ github.event_name == 'push' && github.sha || github.ref }}",
        "ci-${{ github.workflow }}",
    ],
)
def test_ci_concurrency_group_must_be_per_run_outside_pull_requests(
    tmp_path: Path, group: str
) -> None:
    """A shared group lets GitHub replace an older pending main/merge-group run."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    current = (
        "  group: ci-${{ github.event_name == 'pull_request' && github.ref || github.run_id }}\n"
    )
    assert current in workflow
    errors = _wasm_errors(tmp_path, workflow.replace(current, f"  group: {group}\n", 1))
    assert any("concurrency group must be per run" in e for e in errors)


PIPED_STEPS = (
    "Line decimation vs plotly-resampler (methodology line_10M)",
    "Install footprint & cold import (methodology §1)",
    "Fresh-environment footprint (XYG vs Plotly)",
    "Ingestion, streaming, and export workflows",
    "Browser interaction latency (methodology interaction_smoothness)",
    "Many-chart dashboard startup (methodology dashboard_scale)",
)


@pytest.mark.parametrize("step", PIPED_STEPS)
def test_ci_workflow_requires_pipefail_on_benchmark_pipes(tmp_path: Path, step: str) -> None:
    """`bench.py | tee report` without pipefail reports tee's success and hides a crash."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    start = workflow.index(f"      - name: {step}\n")
    shell = workflow.index("        shell: bash\n", start)
    assert shell - start < 200
    mutated = workflow[:shell] + workflow[shell + len("        shell: bash\n") :]
    errors = _wasm_errors(tmp_path, mutated)
    assert any("pipes a command without pipefail" in e and step in e for e in errors), errors


def test_pipefail_rule_accepts_explicit_pipefail_and_ignores_non_pipes() -> None:
    pipe_lines = verify_ci_workflow._pipe_lines
    assert pipe_lines(["python bench.py | tee out.md"]) == ["python bench.py | tee out.md"]
    assert pipe_lines(["a || b", "grep -Eq '(^| )png v' f", 'echo "a | b"']) == []
    assert pipe_lines(["python - <<'PY'", "x = a | b", "PY", "echo done"]) == []
    assert pipe_lines(["cat f # a | b"]) == []


@pytest.mark.parametrize(
    ("name", "workflow", "validate"),
    [
        ("CI", "ci.yml", "validate_ci_workflow"),
        ("release", "publish.yaml", "validate_release_workflow"),
        ("CodSpeed", "codspeed.yml", "validate_codspeed_workflow"),
        ("density authority", "density-100m.yml", "validate_density_workflow"),
        ("ceiling comparison", "ceiling-benchmark.yml", "validate_ceiling_workflow"),
    ],
)
def test_every_validated_workflow_rejects_a_piped_step_without_pipefail(
    tmp_path: Path, name: str, workflow: str, validate: str
) -> None:
    text = Path(f".github/workflows/{workflow}").read_text(encoding="utf-8")
    bad = "      - name: Unsafe pipe\n        run: python bench.py | tee report.md\n"
    good = (
        "      - name: Safe pipe\n        shell: bash\n        run: python bench.py | tee report.md\n"
        "      - name: Explicit pipefail\n        run: |\n"
        "          set -o pipefail\n          python bench.py | tee report.md\n"
    )
    first_steps = text.index("    steps:\n") + len("    steps:\n")
    path = tmp_path / workflow
    path.write_text(text[:first_steps] + bad + text[first_steps:], encoding="utf-8")
    errors = getattr(verify_ci_workflow, validate)(path)
    assert any(f"{name} job" in e and "Unsafe pipe" in e and "pipefail" in e for e in errors), (
        errors
    )
    path.write_text(text[:first_steps] + good + text[first_steps:], encoding="utf-8")
    assert not any(
        "Safe pipe" in e or "Explicit pipefail" in e
        for e in getattr(verify_ci_workflow, validate)(path)
    )


def test_release_workflow_requires_wasm_enforcement_inside_cibuildwheel(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    line = "            XYG_REQUIRE_WASM=1\n"
    assert line in workflow
    errors = _release_errors(tmp_path, workflow.replace(line, "", 1))
    assert any("XYG_REQUIRE_WASM=1" in e for e in errors), errors


@pytest.mark.parametrize(
    "command",
    [
        "cargo build --release --target wasm32-unknown-unknown -p xyg-wasm",
        "cargo build --target=wasm32-unknown-unknown --package xyg-wasm --release",
        "cargo build -pxyg-wasm --target wasm32-unknown-unknown",
        "npm  run   build:wasm",
        "node ./js/package-wasm.mjs target/x.wasm",
    ],
)
def test_single_producer_guard_tolerates_reordered_flags(tmp_path: Path, command: str) -> None:
    assert verify_ci_workflow._runs_wasm_producer(command) is not None
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    mutated = _mutate_job(
        workflow,
        "benchmark_methodology",
        "      - name: Install JS build toolchain\n        run: scripts/ci_retry.sh 3 npm ci\n",
        f"      - name: Install JS build toolchain\n        run: |\n          scripts/ci_retry.sh 3 npm ci\n          {command}\n",
    )
    assert any("must consume wasm-assets" in e for e in _wasm_errors(tmp_path, mutated))


@pytest.mark.parametrize(
    "command",
    [
        "cargo build -p xyg-wasm --bin geo_scene_conformance",
        "cargo build --release -p xyg-core",
        "cargo build --release --target wasm32-unknown-emscripten",
        "cargo build --target wasm32-unknown-unknown",
        "cargo test -p xyg-wasm",
        "npm run build",
        "echo 'npm run build:wasm' # not a command",
    ],
)
def test_single_producer_guard_ignores_non_producers(command: str) -> None:
    assert verify_ci_workflow._runs_wasm_producer(command) is None


# ---------------------------------------------------------------------------
# Round-4: oracle position, hardened pipefail rule, argument-parsing producer guard
# ---------------------------------------------------------------------------

_DIVAN_STEP = "Native benchmark oracles (divan --test, no timing)"
_PYTEST_STEP = "CodSpeed benchmark oracles (pytest, no timing)"


def test_benchmark_oracles_are_the_final_two_steps_of_the_test_job(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    start, end = _job_span(workflow, "test")
    steps = [m.group(1) for m in re.finditer(r"^      - name: (.+)$", workflow[start:end], re.M)]
    assert steps[-2:] == [_DIVAN_STEP, _PYTEST_STEP]
    assert steps.index("Python tests (native core)") < steps.index(_DIVAN_STEP)

    # Moving an oracle step before the native build (the pre-fix placement) is rejected.
    block = workflow[start:end]
    divan_at = block.index("      # Benchmark bodies carry correctness assertions")
    divan_end = block.index("      # Same intent for the pytest benchmarks")
    divan = block[divan_at:divan_end]
    moved = block.replace(divan, "", 1).replace(
        "      - name: Build native core\n", divan + "      - name: Build native core\n", 1
    )
    errors = _wasm_errors(tmp_path, workflow[:start] + moved + workflow[end:])
    assert any("must be its final two steps" in e for e in errors), errors


def _sub(root: Path, name: str) -> Path:
    (root / name).mkdir()
    return root / name


def test_benchmark_methodology_contract_cannot_be_dropped_from_the_test_job(
    tmp_path: Path,
) -> None:
    """The pre-merge producer + report-verifier step is verifier-enforced (#1005/#1008)."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    start, end = _job_span(workflow, "test")
    block = workflow[start:end]
    step = "      - name: Benchmark methodology contract (smallest sizes, report verified)\n"
    at = block.index(step)
    after = block.index("\n      # Benchmark bodies carry correctness assertions")
    assert _wasm_errors(_sub(tmp_path, "ok"), workflow) == []

    dropped = _wasm_errors(
        _sub(tmp_path, "dropped"), workflow[:start] + block[:at] + block[after:] + workflow[end:]
    )
    assert any("Benchmark methodology contract" in e for e in dropped), dropped

    weakened = block.replace(
        '.venv/bin/python scripts/verify_benchmark_report.py "$RUNNER_TEMP/bench-contract/workflows.json" --kind workflow-native\n',
        "",
        1,
    )
    errors = _wasm_errors(_sub(tmp_path, "weak"), workflow[:start] + weakened + workflow[end:])
    assert any("Benchmark methodology contract" in e for e in errors), errors


def test_makefile_check_bench_oracles_runs_the_same_commands_as_ci() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")
    recipe = makefile.split("check-bench-oracles:\n", 1)[1].split("\n\n", 1)[0]
    commands = [line.strip() for line in recipe.splitlines()]
    assert commands == [*_ORACLE_COMMANDS, "$(PYTHON) -m pytest benchmarks/test_codspeed_*.py -q"]
    assert "check-bench-oracles" in makefile.split(".PHONY:", 1)[1].split("\n", 1)[0]
    assert "--group codspeed" in makefile.split("setup:\n", 1)[1].split("\n\n", 1)[0]


def test_docs_and_dependency_comment_describe_the_oracle_gate() -> None:
    build_ci = Path("spec/design/build-ci.md").read_text(encoding="utf-8")
    block = build_ci.split("## Local reproduction", 1)[1].split("```", 2)[1]
    assert "--group dev --group codspeed" in block and "make check-bench-oracles" in block
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "not needed for unit tests or static analysis" not in pyproject
    assert "check-bench-oracles" in pyproject


def test_checker_ok_line_lists_every_validated_workflow(capsys: pytest.CaptureFixture[str]) -> None:
    assert verify_ci_workflow.main([]) == 0
    out = capsys.readouterr().out
    for name in (
        "ci.yml",
        "codspeed.yml",
        "density-100m.yml",
        "ceiling-benchmark.yml",
        "final-coderabbit.yml",
        "publish.yaml",
        "merge-queue-ruleset.json",
    ):
        assert name in out


def _pipefail_errors(tmp_path: Path, step_yaml: str, *, header: str = "") -> list[str]:
    text = (
        "name: T\non: push\n"
        + header
        + "jobs:\n  j:\n    runs-on: blacksmith-4vcpu-ubuntu-2404\n    steps:\n"
        + step_yaml
    )
    errors: list[str] = []
    verify_ci_workflow._require_pipefail_for_piped_steps(errors, text, "T")
    return errors


@pytest.mark.parametrize(
    "step",
    [
        # folded scalar: line structure is rewritten, so a pipe cannot be analyzed
        "      - name: Folded\n        run: >-\n          python bench.py | tee out.md\n",
        # unnamed step whose first key is run (indent 6)
        "      - run: python bench.py | tee out.md\n",
        "      - run: |\n          python bench.py | tee out.md\n",
        # pipe inside a command substitution inside double quotes is still a pipe
        '      - name: Subst\n        run: |\n          x="$(python bench.py | tail -1)"\n',
        # a `<<` that is arithmetic is not a heredoc, so the pipe after it still counts
        "      - name: Shift\n        run: |\n          n=$((1 << 3))\n          bench | tee out\n",
        # here-string is not a heredoc terminator either
        "      - name: Herestring\n        run: |\n          cat <<<word\n          bench | tee out\n",
        # only bash implies pipefail
        "      - name: Sh\n        shell: sh\n        run: bench | tee out\n",
        "      - name: Pwsh\n        shell: pwsh\n        run: bench | tee out\n",
        "      - name: Custom\n        shell: bash -e {0}\n        run: bench | tee out\n",
        # a mention in an echo is not a statement
        '      - name: Echo\n        run: |\n          echo "set -o pipefail"\n          bench | tee out\n',
        # turning it off again
        "      - name: Off\n        shell: bash\n        run: |\n          set +o pipefail\n          bench | tee out\n",
        "      - name: Off2\n        run: |\n          set -o pipefail\n          set +o pipefail\n          bench | tee out\n",
        # enabling after the pipe is too late
        "      - name: Late\n        run: |\n          bench | tee out\n          set -o pipefail\n",
    ],
)
def test_pipefail_rule_rejects_each_false_negative(tmp_path: Path, step: str) -> None:
    errors = _pipefail_errors(tmp_path, step)
    assert any("pipefail" in e for e in errors), (step, errors)


@pytest.mark.parametrize(
    "step",
    [
        "      - name: Bash\n        shell: bash\n        run: bench | tee out\n",
        "      - run: |\n          set -euo pipefail\n          bench | tee out\n",
        "      - name: Stmt\n        run: |\n          set -o pipefail\n          bench | tee out\n",
        "      - name: Continued\n        shell: bash\n        run: |\n          bench \\\n            | tee out\n",
        "      - name: Quoted\n        run: |\n          echo 'a | b'\n          grep -Eq '(^| )x' f\n          a || b\n",
        "      - name: Heredoc\n        run: |\n          python - <<'PY'\n          x = a | b\n          PY\n",
        "      - name: Folded no pipe\n        run: >-\n          echo one\n          two\n",
        "      - name: Comment\n        run: |\n          echo hi # a | b\n",
    ],
)
def test_pipefail_rule_accepts_safe_or_pipe_free_steps(tmp_path: Path, step: str) -> None:
    assert _pipefail_errors(tmp_path, step) == []


def test_pipefail_rule_honors_job_and_workflow_default_shell(tmp_path: Path) -> None:
    step = "      - name: P\n        run: bench | tee out\n"
    workflow_default = "defaults:\n  run:\n    shell: bash\n"
    assert _pipefail_errors(tmp_path, step, header=workflow_default) == []
    wrong_default = "defaults:\n  run:\n    shell: sh\n"
    assert _pipefail_errors(tmp_path, step, header=wrong_default)
    job_default = (
        "name: T\non: push\njobs:\n  j:\n    runs-on: x\n    defaults:\n      run:\n"
        "        shell: bash\n    steps:\n" + step
    )
    errors: list[str] = []
    verify_ci_workflow._require_pipefail_for_piped_steps(errors, job_default, "T")
    assert errors == []


def test_pipe_scanner_unit_cases() -> None:
    pipes = verify_ci_workflow._pipe_lines
    assert pipes(["n=$((1 << 3))", "a | b"]) == ["a | b"]
    assert pipes(['x="$(a | b)"']) == ['x="$(a | b)"']
    assert pipes(["x=$(a | b)"]) == ["x=$(a | b)"]
    assert pipes(["echo 'a | b' \"c | d\""]) == []
    assert pipes(["cat <<EOF", "a | b", "EOF", "c | d"]) == ["c | d"]


@pytest.mark.parametrize(
    "command",
    [
        "cargo build -p xyg-wasm \\\n    --release \\\n    --target wasm32-unknown-unknown",
        "cargo build --manifest-path crates/xyg-wasm/Cargo.toml --target wasm32-unknown-unknown",
        "cargo build --manifest-path=crates/xyg-wasm/Cargo.toml --release --target=wasm32-unknown-unknown",
        "npm run-script build:wasm",
        "pnpm run build:wasm",
        "yarn build:wasm",
    ],
)
def test_single_producer_guard_catches_continuations_manifest_paths_and_managers(
    tmp_path: Path, command: str
) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    body = "\n".join(f"          {line}" for line in command.splitlines())
    mutated = _mutate_job(
        workflow,
        "benchmark_methodology",
        "      - name: Install JS build toolchain\n        run: scripts/ci_retry.sh 3 npm ci\n",
        "      - name: Install JS build toolchain\n        run: |\n"
        f"          scripts/ci_retry.sh 3 npm ci\n{body}\n",
    )
    assert any("must consume wasm-assets" in e for e in _wasm_errors(tmp_path, mutated)), command


def test_single_producer_guard_sees_folded_and_continued_commands() -> None:
    step = (
        "      - name: Hidden\n        run: >-\n          cargo build -p xyg-wasm\n"
        "          --target wasm32-unknown-unknown\n"
    )
    job = "  j:\n    steps:\n" + step
    lines = verify_ci_workflow._active_run_lines(job)
    assert [verify_ci_workflow._runs_wasm_producer(line) for line in lines] == [
        "cargo build -p xyg-wasm --target wasm32-unknown-unknown"
    ]


# ---------------------------------------------------------------------------
# Round-5: heredoc detection in code only, whole-value default shell, quoted run scalars,
# unnamed trailing steps
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "opener",
    [
        'echo "use <<EOF"',
        "python -c 'print(1<<n)'",
        "n=$((x << shift))",
        "((x << shift))",
        "cat <<<word",
        "echo hi # <<EOF",
    ],
)
def test_heredoc_is_opened_only_by_plain_shell_code(tmp_path: Path, opener: str) -> None:
    """A quoted/arithmetic/commented `<<` must not swallow the pipe that follows."""
    assert verify_ci_workflow._heredoc_delimiter(opener) is None
    step = f"      - name: H\n        run: |\n          {opener}\n          bench | tee out\n"
    assert any("pipefail" in e for e in _pipefail_errors(tmp_path, step))


@pytest.mark.parametrize(
    ("command", "delimiter"),
    [
        ("cat <<EOF", "EOF"),
        ("python - <<'PY'", "PY"),
        ('python - <<"PY"', "PY"),
        ("cat <<-EOF", "EOF"),
        ("cat > f <<EOF && echo x", "EOF"),
    ],
)
def test_real_heredocs_still_open_one(command: str, delimiter: str) -> None:
    assert verify_ci_workflow._heredoc_delimiter(command) == delimiter


def test_step_ending_inside_a_heredoc_fails_closed(tmp_path: Path) -> None:
    unterminated = "      - name: H\n        run: |\n          cat <<EOF\n          a | b\n"
    errors = _pipefail_errors(tmp_path, unterminated)
    assert any("ends inside a heredoc" in e and "'EOF'" in e for e in errors), errors
    terminated = (
        "      - name: H\n        run: |\n          cat <<EOF\n          a | b\n          EOF\n"
    )
    assert _pipefail_errors(tmp_path, terminated) == []


@pytest.mark.parametrize("value", ["bash -e {0}", "sh", "pwsh", "bash {0}"])
def test_default_shell_must_be_exactly_bash(tmp_path: Path, value: str) -> None:
    step = "      - name: P\n        run: bench | tee out\n"
    assert _pipefail_errors(tmp_path, step, header=f"defaults:\n  run:\n    shell: {value}\n")
    job_default = (
        "name: T\non: push\njobs:\n  j:\n    runs-on: x\n    defaults:\n      run:\n"
        f"        shell: {value}\n    steps:\n" + step
    )
    errors: list[str] = []
    verify_ci_workflow._require_pipefail_for_piped_steps(errors, job_default, "T")
    assert errors


def test_default_shell_value_comment_is_ignored(tmp_path: Path) -> None:
    step = "      - name: P\n        run: bench | tee out\n"
    header = "defaults:\n  run:\n    shell: bash # pipefail\n"
    assert _pipefail_errors(tmp_path, step, header=header) == []


@pytest.mark.parametrize("quote", ["'", '"'])
def test_quoted_one_line_run_scalar_with_a_pipe_fails_closed(tmp_path: Path, quote: str) -> None:
    step = f"      - name: Q\n        run: {quote}bench | tee out{quote}\n"
    errors = _pipefail_errors(tmp_path, step)
    assert any("folded or quoted" in e for e in errors), errors
    assert (
        _pipefail_errors(tmp_path, f"      - name: Q\n        run: {quote}echo hi{quote}\n") == []
    )
    # Quoted scalars with a pipe stay acceptable when the shell is explicitly bash? No:
    # the YAML scalar is rewritten before the shell sees it, so it still fails closed.
    shelled = f"      - name: Q\n        shell: bash\n        run: {quote}bench | tee out{quote}\n"
    assert any("folded or quoted" in e for e in _pipefail_errors(tmp_path, shelled))


@pytest.mark.parametrize("trailer", ["      - run: echo done\n", "      - uses: ./local\n"])
def test_unnamed_trailing_step_after_the_oracles_is_caught(tmp_path: Path, trailer: str) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    start, end = _job_span(workflow, "test")
    block = workflow[start:end].rstrip("\n") + "\n" + trailer + "\n"
    errors = _wasm_errors(tmp_path, workflow[:start] + block + workflow[end:])
    assert any("must be its final two steps" in e for e in errors), errors


@pytest.mark.parametrize(
    "removed", ["--prerelease", "--latest=false", 'parse_tag(os.environ["GITHUB_REF_NAME"]).stage']
)
def test_release_prerelease_cannot_be_presented_as_latest_stable(
    tmp_path: Path, removed: str
) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    assert removed in workflow
    path = tmp_path / "publish.yaml"
    path.write_text(workflow.replace(removed, "removed", 1), encoding="utf-8")
    errors = verify_ci_workflow.validate_release_workflow(path)
    assert any("GitHub Release" in error for error in errors)


def test_release_pypi_requires_npm_readiness_opt_in(tmp_path: Path) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    path = tmp_path / "publish.yaml"
    path.write_text(
        workflow.replace(
            RELEASE_PUBLISH_GATE_LINE,
            RELEASE_PUBLISH_GATE_LINE.replace("vars.XYG_ALLOW_NPM_PUBLISH == 'true' && ", ""),
        ),
        encoding="utf-8",
    )
    errors = verify_ci_workflow.validate_release_workflow(path)
    assert any("is not gated by the dry-run predicate" in error for error in errors)


@pytest.mark.parametrize(
    "removed",
    ["name: browser-package", "python3 scripts/publish_node_packages.py node-dist --check"],
)
def test_release_npm_must_include_browser_cohort(tmp_path: Path, removed: str) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    prefix, publish = workflow.split("  publish-npm:\n", 1)
    path = tmp_path / "publish.yaml"
    path.write_text(
        prefix + "  publish-npm:\n" + publish.replace(removed, "removed", 1), encoding="utf-8"
    )
    errors = verify_ci_workflow.validate_release_workflow(path)
    assert any("npm trusted-publishing set" in error for error in errors)


@pytest.mark.parametrize(
    ("tag", "prerelease"),
    [
        ("xyg-v0.6.0", False),
        ("xyg-v0.6.0-alpha.1", True),
        ("xyg-v0.6.0-beta.2", True),
        ("xyg-v0.6.0-rc.3", True),
        ("xyg-v0.6.0rc3", True),
        ("xyg-v0.6.0a1", True),
        ("xyg-v0.6.0-rc.03", None),
    ],
)
def test_github_release_executes_canonical_prerelease_classification(
    tmp_path: Path, tag: str, prerelease: bool | None
) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    job = verify_ci_workflow._job_blocks(workflow)["github-release"]
    step = verify_ci_workflow._named_step_blocks(job)["Create release and attach browser artifacts"]
    command = "\n".join(verify_ci_workflow._step_run_lines(step))
    captured = tmp_path / "gh-args.json"
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        f"#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\nPath(os.environ['CAPTURED_GH_ARGS']).write_text(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "GITHUB_REF_NAME": tag,
            "GITHUB_REPOSITORY": "CurateLabs/xyg",
            "CAPTURED_GH_ARGS": str(captured),
        },
    )
    if prerelease is None:
        assert result.returncode != 0
        assert not captured.exists()
        return
    assert result.returncode == 0, result.stderr
    args = json.loads(captured.read_text())
    assert args[:3] == ["release", "create", tag]
    assert ("--prerelease" in args) is prerelease
    assert ("--latest=false" in args) is prerelease


@pytest.mark.parametrize(
    "removed", ["name: browser-package", '--tag "$GITHUB_REF_NAME"', "--check"]
)
def test_release_pypi_preflight_requires_browser_and_tag_validation(
    tmp_path: Path, removed: str
) -> None:
    workflow = Path(".github/workflows/publish.yaml").read_text(encoding="utf-8")
    prefix, publish = workflow.split("  publish:\n", 1)
    path = tmp_path / "publish.yaml"
    path.write_text(
        prefix + "  publish:\n" + publish.replace(removed, "removed", 1), encoding="utf-8"
    )
    errors = verify_ci_workflow.validate_release_workflow(path)
    assert any(
        "seven-package npm cohort" in error
        or "Verify complete npm cohort" in error
        or "name: browser-package" in error
        for error in errors
    )


@pytest.mark.parametrize("mutation", ["missing", "commented", "skipped", "soft-failure"])
def test_ci_requires_consumer_application_smokes(tmp_path: Path, mutation: str) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    command = '          uv run python scripts/consumer_apps_smoke.py --chromium "$CHROME"'
    step = "      - name: Python Streamlit and vanilla TypeScript consumer apps\n"
    if mutation == "missing":
        workflow = workflow.replace(command, "          true")
    elif mutation == "commented":
        workflow = workflow.replace(command, "          # " + command.strip())
    elif mutation == "skipped":
        workflow = workflow.replace(step, step + "        if: false\n")
    else:
        workflow = workflow.replace(step, step + "        continue-on-error: true\n")
    path = tmp_path / "ci.yml"
    path.write_text(workflow, encoding="utf-8")
    errors = verify_ci_workflow.validate_ci_workflow(path)
    assert any("consumer" in error or "continue-on-error" in error for error in errors)


@pytest.mark.parametrize(
    "missing",
    [
        "consumer-apps-smoke.json",
        "consumer-apps-smoke/",
        "if-no-files-found: error",
        "if: always()",
    ],
)
def test_ci_requires_consumer_application_evidence(tmp_path: Path, missing: str) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    prefix, suffix = workflow.split(
        "      - name: Retain consumer application browser evidence\n", 1
    )
    evidence, suffix = suffix.split("      - name: Browser lifecycle smoke (Chromium)\n", 1)
    path = tmp_path / "ci.yml"
    path.write_text(
        prefix
        + "      - name: Retain consumer application browser evidence\n"
        + evidence.replace(missing, "removed", 1)
        + "      - name: Browser lifecycle smoke (Chromium)\n"
        + suffix,
        encoding="utf-8",
    )
    errors = verify_ci_workflow.validate_ci_workflow(path)
    assert any("Retain consumer application browser evidence" in error for error in errors)


@pytest.mark.parametrize("condition", ["success()", "failure()", "always() && false", "false"])
def test_ci_retains_consumer_evidence_after_failure(tmp_path: Path, condition: str) -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    step = "      - name: Retain consumer application browser evidence\n        if: always()"
    path = tmp_path / "ci.yml"
    path.write_text(workflow.replace(step, step.replace("always()", condition)), encoding="utf-8")
    errors = verify_ci_workflow.validate_ci_workflow(path)
    assert any("Retain consumer application browser evidence" in error for error in errors)


def test_ceiling_comparison_accepts_existing_manual_capacity_and_defaults() -> None:
    assert verify_ci_workflow.validate_ceiling_workflow() == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("on:\n  workflow_dispatch:", "on:\n  pull_request:\n  workflow_dispatch:"),
        (
            "on:\n  workflow_dispatch:",
            "on:\n  schedule:\n    - cron: '0 0 * * *'\n  workflow_dispatch:",
        ),
        (
            "  ceiling:\n",
            "  extra:\n    runs-on: blacksmith-12vcpu-macos-15\n    steps: []\n  ceiling:\n",
        ),
        (
            "    if: inputs.experiment != 'density-comparison' || github.ref == 'refs/heads/main'",
            "    if: always()",
        ),
        ("    runs-on: blacksmith-12vcpu-macos-15", "    runs-on: blacksmith-6vcpu-macos-15"),
        ("    timeout-minutes: 720", "    timeout-minutes: 1440"),
        ("    steps:\n", "    continue-on-error: true\n    steps:\n"),
        ("    steps:\n", "    strategy:\n      matrix:\n        repeat: [1, 2]\n    steps:\n"),
        ("    steps:\n", "    env:\n      BASH_ENV: /tmp/override\n    steps:\n"),
        ("        default: ceiling", "        default: density-comparison"),
        (
            "        options: [ceiling, density-comparison]",
            "        options: [ceiling, density-comparison, unsafe]",
        ),
        ('        default: "300"', '        default: "600"'),
        ('        default: "20"', '        default: "40"'),
        ('        default: "3"', '        default: "1"'),
        ("          persist-credentials: false", "          persist-credentials: true"),
        ("          fetch-depth: 0", "          fetch-depth: 1"),
        ("          INPUT_ARMS: ${{ inputs.arms }}", "          INPUT_ARMS: ${{ inputs.sizes }}"),
        (
            "          INPUT_EXPERIMENT: ${{ inputs.experiment }}",
            "          INPUT_EXPERIMENT: ceiling",
        ),
        (
            '--sizes "$INPUT_SIZES" --arms "$INPUT_ARMS"',
            '--sizes "${{ inputs.sizes }}" --arms "$INPUT_ARMS"',
        ),
        (
            '--sizes "$INPUT_SIZES" --arms "$INPUT_ARMS"',
            '--sizes $INPUT_SIZES --arms "$INPUT_ARMS"',
        ),
        ("--profile f64-memmap", "--profile f32"),
        ("--chunk 1000000", "--chunk 1000000000"),
        ("--disk-gib 20", "--disk-gib 40"),
        ("--step-timeout 15", "--step-timeout 60"),
        ('--repetitions "$INPUT_REPETITIONS"', "--repetitions 1"),
        ('--timeout "$INPUT_TIMEOUT"', "--timeout 7200"),
        ('--memory-gib "$INPUT_MEMORY_GIB"', "--memory-gib 40"),
        (
            '--out "$RUNNER_TEMP/density-comparison-${GITHUB_SHA}.json"',
            "--out density-comparison.json",
        ),
        ('--sha "$GITHUB_SHA"', "--sha stale"),
        ('--artifact-root "$GITHUB_WORKSPACE"', "--artifact-root /tmp/stale"),
        (
            '--sizes "$INPUT_SIZES" --arms "$INPUT_ARMS"\n          else',
            "--sizes 1000 --arms xy-density\n          else",
        ),
        (
            "python3 scripts/verify_density_comparison_report.py",
            "echo scripts/verify_density_comparison_report.py",
        ),
        (
            '--sizes "$INPUT_SIZES" --arms "$INPUT_ARMS"\n          else',
            '--sizes "$INPUT_SIZES" --arms "$INPUT_ARMS" || true\n          else',
        ),
        (
            "      - name: Run ceiling sweep\n",
            "      - name: Run ceiling sweep\n        if: 'false'\n",
        ),
        (
            "      - name: Run ceiling sweep\n",
            "      - name: Run ceiling sweep\n        continue-on-error: true\n",
        ),
        (
            "      - name: Build native core\n",
            "      - name: Build native core\n        if: 'false'\n",
        ),
        (
            '          if [ "$INPUT_EXPERIMENT" = "density-comparison" ]; then',
            "          if false; then",
        ),
        (
            "uv pip install --constraint benchmarks/requirements-ci.lock hvplot",
            "uv pip install hvplot",
        ),
        (
            "NUMBA_NUM_THREADS=2 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2",
            "NUMBA_NUM_THREADS=48 OMP_NUM_THREADS=48 OPENBLAS_NUM_THREADS=48",
        ),
        ("uv run python benchmarks/bench_ceiling.py \\", "echo benchmarks/bench_ceiling.py \\"),
        ("${{ runner.temp }}/density-comparison-${{ github.sha }}.json", "density-comparison.json"),
        (
            "      - name: Upload ceiling report\n        if: always()",
            "      - name: Upload ceiling report\n        if: success()",
        ),
        ("          if-no-files-found: warn", "          if-no-files-found: ignore"),
    ],
)
def test_ceiling_comparison_rejects_changed_capacity_or_unbound_evidence(
    tmp_path: Path, old: str, new: str
) -> None:
    workflow = verify_ci_workflow.DEFAULT_CEILING_WORKFLOW.read_text(encoding="utf-8")
    assert old in workflow, old
    path = tmp_path / "ceiling-benchmark.yml"
    path.write_text(workflow.replace(old, new, 1), encoding="utf-8")
    assert verify_ci_workflow.validate_ceiling_workflow(path)


def test_all_workflows_checks_optional_ceiling_comparison(tmp_path: Path) -> None:
    source = verify_ci_workflow.DEFAULT_CEILING_WORKFLOW.read_text(encoding="utf-8")
    path = tmp_path / "ceiling-benchmark.yml"
    path.write_text(source.replace("--profile f64-memmap", "--profile f32"), encoding="utf-8")
    assert any(
        "Run ceiling sweep" in error
        for error in verify_ci_workflow.validate_all_workflows(ceiling_path=path)
    )
