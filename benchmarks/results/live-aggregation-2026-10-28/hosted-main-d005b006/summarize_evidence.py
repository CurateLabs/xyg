#!/usr/bin/env python3
"""Extract descriptive metadata; never execute the source/oracle or certify acceptance."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import statistics
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def output(checkpoint: dict) -> dict:
    return (checkpoint.get("state") or {}).get("output") or {}


def main() -> None:
    path = next(HERE.glob("density-comparison-*.json.gz"))
    raw = gzip.decompress(path.read_bytes())
    report = json.loads(raw)
    summary = {
        "report": path.name,
        "decoded_report_sha256": hashlib.sha256(raw).hexdigest(),
        "scope": "Descriptive retained metadata only. Hosted verifier log is authoritative; no competitive acceptance or winner.",
        "hosted_verifier_output": (HERE / "hosted-verifier-output.txt").read_text(),
        "quantiles": "Per repetition, all recorded steps: median p50; p95 at sorted index floor(.95*(n-1)); no best-of-N selection.",
        "producer_status_counts": dict(Counter(c["status"] for c in report["results"])),
        **{k: report.get(k) for k in ("environment", "argv", "runtime", "limits", "sources")},
        "cells": [],
    }
    run = json.loads((HERE / "workflow-run.json").read_bytes())
    jobs = json.loads((HERE / "jobs-attempt-1.json").read_bytes())["jobs"]
    verifier = summary["hosted_verifier_output"]
    summary["hosted_outcome"] = {
        "run_id": run["id"],
        "attempt": run["run_attempt"],
        "source_commit": run["head_sha"],
        "run_status": run["status"],
        "run_conclusion": run["conclusion"],
        "created_at": run["created_at"],
        "run_started_at": run["run_started_at"],
        "updated_at": run["updated_at"],
        "jobs": [
            {
                key: job.get(key)
                for key in (
                    "id",
                    "name",
                    "status",
                    "conclusion",
                    "started_at",
                    "completed_at",
                    "html_url",
                )
            }
            for job in jobs
        ],
        "hosted_structural_verifier_accepted": (
            run["status"] == "completed"
            and run["conclusion"] == "success"
            and "Valid evidence:" in verifier
            and "INVALID:" not in verifier
        ),
        "scope": "Actual hosted verifier decision only; no winner, competitive or whole-#108 acceptance.",
    }
    diagnosis = {
        "scope": "Metadata-only extraction, no native/oracle execution or benchmark repetition.",
        "failures": [],
        "xyg_count_grid_checkpoints": [],
    }
    for cell in report["results"]:
        identity = {k: cell[k] for k in ("n", "arm", "repetition")}
        steps = cell.get("steps", [])
        checkpoints = [("cold", cell.get("cold", {}))]
        checkpoints += [(f"step-{s.get('index', i)}", s) for i, s in enumerate(steps)]
        checkpoints += [("empty_control", cell.get("empty_control", {}))]
        outputs = [output(s) for s in steps]
        times = sorted(
            s["paint_stable_ms"]
            for s in steps
            if isinstance(s.get("paint_stable_ms"), (int, float))
        )
        meta = cell.get("host_meta") or {}
        item = {
            **identity,
            "producer_status": cell["status"],
            **{
                k: cell.get(k)
                for k in (
                    "comparison_status",
                    "phase",
                    "reason",
                    "error",
                    "host_peak_rss_bytes",
                    "browser_peak_rss_bytes",
                    "host_prepare_wall_ms",
                )
            },
            "source_identity": {
                key: (meta.get("source") or {}).get(key)
                for key in ("actual_rows", "dtype", "sha256_x_then_y", "columns")
            }
            if meta.get("source")
            else None,
            "source_identity_matches_shared_manifest": (
                meta["source"]
                == {
                    key: value
                    for key, value in report["sources"].get(str(cell["n"]), {}).items()
                    if key not in ("creation_wall_ms", "source_peak_rss_bytes")
                }
            )
            if meta.get("source")
            else None,
            "host_build_ms": meta.get("build_ms"),
            "host_meta": {key: value for key, value in meta.items() if key != "source"},
            "warm_steps_recorded": len(steps),
            "warm_steps_producer_ok": sum(s.get("ok") is True for s in steps),
            "cold": cell.get("cold"),
            "empty_control": cell.get("empty_control"),
            "warm_paint_stable_ms": {
                "p50": statistics.median(times),
                "p95": times[int(0.95 * (len(times) - 1))],
                "max": max(times),
                "sample_count": len(times),
            }
            if times
            else None,
            "output_modes": dict(Counter(o.get("mode") for o in outputs)),
            "exact_fallback_steps": sum(o.get("exact_fallback") is True for o in outputs),
            "raster_shapes": sorted(
                {tuple(o["raster_shape"]) for o in outputs if o.get("raster_shape")}
            ),
            "binning": sorted({o["binning"] for o in outputs if o.get("binning")}),
            "warm_application_body_bytes": (
                sum(s.get("application_body_bytes", {}).get("total_bytes", 0) for s in steps)
                if steps
                else None
            ),
            "transport": {
                "scope": cell.get("transport", {}).get("scope"),
                "cold_cumulative": cell.get("transport", {})
                .get("checkpoints", {})
                .get("visible-complete", {})
                .get("cdp_application_bytes"),
                "terminal_cumulative": cell.get("transport", {})
                .get("checkpoints", {})
                .get("terminal", {})
                .get("cdp_application_bytes"),
                "empty_control_delta": cell.get("empty_control", {}).get("application_body_bytes"),
            }
            if cell.get("transport")
            else None,
            "last_host_observation": next(
                (s["host_observation"] for s in reversed(steps) if s.get("host_observation")), None
            ),
        }
        summary["cells"].append(item)
        if cell["status"] != "ok":
            diagnosis["failures"].append({**identity, "cell": cell})
        if cell["arm"] == "xy-density":
            for label, cp in checkpoints:
                o = output(cp)
                if not cp:
                    continue
                a = o.get("numerical_oracle")
                diagnosis["xyg_count_grid_checkpoints"].append(
                    {
                        **identity,
                        "checkpoint": label,
                        "producer_ok": cp.get("ok"),
                        "expected_count": cp.get("expected_count"),
                        "output_visible": o.get("visible"),
                        "mode": o.get("mode"),
                        "exact_fallback": o.get("exact_fallback"),
                        "numerical_oracle": a,
                        "exact_source_count": a.get("exact_source_count") if a else None,
                        "half_open_source_count": a.get("half_open_source_count") if a else None,
                        "expected_visible": a.get("expected_visible") if a else None,
                        "emitted_visible_matches_expected": o.get("visible")
                        == a.get("expected_visible")
                        if a
                        else None,
                        "encoded_hashes_equal": a.get("expected_encoded_sha256")
                        == a.get("actual_encoded_sha256")
                        if a and a.get("expected_encoded_sha256")
                        else None,
                        "adopted_hashes_equal": a.get("expected_decoded_sha256")
                        == a.get("adopted_decoded_sha256")
                        if a and a.get("expected_decoded_sha256")
                        else None,
                    }
                )
    numerical = {
        "scope": "Arithmetic summaries of recorded metadata, not source/grid recomputation or local verifier execution.",
        "checkpoints": len(diagnosis["xyg_count_grid_checkpoints"]),
        "cells": [],
    }
    for cell in report["results"]:
        if cell["arm"] != "xy-density":
            continue
        records = [
            x
            for x in diagnosis["xyg_count_grid_checkpoints"]
            if (x["n"], x["repetition"]) == (cell["n"], cell["repetition"])
        ]
        records = [x for x in records if x["numerical_oracle"]]
        arrays = [x["numerical_oracle"] for x in records]
        prep = (
            cell.get("transport", {})
            .get("checkpoints", {})
            .get("visible-complete", {})
            .get("host_observation", {})
            .get("numerical_oracle_preparation")
        )
        numerical["cells"].append(
            {
                "n": cell["n"],
                "arm": cell["arm"],
                "repetition": cell["repetition"],
                "recorded_checkpoints": len(records),
                "preparation": prep,
                "count_methods": dict(Counter(a["count_method"] for a in arrays)),
                "max_abs_emitted_minus_exact_source_count": max(
                    (abs(a["emitted_visible"] - a["exact_source_count"]) for a in arrays),
                    default=None,
                ),
                "max_boundary_mass_bound": max(
                    (a["boundary_mass_bound"] for a in arrays), default=None
                ),
                "max_upper_boundary_excluded": max(
                    (a["upper_boundary_excluded"] for a in arrays), default=None
                ),
                "all_recorded_oracles_passed": all(a["passed"] is True for a in arrays)
                if arrays
                else None,
                "all_recorded_emitted_match_expected": all(
                    x["emitted_visible_matches_expected"] for x in records
                )
                if records
                else None,
                "all_recorded_encoded_hashes_match": all(x["encoded_hashes_equal"] for x in records)
                if records
                else None,
                "all_recorded_adopted_hashes_match": all(x["adopted_hashes_equal"] for x in records)
                if records
                else None,
                "all_recorded_source_hashes_match": all(
                    a["source_sha256"] == report["sources"][str(cell["n"])]["sha256_x_then_y"]
                    for a in arrays
                )
                if arrays
                else None,
                "validation_wall_ms_sum": sum(a["validation_wall_ms"] for a in arrays)
                if arrays
                else None,
                "validation_http_request_bytes_sum": sum(
                    a["validation_http_request_bytes"] for a in arrays
                )
                if arrays
                else None,
            }
        )
    (HERE / "numerical-summary.json").write_text(json.dumps(numerical, indent=2) + "\n")
    summary["producer_completed_warm_windows"] = sum(
        c["warm_steps_producer_ok"] for c in summary["cells"]
    )
    summary["producer_completed_empty_controls"] = sum(
        (c["empty_control"] or {}).get("ok") is True for c in summary["cells"]
    )
    diagnosis["hosted_verifier_output"] = summary["hosted_verifier_output"]
    diagnosis["interpretation"] = (
        "Original failure cells and XYG numerical metadata only. "
        "No local benchmark, source recreation or large independent verifier. "
        "A producer ok status alone does not establish hosted acceptance."
    )
    log = gzip.decompress(next(HERE.glob("job-*.log.gz")).read_bytes())
    inputs, environment, extracted = {}, None, []
    for line in log.splitlines(keepends=True):
        text = line.decode()
        matched = re.search(
            r"\s(INPUT_(?:EXPERIMENT|SIZES|ARMS|REPETITIONS|TIMEOUT|MEMORY_GIB|HARDWARE_GL)): (.*)",
            text,
        )
        if matched:
            inputs[matched[1]] = matched[2].strip()
            extracted.append(line)
        if b'"xy_backend": "native"' in line:
            environment = json.loads(text[text.index("{") :])
            extracted.append(line)
    (HERE / "hosted-inputs-and-environment.txt").write_bytes(b"".join(extracted))
    actual = {
        "scope": "Actual values observed in retained hosted log and raw report; original dispatch request payload is not exposed by these REST responses. Requested values are stated in README; no original dispatch request body is claimed.",
        "log_input_environment": inputs,
        "report_argv": report["argv"],
        "hosted_environment_check": environment,
        "report_environment": report["environment"],
        "limits": report["limits"],
        "source_counts_windows": {n: source["windows"] for n, source in report["sources"].items()},
    }
    (HERE / "actual-values.json").write_text(json.dumps(actual, indent=2) + "\n")
    for name, value in (("summary.json", summary), ("diagnosis.json", diagnosis)):
        (HERE / name).write_text(json.dumps(value, indent=2) + "\n")
    print(
        json.dumps(
            {
                "statuses": summary["producer_status_counts"],
                "warm_windows": summary["producer_completed_warm_windows"],
                "empty_controls": summary["producer_completed_empty_controls"],
            }
        )
    )


if __name__ == "__main__":
    main()
