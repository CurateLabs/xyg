#!/usr/bin/env python3
"""Validate the hard (non-timing) contracts of a #876 density report."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, TypeGuard

SCHEMA_VERSION = 1
AUTHORITY_POINTS = 100_000_000
CANONICAL_POINT_COUNTS = {250_000, 1_000_000, AUTHORITY_POINTS}
MAX_CHUNK_POINTS = 1_000_000
PYRAMID_MIN_POINTS = 2_000_000
PYRAMID_BASE_DIM = 2048
PYRAMID_MAX_DIM = 16384
PYRAMID_TARGET_POINTS_PER_CELL = 16.0
PYRAMID_RESIDENT_BYTES = 512 * (1 << 20)
MAX_PAYLOAD_BYTES = 4 * 1024 * 1024
MAX_RSS_BYTES = 12 * 1024**3
MAX_DISK_BYTES = 4 * 1024**3
MAX_TIMEOUT_SECONDS = 3600
MAX_SOURCE_RATIO = 0.10
MAX_TRANSITION_UPLOAD_CALLS = 64


def _sha256_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _positive_int(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonempty_string(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


def _finite_nonnegative(value: Any) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _finite_number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _resident_pyramid_relation(binning: Any, reduction: Any, points: Any) -> bool:
    match = re.fullmatch(r"pyramid-L(\d+)", binning) if isinstance(binning, str) else None
    if match is None or reduction != "pyramid-count" or not _positive_int(points):
        return False
    _, base_dim = _expected_pyramid_residency(points)
    return 0 <= int(match.group(1)) <= int(math.log2(base_dim))


def _initial_density_relation(binning: Any, reduction: Any, points: Any) -> bool:
    if not _positive_int(points):
        return False
    if points < PYRAMID_MIN_POINTS:
        return binning == "exact" and reduction == "bin2d"
    return _resident_pyramid_relation(binning, reduction, points)


def _refine_density_relation(binning: Any, reduction: Any, points: Any) -> bool:
    if not _positive_int(points):
        return False
    if points < PYRAMID_MIN_POINTS:
        return binning == "bin2d-oversized" and reduction == "bin2d-oversized"
    return _resident_pyramid_relation(binning, reduction, points)


def _expected_pyramid_residency(points: Any) -> tuple[int, int]:
    if not _positive_int(points):
        return -1, 0
    if points < PYRAMID_MIN_POINTS:
        return 0, 0
    ideal_side = math.sqrt(max(2.0, points / PYRAMID_TARGET_POINTS_PER_CELL))
    power_of_two = 1 << max(1, math.ceil(math.log2(ideal_side)))
    base_dim = min(PYRAMID_MAX_DIM, max(PYRAMID_BASE_DIM, power_of_two))
    resident_bytes = 0
    dim = base_dim
    while True:
        resident_bytes += dim * dim * 4
        if dim == 1:
            break
        dim >>= 1
    return resident_bytes, base_dim


def validate(report: Any, *, expected_sha: str | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["report must be an object"]
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if report.get("report_kind") != "density-e2e":
        errors.append("report_kind must be density-e2e")
    if report.get("status") != "ok":
        errors.append("status must be ok")
    points = report.get("point_count")
    if not _positive_int(points) or points not in CANONICAL_POINT_COUNTS:
        errors.append("point_count must be a canonical 250k, 1M, or 100M lane")
    authority = report.get("authority")
    if not isinstance(authority, bool):
        errors.append("authority must be boolean")
    elif authority is not (points == AUTHORITY_POINTS):
        errors.append(f"authority must be true if and only if point_count is {AUTHORITY_POINTS}")

    environment = report.get("environment")
    if not isinstance(environment, dict):
        errors.append("environment must be an object")
    else:
        git = environment.get("git")
        if (
            not isinstance(git, dict)
            or re.fullmatch(r"[0-9a-f]{40}", str(git.get("commit", ""))) is None
        ):
            errors.append("environment.git.commit must be a full lowercase hexadecimal SHA")
        elif expected_sha is not None and git["commit"] != expected_sha:
            errors.append(f"environment.git.commit must equal {expected_sha}")
        if isinstance(git, dict) and git.get("dirty") is not False:
            errors.append("environment.git.dirty must be false")
        if environment.get("xy_backend") != "native":
            errors.append("environment.xy_backend must be native")
        if (
            re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z",
                str(environment.get("generated_at_utc", "")),
            )
            is None
        ):
            errors.append("environment.generated_at_utc must be an ISO-8601 UTC timestamp")
        python = environment.get("python")
        if not isinstance(python, dict) or not all(
            _nonempty_string(python.get(key)) for key in ("version", "implementation", "compiler")
        ):
            errors.append("environment.python must identify the Python runtime")
        platform = environment.get("platform")
        if (
            not isinstance(platform, dict)
            or not all(
                _nonempty_string(platform.get(key))
                for key in ("system", "release", "version", "machine")
            )
            or not isinstance(platform.get("processor"), str)
        ):
            errors.append("environment.platform must identify the host platform")
        if not _positive_int(environment.get("cpu_count")):
            errors.append("environment.cpu_count must be measured")
        packages = environment.get("package_versions")
        if not isinstance(packages, dict) or not _nonempty_string(packages.get("xyg")):
            errors.append("environment.package_versions.xyg must identify the package")
        executables = environment.get("executables")
        if not isinstance(executables, dict) or not all(
            _nonempty_string(executables.get(key)) for key in ("node", "rustc", "cargo", "chromium")
        ):
            errors.append("environment.executables must identify Node, Rust, Cargo, and Chromium")
        if environment.get("browser_renderer") != "software-gl":
            errors.append("environment.browser_renderer must record the bounded software GL mode")
    if authority is True and expected_sha is None:
        errors.append("authority report verification requires --sha")
    if expected_sha is not None and re.fullmatch(r"[0-9a-f]{40}", expected_sha) is None:
        errors.append("--sha must be a full lowercase hexadecimal git SHA")
    authority_context = report.get("authority_context")
    if not isinstance(authority_context, dict):
        errors.append("authority_context must be an object")
    else:
        for key in ("github_ref", "github_event_name"):
            if authority_context.get(key) is not None and not _nonempty_string(
                authority_context.get(key)
            ):
                errors.append(f"authority_context.{key} must be a string or null")
        if not isinstance(authority_context.get("capability"), bool):
            errors.append("authority_context.capability must be boolean")
        if authority is True and (
            authority_context.get("github_ref") != "refs/heads/main"
            or authority_context.get("github_event_name") not in {"schedule", "workflow_dispatch"}
            or authority_context.get("capability") is not True
        ):
            errors.append("authority context must prove the explicit main-only workflow capability")
        if authority is False and authority_context.get("capability") is not False:
            errors.append("non-authority reports must not hold the 100M capability")

    source = report.get("source")
    if not isinstance(source, dict):
        errors.append("source must be an object")
        source_bytes = 0
    else:
        source_bytes = source.get("bytes")
        if not _positive_int(source_bytes):
            errors.append("source.bytes must be a positive integer")
            source_bytes = 0
        if source.get("backing") != "mmap-f64":
            errors.append("source.backing must be mmap-f64")
        if source.get("generator") != "diagonal-band-v1":
            errors.append("source.generator must be diagonal-band-v1")
        chunk_points = source.get("chunk_points")
        if not _positive_int(chunk_points) or chunk_points > MAX_CHUNK_POINTS:
            errors.append(f"source.chunk_points must be between 1 and {MAX_CHUNK_POINTS}")
        x_bytes = source.get("x_bytes")
        y_bytes = source.get("y_bytes")
        if not _positive_int(x_bytes) or not _positive_int(y_bytes):
            errors.append("source x/y byte counts must be positive integers")
        elif x_bytes + y_bytes != source_bytes:
            errors.append("source component bytes must sum to source.bytes")
        for name in ("x_sha256", "y_sha256"):
            value = source.get(name)
            if not _sha256_digest(value):
                errors.append(f"source.{name} must be a SHA-256 digest")
        if _positive_int(points):
            if x_bytes != points * 8 or y_bytes != points * 8:
                errors.append("each source file must contain exactly point_count f64 values")
            if source_bytes != points * 16:
                errors.append("source.bytes must equal two f64 columns at point_count")

    limits = report.get("limits")
    payload = report.get("payload")
    if not isinstance(limits, dict):
        errors.append("limits must be an object")
        limits = {}
    limit_contracts = {
        "timeout_seconds": MAX_TIMEOUT_SECONDS,
        "max_tree_rss_bytes": MAX_RSS_BYTES,
        "max_disk_bytes": MAX_DISK_BYTES,
        "first_payload_bytes": MAX_PAYLOAD_BYTES,
        "refine_payload_bytes": MAX_PAYLOAD_BYTES,
        "source_ratio": MAX_SOURCE_RATIO,
        "derived_cache_ratio": MAX_SOURCE_RATIO,
    }
    limit_values: dict[str, float] = {}
    for name, maximum in limit_contracts.items():
        value = limits.get(name)
        if not _finite_nonnegative(value) or value <= 0 or value > maximum:
            errors.append(f"limits.{name} must be positive and no greater than {maximum}")
            limit_values[name] = -1
        else:
            limit_values[name] = float(value)
    if not isinstance(payload, dict):
        errors.append("payload must be an object")
        payload = {}
    payload_bytes = payload.get("bytes")
    if not _positive_int(payload_bytes):
        errors.append("payload.bytes must be a positive integer")
    spec_json_bytes = payload.get("spec_json_bytes")
    wire_bytes = payload.get("wire_bytes")
    if not _positive_int(spec_json_bytes):
        errors.append("payload.spec_json_bytes must be a positive integer")
    if (
        not _positive_int(wire_bytes)
        or not _positive_int(payload_bytes)
        or not _positive_int(spec_json_bytes)
        or wire_bytes != payload_bytes + spec_json_bytes
    ):
        errors.append("payload.wire_bytes must equal spec JSON plus raw paint buffers")
    elif wire_bytes > limit_values["first_payload_bytes"]:
        errors.append("payload.wire_bytes exceeds the recorded first-payload ceiling")
    if payload.get("canonical_f64_buffers") != 0:
        errors.append("ordinary first paint must ship zero canonical f64 buffers")
    classes = payload.get("classes")
    if not isinstance(classes, dict) or not classes:
        errors.append("payload.classes must inventory every split buffer")
    else:
        class_buffers = 0
        class_bytes = 0
        for name, entry in classes.items():
            if not isinstance(name, str):
                errors.append("payload.classes keys must be strings")
                continue
            if name in {"f64", "unknown", "unreferenced"} or any(
                part in {"f64", "unknown", "unreferenced"} for part in name.split("+")
            ):
                errors.append(f"payload.classes contains forbidden class {name!r}")
            if not isinstance(entry, dict) or not _positive_int(entry.get("buffers")):
                errors.append(f"payload.classes[{name!r}] has invalid buffer count")
                continue
            if not _positive_int(entry.get("bytes")):
                errors.append(f"payload.classes[{name!r}] has invalid byte count")
                continue
            class_buffers += entry["buffers"]
            class_bytes += entry["bytes"]
        if class_buffers != payload.get("buffer_count") or class_bytes != payload_bytes:
            errors.append("payload.classes must sum exactly to buffer_count and payload.bytes")
        if "u8" not in classes or "offset-f32" not in classes:
            errors.append("first payload must contain u8 density and offset-f32 sample classes")
    raw_ratio = payload.get("raw_source_ratio")
    computed_raw_ratio = (
        payload_bytes / source_bytes if _positive_int(payload_bytes) and source_bytes else -1
    )
    if not _finite_nonnegative(raw_ratio) or not math.isclose(
        raw_ratio, computed_raw_ratio, rel_tol=1e-12, abs_tol=1e-15
    ):
        errors.append("payload raw-buffer source ratio must match measured bytes")
    ratio = payload.get("source_ratio")
    computed_ratio = wire_bytes / source_bytes if _positive_int(wire_bytes) and source_bytes else -1
    if (
        not _finite_nonnegative(ratio)
        or not math.isclose(ratio, computed_ratio, rel_tol=1e-12, abs_tol=1e-15)
        or computed_ratio > limit_values["source_ratio"]
    ):
        errors.append("payload wire source ratio exceeds its hard ceiling")
    semantics = payload.get("semantics")
    initial_expected = {
        "trace_count": 1,
        "trace_id": 0,
        "kind": "scatter",
        "tier": "density",
        "n_points": points,
        "visible": points,
        "encoding": "log-u8",
        "sample_mode": "sampled",
        "sample_visible": points,
    }
    if not isinstance(semantics, dict) or any(
        semantics.get(key) != value for key, value in initial_expected.items()
    ):
        errors.append("initial payload must preserve native density tier and source counts")
    elif not _initial_density_relation(
        semantics.get("binning"), semantics.get("reduction"), points
    ):
        errors.append("initial payload must use its scale-required density route")
    elif (
        not _positive_int(semantics.get("grid_width"))
        or not _positive_int(semantics.get("grid_height"))
        or semantics.get("grid_cells") != semantics["grid_width"] * semantics["grid_height"]
        or semantics.get("n_marks") != semantics.get("grid_cells")
        or not _positive_int(semantics.get("sample_points"))
        or semantics["sample_points"] > semantics["n_marks"]
    ):
        errors.append("initial native density grid and sample counts must be conserved")
    count_oracle = report.get("count_oracle")
    if not isinstance(count_oracle, dict):
        errors.append("count_oracle must be an object")
    else:
        oracle_width = count_oracle.get("grid_width")
        oracle_height = count_oracle.get("grid_height")
        expected_oracle_backend = (
            "native-bin2d"
            if _positive_int(points) and points < PYRAMID_MIN_POINTS
            else "native-resident-pyramid"
        )
        recomposed_count = count_oracle.get("recomposed_count")
        recomposed_absolute_error = count_oracle.get("recomposed_absolute_error")
        computed_recomposed_error = (
            abs(recomposed_count - points)
            if _finite_nonnegative(recomposed_count) and _positive_int(points)
            else math.inf
        )
        if (
            count_oracle.get("backend") != expected_oracle_backend
            or count_oracle.get("expected_count") != points
            or count_oracle.get("observed_count") != points
            or not _finite_nonnegative(recomposed_count)
            or recomposed_count <= 0
            or not _finite_nonnegative(recomposed_absolute_error)
            or not math.isclose(
                recomposed_absolute_error,
                computed_recomposed_error,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            or computed_recomposed_error >= 0.5
            or count_oracle.get("match") is not True
            or not _positive_int(oracle_width)
            or not _positive_int(oracle_height)
            or count_oracle.get("grid_bytes") != oracle_width * oracle_height * 4
            or count_oracle.get("grid_bytes", MAX_PAYLOAD_BYTES + 1) > MAX_PAYLOAD_BYTES
            or not _sha256_digest(count_oracle.get("grid_sha256"))
            or not isinstance(semantics, dict)
            or oracle_width != semantics.get("grid_width")
            or oracle_height != semantics.get("grid_height")
        ):
            errors.append(
                "native count oracle must equal point_count exactly and f32 compose must "
                "conserve it within a sub-point bound"
            )
        product_link = count_oracle.get("product_link")
        expected_route = (
            "exact-bin2d"
            if _positive_int(points) and points < PYRAMID_MIN_POINTS
            else "resident-pyramid"
        )
        expected_pyramid_bytes, expected_base_dim = _expected_pyramid_residency(points)
        expected_level = None
        if isinstance(semantics, dict) and isinstance(semantics.get("binning"), str):
            level_match = re.fullmatch(r"pyramid-L(\d+)", semantics["binning"])
            if level_match is not None:
                expected_level = int(level_match.group(1))
        emitted_index = (
            product_link.get("emitted_buffer_index") if isinstance(product_link, dict) else None
        )
        expected_encoded_bytes = (
            oracle_width * oracle_height
            if _positive_int(oracle_width) and _positive_int(oracle_height)
            else -1
        )
        payload_hashes = payload.get("buffer_sha256")
        emitted_hash_is_payload = (
            isinstance(emitted_index, int)
            and not isinstance(emitted_index, bool)
            and emitted_index >= 0
            and isinstance(payload_hashes, list)
            and emitted_index < len(payload_hashes)
            and isinstance(product_link, dict)
            and product_link.get("emitted_buffer_sha256") == payload_hashes[emitted_index]
        )
        if (
            not isinstance(product_link, dict)
            or product_link.get("route") != expected_route
            or product_link.get("emitted_buffer_bytes") != expected_encoded_bytes
            or product_link.get("oracle_encoded_bytes") != expected_encoded_bytes
            or not _sha256_digest(product_link.get("emitted_buffer_sha256"))
            or not _sha256_digest(product_link.get("oracle_encoded_sha256"))
            or product_link.get("emitted_buffer_sha256")
            != product_link.get("oracle_encoded_sha256")
            or not emitted_hash_is_payload
            or not _finite_nonnegative(product_link.get("emitted_max"))
            or product_link.get("emitted_max") != product_link.get("oracle_max")
            or product_link.get("encoded_match") is not True
            or product_link.get("max_match") is not True
            or not isinstance(semantics, dict)
            or product_link.get("emitted_binning") != semantics.get("binning")
            or product_link.get("recomposed_binning") != semantics.get("binning")
            or product_link.get("pyramid_level") != expected_level
            or product_link.get("pyramid_base_dim") != expected_base_dim
            or (expected_route == "resident-pyramid" and expected_pyramid_bytes <= 0)
        ):
            errors.append(
                "native product-link oracle must reproduce the emitted density buffer, max, "
                "binning, and count"
            )
    deterministic = payload.get("determinism")
    if deterministic != {"checked": True, "match": True}:
        errors.append("payload determinism must be checked and matching")
    for name in ("spec_sha256", "fingerprint_sha256"):
        value = payload.get(name)
        if not _sha256_digest(value):
            errors.append(f"payload.{name} must be a SHA-256 digest")
    hashes = payload.get("buffer_sha256")
    if (
        not isinstance(hashes, list)
        or len(hashes) != payload.get("buffer_count")
        or not all(_sha256_digest(value) for value in hashes)
    ):
        errors.append("payload.buffer_sha256 must cover every buffer")

    memory = report.get("host_memory_report")
    if not isinstance(memory, dict):
        errors.append("host_memory_report must be an object")
    else:
        if memory.get("canonical_bytes") != 0:
            errors.append("mmap journey must not retain resident canonical f64 columns")
        if memory.get("canonical_mapped_bytes") != source_bytes:
            errors.append("host memory report must account for both mapped f64 sources")
        resident_derived = memory.get("resident_array_bytes")
        pyramid_derived = memory.get("pyramid_bytes")
        spilled_derived = memory.get("pyramid_spilled_bytes")
        expected_pyramid_bytes, expected_pyramid_base_dim = _expected_pyramid_residency(points)
        if (
            pyramid_derived != expected_pyramid_bytes
            or spilled_derived != 0
            or expected_pyramid_bytes > PYRAMID_RESIDENT_BYTES
        ):
            errors.append(
                "density route must retain the expected resident pyramid "
                f"(base_dim={expected_pyramid_base_dim}) without tile spill"
            )
        derived_limit = limit_values["derived_cache_ratio"]
        derived_valid = (
            _finite_nonnegative(resident_derived)
            and _finite_nonnegative(pyramid_derived)
            and _finite_nonnegative(spilled_derived)
        )
        # resident_array_bytes already includes the live resident pyramid.
        derived_bytes = resident_derived + spilled_derived if derived_valid else -1
        if (
            not derived_valid
            or not _finite_nonnegative(derived_limit)
            or derived_bytes > source_bytes * derived_limit
        ):
            errors.append("live derived caches must remain materially smaller than source")
    tree = report.get("process_tree")
    if not isinstance(tree, dict) or not _positive_int(tree.get("peak_rss_bytes")):
        errors.append("process_tree.peak_rss_bytes must be measured")
    elif tree["peak_rss_bytes"] > limit_values["max_tree_rss_bytes"]:
        errors.append("measured process-tree peak RSS exceeds its hard limit")
    if not isinstance(tree, dict) or not _positive_int(tree.get("peak_temp_bytes")):
        errors.append("process_tree.peak_temp_bytes must be measured")
    elif tree["peak_temp_bytes"] > limit_values["max_disk_bytes"]:
        errors.append("measured temporary-disk peak exceeds its hard limit")
    platform_system = None
    if isinstance(environment, dict) and isinstance(environment.get("platform"), dict):
        platform_system = environment["platform"].get("system")
    if platform_system == "Linux" and isinstance(tree, dict):
        observed = tree.get("observed_processes")
        observed_valid = isinstance(observed, list) and all(
            isinstance(entry, dict)
            and set(entry) == {"pid", "name"}
            and _positive_int(entry.get("pid"))
            and _nonempty_string(entry.get("name"))
            for entry in observed
        )
        observed_pids = [entry["pid"] for entry in observed] if observed_valid else []
        observed_names = [entry["name"] for entry in observed] if observed_valid else []
        peak_pids = tree.get("peak_pids")
        peak_valid = (
            isinstance(peak_pids, list)
            and all(_positive_int(pid) for pid in peak_pids)
            and len(set(peak_pids)) == len(peak_pids)
        )
        if (
            not observed_valid
            or len(observed_pids) < 2
            or len(set(observed_pids)) != len(observed_pids)
            or tree.get("observed_process_count") != len(observed_pids)
            or not peak_valid
            or tree.get("peak_process_count") != len(peak_pids)
            or not set(peak_pids).issubset(observed_pids)
            or not _positive_int(tree.get("max_live_process_count"))
            or tree["max_live_process_count"] < max(2, len(peak_pids))
        ):
            errors.append("Linux process inventory must consistently cover worker and descendants")
        browser_seen = any(
            "chrome" in name.lower() or "chromium" in name.lower() for name in observed_names
        )
        if tree.get("browser_process_observed") is not True or not browser_seen:
            errors.append("Linux process inventory must prove a Chromium descendant was sampled")
        worker_peak = tree.get("worker_peak_rss_bytes")
        if (
            not _positive_int(worker_peak)
            or not _positive_int(tree.get("peak_rss_bytes"))
            or worker_peak > tree["peak_rss_bytes"]
        ):
            errors.append("process-tree RSS must be at least the worker VmHWM backstop")

    phases = report.get("phases")
    required_phases = {
        "source_creation",
        "source_admission",
        "native_aggregation_build",
        "native_count_oracle",
        "determinism_rebuild",
        "browser_journey",
    }
    if not isinstance(phases, dict) or not required_phases.issubset(phases):
        errors.append(f"phases must include {sorted(required_phases)}")
    else:
        for name in required_phases:
            phase = phases[name]
            if not isinstance(phase, dict) or not _finite_nonnegative(phase.get("seconds")):
                errors.append(f"phases.{name}.seconds must be finite and nonnegative")

    host_refine = report.get("host_refine")
    if not isinstance(host_refine, dict) or not _finite_nonnegative(host_refine.get("seconds")):
        errors.append("host_refine.seconds must be measured")
    elif host_refine.get("audit_after_browser_done") is not True:
        errors.append("host refine audit must run after browser timing and paint complete")
    elif not _finite_nonnegative(host_refine.get("oracle_seconds")):
        errors.append("host_refine.oracle_seconds must be measured outside product response time")
    elif not _positive_int(host_refine.get("reply_bytes")):
        errors.append("host_refine.reply_bytes must be positive")
    elif not _positive_int(host_refine.get("wire_bytes")):
        errors.append("host_refine.wire_bytes must be positive")
    elif host_refine["wire_bytes"] < host_refine["reply_bytes"]:
        errors.append("host refine wire bytes cannot be smaller than raw reply buffers")
    elif host_refine["wire_bytes"] <= 4 * ((host_refine["reply_bytes"] + 2) // 3):
        errors.append("host refine wire bytes must include base64 JSON envelope overhead")
    elif host_refine["wire_bytes"] > limit_values["refine_payload_bytes"]:
        errors.append("host refine wire bytes exceed the hard refine-payload ceiling")
    if isinstance(host_refine, dict):
        raw_refine_ratio = host_refine.get("raw_source_ratio")
        computed_raw_refine_ratio = (
            host_refine.get("reply_bytes") / source_bytes
            if _positive_int(host_refine.get("reply_bytes")) and source_bytes
            else -1
        )
        if not _finite_nonnegative(raw_refine_ratio) or not math.isclose(
            raw_refine_ratio,
            computed_raw_refine_ratio,
            rel_tol=1e-12,
            abs_tol=1e-15,
        ):
            errors.append("host refine raw-buffer source ratio must match measured bytes")
        refine_ratio = host_refine.get("source_ratio")
        computed_refine_ratio = (
            host_refine.get("wire_bytes") / source_bytes
            if _positive_int(host_refine.get("wire_bytes")) and source_bytes
            else -1
        )
        if (
            not _finite_nonnegative(refine_ratio)
            or not math.isclose(refine_ratio, computed_refine_ratio, rel_tol=1e-12, abs_tol=1e-15)
            or computed_refine_ratio > limit_values["source_ratio"]
        ):
            errors.append("host refine wire source ratio exceeds its hard ceiling")
        refine_semantics = host_refine.get("semantics")
        refine_expected = {
            "message_type": "density_update",
            "trace_count": 1,
            "trace_id": 0,
            "mode": "density",
            "tier": "density",
            "encoding": "log-u8",
        }
        if not isinstance(refine_semantics, dict) or any(
            refine_semantics.get(key) != value for key, value in refine_expected.items()
        ):
            errors.append("host refine must preserve strict native density semantics")
        elif not _refine_density_relation(
            refine_semantics.get("binning"), refine_semantics.get("reduction"), points
        ):
            errors.append("host refine must use its scale-required density route")
        elif (
            not _positive_int(refine_semantics.get("visible"))
            or not _positive_int(points)
            or refine_semantics["visible"] > points
            or not _positive_int(refine_semantics.get("grid_width"))
            or not _positive_int(refine_semantics.get("grid_height"))
        ):
            errors.append("host refine density counts and grid dimensions must be valid")
        refine_inventory = host_refine.get("buffer_inventory")
        if not isinstance(refine_inventory, dict):
            errors.append("host_refine.buffer_inventory must be present")
        else:
            refine_classes = refine_inventory.get("classes")
            if refine_inventory.get("bytes") != host_refine.get("reply_bytes"):
                errors.append("host refine inventory bytes must equal reply_bytes")
            if not isinstance(refine_classes, dict) or set(refine_classes) != {"u8"}:
                errors.append("host density refine must contain only the bounded u8 grid class")
            else:
                entries_valid = all(
                    isinstance(entry, dict)
                    and _positive_int(entry.get("buffers"))
                    and _positive_int(entry.get("bytes"))
                    for entry in refine_classes.values()
                )
                if (
                    not entries_valid
                    or sum(entry["buffers"] for entry in refine_classes.values())
                    != refine_inventory.get("buffer_count")
                    or sum(entry["bytes"] for entry in refine_classes.values())
                    != refine_inventory.get("bytes")
                ):
                    errors.append("host refine classes must cover every reply buffer and byte")
            refine_hashes = refine_inventory.get("buffer_sha256")
            if (
                not isinstance(refine_hashes, list)
                or len(refine_hashes) != refine_inventory.get("buffer_count")
                or not all(_sha256_digest(value) for value in refine_hashes)
            ):
                errors.append("host refine hashes must cover every reply buffer")
        refine_oracle = host_refine.get("product_link_oracle")
        expected_refine_backend = (
            "native-bin2d"
            if _positive_int(points) and points < PYRAMID_MIN_POINTS
            else "native-resident-pyramid"
        )
        expected_refine_route = (
            "exact-bin2d"
            if _positive_int(points) and points < PYRAMID_MIN_POINTS
            else "resident-pyramid"
        )
        oracle_link = refine_oracle.get("product_link") if isinstance(refine_oracle, dict) else None
        refine_width = refine_oracle.get("grid_width") if isinstance(refine_oracle, dict) else None
        refine_height = (
            refine_oracle.get("grid_height") if isinstance(refine_oracle, dict) else None
        )
        refine_cells = (
            refine_width * refine_height
            if _positive_int(refine_width) and _positive_int(refine_height)
            else -1
        )
        refine_observed = (
            refine_oracle.get("observed_count") if isinstance(refine_oracle, dict) else None
        )
        refine_recomposed = (
            refine_oracle.get("recomposed_count") if isinstance(refine_oracle, dict) else None
        )
        refine_error = (
            abs(refine_recomposed - refine_observed)
            if _finite_nonnegative(refine_recomposed) and _finite_nonnegative(refine_observed)
            else math.inf
        )
        refine_reported_error = (
            refine_oracle.get("recomposed_absolute_error")
            if isinstance(refine_oracle, dict)
            else None
        )
        refine_index = (
            oracle_link.get("emitted_buffer_index") if isinstance(oracle_link, dict) else None
        )
        refine_hashes = (
            refine_inventory.get("buffer_sha256") if isinstance(refine_inventory, dict) else None
        )
        refine_hash_is_reply = (
            isinstance(refine_index, int)
            and not isinstance(refine_index, bool)
            and refine_index >= 0
            and isinstance(refine_hashes, list)
            and refine_index < len(refine_hashes)
            and isinstance(oracle_link, dict)
            and oracle_link.get("emitted_buffer_sha256") == refine_hashes[refine_index]
        )
        expected_refine_level = None
        if isinstance(refine_semantics, dict) and isinstance(refine_semantics.get("binning"), str):
            level_match = re.fullmatch(r"pyramid-L(\d+)", refine_semantics["binning"])
            if level_match is not None:
                expected_refine_level = int(level_match.group(1))
        _, expected_refine_base_dim = _expected_pyramid_residency(points)
        if (
            not isinstance(refine_oracle, dict)
            or refine_oracle.get("backend") != expected_refine_backend
            or not isinstance(refine_semantics, dict)
            or refine_oracle.get("expected_visible") != refine_semantics.get("visible")
            or refine_observed != refine_semantics.get("visible")
            or not _finite_nonnegative(refine_recomposed)
            or not _finite_nonnegative(refine_reported_error)
            or not math.isclose(refine_reported_error, refine_error, rel_tol=1e-12, abs_tol=1e-12)
            or (expected_refine_route == "exact-bin2d" and refine_error != 0.0)
            or refine_oracle.get("count_match") is not True
            or refine_oracle.get("grid_width") != refine_semantics.get("grid_width")
            or refine_oracle.get("grid_height") != refine_semantics.get("grid_height")
            or refine_oracle.get("grid_bytes") != refine_cells * 4
            or not _sha256_digest(refine_oracle.get("grid_sha256"))
            or not isinstance(oracle_link, dict)
            or oracle_link.get("route") != expected_refine_route
            or oracle_link.get("emitted_buffer_bytes") != refine_cells
            or oracle_link.get("oracle_encoded_bytes") != refine_cells
            or oracle_link.get("emitted_buffer_bytes") != host_refine.get("reply_bytes")
            or not _sha256_digest(oracle_link.get("emitted_buffer_sha256"))
            or oracle_link.get("emitted_buffer_sha256") != oracle_link.get("oracle_encoded_sha256")
            or not refine_hash_is_reply
            or not _finite_nonnegative(oracle_link.get("emitted_max"))
            or oracle_link.get("emitted_max") != oracle_link.get("oracle_max")
            or oracle_link.get("encoded_match") is not True
            or oracle_link.get("max_match") is not True
            or oracle_link.get("emitted_binning") != refine_semantics.get("binning")
            or oracle_link.get("emitted_reduction") != refine_semantics.get("reduction")
            or oracle_link.get("recomposed_binning") != refine_semantics.get("binning")
            or oracle_link.get("pyramid_level") != expected_refine_level
            or oracle_link.get("pyramid_base_dim") != expected_refine_base_dim
        ):
            errors.append(
                "native refine product-link oracle must reproduce density_view bytes, max, "
                "counts, and routing"
            )
    browser = report.get("browser")
    if not isinstance(browser, dict):
        errors.append("browser must be an object")
    else:
        if browser.get("initial_payload_bytes") != payload_bytes:
            errors.append("browser must consume the complete bounded first payload")
        if browser.get("initial_spec_json_bytes") != spec_json_bytes:
            errors.append("browser must consume the exact served spec JSON bytes")
        if browser.get("initial_wire_bytes") != wire_bytes:
            errors.append("browser must consume the exact complete initial wire bytes")
        if (
            browser.get("strict_csp") is not True
            or browser.get("csp_inline_blocked") is not True
            or browser.get("unexpected_requests") != []
        ):
            errors.append("browser must stay within the strict-CSP loopback route set")
        if not _nonempty_string(browser.get("renderer")):
            errors.append("browser.renderer must identify the observed WebGL renderer")
        if browser.get("view_destroyed") is not True:
            errors.append("browser ChartView must be destroyed")
        if browser.get("server_stopped") is not True or browser.get("browser_exited") is not True:
            errors.append("browser and loopback server must stop")
        if not isinstance(browser.get("refine"), dict):
            errors.append("browser.refine must be measured")
        else:
            expected_refine_bytes = (
                host_refine.get("reply_bytes") if isinstance(host_refine, dict) else None
            )
            expected_refine_hashes = None
            if isinstance(host_refine, dict) and isinstance(
                host_refine.get("buffer_inventory"), dict
            ):
                expected_refine_hashes = host_refine["buffer_inventory"].get("buffer_sha256")
            if browser["refine"].get("reply_bytes") != expected_refine_bytes:
                errors.append("browser and host refine byte counts must match")
            expected_refine_wire_bytes = (
                host_refine.get("wire_bytes") if isinstance(host_refine, dict) else None
            )
            if browser["refine"].get("wire_bytes") != expected_refine_wire_bytes:
                errors.append("browser and host refine wire byte counts must match")
            if browser["refine"].get("buffer_sha256") != expected_refine_hashes:
                errors.append("browser and host refine buffer hashes must match")
            expected_refine_semantics = (
                host_refine.get("semantics") if isinstance(host_refine, dict) else None
            )
            if browser["refine"].get("semantics") != expected_refine_semantics:
                errors.append("browser and host refine density semantics must match exactly")
            browser_semantics = browser["refine"].get("semantics")
            if (
                not isinstance(browser_semantics, dict)
                or browser["refine"].get("mode") != browser_semantics.get("mode")
                or browser["refine"].get("binning") != browser_semantics.get("binning")
            ):
                errors.append("browser refine labels must match its native density semantics")
            if (
                browser.get("prefers_reduced_motion") is not False
                or browser["refine"].get("transition_mode") != "normal"
                or browser["refine"].get("transition_settled") is not True
            ):
                errors.append("browser refine must finish the normal product transition")
        if browser.get("requests") != ["density_view"]:
            errors.append("browser must issue exactly one density_view request")
        expected_span_fraction = 0.2 if _positive_int(points) and points >= 1_000_000 else 0.25
        expected_offset_fraction = 0.25
        transform = browser.get("view_transform")
        home_view = transform.get("home") if isinstance(transform, dict) else None
        requested_view = transform.get("requested") if isinstance(transform, dict) else None
        applied_view = transform.get("applied") if isinstance(transform, dict) else None
        view_values_valid = all(
            isinstance(view, dict)
            and set(view) == {"x0", "x1", "y0", "y1"}
            and all(_finite_number(value) for value in view.values())
            and view["x1"] > view["x0"]
            and view["y1"] > view["y0"]
            for view in (home_view, requested_view, applied_view)
        )
        transform_geometry_valid = False
        if view_values_valid:
            home_span = home_view["x1"] - home_view["x0"]
            requested_span = requested_view["x1"] - requested_view["x0"]
            transform_geometry_valid = (
                home_span > 0
                and math.isclose(
                    requested_span / home_span,
                    expected_span_fraction,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
                and math.isclose(
                    (requested_view["x0"] - home_view["x0"]) / home_span,
                    expected_offset_fraction,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
                and requested_view["y0"] == home_view["y0"]
                and requested_view["y1"] == home_view["y1"]
            )
        if (
            not isinstance(transform, dict)
            or transform.get("kind") != "in-domain-x-zoom-pan"
            or transform.get("x_span_fraction") != expected_span_fraction
            or transform.get("x_offset_fraction") != expected_offset_fraction
            or transform.get("y_span_fraction") != 1
            or transform.get("applied_matches_requested") is not True
            or not view_values_valid
            or not transform_geometry_valid
            or requested_view != applied_view
        ):
            errors.append("browser must apply the required in-domain x zoom/pan journey")
        request_window = browser.get("request_window")
        host_request_window = (
            host_refine.get("request_window") if isinstance(host_refine, dict) else None
        )
        request_contains_applied = (
            isinstance(request_window, dict)
            and isinstance(applied_view, dict)
            and request_window.get("x0", math.inf) <= applied_view["x0"]
            and request_window.get("x1", -math.inf) >= applied_view["x1"]
            and request_window.get("y0", math.inf) <= applied_view["y0"]
            and request_window.get("y1", -math.inf) >= applied_view["y1"]
        )
        authority_ladder_aligned = True
        if points == AUTHORITY_POINTS and isinstance(request_window, dict) and view_values_valid:
            home_span = home_view["x1"] - home_view["x0"]
            ladder_span = home_span * 0.25
            request_offset_steps = (
                request_window.get("x0", math.inf) - home_view["x0"]
            ) / ladder_span
            authority_ladder_aligned = math.isclose(
                (request_window.get("x1", -math.inf) - request_window.get("x0", math.inf))
                / home_span,
                0.25,
                rel_tol=1e-9,
                abs_tol=1e-9,
            ) and math.isclose(
                request_offset_steps,
                round(request_offset_steps),
                rel_tol=1e-9,
                abs_tol=1e-9,
            )
        if (
            request_window != host_request_window
            or not isinstance(request_window, dict)
            or set(request_window) != {"trace", "x0", "x1", "y0", "y1", "w", "h"}
            or request_window.get("trace") != 0
            or not all(_finite_number(request_window.get(key)) for key in ("x0", "x1", "y0", "y1"))
            or request_window.get("x1", 0) <= request_window.get("x0", 0)
            or request_window.get("y1", 0) <= request_window.get("y0", 0)
            or not _positive_int(request_window.get("w"))
            or not _positive_int(request_window.get("h"))
            or not request_contains_applied
            or not authority_ladder_aligned
        ):
            errors.append("browser and host must record the same valid density_view window")
        initial_upload = browser.get("initial_upload")
        if not isinstance(initial_upload, dict) or not _positive_int(initial_upload.get("calls")):
            errors.append("browser initial upload calls must be measured")
        elif (
            not _positive_int(initial_upload.get("bytes"))
            or not _positive_int(payload_bytes)
            or initial_upload["bytes"] < payload_bytes
            or initial_upload["bytes"] > payload_bytes * 4
            or not _finite_nonnegative(initial_upload.get("call_ms"))
        ):
            errors.append("browser initial upload bytes/time must be bounded and measured")
        refine_upload = browser.get("refine", {}).get("upload")
        refine_application = browser.get("refine", {}).get("application")
        texture_changed = browser.get("refine", {}).get("texture_changed")
        facts_cache_delta = browser.get("refine", {}).get("facts_cache_delta")
        upload_measured = isinstance(refine_upload, dict) and _finite_nonnegative(
            refine_upload.get("call_ms")
        )
        upload_positive_bounded = (
            upload_measured
            and _positive_int(refine_upload.get("calls"))
            and refine_upload["calls"] <= MAX_TRANSITION_UPLOAD_CALLS
            and _positive_int(refine_upload.get("bytes"))
            and isinstance(host_refine, dict)
            and _positive_int(host_refine.get("reply_bytes"))
            and host_refine["reply_bytes"]
            <= refine_upload["bytes"]
            <= host_refine["reply_bytes"] * refine_upload["calls"]
            and refine_upload["bytes"] % host_refine["reply_bytes"] == 0
        )
        facts_only_valid = (
            upload_measured
            and refine_upload.get("calls") == 0
            and refine_upload.get("bytes") == 0
            and refine_application == "facts-only"
            and texture_changed is False
            and _positive_int(facts_cache_delta)
        )
        texture_valid = (
            upload_positive_bounded
            and refine_application == "texture"
            and texture_changed is True
            and _positive_int(facts_cache_delta)
        )
        if points == AUTHORITY_POINTS:
            if not texture_valid:
                errors.append(
                    "100M authority refine must apply a texture with a positive bounded GPU upload"
                )
        elif _positive_int(points) and points <= 1_000_000:
            if not facts_only_valid:
                errors.append("250k/1M refine must record the intentional facts-only application")
        elif not (facts_only_valid or texture_valid):
            errors.append("browser refine application must be measured as facts-only or texture")
        for phase in ("first_pixels", "refined_pixels"):
            pixels = browser.get(phase)
            if not isinstance(pixels, dict):
                errors.append(f"browser.{phase} must contain decoded pixel evidence")
                continue
            width = pixels.get("width")
            height = pixels.get("height")
            if (
                not _positive_int(width)
                or not _positive_int(height)
                or pixels.get("region") != "plot"
                or pixels.get("bytes") != width * height * 4
                or not _positive_int(pixels.get("non_background_pixels"))
                or not _sha256_digest(pixels.get("sha256"))
            ):
                errors.append(f"browser.{phase} must contain nonblank RGBA pixel evidence")
        first_pixels = browser.get("first_pixels")
        refined_pixels = browser.get("refined_pixels")
        if (
            isinstance(first_pixels, dict)
            and isinstance(refined_pixels, dict)
            and first_pixels.get("sha256") == refined_pixels.get("sha256")
        ):
            errors.append("refined plot pixels must differ from first-paint plot pixels")
        for parent, key in (
            (browser.get("first_paint", {}), "construct_upload_ms"),
            (browser.get("first_paint", {}), "settle_ms"),
            (browser.get("refine", {}), "roundtrip_ms"),
            (browser.get("refine", {}), "apply_paint_ms"),
        ):
            if not isinstance(parent, dict) or not _finite_nonnegative(parent.get(key)):
                errors.append(f"browser timing {key} must be finite and nonnegative")

    cleanup = report.get("cleanup")
    if not isinstance(cleanup, dict):
        errors.append("cleanup must be an object")
    else:
        for key in ("mmap_closed", "figure_released", "temp_tree_removed"):
            if cleanup.get(key) is not True:
                errors.append(f"cleanup.{key} must be true")
        if cleanup.get("worker_exit_code") != 0:
            errors.append("cleanup.worker_exit_code must be zero")
        if cleanup.get("orphan_pids_after_reap") != []:
            errors.append("cleanup must leave no process-group orphans")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--sha")
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read density report: {exc}", file=sys.stderr)
        return 1
    errors = validate(report, expected_sha=args.sha)
    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"density end-to-end report OK: {report['point_count']} points, "
        f"{report['payload']['bytes']} first-paint bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
