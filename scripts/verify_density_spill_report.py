#!/usr/bin/env python3
"""Validate the distinct colored-spill host/kernel slice; never certify #11.

Policy constants are pinned here independently of report/harness declarations.
Authority additionally requires trusted *ambient* scheduled/manual main context;
self-reported GitHub fields alone cannot promote a local control.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

MAX_RSS = 12 * 1024**3
MAX_DISK = 4 * 1024**3
TILE_BUDGET = 16 * 1024**2
TIMING_SCOPE = (
    "tile_store_paint ABI wrapper only; excludes host dispatch, stats, parsing and oracles"
)
AUTH_KEYS = (
    "GITHUB_ACTIONS",
    "GITHUB_REF",
    "GITHUB_EVENT_NAME",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_SHA",
    "XYG_DENSITY_100M_AUTHORITY",
)


class InvalidReport(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise InvalidReport(message)


def integer(value: Any, low: int = 0, high: int = 2**63) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def number(value: Any, low: float = 0, high: float = math.inf) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and low <= value <= high
    )


def digest(value: Any, length: int = 64) -> bool:
    return (
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is not None
    )


def hash_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def check_stats(value: dict) -> None:
    require(
        all(
            integer(value[key])
            for key in ("hit", "miss", "resident_bytes", "spilled_bytes", "budget_bytes")
        ),
        "native stats must be nonnegative integers",
    )
    require(value["spilled_bytes"] > 0, "native stats must prove actual spill")
    require(
        value["resident_bytes"] <= value["budget_bytes"] == TILE_BUDGET
        and value["over_budget"] is False,
        "native tile residency/budget changed or exceeded",
    )


def check_frame(frame: dict, pool: dict, domain: list, base: int) -> dict:
    require(
        integer(frame["generation"], 1) and integer(frame["level"], 0, int(math.log2(base))),
        "invalid generation/served level",
    )
    require(
        frame["flags"] == 1 and frame["target_level"] == frame["level"],
        "frame must carry color and a completed uncoarsened level decision",
    )
    require(
        frame["opacity"] == 1 and number(frame["window_max"]) and number(frame["source_log_max"]),
        "invalid frame color/normalization",
    )
    require(digest(frame["packet_sha256"]), "invalid frame hash")
    inventory = frame["inventory"]
    require(
        isinstance(inventory, list) and 0 < len(inventory) <= 256, "frame inventory must be bounded"
    )
    kept, total, missing, active_count = {}, 0, 0, 0
    saw_retained = False
    reply = 128 + len(inventory) * 96
    for tile in inventory:
        key = tile["key"]
        require(
            isinstance(key, list) and len(key) == 3 and all(integer(v) for v in key),
            "invalid tile key",
        )
        key = tuple(key)
        require(
            key not in kept and key[0] <= int(math.log2(base)), "duplicate/out-of-range tile key"
        )
        side = max(1, math.ceil((base >> key[0]) / 256))
        require(key[1] < side and key[2] < side, "tile coordinates exceed source level")
        w, h = tile["width"], tile["height"]
        require(integer(w, 3, 258) and integer(h, 3, 258), "invalid guttered tile shape")
        require(isinstance(tile["active"], bool), "active must be boolean")
        require(
            not (saw_retained and tile["active"]), "active tiles must precede retained inventory"
        )
        saw_retained |= not tile["active"]
        active_count += int(tile["active"])
        require(
            not tile["active"] or key[0] == frame["level"],
            "active tile level differs from served level",
        )
        require(digest(tile["sha256"]), "invalid tile hash")
        body = tile["body_bytes"]
        require(integer(body) and body in (0, w * h * 4), "invalid RGBA tile body bytes")
        if body:
            require(tile["active"], "retained-only tile cannot transfer a body")
            missing += 1
        else:
            require(pool.get(key) == tile["sha256"], "omitted tile not held in observed inventory")
        geometry = tile["geometry"]
        require(
            isinstance(geometry, list)
            and len(geometry) == 8
            and all(number(v, -1e300, 1e300) for v in geometry),
            "invalid tile framing",
        )
        require(all(geometry[i + 1] > geometry[i] for i in (0, 2, 4, 6)), "empty tile geometry")
        require(
            domain[0] <= geometry[4] < geometry[5] <= domain[1]
            and domain[2] <= geometry[6] < geometry[7] <= domain[3],
            "interior tile framing outside canonical domain",
        )
        kept[key] = tile["sha256"]
        total += w * h * 4
        reply += body
    require(active_count > 0, "frame has no active tiles")
    require(
        frame["transferred_tiles"] == missing and frame["reply_bytes"] == reply,
        "frame transfer totals do not match inventory",
    )
    require(
        frame["gpu_bytes"] == total <= frame["gpu_budget_bytes"] == 512 * 512 * 4 * 8,
        "GPU budget changed/exceeded",
    )
    return kept


def check_latency(pans: list, zooms: list, authority: bool) -> tuple[float, float]:
    require(
        len(pans) >= 20 and len(zooms) >= 8 and all(number(value) for value in pans + zooms),
        "missing/invalid raw latency samples",
    )
    ordered = sorted(pans)
    position = (len(ordered) - 1) * 0.95
    lo = int(position)
    p95 = ordered[lo] + (ordered[min(lo + 1, len(ordered) - 1)] - ordered[lo]) * (position - lo)
    if authority:
        require(
            p95 < 16 and all(value < 50 for value in zooms),
            "authority hard latency gate failed: pan p95<16ms and each zoom<50ms",
        )
    return p95, max(zooms)


def validate(
    report: Any,
    *,
    expected_sha: str | None = None,
    environ: dict[str, str] | None = None,
    artifact_root: Path | None = None,
) -> list[str]:
    try:
        _validate(
            report, expected_sha, dict(os.environ) if environ is None else environ, artifact_root
        )
    except (
        InvalidReport,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        AttributeError,
        OSError,
    ) as exc:
        return [str(exc) or type(exc).__name__]
    return []


def _validate(
    r: dict, expected_sha: str | None, environ: dict[str, str], artifact_root: Path | None
) -> None:
    require(
        r["schema_version"] == 2
        and r["report_kind"] == "density-colored-spill"
        and r["workload"] == "colored-spill",
        "must be a distinct colored-spill report; resident reports cannot be relabeled",
    )
    require(
        r["status"] == "ok" and r["scope"] == "host-kernel-only",
        "report must pass the explicitly limited host-kernel slice",
    )
    authority, n = r["authority"], r["point_count"]
    require(isinstance(authority, bool) and integer(n, 1), "invalid authority/count")
    require(
        n == 100_000_000 if authority else n <= 1_000_000,
        "authority must be exactly 100M; controls at most 1M",
    )
    env = r["environment"]
    require(
        env["xy_backend"] == "native" and digest(env["git"]["commit"], 40),
        "environment must identify native backend and source commit",
    )
    require(isinstance(env["git"]["dirty"], bool), "environment must record worktree cleanliness")
    if expected_sha:
        require(env["git"]["commit"] == expected_sha, "source commit differs from expected SHA")
    context = r["authority_context"]
    require(set(context) == set(AUTH_KEYS), "missing authority context")
    if authority:
        require(expected_sha is not None, "authority verifier requires externally supplied --sha")
        require(
            environ.get("GITHUB_ACTIONS") == "true"
            and environ.get("GITHUB_REF") == "refs/heads/main"
            and environ.get("GITHUB_EVENT_NAME") in {"schedule", "workflow_dispatch"}
            and environ.get("XYG_DENSITY_100M_AUTHORITY") == "1",
            "authority requires trusted ambient GitHub scheduled/manual main capability; report cannot self-authorize",
        )
        require(
            all(context[k] == environ.get(k) for k in AUTH_KEYS),
            "authority context differs from ambient run",
        )
        require(
            all(
                re.fullmatch(r"[1-9][0-9]*", context[k] or "")
                for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
            ),
            "invalid authority run identity",
        )
        require(
            context["GITHUB_SHA"] == env["git"]["commit"] and env["git"]["dirty"] is False,
            "authority source must be the clean actual run SHA",
        )
    limits = r["limits"]
    require(
        integer(limits["max_tree_rss_bytes"], 1, MAX_RSS)
        and integer(limits["max_disk_bytes"], 1, MAX_DISK)
        and number(limits["timeout_seconds"], 0.001, 3600),
        "fixed resource ceilings exceeded/changed",
    )
    tree = r["process_tree"]
    require(
        integer(tree["peak_rss_bytes"], 1, limits["max_tree_rss_bytes"])
        and integer(tree["peak_temp_bytes"], n * 24, limits["max_disk_bytes"])
        and number(tree["elapsed_seconds"], 0.001, limits["timeout_seconds"]),
        "measured supervisor resources missing/exceeded",
    )
    require(
        integer(tree["worker_peak_rss_bytes"], 1, limits["max_tree_rss_bytes"])
        and integer(tree["observed_process_count"], 1),
        "supervisor must observe worker RSS/processes",
    )
    if env["platform"]["system"] == "Darwin":
        require(
            tree["rss_observer"] == "darwin-ps-sampled-group-rss"
            and tree["worker_rss_measurement"] == "sampled-high-water"
            and tree["sample_interval_seconds"] == 0.05,
            "Darwin requires sampled group RSS observation, not VmHWM",
        )
    require(
        r["latency_policy"]
        == {
            "pan_p95_ms": 16,
            "each_zoom_ms": 50,
            "enforcement": "hard" if authority else "advisory",
        },
        "latency budgets are pinned independently at pan p95<16ms / each zoom<50ms",
    )
    require(r["timing_scope"] == TIMING_SCOPE, "timing must exclude browser and oracles")
    source = r["source"]
    require(
        source["generator"] == "diagonal-band-two-color-v1"
        and source["backing"] == "mmap-f64"
        and source["bytes"] == n * 24
        and integer(source["chunk_points"], 1, 1_000_000),
        "invalid chunked canonical source",
    )
    require(
        source["colormap"] == [[240, 50, 40], [20, 90, 230]]
        and source["color_mode"] == "continuous-mapped-to-u8-index",
        "missing prescribed color source",
    )
    for name in ("x", "y", "color"):
        require(
            source["columns"][name]["bytes"] == n * 8 and digest(source["columns"][name]["sha256"]),
            "invalid source column bytes/hash",
        )
    for phase in ("admission", "after_build", "after_samples"):
        for name in ("x", "y", "color"):
            require(
                r["mapping_inventory"][phase][name]
                == {"bytes": n * 8, "pointer_equal": True, "mapped": True},
                "canonical mapping was copied/demoted",
            )
    inputs = r["native_build_inputs"]
    require(len(inputs) == 1, "must observe exactly one native color build")
    require(
        inputs[0]["x_pointer_equal"] is True
        and inputs[0]["y_pointer_equal"] is True
        and inputs[0]["index_bytes"] == n
        and inputs[0]["lut_bytes"] == 1024
        and digest(inputs[0]["index_sha256"])
        and digest(inputs[0]["lut_sha256"]),
        "native build must borrow canonical x/y with bounded indexed colors",
    )
    d = r["decisions"]
    require(
        r["request_path"]
        == ("product-density-view" if authority else "native-tile-painter-fixture"),
        "request path must distinguish native tile fixtures from product authority",
    )
    base = 4096 if authority else 2048
    require(
        d["base_dim"] == base
        and d["screen"] == [512, 512]
        and d["tile_budget_bytes"] == TILE_BUDGET
        and d["force_spill"] is True,
        "base/screen/tile resource decision changed",
    )
    require(
        d["pyramid_min_points"] == (2_000_000 if authority else 1)
        and d["production_pyramid_min_points"] == 2_000_000
        and d["test_override"] is (not authority),
        "bounded threshold override must be explicit; authority uses production eligibility",
    )
    require(
        d["color_source"] == "u8-index+RGBA-LUT"
        and d["color_index_max_bytes"] == n
        and d["color_lut_bytes"] == 1024,
        "color storage decision changed",
    )
    require(
        d["control_prewarm"] is (not authority)
        and d["first_payload_policy"] == "production-native",
        "control prewarm must not relabel native first paint",
    )
    domain = d["domain"]
    require(
        isinstance(domain, list)
        and len(domain) == 4
        and all(number(v, -1e300, 1e300) for v in domain)
        and domain[0] < domain[1]
        and domain[2] < domain[3],
        "invalid canonical domain",
    )
    initial = r["initial_payload"]
    require(
        initial["mean_color"] is True
        and initial["canonical_f64_buffers"] == 0
        and integer(initial["bytes"], 1, 4 * 1024**2),
        "first payload must be bounded colored density",
    )
    if authority:
        require(
            initial["reduction"] == "pyramid-count"
            and re.fullmatch(r"pyramid-L[0-9]+(?:-upsampled)?-tiles", initial["binning"]),
            "authority first paint must use spilled pyramid",
        )
    else:
        require(
            initial["reduction"] == "bin2d" and initial["binning"] == "exact",
            "bounded first paint must retain the production exact route",
        )
    samples, fresh = r["samples"], r["fetch_all"]
    require(
        isinstance(samples, list)
        and len(samples) == 32
        and isinstance(fresh, list)
        and len(fresh) == len(samples),
        "raw samples missing: require 24 pans and 8 actual adjacent zooms plus fetch-all replay",
    )
    require(
        r["allocation_proof"]
        == "canonical pointer identity and retained-cache accounting; not a complete transient allocator audit",
        "allocation proof must state its transient-audit limitation",
    )
    spill_file = r["spill_file"]
    require(
        integer(spill_file["bytes"], 1)
        and digest(spill_file["sha256"])
        and spill_file["bytes"] == r["final_stats"]["spilled_bytes"],
        "actual spill file bytes/hash missing",
    )
    seed = r["seed"]
    check_stats(seed["stats"])
    last_stats = seed["stats"]
    pool = check_frame(seed, {}, domain, base)
    previous = seed
    pan_times, zoom_times = [], []
    cached_count = uncached_count = 0
    for index, (sample, oracle) in enumerate(zip(samples, fresh, strict=True)):
        kind = "pan" if index < 24 else "zoom"
        require(sample["kind"] == kind and number(sample["kernel_ms"]), "invalid raw kernel sample")
        offset = ([0, 1, 2, 3, 4, 3, 2, 1][index % 8] / 16) if kind == "pan" else 0.125
        span = 0.5 if kind == "pan" or index % 2 else 0.25
        yoffset = 0 if kind == "pan" else 0.125
        window = [
            domain[0] + offset * (domain[1] - domain[0]),
            domain[0] + (offset + span) * (domain[1] - domain[0]),
            domain[2] + yoffset * (domain[3] - domain[2]),
            domain[2] + (yoffset + span) * (domain[3] - domain[2]),
        ]
        require(
            sample["window"] == window,
            "sample is not the deterministic overlapping pan/zoom journey",
        )
        require(
            sample["generation"] == seed["generation"],
            "store generation changed during immutable journey",
        )
        pool = check_frame(sample, pool, domain, base)
        require(
            sample["previous_level"] == previous["level"]
            and abs(sample["level"] - previous["level"]) == (1 if kind == "zoom" else 0),
            "zoom must actually change to an adjacent level; pan keeps level",
        )
        require(
            sample["binning"] == f"pyramid-L{sample['level']}-tiles"
            and sample["reduction"] == "pyramid-count",
            "sample lost spilled host route",
        )
        check_stats(sample["stats"])
        require(
            all(sample["stats"][key] >= last_stats[key] for key in ("hit", "miss"))
            and sample["stats"]["spilled_bytes"] == spill_file["bytes"],
            "per-call native counters regressed or spill size changed",
        )
        last_stats = sample["stats"]
        check_stats(oracle["stats"])
        check_frame(oracle, {}, domain, base)

        def active(frame):
            return [
                {k: v for k, v in tile.items() if k != "body_bytes"}
                for tile in frame["inventory"]
                if tile["active"]
            ]

        require(
            active(sample) == active(oracle)
            and all(
                sample[k] == oracle[k]
                for k in ("generation", "level", "opacity", "source_log_max", "window_max")
            ),
            "cached/fetch-all active hashes, framing or exposure differ",
        )
        cached_count += sample["transferred_tiles"]
        uncached_count += oracle["transferred_tiles"]
        (pan_times if kind == "pan" else zoom_times).append(sample["kernel_ms"])
        previous = sample
    require(
        0 < cached_count < uncached_count, "cache must transfer strictly fewer tiles than fetch-all"
    )
    p95, zoom_max = check_latency(pan_times, zoom_times, authority)
    require(
        math.isclose(r["pan_p95_ms"], p95, abs_tol=1e-9) and r["zoom_max_ms"] == zoom_max,
        "latency summary differs from actual raw samples",
    )
    oracle = r["count_color_oracle"]
    require(
        oracle["method"] == "chunked-numpy-histogram-linear-srgb"
        and oracle["grid_dim"] == 64
        and oracle["level"] == int(math.log2(base // 64))
        and oracle["count"] == oracle["expected_count"] == n
        and oracle["max_count_error"] == 0,
        "independent counts oracle failed",
    )
    require(
        oracle["rgb_tolerance"] == 2
        and integer(oracle["max_rgb_error"], 0, 2)
        and integer(oracle["occupied_cells"], 1, 4096)
        and oracle["nonopaque_occupied_cells"] == 0
        and digest(oracle["counts_sha256"])
        and digest(oracle["rgba_sha256"]),
        "independent mean-color oracle missing/failed",
    )
    last_stats = samples[-1]["stats"]
    for oracle_frame in fresh:
        require(
            all(oracle_frame["stats"][key] >= last_stats[key] for key in ("hit", "miss"))
            and oracle_frame["stats"]["spilled_bytes"] == spill_file["bytes"],
            "fetch-all native counters regressed or spill size changed",
        )
        last_stats = oracle_frame["stats"]
    check_stats(r["final_stats"])
    require(
        r["final_stats"]["hit"] > 0 and r["final_stats"]["miss"] > 0,
        "native hit/miss counters must be observed",
    )
    memory = r["host_memory_report"]
    require(
        memory["canonical_bytes"] == 0
        and memory["canonical_mapped_bytes"] == n * 16
        and memory["channel_bytes"] == n * 8
        and memory["bin_color_bytes"] == 0
        and memory["pyramid_spilled_bytes"] == r["final_stats"]["spilled_bytes"]
        and integer(memory["pyramid_bytes"], 0, TILE_BUDGET),
        "host memory must retain mappings, actual spill and no row color cache",
    )
    p = r["provenance"]
    for name in ("source", "harness"):
        files = p[name + "_files"]
        require(
            isinstance(files, dict)
            and bool(files)
            and all(isinstance(path, str) and digest(value) for path, value in files.items()),
            "invalid source/harness file hash",
        )
        require(p[name + "_sha256"] == hash_json(files), "source/harness manifest hash mismatch")
        if artifact_root is not None:
            root = artifact_root.resolve()
            for name, expected in files.items():
                path = (root / name).resolve()
                require(path.is_relative_to(root), "artifact hash path escapes root")
                require(
                    hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                    f"artifact file hash mismatch: {name}",
                )
    require(
        {
            "benchmarks/bench_density_e2e.py",
            "benchmarks/_density_spill.py",
            "scripts/verify_density_spill_report.py",
            "benchmarks/environment.py",
            "Cargo.lock",
            "package-lock.json",
            "uv.lock",
            "rust-toolchain.toml",
        }
        <= set(p["harness_files"]),
        "harness hashes incomplete",
    )
    require(
        {"python/xyg/interaction.py", "crates/xyg-engine/src/tile_store.rs", "js/src/60_entries.ts"}
        <= set(p["source_files"]),
        "source hashes incomplete",
    )
    if artifact_root is not None:
        root = artifact_root.resolve()
        for kind in ("native", "client"):
            path = (root / p[kind + "_path"]).resolve()
            require(
                path.is_relative_to(root)
                and hashlib.sha256(path.read_bytes()).hexdigest() == p[kind + "_sha256"],
                f"artifact {kind} hash mismatch",
            )
    require(
        p["environment_sha256"] == hash_json(env)
        and digest(p["native_sha256"])
        and digest(p["client_sha256"])
        and integer(p["native_abi"], 1),
        "invalid environment/native/client hashes",
    )
    require(
        r["browser"]["status"] == "not-run"
        and isinstance(r["browser"]["reason"], str)
        and len(r["browser"]["reason"]) > 20,
        "host/kernel report must explicitly leave browser evidence incomplete",
    )
    cleanup = r["cleanup"]
    require(
        all(
            cleanup[key] is True
            for key in (
                "figure_released",
                "spill_store_released",
                "mmap_closed",
                "tile_budget_restored",
                "temp_tree_removed",
            )
        )
        and cleanup["spill_files_remaining"] == []
        and cleanup["worker_exit_code"] == 0
        and cleanup["orphan_pids_after_reap"] == [],
        "native/mmap/process/temp cleanup incomplete",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--sha")
    parser.add_argument("--artifact-root", type=Path)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text())
    except (OSError, ValueError) as exc:
        print(f"cannot read colored-spill report: {exc}", file=sys.stderr)
        return 1
    errors = validate(report, expected_sha=args.sha, artifact_root=args.artifact_root)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    if not errors:
        print(
            f"colored-spill host/kernel slice OK ({report['point_count']} rows); browser and whole #11 remain open"
        )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
