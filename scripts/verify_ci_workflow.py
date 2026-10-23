#!/usr/bin/env python3
"""Verify workflow invariants that protect production-facing gates.

The workflows are YAML, but this checker intentionally stays stdlib-only so it
can run before the dev environment is installed. It does not try to be a full
YAML parser; it checks stable, high-value invariants that are easy to lose when
editing `.github/workflows/ci.yml` or `.github/workflows/publish.yaml`.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Optional

try:
    import verify_release_surface_results as release_inventory
except ModuleNotFoundError:  # imported by tests from the repository root
    from scripts import verify_release_surface_results as release_inventory

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULESET = ROOT / ".github" / "merge-queue-ruleset.json"
DEFAULT_CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DEFAULT_CODSPEED_WORKFLOW = ROOT / ".github" / "workflows" / "codspeed.yml"
DEFAULT_DENSITY_WORKFLOW = ROOT / ".github" / "workflows" / "density-100m.yml"
DEFAULT_FINAL_REVIEW_WORKFLOW = ROOT / ".github" / "workflows" / "final-coderabbit.yml"
DEFAULT_CODERABBIT_CONFIG = ROOT / ".coderabbit.yaml"
DEFAULT_FINAL_REVIEW_SCRIPT = ROOT / "scripts" / "request_final_coderabbit.py"
DEFAULT_RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "publish.yaml"
DEFAULT_WORKFLOWS_DIR = ROOT / ".github" / "workflows"
DEFAULT_WORKFLOW = DEFAULT_CI_WORKFLOW
DEFAULT_CONTRIBUTOR_SPEC = ROOT / "spec" / "process" / "contributing.md"
# Single source of truth: scripts/verify_release_surface_results.py. The workflow is
# checked against it below, so the hard/advisory boundary cannot drift silently.
REQUIRED_CI_JOBS = {
    *release_inventory.HARD_JOBS,
    *release_inventory.ADVISORY_CI_JOBS,
    *release_inventory.SUPPORT_JOBS,
}
PR_REQUIRED_CI_JOBS = set(release_inventory.ALWAYS_HARD_JOBS)
RELEASE_SURFACE_CONDITIONAL_JOBS = set(release_inventory.RELEASE_SURFACE_JOBS)
MAIN_ONLY_CI_JOBS = set(release_inventory.MAIN_EVIDENCE_JOBS)
REQUIRED_CODSPEED_JOBS = {"detect", "benchmarks"}
REQUIRED_RELEASE_JOBS = {
    "wheels",
    "sdist",
    "wasm",
    "wasm-assets",
    "browser-package",
    "node-native-packages",
    "node-facade",
    "release-cohort-linux-x64",
    "publish",
    "publish-npm",
    "github-release",
}
ALLOWED_BLACKSMITH_RUNNERS = {
    "blacksmith-4vcpu-ubuntu-2404",
    "blacksmith-4vcpu-ubuntu-2404-arm",
    "blacksmith-4vcpu-windows-2025",
    "blacksmith-6vcpu-macos-15",
    "blacksmith-12vcpu-macos-15",
}
CODSPEED_HOSTED_RUNNER = "codspeed-macro"


def validate_milestone_governance(
    contributor_spec: Path = DEFAULT_CONTRIBUTOR_SPEC,
) -> list[str]:
    errors: list[str] = []
    try:
        governance = contributor_spec.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read milestone governance specification {contributor_spec}: {exc}"]
    normalized_governance = " ".join(governance.split())
    for phrase in (
        "Creating, renaming, closing, or deleting a milestone",
        "explicit human approval recorded in a GitHub issue or pull request",
        "must not execute it before that approval",
        "Repository automation must not reopen, close, rename, create, or reassign milestones",
    ):
        if phrase not in normalized_governance:
            errors.append(f"milestone governance specification missing {phrase!r}")
    for stale in (
        ROOT / ".github" / "workflows" / "m2-assign-milestone.yml",
        ROOT / ".github" / "workflows" / "m2-wave-c-close.yml",
        ROOT / "scripts" / "m2_assign_milestone.sh",
        ROOT / "scripts" / "m2_wave_c_close.sh",
    ):
        if stale.exists():
            errors.append(f"unauthorized milestone mutation automation remains: {stale}")
    return errors


def _is_structural_npm_trusted_job(block: str, runner: str) -> bool:
    environment, environment_unsafe = _direct_yaml_key_values(block, "environment", indent=4)
    permissions = _unique_mapping_block(block, "permissions", indent=4)
    if permissions is None:
        return False
    id_token, id_token_unsafe = _direct_yaml_key_values(permissions, "id-token", indent=6)
    return (
        runner == "ubuntu-latest"
        and not environment_unsafe
        and environment == ["npm"]
        and not id_token_unsafe
        and id_token == ["write"]
    )


def _job_blocks(text: str) -> dict[str, str]:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line == "jobs:")
    except StopIteration:
        return {}

    blocks: dict[str, list[str]] = {}
    current: Optional[str] = None
    unsafe_index = 0
    for line in lines[start + 1 :]:
        if line.strip() and len(line) == len(line.lstrip(" ")):
            break
        parsed = _direct_yaml_mapping(line)
        if parsed is not None and parsed[0] == 2 and not parsed[3].strip():
            _indent, job_name, unsafe, _value = parsed
            if unsafe or job_name is None:
                unsafe_index += 1
                current = f"__unsafe_job_{unsafe_index}"
            else:
                current = job_name
            blocks[current] = [line]
            continue
        if current is not None:
            blocks[current].append(line)
    return {name: "\n".join(block) for name, block in blocks.items()}


def _matrix_include_entries(job_text: str) -> list[dict[str, str]]:
    """Parse the flat mappings under one job's strategy.matrix.include list."""
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_include = False
    for line in job_text.splitlines():
        if line == "        include:":
            in_include = True
            continue
        if not in_include:
            continue
        if line.startswith("          - "):
            if current is not None:
                entries.append(current)
            current = {}
            item = line.removeprefix("          - ")
        elif line.startswith("            ") and not line.lstrip().startswith("#"):
            item = line.removeprefix("            ")
        elif line.strip() and len(line) - len(line.lstrip()) <= 8:
            break
        else:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_-]+):\s*(.*?)", item)
        if match and current is not None:
            current[match.group(1)] = match.group(2)
    if current is not None:
        entries.append(current)
    return entries


def _matrix_os_values(job_text: str) -> tuple[list[str], bool]:
    """Return static ``strategy.matrix.os`` values and whether an axis is dynamic."""
    lines = job_text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line == "      matrix:")
    except StopIteration:
        return [], False
    matrix_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= 6:
            break
        matrix_lines.append(_strip_yaml_comment(line))

    values: list[str] = []
    direct_axes = []
    axis_unsafe = False
    include_unsafe = False
    in_include = False
    for index, line in enumerate(matrix_lines):
        parsed = _direct_yaml_mapping(line)
        if parsed is not None and parsed[0] == 8 and parsed[1] == "include":
            in_include = True
            include_unsafe = include_unsafe or parsed[2] or bool(parsed[3].strip())
            continue
        if in_include and line.strip() and len(line) - len(line.lstrip()) <= 8:
            in_include = False
        if in_include:
            flow_item = line.strip()
            if flow_item.startswith("- {"):
                if not flow_item.endswith("}"):
                    include_unsafe = True
                    continue
                os_values: list[str] = []
                for match in re.finditer(
                    rf"(?:^|[,{{])\s*(?P<key>{_YAML_KEY_TOKEN})\s*:\s*"
                    r"(?P<value>[^,}]+)",
                    flow_item.removeprefix("- "),
                ):
                    key, unsafe = _decode_yaml_key(match.group("key"))
                    include_unsafe = include_unsafe or unsafe
                    if key == "os":
                        raw_value = match.group("value").strip()
                        if raw_value.startswith(('"', "'")):
                            include_unsafe = True
                        os_values.append(raw_value.strip("\"'"))
                if len(os_values) != 1 or os_values[0].startswith("${{"):
                    include_unsafe = True
                else:
                    values.extend(os_values)
                continue
            item = _sequence_item_yaml_mapping(line)
            continuation = _direct_yaml_mapping(line)
            include_mapping = item or (
                continuation if continuation is not None and continuation[0] == 12 else None
            )
            if include_mapping is not None:
                _indent, key, unsafe, value = include_mapping
                include_unsafe = include_unsafe or unsafe
                if key == "os":
                    raw_value = value.strip()
                    if not raw_value or raw_value.startswith(("{", "[", "${{", '"', "'")):
                        include_unsafe = True
                    else:
                        values.append(raw_value)
                continue
            if line.strip() and len(line) - len(line.lstrip()) >= 10:
                include_unsafe = True
            continue
        if parsed is not None and parsed[0] == 8 and parsed[1] == "os":
            direct_axes.append(parsed)
            value = parsed[3].strip()
            inline_list = re.fullmatch(r"\[(.*)\]", value)
            if inline_list:
                axis_unsafe = True
                continue
            if not value:
                for value_line in matrix_lines[index + 1 :]:
                    if not value_line.strip():
                        continue
                    if len(value_line) - len(value_line.lstrip()) <= 8:
                        break
                    value_match = re.fullmatch(r"\s{10}-\s+(.+?)\s*", value_line)
                    if value_match:
                        scalar = value_match.group(1).strip()
                        if scalar.startswith(("{", "[", "|", ">", "${{", '"', "'")):
                            axis_unsafe = True
                        else:
                            values.append(scalar)
                        continue
                    axis_unsafe = True
            continue
    dynamic_axis = (
        axis_unsafe
        or include_unsafe
        or len(direct_axes) > 1
        or (
            len(direct_axes) == 1
            and (
                direct_axes[0][2]
                or bool(direct_axes[0][3].strip() and not direct_axes[0][3].strip().startswith("["))
            )
        )
    )
    return values, dynamic_axis


def _missing_needles(block: str, needles: tuple[str, ...]) -> list[str]:
    return [needle for needle in needles if needle not in block]


_YAML_KEY_TOKEN = r"""(?:"(?:\\.|[^"\\])*"|'(?:''|[^'])*'|[A-Za-z_][A-Za-z0-9_-]*)"""
_DIRECT_YAML_KEY = re.compile(rf"^(?P<key>{_YAML_KEY_TOKEN})\s*:(?=\s|$)(?P<value>.*)$")
_NODE_PROPERTY_MAPPING_KEY = re.compile(
    rf"^(?:(?:![^\s]+|&[^\s]+)\s+)+"
    rf"(?:{_YAML_KEY_TOKEN}|\*[^\s:]+|<<)\s*:(?=\s|$)"
)
_ALIAS_OR_MERGE_MAPPING_KEY = re.compile(r"^(?:\*[^\s:]+|<<)\s*:(?=\s|$)")
_YAML_NODE_PROPERTIES_ONLY = re.compile(r"(?:(?:![^\s]+|&[^\s]+)\s*)+")


def _strip_yaml_comment(line: str) -> str:
    """Remove a YAML comment while preserving ``#`` inside quoted scalars."""
    quote: Optional[str] = None
    index = 0
    while index < len(line):
        char = line[index]
        if quote == '"':
            if char == "\\":
                index += 2
                continue
            if char == '"':
                quote = None
        elif quote == "'":
            if char == "'" and index + 1 < len(line) and line[index + 1] == "'":
                index += 2
                continue
            if char == "'":
                quote = None
        elif char in {'"', "'"}:
            quote = char
        elif char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip()
        index += 1
    return line.rstrip()


def _yaml_code_lines(text: str) -> list[str]:
    """Return comment-free source lines for indentation-scoped checks.

    The protected keys below are checked only at their exact structural
    indentation. More deeply indented scalar content is irrelevant; a rare
    same-indent quoted continuation that resembles a protected structural key
    deliberately fails closed rather than requiring a full YAML parser.
    """
    return [_strip_yaml_comment(line) for line in text.splitlines()]


def _decode_yaml_key(token: str) -> tuple[Optional[str], bool]:
    """Return a simple scalar key and whether its spelling is unsupported.

    JSON decoding covers YAML's common double-quoted escapes, including
    ``\\u`` spellings used to hide ASCII workflow keys. YAML-only escape forms
    (for example ``\\x`` or ``\\U``) fail closed rather than attempting to
    duplicate a complete YAML scalar decoder.
    """
    if token.startswith('"'):
        try:
            decoded = json.loads(token)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, True
        return (decoded, False) if isinstance(decoded, str) else (None, True)
    if token.startswith("'"):
        return token[1:-1].replace("''", "'"), False
    return token, False


def _yaml_mapping_keys(text: str) -> list[tuple[Optional[int], Optional[str], bool]]:
    """Lex block mapping keys as ``(indent, value, unsafe_syntax)``."""
    lines = _yaml_code_lines(text)
    keys: list[tuple[Optional[int], Optional[str], bool]] = []
    explicit = re.compile(rf"^\?\s+(?P<key>{_YAML_KEY_TOKEN})(?:\s*:.*)?\s*$")
    for line in lines:
        indent = len(line) - len(line.lstrip(" "))
        body = line[indent:]
        match = _DIRECT_YAML_KEY.match(body)
        if match is not None:
            value, unsafe = _decode_yaml_key(match.group("key"))
            keys.append((indent, value, unsafe))
        elif (match := explicit.match(body)) is not None:
            value, _unsafe = _decode_yaml_key(match.group("key"))
            # Explicit keys are valid YAML but unnecessary in these protected
            # workflow scopes. Treat even a recognized spelling as unsafe so
            # a following value line cannot alter the reviewed structure.
            keys.append((indent, value, True))
        elif body == "?" or body.startswith("? "):
            # Complex/multiline explicit keys are irrelevant to these
            # workflow contracts and hard to normalize without a YAML parser.
            # Treat the explicit key indicator itself as unsafe at this scope.
            keys.append((indent, None, True))
        elif body.startswith('"') and "\\" in body:
            # A double-quoted key can continue onto another source line with a
            # backslash, hiding the decoded key from a line-local lexer.
            keys.append((indent, None, True))
        elif _NODE_PROPERTY_MAPPING_KEY.match(body) or _ALIAS_OR_MERGE_MAPPING_KEY.match(body):
            # YAML node properties, aliases, and merge keys can normalize or
            # import an effective mapping key (for example
            # ``!!str BASH_ENV:``, ``*anchored_key:``, or ``<<: *defaults``).
            # Protected workflow scopes do not need them, so fail closed.
            keys.append((indent, None, True))
    return keys


def _direct_yaml_mapping(
    line: str,
) -> Optional[tuple[int, Optional[str], bool, str]]:
    """Return ``(indent, decoded_key, unsafe, raw_value)`` for a block key."""
    indent = len(line) - len(line.lstrip(" "))
    match = _DIRECT_YAML_KEY.match(line[indent:])
    if match is None:
        return None
    key, unsafe = _decode_yaml_key(match.group("key"))
    return indent, key, unsafe, match.group("value")


def _sequence_item_yaml_mapping(
    line: str,
) -> Optional[tuple[int, Optional[str], bool, str]]:
    """Return the first mapping entry carried by a block sequence item.

    A step written as ``- uses: ...`` has a mapping key two columns deeper
    than the sequence indicator. Decode that key exactly like a regular block
    key so quoted and escape-equivalent spellings cannot disappear from
    structural step checks.
    """
    indent = len(line) - len(line.lstrip(" "))
    item = re.match(r"^-\s+(?P<mapping>.*)$", line[indent:])
    if item is None:
        return None
    match = _DIRECT_YAML_KEY.match(item.group("mapping"))
    if match is None:
        return None
    key, unsafe = _decode_yaml_key(match.group("key"))
    return indent + 2, key, unsafe, match.group("value")


def _step_direct_key_values(step: str, key: str) -> tuple[list[str], bool]:
    """Return direct values for one key in a standard Actions step mapping."""
    values: list[str] = []
    unsafe = False
    for index, line in enumerate(_yaml_code_lines(step)):
        parsed = _sequence_item_yaml_mapping(line) if index == 0 else _direct_yaml_mapping(line)
        if parsed is None or parsed[0] != 8:
            continue
        _indent, candidate, candidate_unsafe, value = parsed
        if candidate_unsafe:
            unsafe = True
        elif candidate == key:
            values.append(value.strip())
    return values, unsafe


def _step_direct_keys(step: str) -> tuple[list[str], bool]:
    """Return direct step keys, including the key carried by ``- key:``."""
    keys: list[str] = []
    unsafe = False
    for index, line in enumerate(_yaml_code_lines(step)):
        parsed = _sequence_item_yaml_mapping(line) if index == 0 else _direct_yaml_mapping(line)
        if parsed is None or parsed[0] != 8:
            continue
        _indent, key, key_unsafe, _value = parsed
        unsafe = unsafe or key_unsafe or key is None
        if key is not None:
            keys.append(key)
    return keys, unsafe


def _environment_block_is_unsafe(lines: list[str], index: int, env_indent: int) -> bool:
    """Inspect one reviewed block-style Actions ``env`` mapping."""
    parsed = _direct_yaml_mapping(lines[index])
    if parsed is None or parsed[3].strip():
        # Inline flow maps, aliases, and tagged values are unnecessary in the
        # protected scopes and require full YAML resolution, so fail closed.
        return True

    descendants: list[str] = []
    for line in lines[index + 1 :]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= env_indent:
            break
        descendants.append(line)
    if not descendants:
        return False

    child_indent = min(len(line) - len(line.lstrip(" ")) for line in descendants)
    quote: Optional[str] = None

    def closes(value: str, delimiter: str, *, starts_here: bool) -> bool:
        cursor = 1 if starts_here else 0
        while cursor < len(value):
            char = value[cursor]
            if delimiter == '"' and char == "\\":
                cursor += 2
                continue
            if (
                delimiter == "'"
                and char == "'"
                and cursor + 1 < len(value)
                and value[cursor + 1] == "'"
            ):
                cursor += 2
                continue
            if char == delimiter:
                return True
            cursor += 1
        return False

    for line in descendants:
        if quote is not None:
            if closes(line, quote, starts_here=False):
                quote = None
            continue
        if len(line) - len(line.lstrip(" ")) != child_indent:
            continue
        child = _direct_yaml_mapping(line)
        if child is None:
            return True
        _indent, key, unsafe, value = child
        if unsafe or key in {"BASH_ENV", "ENV", "PATH"}:
            return True
        scalar = value.lstrip()
        if scalar[:1] in {'"', "'"} and not closes(scalar, scalar[0], starts_here=True):
            quote = scalar[0]
    return quote is not None


