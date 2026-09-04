#!/usr/bin/env python3
"""Execute and verify the versioned cross-host ABI delegation corpus (#874)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "spec" / "design" / "host-delegation-corpus.json"
DEFAULT_OUTPUT = ROOT / "target" / "host-delegation-report.json"
PARITY_MATRIX = ROOT / "spec" / "design" / "dual-host-parity.json"


class DelegationFailure(RuntimeError):
    """The executable evidence does not satisfy the reviewed corpus contract."""


def _git_value(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)
    return proc.stdout.strip()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DelegationFailure(f"{path} must contain a JSON object")
    return value


def _load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DelegationFailure(f"invalid trace JSONL at line {line_number}: {exc}") from exc
        if not isinstance(event, dict):
            raise DelegationFailure(f"trace line {line_number} is not an object")
        events.append(event)
    return events


def _event_shape(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: event[key]
        for key in ("symbol", "arguments", "outcome", "returned_size", "error_type")
        if key in event
    }


def verify_journey(contract: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate one journey and return its deterministic, privacy-bounded summary."""

    journey_id = str(contract["id"])
    selected = [event for event in events if event.get("journey") == journey_id]
    if not selected:
        raise DelegationFailure(f"{journey_id}: no executed ABI calls were observed")
    forbidden = [event for event in selected if event.get("type") == "host_fallback"]
    if forbidden:
        raise DelegationFailure(f"{journey_id}: observed host-local canonical fallback")
    bad_outcomes = [event for event in selected if event.get("outcome") != "ok"]
    if bad_outcomes:
        raise DelegationFailure(
            f"{journey_id}: observed non-success ABI outcomes: "
            f"{sorted({str(event.get('outcome')) for event in bad_outcomes})}"
        )

    by_host: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in selected:
        host = event.get("host")
        if host not in {"python", "node"}:
            raise DelegationFailure(f"{journey_id}: invalid trace host {host!r}")
        by_host[str(host)].append(event)

    expected_hosts = [str(host) for host in contract["hosts"]]
    missing_hosts = sorted(set(expected_hosts) - set(by_host))
    if missing_hosts:
        raise DelegationFailure(f"{journey_id}: missing executed hosts {missing_hosts}")

    required = set(map(str, contract["required_shared_symbols"]))
    observed_by_host = {
        host: {str(event["symbol"]) for event in host_events}
        for host, host_events in by_host.items()
    }
    for host in expected_hosts:
        missing = sorted(required - observed_by_host[host])
        if missing:
            raise DelegationFailure(
                f"{journey_id}: {host} did not execute required Rust symbols {missing}"
            )

    hosts: dict[str, Any] = {}
    for host in sorted(expected_hosts):
        host_events = by_host[host]
        counts = Counter(str(event["symbol"]) for event in host_events)
        shaped = sorted(
            (_event_shape(event) for event in host_events),
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
        encoded = json.dumps(shaped, sort_keys=True, separators=(",", ":")).encode()
        hosts[host] = {
            "call_count": len(host_events),
            "symbols": dict(sorted(counts.items())),
            "shape_sha256": hashlib.sha256(encoded).hexdigest(),
        }

    return {
        "id": journey_id,
        "surfaces": contract["surfaces"],
        **({"scope_note": contract["scope_note"]} if "scope_note" in contract else {}),
        "output_oracle": contract["output_oracle"],
        "required_shared_symbols": sorted(required),
        "observed_shared_symbols": sorted(
            set.intersection(*(observed_by_host[h] for h in expected_hosts))
        ),
        "hosts": hosts,
    }


def _run_corpus(corpus: dict[str, Any], trace_path: Path) -> None:
    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = str(ROOT / "python")
    if "XYG_NATIVE_LIB" not in base_env:
        if sys.platform == "win32":
            library_name = "xyg_core.dll"
        elif sys.platform == "darwin":
            library_name = "libxyg_core.dylib"
        else:
            library_name = "libxyg_core.so"
        base_env["XYG_NATIVE_LIB"] = str(ROOT / "target" / "release" / library_name)
    for command in corpus.get("control_commands", []):
        print("==> executable delegation: negative controls", flush=True)
        control_env = dict(base_env)
        control_env.pop("XYG_ABI_TRACE_FILE", None)
        control_env.pop("XYG_ABI_TRACE_JOURNEY", None)
        control_env.pop("XYG_ABI_TRACE_FAULT", None)
        proc = subprocess.run(
            command,
            cwd=ROOT,
            env=control_env,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise DelegationFailure(
                f"negative control command failed ({proc.returncode}): {' '.join(command)}\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )

    base_env["XYG_ABI_TRACE_FILE"] = str(trace_path)
    base_env.pop("XYG_ABI_TRACE_FAULT", None)

    for journey in corpus["journeys"]:
        journey_id = str(journey["id"])
        env = {**base_env, "XYG_ABI_TRACE_JOURNEY": journey_id}
        print(f"==> executable delegation: {journey_id}", flush=True)
        for command in journey["commands"]:
            proc = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise DelegationFailure(
                    f"{journey_id}: command failed ({proc.returncode}): {' '.join(command)}\n"
                    f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
                )


def build_report(corpus: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "python"))
    from xyg._abi_generated import ABI_VERSION, SIGNATURE_SHA256

    parity = _load_json(PARITY_MATRIX)
    admitted = {str(item["kind"]) for item in parity["mark_kinds"]}
    public_journeys = [item for item in corpus["journeys"] if item["id"] == "public-marks"]
    if len(public_journeys) != 1:
        raise DelegationFailure("corpus must define exactly one public-marks journey")
    covered = set(map(str, public_journeys[0]["surfaces"]))
    if covered != admitted:
        raise DelegationFailure(
            "public-marks inventory differs from dual-host-parity.json: "
            f"missing={sorted(admitted - covered)}, extra={sorted(covered - admitted)}"
        )
    commit = os.environ.get("GITHUB_SHA") or _git_value("rev-parse", "HEAD")
    summaries = [verify_journey(journey, events) for journey in corpus["journeys"]]
    return {
        "schema": "xyg.host-delegation-report/v1",
        "corpus_schema": corpus["schema"],
        "corpus_version": corpus["version"],
        "abi_version": ABI_VERSION,
        "abi_signature_sha256": SIGNATURE_SHA256,
        "commit": commit,
        "negative_controls": ["dead-call", "host-local-canonical", "native-fault"],
        "public_mark_inventory": sorted(admitted),
        "uncovered": corpus.get("uncovered", []),
        "journeys": summaries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        corpus = _load_json(args.corpus)
        with tempfile.TemporaryDirectory(prefix="xyg-delegation-") as temp:
            trace_path = Path(temp) / "trace.jsonl"
            trace_path.touch()
            _run_corpus(corpus, trace_path)
            report = build_report(corpus, _load_events(trace_path))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (DelegationFailure, OSError, subprocess.SubprocessError) as exc:
        print(f"host delegation corpus failed: {exc}", file=sys.stderr)
        return 1
    print(f"host delegation corpus: OK ({args.output})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
