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
    summary["producer_completed_warm_windows"] = sum(
        c["warm_steps_producer_ok"] for c in summary["cells"]
    )
    summary["producer_completed_empty_controls"] = sum(
        (c["empty_control"] or {}).get("ok") is True for c in summary["cells"]
    )
    diagnosis["xyg_host_blocker"] = {
        "failed_cells": 6,
        "phase": "host_prepare",
        "return_code": 1,
        "message": "ModuleNotFoundError: No module named 'benchmarks'",
        "historical_source": "benchmarks/_ux_comparison_host.py:58 imports benchmarks._ux_comparison_oracle; benchmarks/bench_density_comparison.py:171-185 launches _ux_live_host.py by file path. Existing sibling-module fallback does not cover this import.",
        "inference": "Package-qualified import is unavailable in the script-launched child context shown in stderr. No local reproduction or source arrays were executed.",
        "C_H_E_grid_proof": "UNAVAILABLE for all six XYG cells: no META or browser checkpoints. Source manifests retain C/H and exclusions, but no XYG E/emitted/adopted grid proof was obtained.",
    }
    mismatches = []
    for cell in report["results"]:
        if cell["arm"] != "datashader-aggregate":
            continue
        cps = cell["transport"]["checkpoints"]
        paints = [("visible-complete", cell["cold"])]
        paints += [(f"step-{i}", step) for i, step in enumerate(cell["steps"])]
        paints += [("empty-control", cell["empty_control"])]
        for label, paint in paints:
            observed = cps[label]["host_observation"]["last_output"]
            adopted = output(paint)
            if observed["grid_shape"] != adopted["raster_shape"]:
                mismatches.append(
                    {
                        **{key: cell[key] for key in ("n", "arm", "repetition")},
                        "checkpoint": label,
                        "host_last_output": observed,
                        "browser_adopted_output": adopted,
                        "paint": {key: value for key, value in paint.items() if key != "state"},
                    }
                )
    diagnosis["bokeh_backend_binding_blocker"] = {
        "hosted_message": "INVALID: Bokeh actual backend output mismatch",
        "historical_verifier": "scripts/verify_density_comparison_report.py:725-731 requires SHA256, backend grid shape equal to adopted raster shape and positive backend revision.",
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "interpretation": "At four 100M/1B cold checkpoints, latest observed backend grid is 512x512 at revision 2 while adopted browser output remains 400x400 at revision 0. Backend mass/count equals N. This is an output-binding mismatch; it does not alone establish wrong counts or a Datashader capacity limit. A cold adoption/observation sequencing disagreement is a hypothesis, not a verified cause.",
        "scope": "Metadata predicate inspection only; no local large-report authority verifier, tolerance change, retry or repair.",
    }
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
        "scope": "Actual values observed in retained hosted log and raw report; original dispatch request payload is not exposed by these REST responses. Requested inputs separately retained in dispatch-receipt.json.",
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