def _has_shell_init_environment(text: str) -> bool:
    """Reject shell-init state in workflow/job/step environment scopes.

    Exact indentation plus the enclosing job section distinguishes Actions
    environment mappings from unrelated data keys such as ``matrix.env`` or a
    ``with.env`` action input. Protected hard-gate jobs also have a simple,
    reviewable policy of never referencing GitHub's persistent environment
    file, so earlier steps cannot directly persist shell initialization for a
    later reviewed command.
    """
    lines = _yaml_code_lines(text)
    protected_jobs = _job_blocks(text)
    protected_job_text = "\n".join(
        protected_jobs.get(job, "") for job in ("matplotlib_reference", "test")
    )
    if any(
        re.search(r"\bGITHUB_(?:ENV|PATH)\b", line)
        for line in _yaml_code_lines(protected_job_text)
        if line.strip()
    ):
        return True

    in_jobs = False
    in_job = False
    job_section: Optional[str] = None
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        parsed = _direct_yaml_mapping(line)
        indent = len(line) - len(line.lstrip(" "))

        relevant_env = False
        if indent == 0:
            key = None if parsed is None else parsed[1]
            value = "" if parsed is None else parsed[3]
            relevant_env = key == "env"
            in_jobs = key == "jobs" and not value.strip()
            in_job = False
            job_section = None
        elif in_jobs and indent == 2:
            in_job = parsed is not None
            job_section = None
        elif in_jobs and in_job and indent == 4:
            key = None if parsed is None else parsed[1]
            value = "" if parsed is None else parsed[3]
            relevant_env = key == "env"
            stripped_value = value.strip()
            opens_block = not stripped_value or _YAML_NODE_PROPERTIES_ONLY.fullmatch(stripped_value)
            job_section = key if parsed is not None and opens_block else None
        elif in_jobs and in_job and indent == 8 and job_section == "steps":
            relevant_env = parsed is not None and parsed[1] == "env"

        if not relevant_env:
            continue
        if parsed is None or parsed[2] or _environment_block_is_unsafe(lines, index, indent):
            return True
    return False


def _has_yaml_key(text: str, key: str, *, indent: Optional[int] = None) -> bool:
    """Recognize equivalent YAML mapping-key spellings.

    Unrecognized escape-encoded mapping keys fail closed: allowing one in a
    protected scope would let the YAML parser reveal ``run``, ``ENV``, or a
    suppression key only after this stdlib-only verifier had approved it.
    """
    return any(
        (candidate_indent is not None or indent is None)
        and (indent is None or candidate_indent == indent)
        and (unsafe or candidate == key)
        for candidate_indent, candidate, unsafe in _yaml_mapping_keys(text)
    )


def _direct_yaml_key_count(text: str, key: str, *, indent: int) -> int:
    """Count equivalent direct mapping keys at one block indentation."""
    return sum(
        candidate_indent == indent and (unsafe or candidate == key)
        for candidate_indent, candidate, unsafe in _yaml_mapping_keys(text)
    )


def _direct_yaml_key_values(text: str, key: str, *, indent: int) -> tuple[list[str], bool]:
    """Return normalized direct values and whether that scope is ambiguous."""
    values: list[str] = []
    for line in _yaml_code_lines(text):
        parsed = _direct_yaml_mapping(line)
        if parsed is None:
            continue
        candidate_indent, candidate, unsafe, value = parsed
        if candidate_indent == indent and candidate == key and not unsafe:
            values.append(value.strip())
    unsafe = any(
        candidate_indent == indent and candidate_unsafe
        for candidate_indent, _candidate, candidate_unsafe in _yaml_mapping_keys(text)
    )
    return values, unsafe


def _unique_mapping_block(text: str, key: str, *, indent: int) -> Optional[str]:
    """Return one block-style mapping value, bounded by its indentation."""
    # Count all normalized occurrences before selecting the reviewed block.
    # In particular, an inline duplicate (``"on": {}``) or an unsupported
    # equivalent spelling must not be ignored merely because one ordinary
    # block-style occurrence is also present.
    if _direct_yaml_key_count(text, key, indent=indent) != 1:
        return None
    raw_lines = text.splitlines()
    code_lines = _yaml_code_lines(text)
    starts: list[int] = []
    for index, line in enumerate(code_lines):
        parsed = _direct_yaml_mapping(line)
        if parsed is None or parsed[0] != indent or parsed[1] != key or parsed[2]:
            continue
        value = parsed[3].strip()
        if not value or _YAML_NODE_PROPERTIES_ONLY.fullmatch(value):
            starts.append(index)
    if len(starts) != 1:
        return None
    start = starts[0]
    end = len(raw_lines)
    for index in range(start + 1, len(code_lines)):
        line = code_lines[index]
        if line.strip() and len(line) - len(line.lstrip(" ")) <= indent:
            end = index
            break
    return "\n".join(raw_lines[start + 1 : end])


def _has_safe_release_dry_run_input(text: str) -> bool:
    """Validate the exact nested manual-release dry-run input mapping."""
    block = _unique_mapping_block(text, "on", indent=0)
    if block is None:
        return False
    block = _unique_mapping_block(block, "workflow_dispatch", indent=2)
    if block is None:
        return False
    block = _unique_mapping_block(block, "inputs", indent=4)
    if block is None:
        return False
    block = _unique_mapping_block(block, "dry_run", indent=6)
    if block is None:
        return False
    type_values, type_unsafe = _direct_yaml_key_values(block, "type", indent=8)
    default_values, default_unsafe = _direct_yaml_key_values(block, "default", indent=8)
    return (
        not type_unsafe
        and not default_unsafe
        and type_values == ["boolean"]
        and default_values == ["true"]
    )


def _require_unique_workflow_structure(
    errors: list[str],
    text: str,
    workflow_label: str,
    required_jobs: set[str],
) -> None:
    """Reject duplicate/encoded overrides of protected workflow mappings."""
    top_blocks: dict[str, Optional[str]] = {}
    for key in ("on", "jobs"):
        block = _unique_mapping_block(text, key, indent=0)
        top_blocks[key] = block
        if block is None:
            errors.append(
                f"{workflow_label} workflow must define exactly one unambiguous block-style "
                "top-level "
                f"{key!r} key"
            )

    job_keys: list[tuple[Optional[int], Optional[str], bool]] = []
    if top_blocks["jobs"] is not None:
        job_keys = _yaml_mapping_keys(top_blocks["jobs"] or "")

    unsafe_job_key = any(indent == 2 and unsafe for indent, _key, unsafe in job_keys)
    for job in sorted(required_jobs):
        count = sum(
            indent == 2 and candidate == job and not unsafe
            for indent, candidate, unsafe in job_keys
        )
        if unsafe_job_key or count != 1:
            errors.append(
                f"{workflow_label} workflow must define exactly one unambiguous {job!r} job"
            )


def _steps_block(job_text: str) -> str:
    """Return the unique actual ``steps:`` sequence inside one job."""
    return _unique_mapping_block(job_text, "steps", indent=4) or ""


def _step_sequence_blocks(job_text: str) -> list[str]:
    """Return the actual sequence items under a job's unique ``steps`` key."""
    blocks: list[list[str]] = []
    current: Optional[list[str]] = None
    for line in _steps_block(job_text).splitlines():
        if re.match(r"^      -(?:\s|$)", line):
            current = [line]
            blocks.append(current)
        elif current is not None:
            current.append(line)
    return ["\n".join(block) for block in blocks]


def _named_step_blocks(job_text: str) -> dict[str, str]:
    """Return named blocks from the job's actual ``steps:`` sequence."""
    blocks: dict[str, str] = {}
    for block in _step_sequence_blocks(job_text):
        first = _strip_yaml_comment(block.splitlines()[0])
        match = re.match(r"^      - name:\s*(.+?)\s*$", first)
        if match is not None:
            blocks[match.group(1)] = block
    return blocks


def _require_step_contains(
    errors: list[str], job_text: str, step: str, description: str, *needles: str
) -> None:
    block = _named_step_blocks(job_text).get(step)
    if block is None:
        errors.append(f"missing required CI step {step!r}")
        return
    missing = _missing_needles(block, needles)
    if missing:
        errors.append(f"CI step {step!r} missing {description}: {missing}")


def _step_run_lines(step_block: str) -> list[str]:
    """Return executable lines from one named step's ``run`` value only."""
    lines = step_block.splitlines()
    for index, line in enumerate(lines):
        match = re.fullmatch(r"        run:\s*(.*?)\s*", line)
        if match is None:
            continue
        value = match.group(1)
        # Folded scalars concatenate adjacent source lines before the shell
        # sees them. That makes a visually separate ``# disabled`` line turn
        # the following command into comment text, so this exact-command gate
        # accepts only a one-line value or a literal block.
        if value.startswith(">"):
            return []
        if value not in {"|", "|-", "|+"}:
            return [value] if value and not value.startswith("#") else []

        commands: list[str] = []
        for command in lines[index + 1 :]:
            if command.strip() and len(command) - len(command.lstrip()) <= 8:
                break
            stripped = command.strip()
            if stripped and not stripped.startswith("#"):
                commands.append(stripped)
        return commands
    return []


HARD_PRODUCER_JOBS = frozenset({"wasm_assets"})


def _needs_only_hard_producers(job_text: str) -> bool:
    """True when a job has no ``needs`` or depends only on the single WASM producer."""
    values, unsafe = _direct_yaml_key_values(job_text, "needs", indent=4)
    if unsafe or len(values) > 1:
        return False
    if not values:
        return True
    names = {item.strip() for item in values[0].strip("[]").split(",") if item.strip()}
    return bool(names) and names <= HARD_PRODUCER_JOBS


def _require_step_runs_exactly(
    errors: list[str],
    job_text: str,
    step: str,
    description: str,
    *commands: str,
    allow_job_gate: bool = False,
    allowed_shell: str | None = None,
    required_id: str | None = None,
    forbid_environment: bool = False,
) -> None:
    """Require the exact active command list in a hard-gate named step."""
    block = _named_step_blocks(job_text).get(step)
    if block is None:
        errors.append(f"missing required CI step {step!r}")
        return
    # Membership is insufficient: a needle could otherwise be heredoc data,
    # an uninvoked function body, or one folded argument to another command.
    forbidden_step_keys = ("if", "continue-on-error", "working-directory")
    if forbid_environment:
        forbidden_step_keys += ("env",)
    if allowed_shell is None:
        forbidden_step_keys += ("shell",)
    has_forbidden_step_key = any(_has_yaml_key(block, key, indent=8) for key in forbidden_step_keys)
    shell_values, shell_unsafe = _direct_yaml_key_values(block, "shell", indent=8)
    has_required_shell = allowed_shell is None or (
        not shell_unsafe and shell_values == [allowed_shell]
    )
    id_values, id_unsafe = _step_direct_key_values(block, "id")
    has_required_id = required_id is None or (not id_unsafe and id_values == [required_id])
    forbidden_job_keys = ("continue-on-error", "defaults", "container", "strategy")
    if forbid_environment:
        forbidden_job_keys += ("env",)
    if not allow_job_gate:
        job_if, job_if_unsafe = _direct_yaml_key_values(job_text, "if", indent=4)
        if job_if_unsafe or job_if not in (
            [],
            ["github.event_name != 'pull_request'"],
            ["github.event_name == 'push' || github.event_name == 'workflow_dispatch'"],
        ):
            forbidden_job_keys += ("if",)
        # `needs` may name only the single WASM producer: a skipped or failed producer
        # skips the consumer, and the Release surfaces aggregate treats an applicable
        # skip as a failure, so this dependency cannot hide a missing prerequisite.
        if not _needs_only_hard_producers(job_text):
            forbidden_job_keys += ("needs",)
    has_forbidden_job_key = any(
        _has_yaml_key(job_text, key, indent=4) for key in forbidden_job_keys
    )
    has_exactly_one_run_key = _direct_yaml_key_count(block, "run", indent=8) == 1
    if (
        not has_exactly_one_run_key
        or _step_run_lines(block) != list(commands)
        or has_forbidden_step_key
        or not has_required_shell
        or not has_required_id
        or has_forbidden_job_key
    ):
        errors.append(f"CI step {step!r} missing {description}: {list(commands)!r}")


def _require_release_classifier_structure(errors: list[str], job_text: str) -> None:
    """Bind classifier output provenance to one pinned, side-effect-free step."""
    outputs = _unique_mapping_block(job_text, "outputs", indent=4)
    output_keys = [
        key
        for indent, key, unsafe in _yaml_mapping_keys(outputs or "")
        if indent == 6 and not unsafe
    ]
    required_values, required_unsafe = _direct_yaml_key_values(outputs or "", "required", indent=6)
    if (
        outputs is None
        or required_unsafe
        or output_keys != ["required"]
        or required_values != ["${{ steps.classify.outputs.required }}"]
    ):
        errors.append(
            "CI release-surface classifier output must come only from "
            "steps.classify.outputs.required"
        )

    steps = _step_sequence_blocks(job_text)
    classifier_steps = []
    classifier_ids = 0
    for step in steps:
        names, names_unsafe = _step_direct_key_values(step, "name")
        ids, ids_unsafe = _step_direct_key_values(step, "id")
        if names_unsafe or names == ["Classify changed paths"]:
            classifier_steps.append(step)
        if ids_unsafe or ids == ["classify"]:
            classifier_ids += 1

    checkout_ok = False
    if steps:
        checkout = steps[0]
        checkout_keys = [
            key
            for indent, key, unsafe in _yaml_mapping_keys(checkout)
            if indent == 8 and not unsafe
        ]
        uses, uses_unsafe = _step_direct_key_values(checkout, "uses")
        uses = [value.split(" #", 1)[0] for value in uses]
        with_block = _unique_mapping_block(checkout, "with", indent=8)
        with_keys = [
            key
            for indent, key, unsafe in _yaml_mapping_keys(with_block or "")
            if indent == 10 and not unsafe
        ]
        depths, depth_unsafe = _direct_yaml_key_values(with_block or "", "fetch-depth", indent=10)
        checkout_ok = (
            not uses_unsafe
            and checkout_keys == ["with"]
            and uses == ["actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"]
            and with_block is not None
            and with_keys == ["fetch-depth"]
            and not depth_unsafe
            and depths == ["0"]
        )
    if len(steps) != 2 or not checkout_ok or len(classifier_steps) != 1 or classifier_ids != 1:
        errors.append(
            "CI release-surface classifier job must contain only the pinned checkout and "
            "one classify step with the unique id 'classify'"
        )


def _require_action_step_with_runs_exactly(
    errors: list[str], job_text: str, step: str, action: str, mode: str, *commands: str
) -> None:
    """Bind an action's exact mode and fail-fast command list to its named step."""
    block = _named_step_blocks(job_text).get(step)
    if block is None:
        errors.append(f"missing required CI step {step!r}")
        return
    lines = block.splitlines()
    uses = [
        line.strip()[6:].split(" #", 1)[0] for line in lines if line.startswith("        uses: ")
    ]
    modes, modes_unsafe = _direct_yaml_key_values(block, "mode", indent=10)
    runs, runs_unsafe = _direct_yaml_key_values(block, "run", indent=10)
    unsafe = any(_has_yaml_key(block, key, indent=8) for key in ("continue-on-error", "if"))
    run_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.fullmatch(r"          run:\s*\|[-+]?\s*", line)
        ),
        None,
    )
    actual: list[str] = []
    if run_index is not None:
        for line in lines[run_index + 1 :]:
            if not line.startswith("            "):
                break
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                actual.append(stripped)
    if (
        uses != [action]
        or modes != [mode]
        or modes_unsafe
        or runs not in (["|"], ["|-"], ["|+"])
        or runs_unsafe
        or actual != list(commands)
        or unsafe
    ):
        errors.append(f"CI step {step!r} missing exact action commands: {list(commands)!r}")


def _require_job_contains(
    errors: list[str],
    jobs: dict[str, str],
    job: str,
    workflow_label: str,
    description: str,
    *needles: str,
) -> None:
    block = jobs.get(job)
    if block is None:
        errors.append(f"missing required {workflow_label} job {job!r}")
        return
    missing = _missing_needles(block, needles)
    if missing:
        errors.append(f"{workflow_label} {job} job missing {description}: {missing}")


def _step_block(job_text: str, step_needle: str) -> Optional[str]:
    """The indented block of the step whose `uses:`/`run:` line contains
    `step_needle` — the step's own lines only, so a same-level sibling step
    can't mask a missing key.

    The prefix (the step's own `uses:`/`name:`/`run:` line) is matched with
    `[^\\n]*`, not a dot-all `.*` — under re.DOTALL a greedy `.*` would happily
    span past earlier sibling steps and swallow their `if:` lines too, which
    defeats the whole point of scoping this to one step.
    """
    match = re.search(
        rf"( *)- (?:uses|name|run): [^\n]*{re.escape(step_needle)}[^\n]*\n([\s\S]*?)(?=\n\1- |\Z)",
        _steps_block(job_text),
    )
    return None if match is None else match.group(0)


def _step_is_conditioned(job_text: str, step_needle: str) -> bool:
    """True if the step has its own `if:` key — not just any `if:` elsewhere
    in the job (e.g. a sibling step's dry-run summary)."""
    block = _step_block(job_text, step_needle)
    return block is not None and "if:" in block


# The one condition that actually gates a PyPI upload: the explicit
# XYG_ALLOW_PYPI_PUBLISH repository-variable opt-in (which does not exist by
# default on this fork, see issue #13), an XYG-owned tag, AND the manual
# dry-run switch.
# Requiring this exact predicate on the upload step itself — not merely *an*
# `if:` — is the point: `if: always()` or any unrelated condition would
# satisfy a mere presence check while gating nothing.
PYPI_PUBLISH_GATE = (
    "if: vars.XYG_ALLOW_NPM_PUBLISH == 'true' && vars.XYG_ALLOW_PYPI_PUBLISH == 'true' && "
    "startsWith(github.ref, 'refs/tags/xyg-v') && "
    "(github.event_name != 'workflow_dispatch' || github.event.inputs.dry_run != 'true')"
)
REAL_PUBLISH_STEP_GATE = "if: github.event_name == 'push' || github.event.inputs.dry_run != 'true'"
GITHUB_RELEASE_GATE = (
    "vars.XYG_ALLOW_PYPI_PUBLISH == 'true' && "
    "vars.XYG_ALLOW_NPM_PUBLISH == 'true' && "
    "startsWith(github.ref, 'refs/tags/xyg-v') && "
    "(github.event_name != 'workflow_dispatch' || github.event.inputs.dry_run != 'true')"
)

# The fork repository guard on the publish job itself (issue #13): only
# CurateLabs/xyg may reach the OIDC upload. PyPI trusted publishing is bound
# to this slug, workflow filename publish.yaml, and environment `pypi`.
PUBLISH_REPOSITORY_GUARD = "github.repository == 'CurateLabs/xyg'"


def _step_carries_publish_gate(job_text: str, step_needle: str) -> bool:
    block = _step_block(job_text, step_needle)
    if block is None:
        return False
    values, unsafe = _direct_yaml_key_values(block, "if", indent=8)
    expected = PYPI_PUBLISH_GATE.partition(":")[2].strip()
    return not unsafe and values == [expected]


def _require_workflow_contains(
    errors: list[str],
    text: str,
    workflow_label: str,
    description: str,
    *needles: str,
) -> None:
    missing = _missing_needles(text, needles)
    if missing:
        errors.append(f"{workflow_label} workflow missing {description}: {missing}")


