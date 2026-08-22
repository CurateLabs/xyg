from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_ownership.py"
    spec = importlib.util.spec_from_file_location("verify_ownership", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFY = _module()


def _fixture(tmp_path: Path, *, source: str = "pass\n") -> tuple[Path, set[str]]:
    path = "python/xyg/example.py"
    source_path = tmp_path / path
    source_path.parent.mkdir(parents=True)
    source_path.write_text(source, encoding="utf-8")
    human_path = tmp_path / "spec/design/ownership-audit.md"
    human_path.parent.mkdir(parents=True)
    human_path.write_text(
        "<!-- xyg-ownership-schema: 1 -->\n\n"
        "## File ledger\n\n"
        "| Path | Owner | Policy | Disposition | Follow-up |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"| `{path}` | Python | `host` | `keep-host` | — |\n\n"
        "## Contributor rule\n",
        encoding="utf-8",
    )
    policy = {
        "current_owner": "Python",
        "disposition": "keep-host",
        "follow_up_issue": None,
        "allowed_responsibilities": ["Host API."],
        "forbidden_responsibilities": ["Engine policy."],
        "forbidden_patterns": [{"pattern": "FORBIDDEN", "instruction": "Move it to Rust."}],
        "rationale": "Host shell.",
    }
    manifest = {
        "schema_version": 1,
        "human_audit": "spec/design/ownership-audit.md",
        "scope": {"tracked_only": True, "roots": [{"prefix": "python/xyg/", "extensions": [".py"]}]},
        "policies": {"host": policy},
        "files": [
            {
                "path": path,
                "current_owner": "Python",
                "policy": "host",
                "disposition": "keep-host",
                "follow_up_issue": None,
                "rationale": "Host shell.",
            }
        ],
    }
    manifest_path = tmp_path / "spec/design/ownership-audit.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, {path}


def _errors(tmp_path: Path, tracked: set[str]) -> list[str]:
    return VERIFY.validate(
        tmp_path, tmp_path / "spec/design/ownership-audit.json", tracked_files=tracked
    )


def test_real_repository_ownership_audit_is_complete() -> None:
    root = Path(__file__).resolve().parents[1]
    assert VERIFY.validate(root, root / "spec/design/ownership-audit.json") == []


def test_missing_production_file_is_named(tmp_path: Path) -> None:
    _fixture(tmp_path)
    tracked = {"python/xyg/example.py", "python/xyg/new_algorithm.py"}
    errors = _errors(tmp_path, tracked)
    assert any(
        "unclassified production source: python/xyg/new_algorithm.py" in error for error in errors
    )


def test_duplicate_classification_is_named(tmp_path: Path) -> None:
    manifest_path, tracked = _fixture(tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["files"].append(dict(data["files"][0]))
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    assert any(
        "duplicate classification: python/xyg/example.py" in error
        for error in _errors(tmp_path, tracked)
    )


def test_stale_classification_is_named(tmp_path: Path) -> None:
    _fixture(tmp_path)
    assert any(
        "stale classification: python/xyg/example.py" in error for error in _errors(tmp_path, set())
    )


def test_malformed_manifest_is_actionable(tmp_path: Path) -> None:
    manifest_path, tracked = _fixture(tmp_path)
    manifest_path.write_text("{", encoding="utf-8")
    errors = _errors(tmp_path, tracked)
    assert errors and "manifest malformed at line 1" in errors[0]


def test_forbidden_host_behavior_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path, source="FORBIDDEN = 'parallel layout'\n")
    errors = _errors(tmp_path, {"python/xyg/example.py"})
    assert any(
        "boundary violation: python/xyg/example.py" in error and "Move it to Rust" in error
        for error in errors
    )


def test_human_ledger_cannot_silently_drift(tmp_path: Path) -> None:
    _fixture(tmp_path)
    human = tmp_path / "spec/design/ownership-audit.md"
    human.write_text(
        "<!-- xyg-ownership-schema: 1 -->\n## File ledger\n## Contributor rule\n", encoding="utf-8"
    )
    errors = _errors(tmp_path, {"python/xyg/example.py"})
    assert any("human audit stale" in error and "python/xyg/example.py" in error for error in errors)