def _require_unshallow_checkouts(errors: list[str], text: str, workflow_label: str) -> None:
    """Every checkout must fetch full history, tags included.

    The distribution version is derived from the latest `xyg-v*` tag
    (uv-dynamic-versioning in pyproject), and `actions/checkout` defaults to a
    depth-1 clone carrying no tags at all. Under that default the version
    resolves to the `0.0.0` fallback *silently* — a build succeeds and ships the
    wrong number rather than failing. So a shallow checkout here is a publishing
    bug, not a performance tweak, and it is invisible until someone reads a
    PyPI page. Cheap to require, expensive to notice late.
    """
    checkout_count = 0
    for job in _job_blocks(text).values():
        for step in _step_sequence_blocks(job):
            uses_values, uses_unsafe = _step_direct_key_values(step, "uses")
            uses_checkout = uses_unsafe or any(
                value.startswith("actions/checkout@") for value in uses_values
            )
            if not uses_checkout:
                continue
            checkout_count += 1
            with_block = _unique_mapping_block(step, "with", indent=8)
            if with_block is not None:
                values, unsafe = _direct_yaml_key_values(with_block, "fetch-depth", indent=10)
            else:
                values, unsafe = [], False
            if not unsafe and values == ["0"]:
                continue
            errors.append(
                f"{workflow_label} workflow has an actions/checkout step without a unique "
                "direct `fetch-depth: 0` input — the distribution version is derived from "
                "git tags, which a shallow checkout does not fetch, so the build would "
                "quietly fall back to 0.0.0"
            )
    if checkout_count == 0:
        errors.append(f"{workflow_label} workflow has no structurally recognized checkout step")


def _workflow_trigger_block(text: str, trigger: str) -> Optional[str]:
    """Return one trigger mapping from the unique top-level ``on`` block."""
    on_block = _unique_mapping_block(text, "on", indent=0)
    if on_block is None:
        return None
    return _unique_mapping_block(on_block, trigger, indent=2)


def _require_trigger_with_direct_option(
    errors: list[str],
    text: str,
    workflow_label: str,
    trigger: str,
    option: str,
    expected: str,
) -> None:
    """Require one direct trigger option inside the unique ``on`` mapping."""
    block = _workflow_trigger_block(text, trigger)
    if block is None:
        errors.append(f"{workflow_label} workflow missing {trigger} trigger")
        return
    values, unsafe = _direct_yaml_key_values(block, option, indent=4)
    if unsafe or values != [expected]:
        errors.append(
            f"{workflow_label} {trigger} trigger must define exactly one direct "
            f"{option}: {expected} option"
        )


def _require_docs_spec_pr_paths_ignored(errors: list[str], text: str, workflow_label: str) -> None:
    """Require PR-only docs/spec changes in the unique top-level trigger block."""
    pull_request = _workflow_trigger_block(text, "pull_request")
    if pull_request is None:
        errors.append(f"{workflow_label} workflow missing pull_request trigger")
        return
    paths_block = _unique_mapping_block(pull_request, "paths-ignore", indent=4)
    paths_ignore: list[str] = []
    for line in _yaml_code_lines(paths_block or ""):
        if len(line) - len(line.lstrip(" ")) != 6:
            continue
        item = re.fullmatch(r"\s*-\s+(.+?)\s*", line)
        if item is None:
            continue
        value = item.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        paths_ignore.append(value)

    required = {"docs/**", "spec/**"}
    missing = sorted(required - set(paths_ignore))
    if missing:
        errors.append(
            f"{workflow_label} pull_request trigger must skip docs/spec-only changes: {missing}"
        )


WASM_CONSUMER_JOBS = (
    "test",
    "wasm_foundation",
    "python_floor",
    "matplotlib_reference",
    "benchmark_methodology",
    "wheels",
    "sdist",
)
WASM_ARTIFACT = "wasm-assets"
WASM_DOWNLOAD_STEP = "Fetch packaged WASM assets from the wasm_assets producer"
WASM_VERIFY_STEP = "Verify packaged WASM assets (missing or stale fails here)"
# Release workflow (publish.yaml): same contract, hyphenated job ids.
RELEASE_WASM_PRODUCER = "wasm-assets"
RELEASE_WASM_CONSUMER_JOBS = ("wheels", "wasm", "browser-package", "sdist")
RELEASE_WASM_DOWNLOAD_STEP = "Fetch packaged WASM assets from the wasm-assets producer"


# Anything that compiles or packages xyg-wasm outside the producer is a second,
# unverified producer whose output a consumer could mistake for the real one.
def _runs_wasm_producer(line: str) -> Optional[str]:
    """Name the producer command a shell line runs, whatever the flag order or spelling.

    Parses the arguments instead of matching one exact string, so reordered, abbreviated,
    or package-manager-spelled invocations cannot slip a second, unverified producer past
    the single-producer rule. Callers join backslash-continued lines first.
    """
    try:
        words = shlex.split(line, comments=True)
    except ValueError:
        words = line.split()
    managers = {"npm", "pnpm", "yarn", "bun"}
    if "build:wasm" in words and managers & set(words):
        return "npm run build:wasm"
    if any(word.endswith("package-wasm.mjs") for word in words):
        return "node js/package-wasm.mjs"
    if "cargo" in words and "build" in words:

        def flag_value(*flags: str) -> list[str]:
            values: list[str] = []
            for index, word in enumerate(words):
                if word in flags and index + 1 < len(words):
                    values.append(words[index + 1])
                for flag in flags:
                    if flag.startswith("--") and word.startswith(flag + "="):
                        values.append(word[len(flag) + 1 :])
                if word.startswith("-p") and not word.startswith("--") and "-p" in flags:
                    values.append(word[2:])
            return values

        package = "xyg-wasm" in flag_value("-p", "--package") or any(
            value.replace("\\", "/").rstrip("/").endswith("xyg-wasm/Cargo.toml")
            for value in flag_value("--manifest-path")
        )
        if package and WASM_TARGET in flag_value("--target"):
            return "cargo build -p xyg-wasm --target wasm32-unknown-unknown"
    return None


WASM_TARGET = "wasm32-unknown-unknown"


def _require_wasm_asset_contract(
    errors: list[str],
    jobs: dict[str, str],
    *,
    label: str = "CI",
    producer_name: str = "wasm_assets",
    consumers: tuple[str, ...] = WASM_CONSUMER_JOBS,
    download_step: str = WASM_DOWNLOAD_STEP,
    # job -> must also build with XYG_REQUIRE_WASM=1 (every artifact must verify with
    # --require-wasm; the Pyodide wheel's build happens inside cibuildwheel).
    distributions: Optional[dict[str, bool]] = None,
) -> None:
    """One producer, explicit consumers, early verification (#1005, §33)."""
    if distributions is None:
        distributions = {"wheels": True, "sdist": True}
    producer = jobs.get(producer_name)
    if producer is None:
        errors.append(f"{label} workflow missing the single WASM producer job {producer_name}")
        return
    for needle in (
        "npm run build:wasm",
        "node js/build.mjs",
        "scripts/verify_wasm_assets.py",
        "actions/upload-artifact@",
        f"name: {WASM_ARTIFACT}",
        "if-no-files-found: error",
        "cargo tree -p xyg-wasm --target wasm32-unknown-unknown",
        "packages/xy-client/dist/xyg-wasm.wasm",
        "python/xyg/static/xyg-wasm.manifest.json",
    ):
        if needle not in producer:
            errors.append(f"{label} {producer_name} producer missing {needle!r}")
    _require_step_runs_exactly(
        errors,
        producer,
        "Build raw browser adapter without raster or PNG",
        "exact fail-closed wasm32 build and dependency evidence commands",
        "set -euo pipefail",
        "cargo build -p xyg-wasm --release --target wasm32-unknown-unknown",
        "cargo tree -p xyg-wasm --target wasm32-unknown-unknown | tee wasm-tree.txt",
        "test -s wasm-tree.txt",
        "if grep -Eq '(^| )png v' wasm-tree.txt; then",
        'echo "::error::direct-browser xyg-wasm unexpectedly enables native PNG"',
        "exit 1",
        "fi",
    )
    _require_step_runs_exactly(
        errors,
        producer,
        "Build static worker and package WASM artifact",
        "worker build, packaging contract tests, then the single packaging command",
        "npm ci",
        "node js/build.mjs",
        "node --test js/test/package-wasm-contract.test.mjs js/test/package-wasm-manifest.test.mjs",
        "npm run build:wasm",
    )
    for key in ("if", "needs", "continue-on-error"):
        if _has_yaml_key(producer, key, indent=4):
            errors.append(f"{label} {producer_name} producer must not use job-level {key!r}")
    if any(
        _has_yaml_key(block, "continue-on-error", indent=8)
        for block in _step_sequence_blocks(producer)
    ):
        errors.append(f"{label} {producer_name} producer steps must not use continue-on-error")
    for name, block in sorted(jobs.items()):
        if name == producer_name:
            continue
        for command in sorted(
            {c for c in map(_runs_wasm_producer, _active_run_lines(block)) if c is not None}
        ):
            errors.append(f"{label} job {name!r} must consume wasm-assets, not run {command!r}")
    for name in consumers:
        block = jobs.get(name, "")
        values, unsafe = _direct_yaml_key_values(block, "needs", indent=4)
        needed = {item.strip() for item in (values[0] if values else "").strip("[]").split(",")}
        if unsafe or producer_name not in needed:
            errors.append(f"{label} WASM consumer {name!r} must list {producer_name} in needs")
        steps = _named_step_blocks(block)
        order = list(steps)
        download = steps.get(download_step)
        verify = steps.get(WASM_VERIFY_STEP)
        if download is None or verify is None:
            errors.append(
                f"{label} WASM consumer {name!r} must download then verify the packaged WASM assets"
            )
            continue
        if order.index(download_step) > order.index(WASM_VERIFY_STEP):
            errors.append(f"{label} WASM consumer {name!r} must download before it verifies")
        # wasm-worker.js is not in the artifact; only the client build creates it, so the
        # build must run before the verifier (a clean checkout would otherwise fail every
        # time: tests/test_verify_wasm_assets.py reconstructs this per consumer).
        built = any(
            "node js/build.mjs" in line
            for step_name in order[: order.index(WASM_VERIFY_STEP)]
            for line in _step_run_lines(steps[step_name])
        )
        if not built:
            errors.append(
                f"{label} WASM consumer {name!r} must run node js/build.mjs before verifying "
                "(wasm-worker.js is built, not downloaded)"
            )
        for needle in ("actions/download-artifact@", f"name: {WASM_ARTIFACT}"):
            if needle not in download:
                errors.append(f"{label} WASM consumer {name!r} download step missing {needle!r}")
        if "verify_wasm_assets.py" not in verify:
            errors.append(
                f"{label} WASM consumer {name!r} verify step must run verify_wasm_assets.py"
            )
        if any(
            _has_yaml_key(step, key, indent=8)
            for step in (download, verify)
            for key in ("if", "continue-on-error")
        ):
            errors.append(f"{label} WASM consumer {name!r} asset steps must be unconditional")
    for name, needs_env in distributions.items():
        block = jobs.get(name, "")
        if (needs_env and 'XYG_REQUIRE_WASM: "1"' not in block) or "--require-wasm" not in block:
            errors.append(
                f"{label} {name} job must build with XYG_REQUIRE_WASM and verify --require-wasm"
                if needs_env
                else f"{label} {name} job must verify --require-wasm"
            )


def _active_run_lines(job_text: str) -> list[str]:
    """Every shell command of every ``run:`` step in a job.

    Backslash-continued lines are joined and a folded ``run: >`` scalar becomes one
    command, so the single-producer guard sees what the shell sees.
    """
    lines: list[str] = []
    for step in _step_sequence_blocks(job_text):
        commands, analyzable = _step_run_commands(step)
        lines.extend(commands if analyzable else [" ".join(commands)])
    return lines


RELEASE_CONDITION = (
    "github.event_name != 'pull_request' || "
    "needs.release_surface_changes.outputs.required == 'true'"
)
CI_CONCURRENCY_GROUP = (
    "ci-${{ github.event_name == 'pull_request' && github.ref || github.run_id }}"
)
MAIN_EVIDENCE_CONDITION = "github.event_name == 'push' || github.event_name == 'workflow_dispatch'"
AGGREGATE_STATUS_NAME = "Release surfaces"
# (event, classifier result) combinations CI can produce. Non-PR events always classify
# as required (the classifier step short-circuits), so there is no (push, False) case.
AGGREGATE_SCENARIOS = (
    ("pull_request", False),
    ("pull_request", True),
    ("merge_group", True),
    ("push", True),
    ("workflow_dispatch", True),
)


def _job_runs(if_values: list[str], *, event: str, required: bool) -> Optional[bool]:
    """Evaluate the only ``if`` forms the contract permits; None for anything else."""
    if not if_values:
        return True
    expression = if_values[0]
    if expression == RELEASE_CONDITION:
        return event != "pull_request" or required
    if expression in (MAIN_EVIDENCE_CONDITION, f"always() && ({MAIN_EVIDENCE_CONDITION})"):
        return event in release_inventory.MAIN_EVIDENCE_EVENTS
    return None


def _aggregate_arguments(job_text: str) -> tuple[dict[str, str], list[str], list[str]]:
    """Parse the aggregate step: (job -> needs reference, event refs, required refs)."""
    run = "\n".join(
        line
        for step in _step_sequence_blocks(job_text)
        for line in _step_run_lines(step)
        if "verify_release_surface_results.py" in " ".join(_step_run_lines(step))
    )
    jobs = {
        name: ref
        for name, ref in re.findall(
            r'--job "([a-z_0-9]+)=\$\{\{ needs\.([a-z_0-9]+)\.result \}\}"', run
        )
    }
    events = re.findall(r'--event "\$\{\{ (github\.event_name) \}\}"', run)
    required = re.findall(
        r'--required "\$\{\{ (needs\.release_surface_changes\.outputs\.required) \}\}"', run
    )
    return jobs, events, required


def _require_release_aggregate_contract(errors: list[str], jobs: dict[str, str], text: str) -> None:
    """The hard/advisory boundary: one aggregate observes exactly the applicable hard jobs."""
    inventory = release_inventory
    # 1. Classification is total: a job is hard, support, or explicitly advisory.
    known = set(inventory.HARD_JOBS) | set(inventory.SUPPORT_JOBS) | set(inventory.ADVISORY_CI_JOBS)
    for name in sorted(set(jobs) - known):
        errors.append(
            f"CI job {name!r} is neither a hard release gate nor listed advisory; classify it in "
            "scripts/verify_release_surface_results.py"
        )
    # 2. Advisory work cannot hide inside a hard workflow: no continue-on-error anywhere.
    if any(re.match(r"\s*(?:- )?continue-on-error\s*:", line) for line in _yaml_code_lines(text)):
        errors.append("CI workflow must not use continue-on-error; advisory work is scheduled")
    # 3. The aggregate depends on exactly the classifier plus every hard job.
    aggregate = jobs.get("release_surfaces", "")
    values, unsafe = _direct_yaml_key_values(aggregate, "needs", indent=4)
    needs = _yaml_list_items(aggregate, "needs")
    expected = {"release_surface_changes", *inventory.HARD_JOBS}
    if unsafe or needs is None or set(needs) != expected or len(needs) != len(set(needs)):
        errors.append(
            "CI Release surfaces must need exactly the classifier and every hard job: "
            f"expected {sorted(expected)}, found {sorted(needs or [])}"
        )
    # 4. The aggregate command passes each hard job's own result, the event, and the classifier.
    passed, events, required_refs = _aggregate_arguments(aggregate)
    if set(passed) != set(inventory.HARD_JOBS) or any(name != ref for name, ref in passed.items()):
        errors.append(
            "CI Release surfaces must pass --job NAME=${{ needs.NAME.result }} for every hard job: "
            f"expected {sorted(inventory.HARD_JOBS)}, found {sorted(passed)}"
        )
    if events != ["github.event_name"] or required_refs != [
        "needs.release_surface_changes.outputs.required"
    ]:
        errors.append("CI Release surfaces must pass --event and the classifier --required output")
    # 5. Applicability in the aggregate equals what the workflow actually runs.
    for event, required in AGGREGATE_SCENARIOS:
        runs: set[str] = set()
        for name in inventory.HARD_JOBS:
            if_values, if_unsafe = _direct_yaml_key_values(jobs.get(name, ""), "if", indent=4)
            outcome = None if if_unsafe else _job_runs(if_values, event=event, required=required)
            if outcome is None:
                errors.append(f"CI hard job {name!r} uses an unrecognized if condition")
                break
            if outcome:
                runs.add(name)
        else:
            applicable = inventory.applicable_jobs(event=event, required=required)
            if runs != applicable:
                errors.append(
                    f"CI aggregate applicability for {event} (required={required}) differs from "
                    f"the jobs the workflow runs: aggregate-only {sorted(applicable - runs)}, "
                    f"workflow-only {sorted(runs - applicable)}"
                )
    # 6. Propagation self-test: an injected failure in the real job set fails the aggregate.
    if set(passed) == set(inventory.HARD_JOBS):
        errors.extend(_aggregate_propagation_errors(passed))


def _yaml_list_items(job_text: str, key: str) -> Optional[list[str]]:
    """Items of a job-level ``key:`` given as an inline ``[a, b]`` or a block sequence."""
    lines = job_text.splitlines()
    for index, line in enumerate(lines):
        match = re.fullmatch(rf"    {re.escape(key)}:\s*(.*?)\s*", line)
        if match is None:
            continue
        value = match.group(1)
        if value.startswith("["):
            return [item.strip() for item in value.strip("[]").split(",") if item.strip()]
        if value:
            return [value]
        items: list[str] = []
        for following in lines[index + 1 :]:
            item = re.fullmatch(r"      - ([a-z_0-9]+)\s*", following)
            if item is None:
                break
            items.append(item.group(1))
        return items
    return None


def _aggregate_propagation_errors(passed: dict[str, str]) -> list[str]:
    """Drive the real aggregate script logic with injected failures for every job class."""
    errors: list[str] = []
    verify = release_inventory.verify
    for event, required in AGGREGATE_SCENARIOS:
        applicable = release_inventory.applicable_jobs(event=event, required=required)
        green = {name: ("success" if name in applicable else "skipped") for name in passed}
        label = f"{event} required={required}"
        if verify(required=required, results=green, event=event):
            errors.append(f"CI aggregate rejects a fully green {label} run")
        for name in sorted(passed):
            for result in ("failure", "cancelled") + (("skipped",) if name in applicable else ()):
                if not verify(required=required, results={**green, name: result}, event=event):
                    errors.append(
                        f"CI aggregate accepts {name}={result} on {label}; injected "
                        "failures must fail Release surfaces"
                    )
        for name in sorted(passed):
            if (
                verify(
                    required=required,
                    results={k: v for k, v in green.items() if k != name},
                    event=event,
                )
                == []
            ):
                errors.append(f"CI aggregate accepts a missing result for {name} on {label}")
    return errors


def validate_merge_queue_ruleset(path: Path = DEFAULT_RULESET) -> list[str]:
    """The checked-in ruleset must keep the lean one-aggregate queue contract."""
    try:
        ruleset = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"cannot read merge-queue ruleset {path}: {exc}"]
    errors: list[str] = []
    if ruleset.get("target") != "branch" or ruleset.get("enforcement") != "active":
        errors.append("merge-queue ruleset must be an active branch ruleset")
    ref_name = (ruleset.get("conditions") or {}).get("ref_name") or {}
    if ref_name.get("include") != ["refs/heads/main"] or ref_name.get("exclude") != []:
        errors.append("merge-queue ruleset must target exactly refs/heads/main")
    rules = ruleset.get("rules") or []
    queues = [rule for rule in rules if rule.get("type") == "merge_queue"]
    if len(queues) != 1:
        errors.append("merge-queue ruleset must define exactly one merge_queue rule")
    elif queues[0].get("parameters") != MERGE_QUEUE_PARAMETERS:
        errors.append(
            f"merge-queue ruleset parameters must be {MERGE_QUEUE_PARAMETERS}, "
            f"found {queues[0].get('parameters')}"
        )
    for rule in rules:
        if rule.get("type") == "merge_queue":
            continue
        # One lean required aggregate, no duplicate required statuses.
        contexts = [
            check.get("context")
            for check in (rule.get("parameters") or {}).get("required_status_checks", [])
        ]
        if rule.get("type") != "required_status_checks" or contexts != [AGGREGATE_STATUS_NAME]:
            errors.append(
                f"merge-queue ruleset may only add the single {AGGREGATE_STATUS_NAME!r} "
                f"required status; found {rule.get('type')} {contexts}"
            )
    return errors


MERGE_QUEUE_PARAMETERS = {
    "check_response_timeout_minutes": 240,
    "grouping_strategy": "ALLGREEN",
    "max_entries_to_build": 1,
    "max_entries_to_merge": 1,
    "merge_method": "SQUASH",
    "min_entries_to_merge": 1,
    "min_entries_to_merge_wait_minutes": 5,
}


def validate_live_readback(
    fetch: Callable[[str], object], ruleset_path: Path = DEFAULT_RULESET
) -> list[str]:
    """Compare live GitHub ruleset and branch protection with the checked-in contract.

    ``fetch`` maps a ``repos/{owner}/{repo}``-relative API path to decoded JSON; it is
    injected so the comparison is testable offline (``--live-readback`` wires ``gh api``).
    """
    errors: list[str] = []
    local = json.loads(ruleset_path.read_text(encoding="utf-8"))
    summaries = fetch("rulesets")
    matches = [
        item
        for item in summaries
        if isinstance(item, dict) and item.get("name") == local.get("name")
    ]
    if len(matches) != 1:
        return [f"live repository must have exactly one ruleset named {local.get('name')!r}"]
    live = fetch(f"rulesets/{matches[0]['id']}")
    if not isinstance(live, dict):
        return ["live ruleset read-back is not an object"]
    for key in ("name", "target", "enforcement", "conditions"):
        if live.get(key) != local.get(key):
            errors.append(f"live ruleset {key} {live.get(key)!r} differs from checked-in file")
    if live.get("rules") != local.get("rules"):
        errors.append("live ruleset rules differ from .github/merge-queue-ruleset.json")
    protection = fetch("branches/main/protection")
    contexts = (
        (protection.get("required_status_checks") or {}).get("contexts")
        if isinstance(protection, dict)
        else None
    )
    if contexts != [AGGREGATE_STATUS_NAME]:
        errors.append(
            f"live branch protection must require only {AGGREGATE_STATUS_NAME!r}, found {contexts}"
        )
    return errors


def _gh_api_fetch(repo: str) -> Callable[[str], object]:
    def fetch(path: str) -> object:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/{path}"], capture_output=True, text=True, check=True
        )
        return json.loads(result.stdout)

    return fetch


def _code_outside_literals(command: str) -> str:
    """Shell code with quoted literals and comments removed.

    Single-quoted text is literal; double-quoted text is literal except for ``$(...)``
    command substitutions, whose pipes are real (``x="$(a | b)"`` pipes ``a`` into ``b``).
    """
    out: list[str] = []
    i, n = 0, len(command)
    while i < n:
        char = command[i]
        if char == "\\":
            i += 2
        elif char == "'":
            end = command.find("'", i + 1)
            i = n if end < 0 else end + 1
        elif char == '"':
            i += 1
            while i < n and command[i] != '"':
                if command[i] == "\\":
                    i += 2
                elif command.startswith("$(", i):
                    depth, j = 1, i + 2
                    while j < n and depth:
                        depth += (command[j] == "(") - (command[j] == ")")
                        j += 1
                    out.append(" " + command[i + 2 : j - 1] + " ")
                    i = j
                else:
                    i += 1
            i += 1
        elif char == "#" and (i == 0 or command[i - 1].isspace()):
            break
        else:
            out.append(char)
            i += 1
    return "".join(out)


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_]\w*)\1")
_PIPE = re.compile(r"(?<!\|)\|(?!\|)")
_PIPEFAIL_ON = re.compile(r"set\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*o\s+pipefail\b")
_PIPEFAIL_OFF = re.compile(r"set\s+(?:-[A-Za-z]+\s+)*\+[A-Za-z]*o\s+pipefail\b")


def _step_label(step: str) -> str:
    """A step's name, or its first line for an unnamed (``- run:``/``- uses:``) step."""
    first = _strip_yaml_comment(step.splitlines()[0])
    match = re.match(r"^      - name:\s*(.+?)\s*$", first)
    return match.group(1) if match is not None else first.strip()


def _heredoc_delimiter(command: str) -> Optional[str]:
    """The terminator of a heredoc this command opens, if any.

    Only a ``<<`` in plain shell code opens one: not inside quotes (``echo "use <<EOF"``,
    ``python -c 'print(1<<n)'``), not a ``<<<`` here-string, and not inside an arithmetic
    context (``$((x << n))``, ``((x << n))``).
    """
    i, n = 0, len(command)
    while i < n:
        char = command[i]
        if char == "\\":
            i += 2
        elif char in "'\"":
            j = i + 1
            while j < n and command[j] != char:
                j += 2 if char == '"' and command[j] == "\\" else 1
            i = j + 1
        elif char == "#" and (i == 0 or command[i - 1].isspace()):
            return None
        elif command.startswith("$((", i) or (
            command.startswith("((", i) and (i == 0 or command[i - 1] in " \t;&|(")
        ):
            depth, j = 0, i + (command[i] == "$")
            while j < n:
                depth += (command[j] == "(") - (command[j] == ")")
                j += 1
                if depth == 0:
                    break
            i = j
        elif command.startswith("<<", i) and not command.startswith("<<<", i):
            if i > 0 and command[i - 1] == "<":
                i += 2
                continue
            match = _HEREDOC.match(command, i)
            if match is not None:
                return match.group(2)
            i += 2
        else:
            i += 1
    return None


def _step_run_commands(step: str) -> tuple[list[str], bool]:
    """Logical shell commands of one step's ``run`` plus whether they could be analyzed.

    Handles the named form (``run`` at indent 8) and the unnamed ``- run:`` form (indent 6),
    literal blocks (``|``, ``|-``, ``|+``, indentation indicators), and joins
    backslash-continued lines. A folded scalar (``>``/``>-``) is returned unanalyzable
    because folding rewrites line structure.
    """
    lines = step.splitlines()
    for index, line in enumerate(lines):
        match = re.fullmatch(r"(?:        |      - )run:\s*(.*?)\s*", line)
        if match is None:
            continue
        value = match.group(1)
        block = re.fullmatch(r"([|>])[+-]?\d*[+-]?", value)
        if block is None:
            # A quoted YAML scalar is parsed (escapes, folding) before the shell sees it,
            # so fail closed rather than guess what the shell receives.
            if value[:1] in ("'", '"'):
                return [value], False
            return ([value] if value and not value.startswith("#") else []), True
        body: list[str] = []
        for following in lines[index + 1 :]:
            if following.strip() and len(following) - len(following.lstrip()) <= 8:
                break
            body.append(following.strip())
        if block.group(1) == ">":
            return body, False
        logical: list[str] = []
        pending = ""
        for command in body:
            if not command or command.startswith("#"):
                continue
            if command.endswith("\\"):
                pending += command[:-1] + " "
                continue
            logical.append(pending + command)
            pending = ""
        if pending:
            logical.append(pending)
        return logical, True
    return [], True


def _pipe_lines(commands: list[str]) -> list[str]:
    """Commands that contain a shell pipe (outside quotes, heredoc bodies, and ``||``)."""
    piped: list[str] = []
    heredoc_end: Optional[str] = None
    for command in commands:
        if heredoc_end is not None:
            if command.strip() == heredoc_end:
                heredoc_end = None
            continue
        if _PIPE.search(_code_outside_literals(command)):
            piped.append(command)
        heredoc_end = _heredoc_delimiter(command)
    return piped


def _default_shell(text: str, job: str) -> Optional[str]:
    """The shell inherited from ``defaults.run.shell`` (job first, then workflow)."""
    for source, indent in ((job, "    "), (text, "")):
        match = re.search(
            rf"^{indent}defaults:\n{indent}  run:\n(?:{indent}    [^\n]*\n)*?{indent}    shell:[ \t]*([^\n]*)",
            source,
            re.M,
        )
        if match is not None:
            # Whole value (comment stripped): `bash -e {0}` is not `bash`.
            return re.sub(r"\s+#.*$", "", match.group(1)).strip().strip("'\"")
    return None


def _require_pipefail_for_piped_steps(errors: list[str], text: str, label: str) -> None:
    """A piped ``run`` step must fail when its first command fails (#1008).

    GitHub's default ``bash -e`` has no ``pipefail``, so ``bench.py | tee report.md`` would
    report tee's success and mask a crashing benchmark. The effective shell must be ``bash``
    (GitHub runs it as ``bash -eo pipefail``) or the step must enable ``set -o pipefail`` as
    a statement before the pipe; ``set +o pipefail`` turns it off again. Folded ``run: >``
    scalars containing a pipe cannot be analyzed and fail closed.
    """
    for job_name, job in _job_blocks(text).items():
        for step in _step_sequence_blocks(job):
            commands, analyzable = _step_run_commands(step)
            name = step.splitlines()[0].strip()
            if not analyzable:
                if any("|" in command for command in commands):
                    errors.append(
                        f"{label} job {job_name!r} step {name!r} pipes inside a folded or quoted "
                        "`run` scalar the pipefail check cannot analyze; use a literal "
                        "`run: |` block"
                    )
                continue
            shell_values, shell_unsafe = _step_direct_key_values(step, "shell")
            shell = (
                None
                if shell_unsafe
                else (shell_values[0] if shell_values else _default_shell(text, job))
            )
            enabled = shell == "bash"
            heredoc_end: Optional[str] = None
            for command in commands:
                if heredoc_end is not None:
                    if command.strip() == heredoc_end:
                        heredoc_end = None
                    continue
                stripped = command.strip()
                if _PIPEFAIL_ON.match(stripped):
                    enabled = True
                elif _PIPEFAIL_OFF.match(stripped):
                    enabled = False
                if _pipe_lines([command]) and not enabled:
                    errors.append(
                        f"{label} job {job_name!r} step {name!r} pipes a command without pipefail; "
                        f"add `shell: bash` or `set -o pipefail` before it ({stripped!r})"
                    )
                    break
                heredoc_end = _heredoc_delimiter(command)
            if heredoc_end is not None:
                errors.append(
                    f"{label} job {job_name!r} step {name!r} ends inside a heredoc "
                    f"(missing terminator {heredoc_end!r}); the pipefail check cannot analyze it"
                )


def validate_ci_workflow(path: Path = DEFAULT_CI_WORKFLOW) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read CI workflow {path}: {exc}"]

    jobs = _job_blocks(text)
    errors: list[str] = validate_milestone_governance()
    _require_unique_workflow_structure(errors, text, "CI", REQUIRED_CI_JOBS)
    _require_pipefail_for_piped_steps(errors, text, "CI")
    if _has_yaml_key(text, "defaults", indent=0):
        errors.append("CI workflow must not override the shell for hard-gate run steps")
    if _has_yaml_key(text, "env", indent=0):
        errors.append("CI workflow must not set a top-level environment for hard-gate jobs")
    if _has_shell_init_environment(text):
        errors.append("CI workflow must not set shell-init environment variables")
    _require_trigger_with_direct_option(errors, text, "CI", "push", "branches", '["main"]')
    pull_request = _workflow_trigger_block(text, "pull_request")
    if pull_request is None:
        errors.append("CI workflow must run for every pull request")
    elif _direct_yaml_key_count(pull_request, "paths", indent=4) or _direct_yaml_key_count(
        pull_request, "paths-ignore", indent=4
    ):
        errors.append("CI pull_request trigger must not use path filters")
    merge_group = _workflow_trigger_block(text, "merge_group")
    if merge_group is None:
        errors.append("CI workflow must report required checks for merge_group events")
    else:
        types_values, types_unsafe = _direct_yaml_key_values(merge_group, "types", indent=4)
        if types_unsafe or types_values != ["[checks_requested]"]:
            errors.append("CI merge_group trigger must handle checks_requested")
    concurrency = _unique_mapping_block(text, "concurrency", indent=0)
    cancel_values, cancel_unsafe = _direct_yaml_key_values(
        concurrency or "", "cancel-in-progress", indent=2
    )
    if cancel_unsafe or cancel_values != ["${{ github.event_name == 'pull_request' }}"]:
        errors.append(
            "CI must cancel only superseded pull_request runs: in-flight required "
            "merge_group checks and push runs on main must complete"
        )
    group_values, group_unsafe = _direct_yaml_key_values(concurrency or "", "group", indent=2)
    if group_unsafe or group_values != [CI_CONCURRENCY_GROUP]:
        errors.append(
            "CI concurrency group must be per run for every event except pull_request "
            f"({CI_CONCURRENCY_GROUP}): GitHub replaces an older pending run in a shared "
            "group even when cancel-in-progress is false, dropping a main push or merge-group run"
        )
    _require_unshallow_checkouts(errors, text, "CI")
    missing_jobs = sorted(REQUIRED_CI_JOBS - set(jobs))
    if missing_jobs:
        errors.append(f"CI workflow missing required jobs: {missing_jobs}")
    for job_name in sorted(PR_REQUIRED_CI_JOBS):
        values, unsafe = _direct_yaml_key_values(jobs.get(job_name, ""), "if", indent=4)
        if unsafe or values:
            errors.append(f"CI PR-required job {job_name!r} must run unconditionally")
    classifier_if, classifier_if_unsafe = _direct_yaml_key_values(
        jobs.get("release_surface_changes", ""), "if", indent=4
    )
    if classifier_if_unsafe or classifier_if:
        errors.append("CI release-surface classifier must run unconditionally")
    aggregate_if, aggregate_if_unsafe = _direct_yaml_key_values(
        jobs.get("release_surfaces", ""), "if", indent=4
    )
    if aggregate_if_unsafe or aggregate_if != ["always()"]:
        errors.append("CI Release surfaces aggregate must use if: always()")
    release_condition = (
        "github.event_name != 'pull_request' || "
        "needs.release_surface_changes.outputs.required == 'true'"
    )
    for job_name in sorted(RELEASE_SURFACE_CONDITIONAL_JOBS):
        values, unsafe = _direct_yaml_key_values(jobs.get(job_name, ""), "if", indent=4)
        if unsafe or values != [release_condition]:
            errors.append(f"CI release-surface job {job_name!r} must use the classifier condition")
        if "release_surface_changes" not in jobs.get(job_name, ""):
            errors.append(f"CI release-surface job {job_name!r} must depend on the classifier")
    for job_name in sorted(MAIN_ONLY_CI_JOBS):
        values, unsafe = _direct_yaml_key_values(jobs.get(job_name, ""), "if", indent=4)
        expected = (
            "always() && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')"
            if job_name == "benchmark"
            else "github.event_name == 'push' || github.event_name == 'workflow_dispatch'"
        )
        if unsafe or values != [expected]:
            errors.append(f"CI breadth job {job_name!r} must run only outside pull_request events")

    _require_job_contains(
        errors,
        jobs,
        "release_surface_changes",
        "CI",
        "release-surface change classifier",
        "scripts/classify_release_surface.py",
        "github.event.pull_request.base.sha",
        "github.event.pull_request.head.sha",
        'git show "$base:scripts/classify_release_surface.py"',
        'python3 -I "$classifier"',
        "GITHUB_OUTPUT",
    )
    _require_release_classifier_structure(errors, jobs.get("release_surface_changes", ""))
    _require_step_runs_exactly(
        errors,
        jobs.get("release_surface_changes", ""),
        "Classify changed paths",
        "trusted-base release-surface classifier execution",
        'if [ "${{ github.event_name }}" != "pull_request" ]; then',
        'echo "required=true" >> "$GITHUB_OUTPUT"',
        "else",
        'base="${{ github.event.pull_request.base.sha }}"',
        'head="${{ github.event.pull_request.head.sha }}"',
        'classifier="$RUNNER_TEMP/classify_release_surface.py"',
        'changed="$RUNNER_TEMP/release-surface-paths.txt"',
        'git -c core.quotePath=true diff --name-only "$base" "$head" > "$changed"',
        'if grep -q \'^"\' "$changed"; then',
        'echo "required=true" >> "$GITHUB_OUTPUT"',
        'elif git show "$base:scripts/classify_release_surface.py" > "$classifier"; then',
        'python3 -I "$classifier" --github-output "$GITHUB_OUTPUT" < "$changed"',
        "else",
        'echo "required=true" >> "$GITHUB_OUTPUT"',
        "fi",
        "fi",
        allowed_shell="bash",
        required_id="classify",
        forbid_environment=True,
    )
    _require_job_contains(
        errors,
        jobs,
        "authored_scene",
        "CI",
        "pre-merge four-tier authored Scene parity",
        "packages/xy-node/scripts/generate_authored_scene_benchmark.mjs",
        "scripts/generate_authored_scene_benchmark.py",
        "scripts/verify_authored_scene_artifacts.py",
        "XYG_NATIVE_LIB: ${{ github.workspace }}/target/release/libxyg_core.so",
    )
    _require_job_contains(
        errors,
        jobs,
        "release_surfaces",
        "CI",
        "non-skippable aggregate Release surfaces status",
        "name: Release surfaces",
        "if: always()",
        "scripts/verify_release_surface_results.py",
        "needs.wheels.result",
        "needs.sdist.result",
        "needs.install_without_rust.result",
        "needs.authored_scene.result",
        "needs.browser_conformance.result",
    )
    _require_release_aggregate_contract(errors, jobs, text)

    _require_job_contains(
        errors,
        jobs,
        "matplotlib_reference",
        "CI",
        "released Matplotlib compatibility gates",
        "matplotlib==3.11.0",
        "matplotlib.__version__ == '3.11.0'",
        "scripts/sync_matplotlib_compat.py --check",
        "MPLBACKEND: Agg",
    )
    reference = jobs.get("matplotlib_reference", "")
    _require_step_runs_exactly(
        errors,
        reference,
        "Install XYG and released reference wheel",
        "released reference installation",
        "uv venv .venv",
        "uv pip install -p .venv/bin/python -e . --group dev",
        'uv pip install -p .venv/bin/python "matplotlib==3.11.0"',
        allow_job_gate=True,
    )
    _require_step_runs_exactly(
        errors,
        reference,
        "Verify released reference and reviewed snapshot",
        "version and snapshot checks",
        ".venv/bin/python -c \"import matplotlib; assert matplotlib.__version__ == '3.11.0'\"",
        ".venv/bin/python scripts/sync_matplotlib_compat.py --check",
        allow_job_gate=True,
    )
    _require_step_runs_exactly(
        errors,
        reference,
        "Run the full tests/pyplot suite against matplotlib 3.11.0",
        "reference test commands",
        ".venv/bin/pytest -q -rs tests/pyplot",
        allow_job_gate=True,
    )

    _require_job_contains(
        errors,
        jobs,
        "test",
        "CI",
        "hard production gates",
        "scripts/verify_ci_workflow.py",
        "scripts/check_public_api.py",
        "Install Node host bindings",
        "npm ci --prefix packages/xy-node",
        "scripts/verify_node_packages.py",
        "Node XYTS cross-host conformance",
        'export XYG_NATIVE_LIB="$GITHUB_WORKSPACE/target/release/libxyg_core.so"',
        "node --test packages/xy-node/test/xyts-conformance.test.mjs",
        "scripts/abi_smoke.py",
        "scripts/check_abi_parity.py",
        "scripts/gen_abi_manifest.py --check",
        "scripts/verify_ownership.py",
        "scripts/audit_host_parity_landing.py",
        "scripts/check_stale_names.py",
        "cargo test --workspace",
        "Verify bundled Reflex integration import",
        "importlib.metadata as m, reflex_xy",
        "assert reflex_xy.__version__ == m.version('xyg')",
        "ruff check .",
        "scripts/smoke_render.py",
        "Polar phase 6/7 live examples",
        "scripts/polar_phase7_smoke.py",
        "Browser lifecycle smoke",
        "Browser visual regression smoke",
        "Browser interaction stress smoke",
        "Browser dashboard reliability smoke",
        "scripts/reflex_lifecycle_smoke.py",
        "scripts/visual_regression_smoke.py",
        "scripts/interaction_stress_smoke.py",
        "benchmarks/bench_dashboard.py",
        "--chart-counts 10,20,50,60",
        "dashboard-smoke.json --kind dashboard-browser",
        "--sizes 1e5,1e6,1e7 --production --json scatter.json",
        "scripts/bench_native.py --sizes 1e6,1e7 --json kernel.json",
        "scripts/verify_benchmark_report.py scatter.json --kind scatter-native",
        "scripts/verify_benchmark_report.py kernel.json --kind kernel-native",
        "benchmarks/bench_transport.py --n 1e6 --reps 15",
        '--browser-reps 12 --chromium "$CHROME" --require-browser --json transport.json',
        "scripts/verify_benchmark_report.py transport.json --kind transport-loopback",
        "scripts/check_regressions.py --scatter scatter.json --kernel kernel.json",
        "--transport transport.json --emit-md spec/benchmarks/metrics.md",
        "Upload regression benchmark report",
        "if: always()",
        "actions/upload-artifact@",
        "regression-benchmark-report",
        "if-no-files-found: warn",
        "spec/benchmarks/metrics.md",
        "transport.json",
    )
    test_steps = _named_step_blocks(jobs.get("test", ""))
    regression_upload = test_steps.get("Upload regression benchmark report", "")
    regression_upload_if, regression_upload_if_unsafe = _step_direct_key_values(
        regression_upload, "if"
    )
    if regression_upload_if_unsafe or regression_upload_if != ["always()"]:
        errors.append("CI test job Upload regression benchmark report step must use if: always()")
    delegation_upload = test_steps.get("Upload executable host-delegation evidence", "")
    delegation_upload_if, delegation_upload_if_unsafe = _step_direct_key_values(
        delegation_upload, "if"
    )
    if delegation_upload_if_unsafe or delegation_upload_if != ["always()"]:
        errors.append(
            "CI test job Upload executable host-delegation evidence step must use if: always()"
        )
    _require_step_contains(
        errors,
        jobs.get("test", ""),
        "Upload executable host-delegation evidence",
        "deterministic delegation evidence artifact",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "host-delegation-${{ github.sha }}",
        "if-no-files-found: error",
        "target/host-delegation-report.json",
    )
    _require_step_runs_exactly(
        errors,
        jobs.get("test", ""),
        "Node XYTS cross-host conformance",
        "active native Node XYTS cross-host conformance",
        'export XYG_NATIVE_LIB="$GITHUB_WORKSPACE/target/release/libxyg_core.so"',
        "node --test packages/xy-node/test/xyts-conformance.test.mjs",
    )
    _require_step_runs_exactly(
        errors,
        jobs.get("test", ""),
        "Node host suite",
        "complete Node host suite against the shared native core",
        'export XYG_NATIVE_LIB="$GITHUB_WORKSPACE/target/release/libxyg_core.so"',
        "npm test --prefix packages/xy-node",
    )
    _require_step_runs_exactly(
        errors,
        jobs.get("test", ""),
        "Graph and chart-scale smoke gates",
        "graph/kernel ceilings, chart-scale and pyramid smoke coverage",
        'export XYG_NATIVE_LIB="$GITHUB_WORKSPACE/target/release/libxyg_core.so"',
        ".venv/bin/python benchmarks/bench_dual_host_graph.py --sizes 1000",
        ".venv/bin/python benchmarks/bench_parity_kernels.py --sizes 100000 --no-baseline",
        ".venv/bin/python benchmarks/bench_scale_all_charts.py --profile smoke",
        "node benchmarks/bench_scale_all_charts_node.mjs --profile smoke",
        ".venv/bin/python benchmarks/bench_tier3_pyramid.py",
        "node benchmarks/bench_tier3_pyramid_node.mjs",
    )
    _require_job_contains(
        errors,
        jobs,
        "test",
        "CI",
        "real packaged Rust/WASM tick assets for the full browser corpus",
        "toolchain: 1.96.0",
        "needs: wasm_assets",
        "scripts/verify_wasm_assets.py",
        "node --test packages/xy-node/test/painter-admission-wasm-parity.test.mjs",
    )
    _require_step_runs_exactly(
        errors,
        jobs.get("test", ""),
        "Benchmark methodology contract (smallest sizes, report verified)",
        "pre-merge execution of the methodology producers and their report verifier",
        'mkdir -p "$RUNNER_TEMP/bench-contract"',
        ".venv/bin/python benchmarks/bench_workflows.py --profile smoke --reps 1 "
        '--json "$RUNNER_TEMP/bench-contract/workflows.json"',
        '.venv/bin/python scripts/verify_benchmark_report.py "$RUNNER_TEMP/bench-contract/workflows.json" '
        "--kind workflow-native",
        '.venv/bin/python benchmarks/bench_line.py --sizes 1e4,1e5 --json "$RUNNER_TEMP/bench-contract/line.json"',
        '.venv/bin/python scripts/verify_benchmark_report.py "$RUNNER_TEMP/bench-contract/line.json" '
        "--kind line-decimation",
        '.venv/bin/python benchmarks/bench_install.py --packages xyg --json "$RUNNER_TEMP/bench-contract/install.json"',
        '.venv/bin/python scripts/verify_benchmark_report.py "$RUNNER_TEMP/bench-contract/install.json" '
        "--kind install-footprint",
    )
    _require_step_runs_exactly(
        errors,
        jobs.get("test", ""),
        "Native benchmark oracles (divan --test, no timing)",
        "pull-request execution of every Rust benchmark body and its assertions",
        "cargo bench -p xyg-engine --bench kernels -- --test",
        "cargo bench -p xyg-wasm --bench aggregate -- --test",
        "cargo bench -p xyg-wasm --bench typed_series -- --test",
    )
    _require_step_runs_exactly(
        errors,
        jobs.get("test", ""),
        "CodSpeed benchmark oracles (pytest, no timing)",
        "pull-request execution of every CodSpeed pytest body without --codspeed",
        ".venv/bin/python -m pytest benchmarks/test_codspeed_*.py -q",
    )
    # Hard but last: a stale oracle must not skip every other `test` result behind it.
    final_steps = [_step_label(block) for block in _step_sequence_blocks(jobs.get("test", ""))][-2:]
    if final_steps != [
        "Native benchmark oracles (divan --test, no timing)",
        "CodSpeed benchmark oracles (pytest, no timing)",
    ]:
        errors.append(
            "CI test job benchmark oracles must be its final two steps so a stale oracle "
            "cannot hide the other test results"
        )
    _require_step_runs_exactly(
        errors,
        jobs.get("test", ""),
        "Build JS client",
        "JS Worker build ahead of the verified packaged WASM payload for the full browser corpus",
        "node js/build.mjs",
    )
    _require_job_contains(
        errors,
        jobs,
        "wasm_foundation",
        "CI",
        "direct-browser Rust/WASM foundation",
        "wasm32-unknown-unknown",
        "toolchain: 1.96.0",
        "persist-credentials: false",
        "python3 scripts/gen_wasm_abi.py --check",
        "cargo test -p xyg-wasm",
        "node js/build.mjs",
        "needs: wasm_assets",
        "npx playwright install chromium",
        "node scripts/wasm_foundation_smoke.mjs",
        "direct-browser-wasm-foundation",
        "packages/xy-client/dist/xyg-wasm.wasm",
        "packages/xy-client/dist/wasm-worker.js",
    )
    wasm_job = jobs.get("wasm_foundation", "")
    _require_step_runs_exactly(
        errors,
        wasm_job,
        "Install Chromium",
        "active bounded browser-only Playwright install without apt",
        "npx playwright install chromium",
    )
    _require_step_contains(
        errors,
        wasm_job,
        "Install Chromium",
        "bounded Chromium install timeout",
        "timeout-minutes: 10",
    )
    _require_step_runs_exactly(
        errors,
        wasm_job,
        "Strict-CSP local-only lifecycle smoke",
        "active strict-CSP lifecycle command",
        "node scripts/wasm_foundation_smoke.mjs",
    )
    _require_step_contains(
        errors,
        wasm_job,
        "Strict-CSP local-only lifecycle smoke",
        "bounded lifecycle timeout",
        "timeout-minutes: 10",
    )
    test_job = jobs.get("test", "")
    density_pr_steps = [
        step
        for step in _step_sequence_blocks(test_job)
        if _step_direct_key_values(step, "name")[0]
        == ["Density end-to-end harness contract (small scale only)"]
    ]
    if len(density_pr_steps) != 1:
        errors.append("CI test job must contain exactly one small-scale density contract step")
    elif _step_direct_keys(density_pr_steps[0]) != (["name", "run"], False):
        errors.append("CI small-scale density contract step must use only name and run")
    _require_step_runs_exactly(
        errors,
        test_job,
        "Density end-to-end harness contract (small scale only)",
        "exact PR-only 250k density journey and report verification",
        "CHROME=$(node -e 'process.stdout.write(require(\"playwright\").chromium.executablePath())')",
        ".venv/bin/python benchmarks/bench_density_e2e.py \\",
        '--points 250000 --chrome "$CHROME" \\',
        "--timeout 180 --max-rss-gib 4 --max-disk-gib 1 \\",
        '--output "$RUNNER_TEMP/density-e2e-pr.json"',
        "python3 scripts/verify_density_e2e_report.py \\",
        '"$RUNNER_TEMP/density-e2e-pr.json" --sha "$GITHUB_SHA"',
        forbid_environment=True,
    )
    _require_step_runs_exactly(
        errors,
        test_job,
        "Graph scale harness contract (small and medium tiers)",
        "exact PR-only graph scale smoke profile and SHA-linked report verification (#33)",
        "CHROME=$(node -e 'process.stdout.write(require(\"playwright\").chromium.executablePath())')",
        ".venv/bin/python benchmarks/bench_graph_scale.py --profile smoke \\",
        '--chromium "$CHROME" --out "$RUNNER_TEMP/graph-scale-pr.json"',
        ".venv/bin/python scripts/verify_benchmark_report.py \\",
        '"$RUNNER_TEMP/graph-scale-pr.json" --kind graph-scale --expect-commit "$GITHUB_SHA"',
        forbid_environment=True,
    )
    _require_step_runs_exactly(
        errors,
        test_job,
        "Generated ABI artifacts (stdlib only)",
        "ABI artifact freshness check",
        "python3 scripts/gen_abi_manifest.py --check",
    )
    _require_step_runs_exactly(
        errors,
        test_job,
        "Install package + dev deps",
        "locked Reflex development environment carrying the pytest-codspeed plugin",
        "uv sync --locked --extra reflex --group dev --group codspeed",
    )
    _require_step_contains(
        errors,
        test_job,
        "Install Chromium (Playwright)",
        "bounded browser-only Playwright install without apt",
        "timeout-minutes: 10",
        "npx playwright install chromium",
    )
    _require_job_contains(
        errors,
        jobs,
        "browser_conformance",
        "CI",
        "accessibility and three-engine conformance gate",
        'node-version: "22"',
        "npm ci",
        "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
        "~/.cache/ms-playwright",
        "playwright-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('package-lock.json') }}",
        "npx playwright install chromium firefox webkit",
        "node js/build.mjs",
        "node scripts/browser_conformance.mjs",
    )
    _require_step_contains(
        errors,
        jobs.get("browser_conformance", ""),
        "Install Playwright browser engines",
        "bounded browser-only three-engine install without apt",
        "timeout-minutes: 15",
        "npx playwright install chromium firefox webkit",
    )
    _require_step_contains(
        errors,
        jobs.get("browser_conformance", ""),
        "Install WebKit runtime libraries",
        "bounded Blacksmith-only WebKit dependency install",
        "id: webkit-deps",
        "timeout-minutes: 20",
        "npx playwright install-deps webkit",
        # apt's needrestart hook hangs after the install; keep it list-only.
        "$nrconf{restart} = 'l';",
        # The slow mirror: keep, seed, prune, and copy back the cached .debs,
        # and report whether the package set changed.
        'APT::Keep-Downloaded-Packages "true";',
        'sudo cp "$HOME"/.cache/xyg-webkit-debs/*.deb /var/cache/apt/archives/',
        "sudo apt-get autoclean -y",
        "cp /var/cache/apt/archives/*.deb ~/.cache/xyg-webkit-debs/",
        'echo "changed=true" >> "$GITHUB_OUTPUT"',
    )
    _require_step_contains(
        errors,
        jobs.get("browser_conformance", ""),
        "Cache Playwright browsers",
        "pinned actions/cache for the Playwright browser engines",
        "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
        "path: ~/.cache/ms-playwright",
    )
    webkit_key = (
        "webkit-debs-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('package-lock.json') }}-"
    )
    _require_step_contains(
        errors,
        jobs.get("browser_conformance", ""),
        "Restore WebKit runtime packages",
        "pinned newest-prefix restore of WebKit runtime packages (slow runner apt mirror)",
        "actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
        "path: ~/.cache/xyg-webkit-debs",
        f"key: {webkit_key}${{{{ github.run_id }}}}",
        f"restore-keys: {webkit_key}",
    )
    _require_step_contains(
        errors,
        jobs.get("browser_conformance", ""),
        "Save WebKit runtime packages",
        "pinned per-run save of changed WebKit runtime packages",
        "if: steps.webkit-deps.outputs.changed == 'true'",
        "actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
        "path: ~/.cache/xyg-webkit-debs",
        f"key: {webkit_key}${{{{ github.run_id }}}}",
    )
    _require_job_contains(
        errors,
        jobs,
        "python_floor",
        "CI",
        "Python 3.11 floor gate",
        'python-version: "3.11"',
        "scripts/check_python_floor.py",
        "scripts/check_public_api.py",
        "npm ci --prefix packages/xy-node",
        "toolchain: 1.96.0",
        "needs: wasm_assets",
        "scripts/verify_wasm_assets.py",
    )
    _require_step_runs_exactly(
        errors,
        jobs.get("python_floor", ""),
        "Build render client",
        "JS Worker build ahead of the verified packaged WASM payload on the Python floor",
        "npm ci",
        "npm ci --prefix packages/xy-node",
        "node js/build.mjs",
    )
    _require_wasm_asset_contract(errors, jobs)
    _require_job_contains(
        errors,
        jobs,
        "benchmark_vs",
        "CI",
        "parallel cross-library benchmark matrix",
        "timeout-minutes: 10",
        "fail-fast: false",
        "matrix:",
        "xy: false",
        "browser: false",
        "build_js: false",
        "if: matrix.xy",
        "if: matrix.browser",
        "if: matrix.build_js",
        "--constraint benchmarks/requirements-ci.lock",
        "CHROMIUM_ARGS=()",
        "--libraries",
        "--max-n",
        "Run cross-library benchmark group",
        "Upload cross-library benchmark part",
        "benchmark-vs-${{ matrix.name }}",
        "if: always()",
        "actions/upload-artifact@",
        "if-no-files-found: warn",
    )
    cross_library = jobs.get("benchmark_vs", "")
    expected_matrix = {
        "native-and-webgl": {
            "libraries": "xy,plotly_gl,bokeh_webgl,datashader",
            "packages": "plotly kaleido bokeh datashader psutil",
            "max_n": "10000000",
            "xy": "true",
            "browser": "true",
            "build_js": "true",
        },
        "matplotlib": {
            "libraries": "matplotlib",
            "packages": "numpy matplotlib psutil",
            "max_n": "10000000",
            "xy": "false",
            "browser": "false",
            "build_js": "false",
        },
        "seaborn": {
            "libraries": "seaborn",
            "packages": "numpy seaborn psutil",
            "max_n": "10000000",
            "xy": "false",
            "browser": "false",
            "build_js": "false",
        },
        "plotly-svg": {
            "libraries": "plotly_svg",
            "packages": "numpy plotly kaleido psutil",
            "max_n": "10000000",
            "xy": "false",
            "browser": "true",
            "build_js": "false",
        },
        "bokeh-canvas": {
            "libraries": "bokeh_canvas",
            "packages": "numpy bokeh psutil",
            "max_n": "10000000",
            "xy": "false",
            "browser": "true",
            "build_js": "false",
        },
        "html-adapters": {
            "libraries": "altair,hvplot_bokeh",
            "packages": "numpy altair hvplot psutil",
            "max_n": "100000",
            "xy": "false",
            "browser": "true",
            "build_js": "false",
        },
    }
    matrix_entries = _matrix_include_entries(cross_library)
    matrix_by_name = {
        entry["name"]: entry for entry in matrix_entries if isinstance(entry.get("name"), str)
    }
    matrix_names = [entry.get("name") for entry in matrix_entries]
    duplicate_names = sorted({name for name in matrix_names if matrix_names.count(name) > 1})
    if duplicate_names:
        errors.append(f"CI benchmark_vs matrix has duplicate names: {duplicate_names}")
    if set(matrix_by_name) != set(expected_matrix):
        errors.append(
            "CI benchmark_vs matrix names must exactly match isolated benchmark groups; "
            f"got {sorted(matrix_by_name)}, expected {sorted(expected_matrix)}"
        )
    for name, expected in expected_matrix.items():
        actual = matrix_by_name.get(name)
        if actual is None:
            continue
        expected_entry = {"name": name, **expected}
        if actual != expected_entry:
            errors.append(
                f"CI benchmark_vs matrix entry {name!r} must exactly equal "
                f"{expected_entry!r}; got {actual!r}"
            )
    if not _step_is_conditioned(cross_library, "dtolnay/rust-toolchain@"):
        errors.append("CI benchmark_vs Rust toolchain setup must be conditioned on matrix.xy")
    _require_step_contains(
        errors,
        cross_library,
        "Build native core",
        "xy-only setup condition",
        "if: matrix.xy",
    )
    _require_step_contains(
        errors,
        cross_library,
        "Install XYG",
        "xy-only constrained install",
        "if: matrix.xy",
        'XYG_REQUIRE_CARGO: "1"',
        "--constraint benchmarks/requirements-ci.lock",
    )
    benchmark_vs = jobs.get("benchmark_vs", "")
    timeout_values, timeout_unsafe = _direct_yaml_key_values(
        benchmark_vs, "timeout-minutes", indent=4
    )
    if timeout_unsafe or timeout_values != ["25"]:
        errors.append("CI benchmark_vs job must define exactly one direct timeout-minutes: 25")
    methodology_timeout, methodology_unsafe = _direct_yaml_key_values(
        jobs.get("benchmark_methodology", ""), "timeout-minutes", indent=4
    )
    if methodology_unsafe or methodology_timeout != ["45"]:
        errors.append(
            "CI benchmark_methodology job must define exactly one direct timeout-minutes: 45"
        )
    # Hard post-merge evidence must survive transient registry/CDN failures (#1008).
    for job, step, needle in (
        ("benchmark_vs", "Install selected competitors", "scripts/ci_retry.sh 3 uv pip install"),
        ("benchmark_vs", "Install XYG", "scripts/ci_retry.sh 3 uv pip install"),
        ("benchmark_vs", "Install Chromium (Playwright)", "scripts/ci_retry.sh 3 npx playwright"),
        ("benchmark_methodology", "Install JS build toolchain", "scripts/ci_retry.sh 3 npm ci"),
        ("benchmark_methodology", "Install XYG + competitors", "scripts/ci_retry.sh 3 uv pip"),
        (
            "benchmark_methodology",
            "Install Chromium (Playwright)",
            "scripts/ci_retry.sh 3 npx playwright",
        ),
    ):
        _require_step_contains(
            errors, jobs.get(job, ""), step, f"{job} install retry ({needle})", needle
        )
    _require_step_contains(
        errors,
        cross_library,
        "Install selected competitors",
        "locked benchmark dependency constraint",
        "--constraint benchmarks/requirements-ci.lock",
        "${{ matrix.packages }}",
    )
    _require_step_contains(
        errors,
        cross_library,
        "Verify native benchmark backend",
        "xy-only verification condition",
        "if: matrix.xy",
    )
    _require_step_contains(
        errors,
        cross_library,
        "Install Chromium (Playwright)",
        "browser-only setup condition",
        "if: matrix.browser",
    )
    _require_step_contains(
        errors,
        cross_library,
        "Build JS client",
        "xy browser-build condition",
        "if: matrix.build_js",
    )
    _require_job_contains(
        errors,
        jobs,
        "benchmark_methodology",
        "CI",
        "post-merge hard methodology benchmark artifact path",
        "benchmarks/requirements-ci.lock",
        "Verify native benchmark backend",
        "XYG_REQUIRE_CARGO",
        'k.BACKEND == "native"',
        "benchmark job requires native backend",
        "scripts/verify_benchmark_report.py",
        "Upload benchmark methodology",
        "if: always()",
        "actions/upload-artifact@",
        "line.json",
        "install.json",
        "interaction.json",
        "dashboard.json",
        "workflows.json",
        "install-fresh.json",
        "verify_benchmark_report.py line.json --kind line-decimation",
        "verify_benchmark_report.py install.json --kind install-footprint",
        "verify_benchmark_report.py interaction.json --kind interaction-browser",
        "verify_benchmark_report.py dashboard.json --kind dashboard-browser",
        "verify_benchmark_report.py workflows.json --kind workflow-native",
        "bench_interaction.py",
        "bench_dashboard.py",
        "--chart-counts 10,20,50,60",
        "docs/benchmark_ci.md",
        "if-no-files-found: warn",
    )
    _require_job_contains(
        errors,
        jobs,
        "benchmark",
        "CI",
        "merged benchmark artifact path",
        "needs: [benchmark_vs, benchmark_methodology]",
        "if: always()",
        "actions/download-artifact@",
        "pattern: benchmark-vs-*",
        "name: benchmark-methodology",
        "scripts/merge_benchmark_reports.py",
        "benchmark.json",
        "verify_benchmark_report.py benchmark.json --kind scatter-vs",
        "Upload benchmark report",
        "actions/upload-artifact@",
        "line.json",
        "install.json",
        "interaction.json",
        "dashboard.json",
        "workflows.json",
        "install-fresh.json",
        "docs/benchmark_ci.md",
        "if-no-files-found: warn",
    )
    _require_job_contains(
        errors,
        jobs,
        "sdist",
        "CI",
        "source artifact verification",
        "dtolnay/rust-toolchain@",
        "uv build --sdist",
        "scripts/verify_sdist.py",
    )
    ci_sdist = jobs.get("sdist", "")
    _require_step_contains(
        errors,
        ci_sdist,
        "Build and load native core from sdist",
        "Rust-backed sdist install contract",
        "XYG_REQUIRE_CARGO",
        "uv pip install --no-cache",
        '"reflex>=0.9.6"',
        "import reflex_xy",
        "import xyg.kernels as kernels",
        'kernels.BACKEND == "native"',
    )
    _require_step_contains(
        errors,
        ci_sdist,
        "Verify coreless sdist imports reflex_xy",
        "coreless sdist import contract",
        "XYG_SKIP_CARGO",
        "uv pip install --no-cache",
        "import reflex_xy",
        "assert reflex_xy.__version__ == version",
        "native Rust core",
    )
    _require_job_contains(
        errors,
        jobs,
        "wheels",
        "CI",
        "native wheel verification and upload",
        "XYG_REQUIRE_CARGO",
        "scripts/verify_wheel.py",
        "--expect-native",
        "actions/upload-artifact@",
        "dist/*.whl",
    )
    _require_job_contains(
        errors,
        jobs,
        "install_without_rust",
        "CI",
        "no-Rust wheel builds but errors clearly on compute",
        "Remove preinstalled Rust",
        "scripts/verify_wheel.py",
        "--expect-pure",
        "assert xyg.__version__",
        "native Rust core",
    )
    return errors


def validate_workflow(path: Path = DEFAULT_WORKFLOW) -> list[str]:
    """Backward-compatible CI workflow verifier."""
    return validate_ci_workflow(path)


def validate_final_review_policy(
    workflow_path: Path = DEFAULT_FINAL_REVIEW_WORKFLOW,
    config_path: Path = DEFAULT_CODERABBIT_CONFIG,
    script_path: Path = DEFAULT_FINAL_REVIEW_SCRIPT,
) -> list[str]:
    """Validate the optional CodeRabbit helper's opt-in and final-candidate safeguards."""
    errors: list[str] = []
    try:
        text = workflow_path.read_text(encoding="utf-8")
        config = config_path.read_text(encoding="utf-8")
        script = script_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read final CodeRabbit policy: {exc}"]
    expected_config = (
        "language: en-US\n\nreviews:\n  auto_review:\n"
        "    enabled: false\n    auto_incremental_review: false\n"
    )
    if config != expected_config:
        errors.append("CodeRabbit config must disable automatic and incremental reviews exactly")
    required_idempotency = (
        "comments(last:100)",
        "<!-- xyg-final-review:{head} -->",
        "has_existing_request(comments, head)",
        'author.get("login") == "github-actions[bot]"',
    )
    missing_idempotency = _missing_needles(script, required_idempotency)
    if missing_idempotency:
        errors.append(
            "final CodeRabbit request must be exact-head idempotent via trusted comments: "
            f"{missing_idempotency}"
        )
    if '"Release surfaces"' not in script:
        errors.append("final CodeRabbit request must require the Release surfaces aggregate")
    if 'status.get("context") != "CodeRabbit"' not in script:
        errors.append("final CodeRabbit request must not depend on its own status context")
    if "@coderabbitai review" in script:
        errors.append("final CodeRabbit authorization must not emit a bot-authored command")
    validation_index = script.find("head = validate_candidate(")
    refresh_index = script.find('refreshed = _request(f"{api}/pulls/{number}"')
    idempotency_index = script.find("if has_existing_request(comments, head):")
    post_index = script.find('f"{api}/issues/{number}/comments"')
    if not (-1 < validation_index < refresh_index < idempotency_index < post_index):
        errors.append(
            "final CodeRabbit idempotency skip must follow candidate validation and exact-head "
            "refresh, and precede the review request"
        )
    jobs = _job_blocks(text)
    _require_unique_workflow_structure(errors, text, "final CodeRabbit", {"request"})
    on_block = _unique_mapping_block(text, "on", indent=0) or ""
    triggers = [
        key for indent, key, unsafe in _yaml_mapping_keys(on_block) if indent == 2 and not unsafe
    ]
    if triggers != ["workflow_dispatch"]:
        errors.append("final CodeRabbit workflow must be manual-only")
    _require_workflow_contains(
        errors,
        text,
        "final CodeRabbit",
        "required PR number and exact-head inputs",
        "pull_request:",
        "head_sha:",
        "required: true",
    )
    top_permissions, top_unsafe = _direct_yaml_key_values(text, "permissions", indent=0)
    if top_unsafe or top_permissions != ["{}"]:
        errors.append("final CodeRabbit workflow top-level permissions must be empty")
    request = jobs.get("request", "")
    runners, runner_unsafe = _direct_yaml_key_values(request, "runs-on", indent=4)
    if runner_unsafe or runners != ["blacksmith-4vcpu-ubuntu-2404"]:
        errors.append("final CodeRabbit request must run on Blacksmith")
    permissions = _unique_mapping_block(request, "permissions", indent=4) or ""
    permission_pairs = [
        (key, value.strip())
        for line in _yaml_code_lines(permissions)
        if (parsed := _direct_yaml_mapping(line)) is not None
        for indent, key, unsafe, value in [parsed]
        if indent == 6 and not unsafe
    ]
    if permission_pairs != [
        ("checks", "read"),
        ("contents", "read"),
        ("pull-requests", "write"),
        ("statuses", "read"),
    ]:
        errors.append("final CodeRabbit request must have only its four minimal permissions")
    _require_job_contains(
        errors,
        jobs,
        "request",
        "final CodeRabbit",
        "exact-head final-review inputs and command",
        "XYG_CURRENT_RUN_ID: ${{ github.run_id }}",
        "XYG_EXPECTED_HEAD: ${{ inputs.head_sha }}",
        "XYG_PR_NUMBER: ${{ inputs.pull_request }}",
        "XYG_REF: ${{ github.ref }}",
        "run: python3 scripts/request_final_coderabbit.py",
    )
    _require_step_runs_exactly(
        errors,
        request,
        "Verify final candidate and record authorization",
        "exact final-review request command",
        "python3 scripts/request_final_coderabbit.py",
    )
    return errors


def validate_codspeed_workflow(path: Path = DEFAULT_CODSPEED_WORKFLOW) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read CodSpeed workflow {path}: {exc}"]

    jobs = _job_blocks(text)
    errors: list[str] = []
    _require_unique_workflow_structure(errors, text, "CodSpeed", REQUIRED_CODSPEED_JOBS)
    _require_pipefail_for_piped_steps(errors, text, "CodSpeed")
    on_block = _unique_mapping_block(text, "on", indent=0) or ""
    trigger_keys = [
        key for indent, key, unsafe in _yaml_mapping_keys(on_block) if indent == 2 and not unsafe
    ]
    if trigger_keys != ["schedule", "workflow_dispatch"]:
        errors.append("CodSpeed workflow must have only schedule and workflow_dispatch triggers")
    cron_lines = [
        line.strip()
        for line in _yaml_code_lines(on_block)
        if re.fullmatch(r'\s*- cron: "17 7 \* \* \*"\s*', line)
    ]
    if cron_lines != ['- cron: "17 7 * * *"']:
        errors.append("CodSpeed workflow must define exactly the nightly main cron")
    concurrency = _unique_mapping_block(text, "concurrency", indent=0) or ""
    groups, group_unsafe = _direct_yaml_key_values(concurrency, "group", indent=2)
    cancels, cancel_unsafe = _direct_yaml_key_values(concurrency, "cancel-in-progress", indent=2)
    if group_unsafe or groups != ["codspeed-main"] or cancel_unsafe or cancels != ["true"]:
        errors.append("CodSpeed workflow must keep one latest-main concurrency group")
    _require_unshallow_checkouts(errors, text, "CodSpeed")
    missing_jobs = sorted(REQUIRED_CODSPEED_JOBS - set(jobs))
    if missing_jobs:
        errors.append(f"CodSpeed workflow missing required jobs: {missing_jobs}")

    top_permissions, permissions_unsafe = _direct_yaml_key_values(text, "permissions", indent=0)
    if permissions_unsafe or top_permissions != ["{}"]:
        errors.append("CodSpeed workflow top-level permissions must be empty")

    detect = jobs.get("detect", "")
    detect_runners, detect_runner_unsafe = _direct_yaml_key_values(detect, "runs-on", indent=4)
    if detect_runner_unsafe or detect_runners != ["blacksmith-4vcpu-ubuntu-2404"]:
        errors.append("CodSpeed detection must run on the inexpensive Blacksmith runner")
    detect_permissions = _unique_mapping_block(detect, "permissions", indent=4) or ""
    detect_permission_pairs = [
        (key, value.strip())
        for indent, key, unsafe, value in map(
            _direct_yaml_mapping, _yaml_code_lines(detect_permissions)
        )
        if indent == 6 and not unsafe
    ]
    if detect_permission_pairs != [("actions", "read"), ("contents", "read")]:
        errors.append(
            "CodSpeed detection permissions must be exactly actions/read and contents/read"
        )
    detect_outputs = _unique_mapping_block(detect, "outputs", indent=4) or ""
    output_values, output_unsafe = _direct_yaml_key_values(detect_outputs, "should_run", indent=6)
    if output_unsafe or output_values != ["${{ steps.changed.outputs.should_run }}"]:
        errors.append("CodSpeed detect output must bind exactly to the changed step")
    _require_job_contains(
        errors,
        jobs,
        "detect",
        "CodSpeed",
        "fail-closed latest-main change detector",
        "actions: read",
        "contents: read",
        "should_run: ${{ steps.changed.outputs.should_run }}",
        "XYG_CURRENT_RUN_ID: ${{ github.run_id }}",
        "XYG_CURRENT_SHA: ${{ github.sha }}",
        "XYG_EVENT_NAME: ${{ github.event_name }}",
        "XYG_REF: ${{ github.ref }}",
        "XYG_REPOSITORY: ${{ github.repository }}",
        "run: python3 scripts/codspeed_should_run.py",
    )
    _require_step_runs_exactly(
        errors,
        detect,
        "Compare with latest successful main benchmark",
        "exact fail-closed change detector",
        "python3 scripts/codspeed_should_run.py",
    )

    benchmarks = jobs.get("benchmarks", "")
    runner_values, runner_unsafe = _direct_yaml_key_values(benchmarks, "runs-on", indent=4)
    if runner_unsafe or runner_values != [CODSPEED_HOSTED_RUNNER]:
        errors.append("CodSpeed benchmarks job must run on the dedicated codspeed-macro runner")

    benchmark_needs, needs_unsafe = _direct_yaml_key_values(benchmarks, "needs", indent=4)
    benchmark_if, if_unsafe = _direct_yaml_key_values(benchmarks, "if", indent=4)
    if needs_unsafe or benchmark_needs != ["detect"]:
        errors.append("CodSpeed benchmark job must depend directly on detect")
    if if_unsafe or benchmark_if != ["needs.detect.outputs.should_run == 'true'"]:
        errors.append("CodSpeed benchmark job must be gated by the exact detector output")
    benchmark_permissions = _unique_mapping_block(benchmarks, "permissions", indent=4) or ""
    benchmark_permission_pairs = [
        (key, value.strip())
        for indent, key, unsafe, value in map(
            _direct_yaml_mapping, _yaml_code_lines(benchmark_permissions)
        )
        if indent == 6 and not unsafe
    ]
    if benchmark_permission_pairs != [("contents", "read"), ("id-token", "write")]:
        errors.append("CodSpeed benchmark permissions must be exactly contents/read and OIDC write")
    _require_job_contains(
        errors,
        jobs,
        "benchmarks",
        "CodSpeed",
        "minimal benchmark permissions",
        "permissions:",
        "contents: read",
        "id-token: write",
    )
    _require_job_contains(
        errors,
        jobs,
        "benchmarks",
        "CodSpeed",
        "native-only benchmark path",
        "dtolnay/rust-toolchain@",
        "actions/setup-python@",
        'python-version: "3.11"',
        "astral-sh/setup-uv@",
        "cargo build --release",
        "XYG_REQUIRE_CARGO",
        "--group dev --group codspeed",
        "Verify native benchmark backend",
        'k.BACKEND == "native"',
        "CodSpeed requires native backend",
        "CodSpeedHQ/action@",
        "mode: simulation",
        "cargo install cargo-codspeed",
        "cargo codspeed build -m simulation --bench kernels --bench aggregate --bench typed_series",
        "cargo codspeed run --bench kernels --bench aggregate --bench typed_series",
        "benchmarks/test_codspeed_kernels.py --codspeed",
    )
    _require_step_runs_exactly(
        errors,
        benchmarks,
        "Build Rust kernel benchmarks",
        "exact simulation benchmark build",
        "cargo codspeed build -m simulation --bench kernels --bench aggregate --bench typed_series",
        allow_job_gate=True,
    )
    _require_action_step_with_runs_exactly(
        errors,
        benchmarks,
        "Run benchmarks",
        "CodSpeedHQ/action@4296e51e7041e24dadb86d1d6e8b9320d223dbe8",
        "simulation",
        "set -euo pipefail",
        "cargo codspeed run --bench kernels --bench aggregate --bench typed_series",
        ".venv/bin/python -m pytest benchmarks/test_codspeed_*.py --codspeed",
    )
    step_blocks = _step_sequence_blocks(benchmarks)
    step_names = []
    active_codspeed_commands = []
    for block in step_blocks:
        first = _strip_yaml_comment(block.splitlines()[0])
        match = re.match(r"^      - name:\s*(.+?)\s*$", first)
        step_names.append(match.group(1) if match is not None else None)
        direct_commands = _step_run_lines(block)
        if direct_commands:
            active_codspeed_commands.extend(
                command
                for command in direct_commands
                if command.startswith(("cargo codspeed build", "cargo codspeed run"))
            )
        elif any(line.startswith("        uses: ") for line in block.splitlines()):
            active_codspeed_commands.extend(
                line.strip()
                for line in block.splitlines()
                if line.startswith("            cargo codspeed ")
            )
    expected_pair = ["Build Rust kernel benchmarks", "Run benchmarks"]
    if not any(
        step_names[index : index + 2] == expected_pair for index in range(len(step_names) - 1)
    ):
        errors.append("CodSpeed simulation build must be immediately followed by Run benchmarks")
    expected_commands = [
        "cargo codspeed build -m simulation --bench kernels --bench aggregate --bench typed_series",
        "cargo codspeed run --bench kernels --bench aggregate --bench typed_series",
    ]
    if active_codspeed_commands != expected_commands:
        errors.append(
            "CodSpeed benchmarks job must contain only the exact build/run command pair: "
            f"{expected_commands!r}"
        )
    _require_job_contains(
        errors,
        jobs,
        "authored-scene-browser-evidence",
        "CodSpeed",
        "changed-main authored-Scene browser evidence",
        "needs: detect",
        "needs.detect.outputs.should_run == 'true'",
        "cargo build -p xyg-wasm --release --target wasm32-unknown-unknown",
        "node benchmarks/bench_wasm_scene.mjs",
        "packages/xy-node/scripts/generate_authored_scene_benchmark.mjs",
        "scripts/verify_authored_scene_artifacts.py",
        "scripts/verify_wasm_scene_benchmark.py",
        "authored-scene-browser-${{ github.sha }}.json",
        "scripts/inline_density_file_benchmark.py",
        "scripts/verify_inline_density_benchmark.py",
        "hosted-density-browser-${{ github.sha }}.json",
        "benchmarks/bench_graph_scale.py --profile evidence",
        'scripts/verify_benchmark_report.py "graph-scale-${{ github.sha }}.json"',
        "graph-scale-${{ github.sha }}.json",
        'XYG_CHROMIUM="$(node -e \'process.stdout.write(require("playwright").chromium.executablePath())\')"',
        "actions/upload-artifact@",
    )
    _require_step_contains(
        errors,
        jobs["authored-scene-browser-evidence"],
        "Generate and measure four-size authored-Scene first paint",
        "the explicit just-built native library for Node authored-Scene generation",
        "XYG_NATIVE_LIB: ${{ github.workspace }}/target/release/libxyg_core.so",
    )
    if text.count("XYG_NATIVE_LIB: ${{ github.workspace }}/target/release/libxyg_core.so") != 1:
        errors.append(
            "CodSpeed must expose the checkout native library only to the authored-Scene measurement step"
        )
    return errors


def validate_density_workflow(path: Path = DEFAULT_DENSITY_WORKFLOW) -> list[str]:
    """Keep the expensive #876 authority off PRs and non-main refs."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read density authority workflow {path}: {exc}"]

    errors: list[str] = []
    _require_unique_workflow_structure(errors, text, "density authority", {"density"})
    _require_pipefail_for_piped_steps(errors, text, "density authority")
    top_keys = [
        key for indent, key, unsafe in _yaml_mapping_keys(text) if indent == 0 and not unsafe
    ]
    if top_keys != ["name", "on", "permissions", "concurrency", "jobs"]:
        errors.append("density authority must use only the exact reviewed top-level keys")
    permissions = _unique_mapping_block(text, "permissions", indent=0) or ""
    permission_keys = [
        key for indent, key, unsafe in _yaml_mapping_keys(permissions) if indent == 2 and not unsafe
    ]
    contents, contents_unsafe = _direct_yaml_key_values(permissions, "contents", indent=2)
    if permission_keys != ["contents"] or contents_unsafe or contents != ["read"]:
        errors.append("density authority permissions must be exactly contents: read")
    concurrency = _unique_mapping_block(text, "concurrency", indent=0) or ""
    concurrency_keys = [
        key for indent, key, unsafe in _yaml_mapping_keys(concurrency) if indent == 2 and not unsafe
    ]
    group, group_unsafe = _direct_yaml_key_values(concurrency, "group", indent=2)
    cancel, cancel_unsafe = _direct_yaml_key_values(concurrency, "cancel-in-progress", indent=2)
    if (
        concurrency_keys != ["group", "cancel-in-progress"]
        or group_unsafe
        or group != ["density-e2e-main"]
        or cancel_unsafe
        or cancel != ["false"]
    ):
        errors.append("density authority concurrency must serialize runs without cancellation")
    if _has_shell_init_environment(text) or re.search(r"\bGITHUB_(?:ENV|PATH)\b", text):
        errors.append("density authority must not use shell-init environment state")
    on_block = _unique_mapping_block(text, "on", indent=0) or ""
    triggers = [
        key for indent, key, unsafe in _yaml_mapping_keys(on_block) if indent == 2 and not unsafe
    ]
    if triggers != ["schedule", "workflow_dispatch"]:
        errors.append("density authority must have only schedule and workflow_dispatch triggers")
    crons = [
        line.strip()
        for line in _yaml_code_lines(on_block)
        if re.fullmatch(r'\s*- cron: "(?:31 6 \* \* \*|43 5 \* \* 0)"\s*', line)
    ]
    if crons != ['- cron: "31 6 * * *"', '- cron: "43 5 * * 0"']:
        errors.append(
            "density authority must keep the exact daily-control and weekly-authority crons"
        )
    jobs = _job_blocks(text)
    if set(jobs) != {"density"}:
        errors.append("density authority workflow must contain exactly the density job")
    density = jobs.get("density", "")
    job_keys = [
        key for indent, key, unsafe in _yaml_mapping_keys(density) if indent == 4 and not unsafe
    ]
    if job_keys != ["name", "if", "runs-on", "timeout-minutes", "steps"]:
        errors.append("density authority job must use only the reviewed direct job keys")
    runner, runner_unsafe = _direct_yaml_key_values(density, "runs-on", indent=4)
    condition, condition_unsafe = _direct_yaml_key_values(density, "if", indent=4)
    timeout, timeout_unsafe = _direct_yaml_key_values(density, "timeout-minutes", indent=4)
    if runner_unsafe or runner != ["blacksmith-4vcpu-ubuntu-2404"]:
        errors.append("density authority must use the bounded approved Blacksmith runner")
    if condition_unsafe or condition != ["github.ref == 'refs/heads/main'"]:
        errors.append("density authority job must be locked directly to refs/heads/main")
    if timeout_unsafe or timeout != ["90"]:
        errors.append("density authority job must have timeout-minutes: 90")

    steps = _step_sequence_blocks(density)
    expected_steps = [
        (None, "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"),
        (None, "dtolnay/rust-toolchain@4be7066ada62dd38de10e7b70166bc74ed198c30"),
        (None, "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020"),
        (None, "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"),
        (None, "astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990"),
        ("Cache Playwright Chromium", "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"),
        ("Build bounded native and browser product paths", None),
        ("Record runner capacity", None),
        ("Run daily 1M end-to-end control", None),
        ("Run weekly/manual 100M end-to-end authority", None),
        (
            "Upload exact-SHA raw reports",
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        ),
    ]
    actual_steps: list[tuple[str | None, str | None]] = []
    for step in steps:
        names, names_unsafe = _step_direct_key_values(step, "name")
        uses, uses_unsafe = _step_direct_key_values(step, "uses")
        clean_uses = [value.split(" #", 1)[0] for value in uses]
        actual_steps.append(
            (
                names[0] if len(names) == 1 and not names_unsafe else None,
                clean_uses[0] if len(clean_uses) == 1 and not uses_unsafe else None,
            )
        )
    if actual_steps != expected_steps:
        errors.append("density authority must contain only the exact reviewed step sequence")

    expected_step_keys = [
        ["uses", "with"],
        ["uses", "with"],
        ["uses", "with"],
        ["uses", "with"],
        ["uses", "with"],
        ["name", "uses", "with"],
        ["name", "run"],
        ["name", "run"],
        ["name", "run"],
        ["name", "if", "env", "run"],
        ["name", "if", "uses", "with"],
    ]
    if len(steps) == len(expected_step_keys) and any(
        unsafe or keys != expected
        for step, expected in zip(steps, expected_step_keys, strict=True)
        for keys, unsafe in [_step_direct_keys(step)]
    ):
        errors.append("density authority steps must use only their exact reviewed direct keys")

    action_with_contracts = [
        (
            0,
            ["fetch-depth", "persist-credentials"],
            {"fetch-depth": ["0"], "persist-credentials": ["false"]},
        ),
        (1, ["toolchain"], {"toolchain": ["1.96.0"]}),
        (2, ["node-version"], {"node-version": ['"22"']}),
        (3, ["python-version"], {"python-version": ['"3.11"']}),
        (4, ["enable-cache"], {"enable-cache": ["false"]}),
        (
            5,
            ["path", "key"],
            {
                "path": ["~/.cache/ms-playwright"],
                "key": [
                    "density-e2e-playwright-${{ runner.os }}-${{ runner.arch }}-"
                    "${{ hashFiles('package-lock.json') }}"
                ],
            },
        ),
    ]
    for index, expected_keys, expected_values in action_with_contracts:
        if index >= len(steps):
            continue
        with_block = _unique_mapping_block(steps[index], "with", indent=8) or ""
        with_keys = [
            key
            for indent, key, unsafe in _yaml_mapping_keys(with_block)
            if indent == 10 and not unsafe
        ]
        values_ok = all(
            _direct_yaml_key_values(with_block, key, indent=10) == (values, False)
            for key, values in expected_values.items()
        )
        if with_keys != expected_keys or not values_ok:
            errors.append(
                f"density authority setup step {index + 1} must keep exact reviewed inputs"
            )

    _require_step_runs_exactly(
        errors,
        density,
        "Build bounded native and browser product paths",
        "exact bounded build commands",
        "cargo build --release",
        "npm ci",
        "node js/build.mjs",
        "uv sync --locked --group dev",
        "npx playwright install chromium",
        allow_job_gate=True,
        forbid_environment=True,
    )
    _require_step_runs_exactly(
        errors,
        density,
        "Record runner capacity",
        "exact capacity commands",
        "getconf _NPROCESSORS_ONLN",
        "grep -E 'MemTotal|MemAvailable' /proc/meminfo",
        'df -h "$GITHUB_WORKSPACE"',
        allow_job_gate=True,
        forbid_environment=True,
    )
    chrome_command = "CHROME=$(node -e 'process.stdout.write(require(\"playwright\").chromium.executablePath())')"
    _require_step_runs_exactly(
        errors,
        density,
        "Run daily 1M end-to-end control",
        "exact 1M control and verification commands",
        chrome_command,
        ".venv/bin/python benchmarks/bench_density_e2e.py \\",
        '--points 1000000 --chrome "$CHROME" \\',
        "--timeout 600 --max-rss-gib 8 --max-disk-gib 2 \\",
        '--output "$RUNNER_TEMP/density-e2e-control-${GITHUB_SHA}.json"',
        "python3 scripts/verify_density_e2e_report.py \\",
        '"$RUNNER_TEMP/density-e2e-control-${GITHUB_SHA}.json" --sha "$GITHUB_SHA"',
        allow_job_gate=True,
        forbid_environment=True,
    )
    authority_step = _named_step_blocks(density).get(
        "Run weekly/manual 100M end-to-end authority", ""
    )
    authority_if, authority_if_unsafe = _step_direct_key_values(authority_step, "if")
    authority_env = _unique_mapping_block(authority_step, "env", indent=8) or ""
    authority_env_keys = [
        key
        for indent, key, unsafe in _yaml_mapping_keys(authority_env)
        if indent == 10 and not unsafe
    ]
    authority_capability, authority_capability_unsafe = _direct_yaml_key_values(
        authority_env, "XYG_DENSITY_100M_AUTHORITY", indent=10
    )
    authority_commands = [
        chrome_command,
        ".venv/bin/python benchmarks/bench_density_e2e.py \\",
        '--points 100000000 --authority --chrome "$CHROME" \\',
        "--timeout 3600 --max-rss-gib 12 --max-disk-gib 4 \\",
        '--output "$RUNNER_TEMP/density-e2e-100m-${GITHUB_SHA}.json"',
        "python3 scripts/verify_density_e2e_report.py \\",
        '"$RUNNER_TEMP/density-e2e-100m-${GITHUB_SHA}.json" --sha "$GITHUB_SHA"',
    ]
    if (
        authority_if_unsafe
        or authority_if
        != ["github.event_name == 'workflow_dispatch' || github.event.schedule == '43 5 * * 0'"]
        or authority_capability_unsafe
        or authority_capability != ['"1"']
        or authority_env_keys != ["XYG_DENSITY_100M_AUTHORITY"]
        or _step_run_lines(authority_step) != authority_commands
        or _direct_yaml_key_count(authority_step, "run", indent=8) != 1
    ):
        errors.append(
            "density 100M authority step must keep its exact guard, capability, and commands"
        )
    upload = _named_step_blocks(density).get("Upload exact-SHA raw reports", "")
    upload_if, upload_if_unsafe = _step_direct_key_values(upload, "if")
    upload_with = _unique_mapping_block(upload, "with", indent=8) or ""
    upload_values = {
        key: _direct_yaml_key_values(upload_with, key, indent=10)
        for key in ("name", "if-no-files-found", "retention-days", "path")
    }
    if (
        upload_if_unsafe
        or upload_if != ["always()"]
        or upload_values
        != {
            "name": (["density-e2e-${{ github.sha }}"], False),
            "if-no-files-found": (["error"], False),
            "retention-days": (["30"], False),
            "path": (["${{ runner.temp }}/density-e2e-*-${{ github.sha }}.json"], False),
        }
    ):
        errors.append("density raw-report upload must keep exact SHA paths and always-run policy")
    upload_keys = [
        key
        for indent, key, unsafe in _yaml_mapping_keys(upload_with)
        if indent == 10 and not unsafe
    ]
    if upload_keys != ["name", "if-no-files-found", "retention-days", "path"]:
        errors.append("density raw-report upload must use only the exact reviewed inputs")
    if "CodSpeedHQ/action@" in density or "--codspeed" in density:
        errors.append("density end-to-end evidence must remain outside hosted CodSpeed")
    return errors


def validate_release_workflow(path: Path = DEFAULT_RELEASE_WORKFLOW) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read release workflow {path}: {exc}"]

    jobs = _job_blocks(text)
    errors: list[str] = []
    if DEFAULT_RELEASE_WORKFLOW.name != "publish.yaml":
        errors.append(
            "release workflow filename must be publish.yaml to match the PyPI "
            "trusted publisher for project xyg (CurateLabs/xyg#13)"
        )
    stale_release = ROOT / ".github" / "workflows" / "release.yml"
    if stale_release.exists():
        errors.append(
            "stale .github/workflows/release.yml is present; PyPI trusted "
            "publishing is bound to publish.yaml and a second workflow would drift"
        )
    _require_unique_workflow_structure(errors, text, "release", REQUIRED_RELEASE_JOBS)
    _require_pipefail_for_piped_steps(errors, text, "release")
    _require_trigger_with_direct_option(
        errors,
        text,
        "release",
        "push",
        "tags",
        '["xyg-v*"]',
    )
    if _workflow_trigger_block(text, "workflow_dispatch") is None:
        errors.append("release workflow missing workflow_dispatch trigger")
    _require_unshallow_checkouts(errors, text, "release")
    missing_jobs = sorted(REQUIRED_RELEASE_JOBS - set(jobs))
    if missing_jobs:
        errors.append(f"release workflow missing required jobs: {missing_jobs}")

    _require_job_contains(
        errors,
        jobs,
        "wheels",
        "release",
        "cross-platform wheel matrix (glibc+musl, macOS, Windows), verification, and upload",
        "dtolnay/rust-toolchain@",
        "astral-sh/setup-uv@",
        "actions/setup-node@",
        'node-version: "22"',
        "npm ci",
        "cargo-zigbuild",
        "uv build --wheel",
        "XYG_REQUIRE_CARGO",
        "XYG_WHEEL_PLATFORM",
        "musllinux_1_2_x86_64",
        "win_arm64",
        "scripts/verify_wheel.py",
        "--expect-native",
        "Install-size budget (<= 15 MB)",
        '"reflex>=0.9.6"',
        "import importlib.metadata as m, reflex_xy",
        "assert reflex_xy.__version__ == m.version('xyg')",
        "assert k.BACKEND=='native'",
        "scripts/plain_python_smoke.py",
        "actions/upload-artifact@",
        "dist/*.whl",
    )
    wheels_job = jobs.get("wheels", "")
    plain_smoke_name = "Prove plain Python wheel needs no optional host framework"
    plain_smoke_steps = []
    for step in _step_sequence_blocks(wheels_job):
        names, names_unsafe = _step_direct_key_values(step, "name")
        if not names_unsafe and names == [plain_smoke_name]:
            plain_smoke_steps.append(step)
    if len(plain_smoke_steps) != 1:
        errors.append(
            "release wheels job must contain exactly one active named plain-Python wheel smoke step"
        )
    else:
        plain_smoke = plain_smoke_steps[0]
        conditions, conditions_unsafe = _step_direct_key_values(plain_smoke, "if")
        if conditions_unsafe or conditions != ["matrix.native"]:
            errors.append(
                "plain-Python wheel smoke step must use exact if: matrix.native condition"
            )
        expected_commands = [
            "uv venv plain-smoke",
            "uv pip install -p plain-smoke dist/*.whl",
            'cp scripts/plain_python_smoke.py "$RUNNER_TEMP/plain-python-smoke.py"',
            '(cd "$RUNNER_TEMP" && "$GITHUB_WORKSPACE/plain-smoke/bin/python" -I plain-python-smoke.py) \\',
            '|| (cd "$RUNNER_TEMP" && "$GITHUB_WORKSPACE/plain-smoke/Scripts/python.exe" -I plain-python-smoke.py)',
        ]
        if _step_run_lines(plain_smoke) != expected_commands:
            errors.append(
                "plain-Python wheel smoke step must run the exact isolated installed-wheel commands"
            )
    if "continue-on-error:" in wheels_job:
        errors.append(
            "release wheels job must block publishing when any native wheel build or "
            "verification fails"
        )
    _require_job_contains(
        errors,
        jobs,
        "wasm",
        "release",
        "runtime-verified, PyPI-published PyEmscripten WASM wheel",
        "permissions:",
        "contents: read",
        "toolchain: 1.96.0",
        "wasm32-unknown-emscripten",
        'RUSTFLAGS="-C panic=abort"',
        "pypa/cibuildwheel@294735312765b09d24a2fbec22660ce817587d55",
        "CIBW_PLATFORM: pyodide",
        "CIBW_BUILD: cp314-pyodide_wasm32",
        'CIBW_PYODIDE_VERSION: "314.0.0"',
        "CIBW_BEFORE_BUILD_PYODIDE",
        "CIBW_ENVIRONMENT_PYODIDE",
        "XYG_REQUIRE_WASM=1",
        "pyemscripten_2026_0_wasm32",
        "pyodide@314.0.0",
        "scripts/pyodide_load_smoke.py",
        "scripts/verify_wheel.py",
        "--expect-native",
        "wheelhouse/*.whl",
        "name: dist-pyemscripten",
    )
    _require_wasm_asset_contract(
        errors,
        jobs,
        label="release",
        producer_name=RELEASE_WASM_PRODUCER,
        consumers=RELEASE_WASM_CONSUMER_JOBS,
        download_step=RELEASE_WASM_DOWNLOAD_STEP,
        distributions={"wheels": True, "sdist": True, "wasm": False},
    )
    wasm_job = jobs.get("wasm", "")
    if "continue-on-error:" in wasm_job:
        errors.append("release wasm job must block publishing when the Pyodide runtime probe fails")
    _require_job_contains(
        errors,
        jobs,
        "browser-package",
        "release",
        "exact-version host-neutral browser package staging (#53)",
        "toolchain: 1.96.0",
        "wasm32-unknown-unknown",
        'node-version: "24"',
        "node js/build.mjs",
        "needs: wasm-assets",
        "scripts/stage_browser_package.py",
        "--dist packages/xy-client/dist",
        "npm pack ./staged/xyg-browser",
        "npm publish ./packed/*.tgz --dry-run --tag next --provenance=false",
        'XYG_BROWSER_DIST="$PWD/unpacked-browser/package" node scripts/wasm_foundation_smoke.mjs',
        "name: browser-package",
    )
    _require_job_contains(
        errors,
        jobs,
        "sdist",
        "release",
        "sdist build, content verification, Rust-backed install smoke, and upload",
        "astral-sh/setup-uv@",
        "dtolnay/rust-toolchain@",
        "actions/setup-node@",
        'node-version: "22"',
        "npm ci",
        "uv build --sdist",
        "scripts/verify_sdist.py",
        "actions/upload-artifact@",
        "dist/*.tar.gz",
    )
    release_sdist = jobs.get("sdist", "")
    _require_step_contains(
        errors,
        release_sdist,
        "Build and load native core from sdist",
        "Rust-backed release sdist install contract",
        "XYG_REQUIRE_CARGO",
        "uv pip install --no-cache",
        '"reflex>=0.9.6"',
        "import reflex_xy",
        "import xyg.kernels as kernels",
        'kernels.BACKEND == "native"',
    )
    _require_step_contains(
        errors,
        release_sdist,
        "Verify coreless sdist imports reflex_xy",
        "coreless release sdist import contract",
        "XYG_SKIP_CARGO",
        "uv pip install --no-cache",
        "import reflex_xy",
        "assert reflex_xy.__version__ == version",
        "native Rust core",
    )
    _require_job_contains(
        errors,
        jobs,
        "publish",
        "release",
        "trusted PyPI publishing from downloaded artifacts, gated by a dry-run switch, "
        "a tag/version/CHANGELOG agreement gate, and the fork publish guards (#13)",
        "needs: [wheels, sdist, wasm, browser-package, node-native-packages, node-facade, node-clean-install, node-unsupported-windows-arm64, release-cohort-linux-x64]",
        "environment: pypi",
        "contents: read",
        "id-token: write",
        "scripts/check_release_version.py",
        "actions/download-artifact@",
        "pattern: dist-*",
        "merge-multiple: true",
        "dry_run",
        "Fork publish guard (refuse upstream's PyPI package name)",
        "Refusing to publish distribution 'xy'",
        "pypa/gh-action-pypi-publish@",
        "packages-dir: dist/",
        "skip-existing: true",
        'scripts/publish_node_packages.py npm-dist --tag "$GITHUB_REF_NAME" --check',
        "Verify complete npm cohort before PyPI",
        "path: npm-dist/browser",
        "name: browser-package",
    )
    npm_preflight = _named_step_blocks(jobs.get("publish", "")).get(
        "Verify complete npm cohort before PyPI", ""
    )
    preflight_gate, preflight_unsafe = _step_direct_key_values(npm_preflight, "if")
    if (
        preflight_unsafe
        or preflight_gate != ["startsWith(github.ref, 'refs/tags/xyg-v')"]
        or _step_run_lines(npm_preflight)
        != ['python3 scripts/publish_node_packages.py npm-dist --tag "$GITHUB_REF_NAME" --check']
    ):
        errors.append(
            "release PyPI must validate the complete tagged seven-package npm cohort before upload"
        )
    _require_job_contains(
        errors,
        jobs,
        "node-native-packages",
        "release",
        "exact-wheel Node native package staging and dry publication (#52)",
        "needs: [wheels]",
        "dist-${{ matrix.wheel }}",
        "scripts/stage_node_packages.py",
        '--platform "${{ matrix.platform }}"',
        "--wheel wheel/*.whl",
        "npm pack",
        "npm publish ./packed/*.tgz --dry-run --tag next --provenance=false",
        "node-platform-${{ matrix.platform }}",
    )
    _require_job_contains(
        errors,
        jobs,
        "node-facade",
        "release",
        "offline-client Node facade staging and dry publication (#52)",
        "node js/build.mjs",
        "scripts/stage_node_packages.py",
        "--facade",
        "--client packages/xy-client/dist/standalone.js",
        "client/standalone.js",
        "npm pack",
        "node-facade",
    )
    _require_job_contains(
        errors,
        jobs,
        "node-clean-install",
        "release",
        "native supported-platform clean-install/load/export conformance (#52)",
        "needs: [node-native-packages, node-facade]",
        "darwin-arm64",
        "blacksmith-6vcpu-macos-15",
        "darwin-x64",
        "linux-arm64",
        "blacksmith-4vcpu-ubuntu-2404-arm",
        "linux-x64",
        "blacksmith-4vcpu-ubuntu-2404",
        "win32-x64",
        "blacksmith-4vcpu-windows-2025",
        "node-platform-${{ matrix.platform }}",
        "npm install --no-audit --no-fund",
        "Expected optional dependency @curatelabs/xyg-node-",
        "scripts/node_release_smoke.mjs",
        "XYG_EXPECTED_ABI",
    )
    _require_job_contains(
        errors,
        jobs,
        "node-unsupported-windows-arm64",
        "release",
        "Windows-host simulated-arm64 unsupported-platform conformance (#52)",
        "needs: [node-facade]",
        "runs-on: blacksmith-4vcpu-windows-2025",
        'resolveNativeLibrary({ platform: "win32", arch: "arm64", env: {}, requireFn })',
        "optional package resolution must not run",
        "XYG Node does not support Windows arm64",
        "Remediation:",
    )
    _require_job_contains(
        errors,
        jobs,
        "release-cohort-linux-x64",
        "release",
        "exact Python, Node, browser, and clean-consumer release cohort (#54)",
        "needs: [wheels, browser-package, node-native-packages, node-facade, node-clean-install]",
        "dist-manylinux_2_17_x86_64",
        "node-platform-linux-x64",
        "scripts/verify_release_cohort.py",
        "if: startsWith(github.ref, 'refs/tags/xyg-v')",
        '--commit "$GITHUB_SHA"',
        "python3 -m venv",
        "npm install --no-audit --no-fund",
        "@curatelabs/xyg/xyg-wasm.wasm",
        "release-conformance-linux-x64",
        "retention-days: 30",
    )
    _require_job_contains(
        errors,
        jobs,
        "publish-npm",
        "release",
        "complete guarded npm trusted-publishing set (#52)",
        "needs: [node-native-packages, node-facade, browser-package, publish]",
        "runs-on: ubuntu-latest",
        "environment: npm",
        "id-token: write",
        "actions/checkout@",
        "npm@^11.5.1",
        "pattern: node-*",
        "python3 scripts/publish_node_packages.py node-dist --check",
        "name: browser-package",
        "XYG_ALLOW_NPM_PUBLISH",
        "XYG_ALLOW_PYPI_PUBLISH",
        "refs/tags/xyg-v",
        'scripts/publish_node_packages.py node-dist --tag "$GITHUB_REF_NAME"',
    )
    npm_publish = _named_step_blocks(jobs.get("publish-npm", "")).get(
        "Publish native and browser packages before the facade (OIDC)", ""
    )
    npm_gate, npm_gate_unsafe = _step_direct_key_values(npm_publish, "if")
    if npm_gate_unsafe or npm_gate != [GITHUB_RELEASE_GATE]:
        errors.append(
            "release npm upload must use both registry opt-ins, the XYG tag, and the non-dry-run gate"
        )
    if not _has_safe_release_dry_run_input(text):
        errors.append(
            "release workflow missing a unique boolean workflow_dispatch dry-run input "
            "defaulting to true, so a manual run never accidentally publishes"
        )
    publish = jobs.get("publish", "")
    _require_step_contains(
        errors,
        publish,
        "Real publish must run from an XYG release tag",
        "real-publish tag guard",
        REAL_PUBLISH_STEP_GATE,
        "refs/tags/xyg-v*) ;;",
        "exit 1",
    )
    _require_step_contains(
        errors,
        publish,
        "Release version gate (tag == CHANGELOG)",
        "real-publish changelog gate",
        REAL_PUBLISH_STEP_GATE,
        "scripts/check_release_version.py",
    )
    repo_guard_values, repo_guard_unsafe = _direct_yaml_key_values(publish, "if", indent=4)
    if repo_guard_unsafe or repo_guard_values != [PUBLISH_REPOSITORY_GUARD]:
        errors.append(
            "release publish job must carry the fork repository guard "
            f"(`if: {PUBLISH_REPOSITORY_GUARD}`) as its only job-level condition — "
            "this fork publishes PyPI project `xyg` from CurateLabs/xyg only, so no "
            "other repository slug may reach the PyPI upload (#13)"
        )
    if "password:" in publish or "api-token" in publish:
        errors.append("release publish job should use trusted publishing, not a PyPI token")
    if "pypa/gh-action-pypi-publish@" in publish and not _step_carries_publish_gate(
        publish, "pypa/gh-action-pypi-publish@"
    ):
        errors.append(
            "release publish job's PyPI upload step is not gated by the dry-run "
            f"predicate on the step itself (`{PYPI_PUBLISH_GATE}`) — a missing or "
            "unrelated condition (e.g. `if: always()`) would let a manual "
            "dispatch publish unintentionally"
        )
    github_release = jobs.get("github-release", "")
    _require_job_contains(
        errors,
        jobs,
        "github-release",
        "post-PyPI/npm GitHub Release with browser artifacts",
        "needs: [publish, publish-npm]",
        "contents: write",
        "actions/download-artifact@",
        "pattern: dist-pyemscripten",
        "pattern: browser-package",
        "merge-multiple: true",
        "gh release create",
        "release-dist/*.whl release-dist/*.tgz",
        "--verify-tag",
        "--generate-notes",
        'parse_tag(os.environ["GITHUB_REF_NAME"]).stage',
        'if [ "$prerelease" = "true" ]; then',
        "release_args=(--prerelease --latest=false)",
        '"${release_args[@]}"',
    )
    if github_release.count("merge-multiple: true") < 2:
        errors.append(
            "release GitHub Release must flatten both the PyEmscripten wheel and browser "
            "package downloads with merge-multiple"
        )
    release_gate_values, release_gate_unsafe = _direct_yaml_key_values(
        github_release, "if", indent=4
    )
    if release_gate_unsafe or release_gate_values != [GITHUB_RELEASE_GATE]:
        errors.append(
            "release GitHub Release job must use both registry opt-ins, the XYG tag, "
            f"and the non-dry-run gate (`if: {GITHUB_RELEASE_GATE}`)"
        )
    return errors


def validate_all_workflows(
    ci_path: Path = DEFAULT_CI_WORKFLOW,
    codspeed_path: Path = DEFAULT_CODSPEED_WORKFLOW,
    release_path: Path = DEFAULT_RELEASE_WORKFLOW,
    final_review_path: Path = DEFAULT_FINAL_REVIEW_WORKFLOW,
    coderabbit_config_path: Path = DEFAULT_CODERABBIT_CONFIG,
    density_path: Path = DEFAULT_DENSITY_WORKFLOW,
    ruleset_path: Path = DEFAULT_RULESET,
) -> list[str]:
    return [
        *validate_workflow_hosting_policy(),
        *validate_merge_queue_ruleset(ruleset_path),
        *validate_ci_workflow(ci_path),
        *validate_codspeed_workflow(codspeed_path),
        *validate_density_workflow(density_path),
        *validate_final_review_policy(final_review_path, coderabbit_config_path),
        *validate_release_workflow(release_path),
    ]


def validate_workflow_hosting_policy(
    workflows_dir: Path = DEFAULT_WORKFLOWS_DIR,
) -> list[str]:
    """Keep workflows on Blacksmith and browser installs off apt mirrors."""
    errors: list[str] = []
    for path in sorted((*workflows_dir.glob("*.yml"), *workflows_dir.glob("*.yaml"))):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"cannot read workflow {path}: {exc}")
            continue
        if path.name == "binder.yml":
            on_block = _unique_mapping_block(text, "on", indent=0) or ""
            triggers = {
                key
                for indent, key, unsafe in _yaml_mapping_keys(on_block)
                if indent == 2 and not unsafe
            }
            if "pull_request" in triggers or not {"push", "workflow_dispatch"}.issubset(triggers):
                errors.append(f"{path} breadth workflow must run only on push/manual events")
        normalized_shell = re.sub(r"\\\s*\n\s*", " ", text)
        if re.search(
            r"playwright\s+install(?:\s+[^\n]*?)?\s+--with-deps(?:\s|$)",
            normalized_shell,
        ):
            errors.append(
                f"{path} Playwright install must not use --with-deps; "
                "install bounded browser-specific runtime dependencies separately"
            )
        if sum(line == "jobs:" for line in _yaml_code_lines(text)) != 1:
            errors.append(f"{path} must define one canonical block-style top-level jobs mapping")
            continue
        jobs_block = _unique_mapping_block(text, "jobs", indent=0)
        if jobs_block is None:
            errors.append(f"{path} must define one canonical block-style top-level jobs mapping")
            continue
        job_mappings = [
            parsed
            for line in _yaml_code_lines(jobs_block)
            if (parsed := _direct_yaml_mapping(line)) is not None and parsed[0] == 2
        ]
        job_keys = [entry for entry in _yaml_mapping_keys(jobs_block) if entry[0] == 2]
        if (
            not job_mappings
            or len(job_keys) != len(job_mappings)
            or any(unsafe or job_name is None for _indent, job_name, unsafe in job_keys)
            or any(
                unsafe or job_name is None or value.strip()
                for _indent, job_name, unsafe, value in job_mappings
            )
        ):
            errors.append(f"{path} every job must use a canonical block-style mapping")
            continue
        job_blocks = _job_blocks(text)
        if len(job_blocks) != len(job_mappings):
            errors.append(f"{path} every job must be structurally visible to runner validation")
            continue
        for job_name, block in job_blocks.items():
            runner_values, runner_unsafe = _direct_yaml_key_values(block, "runs-on", indent=4)
            if runner_unsafe or len(runner_values) != 1:
                errors.append(f"{path} job {job_name} must declare one direct runs-on value")
                continue
            runner = runner_values[0]
            codspeed_hosted = (
                path.name == "codspeed.yml"
                and job_name == "benchmarks"
                and runner == CODSPEED_HOSTED_RUNNER
            )
            # npm trusted publishing only accepts GitHub-hosted runners. Keep
            # this exception pinned to the OIDC-only release job; build/test
            # work remains on the approved Blacksmith fleet (#52).
            npm_trusted_hosted = (
                path.name == "publish.yaml"
                and job_name == "publish-npm"
                and _is_structural_npm_trusted_job(block, runner)
            )
            if (
                runner != "${{ matrix.os }}"
                and runner not in ALLOWED_BLACKSMITH_RUNNERS
                and not codspeed_hosted
                and not npm_trusted_hosted
            ):
                errors.append(
                    f"{path} job {job_name} must use an approved Blacksmith runner or the "
                    f"dedicated CodSpeed hosted runner, got {runner}"
                )
            if runner != "${{ matrix.os }}":
                continue
            matrix_runners, dynamic_axis = _matrix_os_values(block)
            if dynamic_axis:
                errors.append(
                    f"{path} job {job_name} matrix.os must be a static list, not an expression"
                )
            if not matrix_runners and not dynamic_axis:
                errors.append(
                    f"{path} job {job_name} uses matrix.os without statically "
                    "enumerated runner values"
                )
            for runner in matrix_runners:
                if runner not in ALLOWED_BLACKSMITH_RUNNERS:
                    errors.append(
                        f"{path} job {job_name} matrix runner must use an approved "
                        f"Blacksmith label, got {runner}"
                    )
        publish_npm_block = job_blocks.get("publish-npm", "")
        publish_npm_runners, publish_npm_runner_unsafe = _direct_yaml_key_values(
            publish_npm_block, "runs-on", indent=4
        )
        trusted_npm_alias = (
            path.name == "publish.yaml"
            and not publish_npm_runner_unsafe
            and publish_npm_runners == ["ubuntu-latest"]
            and _is_structural_npm_trusted_job(publish_npm_block, publish_npm_runners[0])
            and sum(line.strip() == "runs-on: ubuntu-latest" for line in _yaml_code_lines(text))
            == 1
        )
        for lineno, line in enumerate(text.splitlines(), start=1):
            code = line.split("#", 1)[0]
            if re.search(
                r"(?:^|[\s,{\[\"'])"
                r"(?:ubuntu-latest|ubuntu-24\.04-arm|windows-latest|macos-latest|macos-\d+(?:-large)?)"
                r"(?=$|[\s,}\]\"'])",
                code,
            ):
                if trusted_npm_alias and code.strip() == "runs-on: ubuntu-latest":
                    continue
                errors.append(
                    f"{path}:{lineno} workflow contains a GitHub-hosted runner alias; "
                    "use an explicit Blacksmith label"
                )
    return errors


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "workflow",
        nargs="?",
        type=Path,
        help="legacy CI workflow path override; checks CI only when provided",
    )
    parser.add_argument("--ci-workflow", type=Path, default=DEFAULT_CI_WORKFLOW)
    parser.add_argument("--codspeed-workflow", type=Path, default=DEFAULT_CODSPEED_WORKFLOW)
    parser.add_argument("--release-workflow", type=Path, default=DEFAULT_RELEASE_WORKFLOW)
    parser.add_argument("--ruleset", type=Path, default=DEFAULT_RULESET)
    parser.add_argument(
        "--live-readback",
        metavar="OWNER/REPO",
        help="also compare the live ruleset and branch protection (read-only `gh api`) "
        "with the checked-in contract",
    )
    parser.add_argument("--ci-only", action="store_true")
    parser.add_argument("--codspeed-only", action="store_true")
    parser.add_argument("--release-only", action="store_true")
    args = parser.parse_args(argv)

    selected_modes = [args.ci_only, args.codspeed_only, args.release_only]
    if sum(1 for selected in selected_modes if selected) > 1:
        parser.error("--ci-only, --codspeed-only, and --release-only are mutually exclusive")

    if args.workflow is not None:
        errors = validate_ci_workflow(args.workflow)
        checked = [args.workflow]
    elif args.ci_only:
        errors = validate_ci_workflow(args.ci_workflow)
        checked = [args.ci_workflow]
    elif args.codspeed_only:
        errors = validate_codspeed_workflow(args.codspeed_workflow)
        checked = [args.codspeed_workflow]
    elif args.release_only:
        errors = validate_release_workflow(args.release_workflow)
        checked = [args.release_workflow]
    else:
        errors = validate_all_workflows(
            args.ci_workflow,
            args.codspeed_workflow,
            args.release_workflow,
            ruleset_path=args.ruleset,
        )
        checked = [
            args.ci_workflow,
            args.codspeed_workflow,
            DEFAULT_DENSITY_WORKFLOW,
            DEFAULT_FINAL_REVIEW_WORKFLOW,
            args.release_workflow,
            args.ruleset,
        ]

    if args.live_readback:
        try:
            errors = [
                *errors,
                *validate_live_readback(_gh_api_fetch(args.live_readback), args.ruleset),
            ]
        except (OSError, subprocess.CalledProcessError, ValueError) as exc:
            errors = [*errors, f"live read-back of {args.live_readback} failed: {exc}"]

    if errors:
        print(
            "Workflow verification failed for " + ", ".join(str(path) for path in checked) + ":",
            file=sys.stderr,
        )
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Workflow verification OK: " + ", ".join(str(path) for path in checked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
