#!/usr/bin/env python3
"""Check equal-window evidence independently; never certify a competitive win."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import platform
import re
import sys
from pathlib import Path
from typing import Any

GIB = 2**30
ARMS = ("xy-density", "plotly-aggregate", "datashader-aggregate")
MAX_REPORT_BYTES = 64 * 2**20
CONTEXT = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_WORKFLOW": "Interactive ceiling benchmark",
    "RUNNER_OS": "macOS",
}
ARCHIVE = Path("benchmarks/results/live-aggregation-2026-10-24/equal-window-v2")
# Decoded original bytes, not a filename or a self-declared historical flag.
HISTORICAL = {
    "fe9b087e8fd20163d9b0d9f706dc9059aa7f9d73bd9f8c763849b466ff4dbed6": "f32-producer",
    "21965ee46178049d37001c9028e80b72259cb1109b19593920560a3e697e06ce": "current-producer",
    "092c9b30ccb2fd28831d3c833ade6a3ad0d53ccfbcaf4e66dd5a80ded8810f11": "current-producer",
}
TIMING_CONTRACT = {
    "cold": "fresh host/browser source admission/build and first correct stable paint; OS disk/JIT caches not flushed",
    "warm": "explicit programmatic range requests, never real-gesture latency",
    "axes_adopt_ms": "first observed matching browser axes since request start",
    "output_adopt_ms": "first observed adopted raster domain/revision, or exact subset covering and clipped to target axes",
    "paint_stable_ms": "first of ten stable readbacks with nonwhite opaque interior pixels (or zero for empty control)",
    "stability_confirmed_ms": "ten-frame verification overhead included; same browser performance.now clock",
    "copy_observations": "retained host arrays only, not a claim about all transient/native copies",
}
TRANSPORT_SCOPE = "WebSocket application message bodies only; HTTP/bootstrap assets, headers, TLS, TCP/IP excluded"
FAILURES = {
    "source_memory_limit",
    "source_timeout",
    "source_failed",
    "host_memory_limit",
    "host_failed",
    "source_mismatch",
    "failed",
    "timeout",
    "browser_memory_limit",
    "memory_limit",
    "cold_failed",
    "step_failed",
    "empty_control_failed",
    "exception",
    "missing_comparison_status",
}
HARNESS = (
    "benchmarks/bench_density_comparison.py",
    "benchmarks/bench_ux.py",
    "benchmarks/_ux_comparison_source.py",
    "benchmarks/_ux_comparison_data.py",
    "benchmarks/_ux_comparison_host.py",
    "benchmarks/_ux_live_host.py",
    "benchmarks/_ux_plotly_aggregate_host.py",
    "benchmarks/_ux_datashader_host.py",
    "benchmarks/_ux_probe.py",
    "benchmarks/_launch_interactive.py",
    "benchmarks/environment.py",
    "benchmarks/requirements-ci.lock",
    "Cargo.lock",
    "package-lock.json",
)


class InvalidReport(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise InvalidReport(message)


def integer(v: Any, low: int = 0, high: int = 2**63) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and low <= v <= high


def number(v: Any, low: float = 0, high: float = 1e300) -> bool:
    return (
        isinstance(v, (int, float))
        and not isinstance(v, bool)
        and math.isfinite(v)
        and low <= v <= high
    )


def text(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def digest(v: Any, length: int = 64) -> bool:
    return isinstance(v, str) and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", v) is not None


def domain(v: Any) -> bool:
    return (
        isinstance(v, list)
        and len(v) == 4
        and all(number(x, -1e100, 1e100) for x in v)
        and v[0] < v[1]
        and v[2] < v[3]
    )


def near(a: Any, b: Any) -> bool:
    return (
        isinstance(a, list)
        and len(a) == len(b)
        and all(
            number(x, -1e100, 1e100) and abs(x - y) <= 1e-9 * max(1, abs(y))
            for x, y in zip(a, b, strict=True)
        )
    )


def trajectory(e: list) -> list[dict]:
    """Pinned independently of producer imports: dossier §12 / comparison v2."""
    x, _, y, _ = e
    dx, dy = e[1] - x, e[3] - y
    pans = [
        {"kind": "pan", "window": [x + i / 16 * dx, x + (i / 16 + 0.5) * dx, y, y + 0.5 * dy]}
        for i in [0, 1, 2, 3, 4, 3, 2, 1] * 3
    ]
    zooms = [
        {
            "kind": "zoom",
            "window": [x + 0.125 * dx, x + (0.125 + s) * dx, y + 0.125 * dy, y + (0.125 + s) * dy],
        }
        for s in [0.25, 0.5] * 4
    ]
    return pans + zooms


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def tree_hash(root: Path, folder: str, pattern: str) -> str:
    h = hashlib.sha256()
    for path in sorted((root / folder).rglob(pattern)):
        h.update(path.relative_to(root).as_posix().encode() + b"\0")
        h.update(bytes.fromhex(file_hash(path)))
    return h.hexdigest()


def check_provenance(p: dict, root: Path | None, historical: str | None) -> None:
    require(all(digest(v) for v in p.values()), "provenance hashes must be SHA256")
    require(all(k in p for k in HARNESS), "missing harness/lock provenance")
    if not historical:
        require("benchmarks/_ux_comparison_oracle.py" in p, "missing independent oracle provenance")
    for folder in ("python/xyg", "crates", "js/src"):
        require(folder + ":tree_sha256" in p, "missing product tree identity")
    require("python/xyg/static/index.js" in p, "missing built client identity")
    loaded = [k for k in p if k.startswith("loaded_native:")]
    require(
        len(loaded) == 1 and Path(loaded[0].split(":", 1)[1]).is_absolute(),
        "missing actually loaded native binary identity",
    )
    # Linux's separately recorded build must agree with the binary actually loaded.
    if "target/release/libxyg_core.so" in p:
        require(
            p[loaded[0]] == p["target/release/libxyg_core.so"],
            "loaded native differs from recorded build",
        )
    if root is None:
        return
    require(root.is_dir(), "artifact root must be an existing directory")
    for key, expected in p.items():
        if historical:
            # Exact raw archive binding permits evolved code; only retained producer files apply.
            path = root / ARCHIVE / historical / (key + ".txt")
            if path.is_file():
                require(file_hash(path) == expected, f"archived producer hash mismatch: {key}")
            elif key in HARNESS and key.startswith("benchmarks/"):
                require(False, f"missing archived producer: {key}")
            continue
        if key.endswith(":tree_sha256"):
            folder = key.split(":", 1)[0]
            require(folder in ("python/xyg", "crates", "js/src"), "unknown product tree")
            pattern = {"python/xyg": "*.py", "crates": "*.rs", "js/src": "*.ts"}[folder]
            if (root / folder).is_dir():
                require(
                    tree_hash(root, folder, pattern) == expected,
                    f"product tree hash mismatch: {folder}",
                )
            continue
        if key.startswith(("loaded_native:", "XYG_NATIVE_LIB:")):
            path = Path(key.split(":", 1)[1])
        else:
            require(
                not Path(key).is_absolute() and ".." not in Path(key).parts,
                "unsafe provenance path",
            )
            path = root / key
        if path.is_file():
            require(file_hash(path) == expected, f"artifact hash mismatch: {key}")


def check_authority(a: dict, n: int, profile: str, rss: int, hosted: bool) -> None:
    require(
        a["actual_rows"] == n
        and a["source_file_bytes"] == n * (16 if profile == "f64-memmap" else 8),
        "authority source byte/count mismatch",
    )
    require(a["per_tree_rss_guard_bytes"] == rss, "authority RSS differs from report limit")
    require(
        integer(a["disk_guard_bytes"], 1, 20 * GIB if hosted else GIB // 4)
        and a["source_file_bytes"] <= a["disk_guard_bytes"],
        "source disk guard exceeds independent policy or actual bytes do not fit",
    )
    require(a["mapped_bytes_are_not_rss"] is True, "mapped-byte scope missing")
    facts = a["facts"]
    require(
        text(facts["system"]) and text(facts["machine"]) and integer(facts["memory"], 1),
        "missing host facts",
    )
    if hosted:
        require(
            a["authority"] == "manual-main-macos-M4"
            and all(facts.get(k) == v for k, v in CONTEXT.items())
            and facts["system"] == "Darwin"
            and facts["machine"] == "arm64"
            and facts["memory"] >= 44 * GIB,
            "invalid recorded hosted authority",
        )
    else:
        require(a["authority"] == "bounded-local" and n <= 1_000_000, "local row/authority limit")


def check_source(s: dict, n: int, profile: str, authority: dict, rss: int) -> None:
    width = 8 if profile == "f64-memmap" else 4
    require(
        s["schema_version"] == 1
        and s["actual_rows"] == n
        and s["profile"] == profile
        and s["dtype"] == ("<f8" if width == 8 else "<f4"),
        "source profile/dtype/actual rows mismatch",
    )
    require(
        s["seed"] == 20260713
        and s["generator"] == ("independent-streams-f64-v1" if width == 8 else "legacy-f32-v1"),
        "source generator identity changed",
    )
    require(
        s["authority"] == authority and integer(s["generation_chunk_rows"], 1, 1_000_000),
        "source authority/chunk mismatch",
    )
    require(
        set(s["columns"]) == {"x", "y"} and digest(s["sha256_x_then_y"]), "source identity missing"
    )
    for name, c in s["columns"].items():
        require(
            c["file"] == f"{name}.{profile}" and c["bytes"] == n * width and digest(c["sha256"]),
            "column actual bytes/file/hash mismatch",
        )
    require(domain(s["extents"]), "invalid source extents")
    require(len(s["windows"]) == 32, "must retain 24 pan + 8 zoom source windows")
    counts = {}
    for w, expected in zip(s["windows"], trajectory(s["extents"]), strict=True):
        require(
            w["kind"] == expected["kind"]
            and near(w["window"], expected["window"])
            and integer(w["expected_count"], 0, n),
            "source window trajectory/count mismatch",
        )
        key = tuple(w["window"])
        require(
            key not in counts or counts[key] == w["expected_count"], "repeated window count changed"
        )
        counts[key] = w["expected_count"]
    require(
        number(s["creation_wall_ms"]) and integer(s["source_peak_rss_bytes"], 1, rss),
        "source creation memory/timing invalid or over cap",
    )


def check_bytes(b: dict) -> None:
    require(b["layer"] == "websocket_application_messages", "wrong transport layer")
    for direction in ("to_host", "from_host"):
        v = b[direction]
        require(
            all(integer(v[k]) for k in ("json_bytes", "binary_frame_bytes", "total_bytes"))
            and v["total_bytes"] == v["json_bytes"] + v["binary_frame_bytes"],
            "invalid transport body counts",
        )
    require(
        integer(b["total_bytes"])
        and b["total_bytes"] == b["to_host"]["total_bytes"] + b["from_host"]["total_bytes"],
        "invalid transport total",
    )


def check_memory(m: dict, cap: int) -> None:
    for who in ("host", "browser"):
        current, peak = m[who + "_rss_bytes"], m[who + "_peak_rss_bytes"]
        require(
            integer(current, 1, cap) and integer(peak, current, cap),
            "checkpoint RSS invalid or exceeds declared cap",
        )


def check_inventory(obs: dict, n: int, arm: str) -> None:
    keys = ["canonical_admission"] + (
        ["canonical_after_build"]
        if arm == "xy-density"
        else ["backend_input"]
        if arm == "datashader-aggregate"
        else []
    )
    for key in keys:
        for name in ("x", "y"):
            c = obs[key][name]
            require(
                c["dtype"] in ("float32", "float64")
                and c["bytes"] == n * (4 if c["dtype"] == "float32" else 8),
                "retained column dtype/bytes mismatch",
            )
            require(
                all(
                    isinstance(c[k], bool)
                    for k in ("pointer_equal", "shares_memory", "source_mapped", "retained_mapped")
                ),
                "missing explicit copy/mapping observations",
            )


def check_numerical(o: dict, target: list, count: int) -> None:
    a = o["numerical_oracle"]
    require(
        a["version"] == "source-cell-compose-v1" and a["passed"] is True,
        "missing/failing independent numerical oracle",
    )
    require(
        a["domain"] == target
        and integer(a["exact_source_count"])
        and a["exact_source_count"] == count,
        "numerical source count/domain mismatch",
    )
    require(
        integer(a["half_open_source_count"], 0, count)
        and integer(a["upper_boundary_excluded"], 0, count)
        and a["upper_boundary_excluded"] == count - a["half_open_source_count"],
        "upper-boundary exclusions mismatch",
    )
    require(
        a["emitted_visible"] == o["visible"] and integer(o["visible"]),
        "oracle substituted for emitted visible",
    )
    require(digest(a["source_sha256"]), "missing numerical source identity")
    require(
        number(a["validation_wall_ms"], 0, 15000)
        and integer(a["validation_http_request_bytes"], 1, 8 * 2**20),
        "missing numerical validation time/HTTP request-body accounting",
    )
    if o["exact_fallback"]:
        require(
            a["points_allowed"] is True
            and o["tier"] == "direct"
            and o["reduction"] == "none"
            and o["exact_count"] == count
            and a["count_exact"] is True
            and a["count_method"] == "inclusive-source"
            and a["expected_visible"] == count
            and a["base_geometry"] is None
            and a["served_level"] is None,
            "invalid exact fallback numerical disclosure",
        )
        return
    require(
        o["tier"] == "density"
        and a["raster_shape"] == o["raster_shape"]
        and o["encoding"] == "log-u8",
        "incompatible density labels/shape/encoding",
    )
    require(
        integer(a["expected_visible"]) and o["visible"] == a["expected_visible"],
        "independent source-derived visible count mismatch",
    )
    require(integer(a["boundary_mass_bound"], 0, 1_000_000_000), "invalid boundary-mass bound")
    geometry = a["base_geometry"]
    if a["count_method"] == "whole-cell-center":
        require(
            a["count_exact"] is False
            and isinstance(geometry, dict)
            and abs(o["visible"] - count) <= a["boundary_mass_bound"],
            "pyramid estimate outside source boundary-mass bound",
        )
    else:
        require(
            a["count_exact"] is True
            and a["count_method"] in ("inclusive-source", "half-open-source"),
            "missing count method/exactness",
        )
        require(
            o["visible"]
            == (a["half_open_source_count"] if a["count_method"] == "half-open-source" else count),
            "exact-route visible count mismatch",
        )
    if geometry is not None:
        dim = geometry["dimension"]
        require(
            domain(geometry["domain"])
            and integer(dim, 2, 16384)
            and dim & (dim - 1) == 0
            and geometry["upper_edge_relative_epsilon"] == 1e-9
            and integer(a["served_level"], 0, int(math.log2(dim)))
            and isinstance(a["upsampled"], bool)
            and o["binning"]
            == f"pyramid-L{a['served_level']}" + ("-upsampled" if a["upsampled"] else "")
            and o["reduction"] == "pyramid-count",
            "invalid pyramid geometry/served level/disclosure",
        )
    else:
        require(
            a["served_level"] is None
            and a["count_method"] != "whole-cell-center"
            and (o["binning"], o["reduction"])
            in (("exact", "bin2d"), ("exact", "count"), ("bin2d-oversized", "bin2d-oversized")),
            "invalid exact aggregation disclosure",
        )
    require(
        digest(a["grid_sha256"]) and number(a["grid_mass_diagnostic"]),
        "missing independent grid observation",
    )
    require(
        digest(a["expected_encoded_sha256"])
        and a["actual_encoded_sha256"] == a["expected_encoded_sha256"]
        and digest(a["expected_decoded_sha256"])
        and a["adopted_decoded_sha256"] == a["expected_decoded_sha256"]
        and a["encoded_bytes"] == math.prod(o["raster_shape"])
        and number(a["expected_max"])
        and a["actual_max"] == a["expected_max"] == o["reply_max"] == o["adopted_max"],
        "emitted/adopted grid or encoding differs from independent source oracle",
    )


def check_output(o: dict, target: list, count: int, arm: str, historical: bool) -> None:
    require(
        o["adopted"] is True and integer(o["revision"]),
        "output not actually adopted/revision missing",
    )
    require(
        isinstance(o["exact_fallback"], bool) and o["mode"] in ("points", "density"),
        "missing output mode/fallback",
    )
    require(domain(o["domain"]), "missing actual output domain")
    if o["exact_fallback"]:
        require(
            arm == "xy-density"
            and o["mode"] == "points"
            and integer(o["exact_count"])
            and o["exact_count"] == count
            and integer(o["payload_count"], count),
            "exact clipped point count/fallback mismatch",
        )
        d = o["domain"]
        require(
            d[0] <= target[0] + 1e-9
            and d[1] >= target[1] - 1e-9
            and d[2] <= target[2] + 1e-9
            and d[3] >= target[3] - 1e-9,
            "exact subset does not cover target",
        )
    else:
        require(
            o["mode"] == "density" and near(o["domain"], target),
            "raster domain differs from target",
        )
        require(
            isinstance(o["raster_shape"], list)
            and len(o["raster_shape"]) == 2
            and all(integer(v, 1, 4096) for v in o["raster_shape"]),
            "invalid actual raster dimensions",
        )
    if arm == "xy-density":
        if not historical:
            check_numerical(o, target, count)
        elif o["mode"] == "density":
            require(o["visible"] == count, "XYG density visible count mismatch")
        require(integer(o["visible"]) and text(o["reduction"]), "missing XYG reduction disclosure")
        if not historical or "rendered_revision" in o:
            require(
                integer(o["rendered_revision"])
                and o["rendered_revision_kind"]
                == ("drill_subset" if o["exact_fallback"] else "density_reply"),
                "missing rendered revision/kind",
            )
            if not o["exact_fallback"]:
                require(
                    near(o["reply_domain"], target)
                    and isinstance(o["equivalent_cached_raster"], bool)
                    and o["grid_value_equality_verified"] is True,
                    "unverified raster reply/cache equivalence",
                )
                require(
                    o["rendered_revision"] == o["revision"]
                    or o["equivalent_cached_raster"] is True,
                    "stale raster revision",
                )
    elif arm == "plotly-aggregate":
        check_oracle(o["oracle"], count)
        require(digest(o["png_sha256"]), "missing actual PNG hash")
    else:
        require(integer(o["requested_revision"]), "missing Bokeh request/data revisions")


def check_oracle(o: dict, count: int) -> None:
    require(
        o["passed"] is True
        and integer(o["count"])
        and integer(o["grid_mass"])
        and o["count"] == o["grid_mass"] == count,
        "count oracle failed or mismatched",
    )


def check_paint(
    p: dict,
    target: list,
    count: int,
    arm: str,
    deadline: float,
    historical: bool,
    cold: bool = False,
) -> None:
    require(
        p["ok"] is True and p["expected_count"] == count and integer(p["expected_count"]),
        "paint expected count/status mismatch",
    )
    clocks = [
        p[k]
        for k in ("axes_adopt_ms", "output_adopt_ms", "paint_stable_ms", "stability_confirmed_ms")
    ]
    require(
        all(number(v, 0, deadline * 1000) for v in clocks) and clocks == sorted(clocks),
        "invalid programmatic clock order/deadline",
    )
    require(
        integer(p["paint_hash32"], 0, 2**32 - 1)
        and integer(p["lit_pixels"])
        and (p["lit_pixels"] > 0 if count else p["lit_pixels"] == 0),
        "nonblank/empty paint oracle failed",
    )
    require(
        near(p["state"]["axes"], target) and near(p["state"]["plot_shape"], [512, 512]),
        "actual axes/plot dimensions mismatch",
    )
    if not cold or (arm == "xy-density" and not historical):
        check_output(p["state"]["output"], target, count, arm, historical)


def check_cell(c: dict, s: dict, cap: int, step_timeout: float, historical: bool) -> None:
    arm, n = c["arm"], c["n"]
    manifest = {
        k: v for k, v in s.items() if k not in ("creation_wall_ms", "source_peak_rss_bytes")
    }
    require(
        c["host_meta"]["source"] == manifest and c["host_meta"]["n"] == n,
        "host source identity differs from shared source",
    )
    require(
        text(c["host_meta"]["mode"])
        and c["host_meta"]["components"]
        and number(c["host_meta"]["build_ms"])
        and number(c["host_prepare_wall_ms"]),
        "missing host build identity/clocks",
    )
    for who in ("host", "browser"):
        require(integer(c[who + "_peak_rss_bytes"], 1, cap), "successful cell RSS exceeds cap")
    require(
        c["comparison_status"] == "ok" and len(c["steps"]) == 32,
        "successful cell must retain all 32 steps",
    )
    require(c["transport"]["scope"] == TRANSPORT_SCOPE, "transport scope changed")
    cps = c["transport"]["checkpoints"]
    if arm == "xy-density" and not historical:
        prep = cps["visible-complete"]["host_observation"]["numerical_oracle_preparation"]
        require(
            prep["version"] == "source-cell-compose-v1"
            and number(prep["wall_ms"], 0, c["host_prepare_wall_ms"])
            and integer(prep["chunk_rows"], 1, 1_000_000)
            and integer(prep["grid_storage_upper_bound_bytes"], 1, cap)
            and prep["scope"]
            == "host_prepare before META; host process-tree RSS/watchdog includes oracle",
            "missing/out-of-phase numerical oracle preparation",
        )
    names = ["visible-complete", *[f"step-{i}" for i in range(32)], "empty-control", "terminal"]
    previous = None
    for name in names:
        cp = cps[name]
        check_memory(cp, cap)
        check_inventory(cp["host_observation"], n, arm)
        b = cp["cdp_application_bytes"]
        check_bytes(b)
        if previous:
            require(
                all(
                    b[d][k] >= previous[d][k]
                    for d in ("to_host", "from_host")
                    for k in ("json_bytes", "binary_frame_bytes", "total_bytes")
                ),
                "cumulative transport decreased",
            )
        previous = b
    check_paint(c["cold"], s["extents"], n, arm, step_timeout, historical, cold=True)
    previous_end = 0
    previous_revision = 0
    for i, (p, w) in enumerate(zip(c["steps"], s["windows"], strict=True)):
        require(
            p["index"] == i and p["kind"] == w["kind"] and near(p["requested_window"], w["window"]),
            "step index/kind/window mismatch",
        )
        require(
            number(p["request_start_ms"], previous_end)
            and number(p["request_return_ms"], 0, step_timeout * 1000),
            "request clock order invalid",
        )
        check_paint(p, w["window"], w["expected_count"], arm, step_timeout, historical)
        require(
            p["request_return_ms"] <= p["axes_adopt_ms"] + 1e-6,
            "axes observed before request returned",
        )
        previous_end = p["request_start_ms"] + p["stability_confirmed_ms"]
        revision = p["state"]["output"]["revision"]
        require(revision > previous_revision, "output data revision did not advance")
        previous_revision = revision
        if arm == "datashader-aggregate":
            require(
                p["state"]["output"]["requested_revision"] == i + 1,
                "Bokeh request revision mismatch",
            )
        cp, prev = cps[f"step-{i}"], cps["visible-complete" if i == 0 else f"step-{i - 1}"]
        require(
            p["memory"] == {k: cp[k] for k in p["memory"]}
            and len(p["memory"]) == 4
            and p["host_observation"] == cp["host_observation"],
            "step/checkpoint observations mismatch",
        )
        check_memory(p["memory"], cap)
        check_bytes(p["application_body_bytes"])
        for d in ("to_host", "from_host"):
            require(
                all(
                    p["application_body_bytes"][d][k]
                    == cp["cdp_application_bytes"][d][k] - prev["cdp_application_bytes"][d][k]
                    for k in ("json_bytes", "binary_frame_bytes", "total_bytes")
                ),
                "step transport delta mismatch",
            )
        if arm == "xy-density":
            request = p["state"]["requested"]
            require(
                request["seq"] == p["state"]["output"]["revision"]
                and near(request["domain"], w["window"]),
                "XYG reply/request mismatch",
            )
    e = s["extents"]
    dx, dy = e[1] - e[0], e[3] - e[2]
    empty = [e[1] + dx, e[1] + 1.5 * dx, e[3] + dy, e[3] + 1.5 * dy]
    require(near(c["empty_control"]["requested_window"], empty), "empty control window changed")
    check_paint(c["empty_control"], empty, 0, arm, step_timeout, historical)
    for name, paint, target, count in [
        ("visible-complete", c["cold"], s["extents"], n),
        *[
            (f"step-{i}", p, w["window"], w["expected_count"])
            for i, (p, w) in enumerate(zip(c["steps"], s["windows"], strict=True))
        ],
        ("empty-control", c["empty_control"], empty, 0),
    ]:
        if arm == "xy-density":
            if not historical:
                a = paint["state"]["output"]["numerical_oracle"]
                require(
                    a == cps[name]["host_observation"]["numerical_oracle"]
                    and a["source_sha256"] == s["sha256_x_then_y"],
                    "numerical oracle differs from host/source binding",
                )
                if name.startswith("step-"):
                    counts = s["windows"][int(name.split("-")[1])]["source_counts"]
                    require(
                        counts
                        == {
                            "inclusive": count,
                            "half_open": a["half_open_source_count"],
                            "upper_boundary_excluded": a["upper_boundary_excluded"],
                        },
                        "numerical endpoint counts differ from source manifest",
                    )
                geometry = a["base_geometry"]
                if geometry is not None:
                    bounds = list(s["source_bounds"])
                    for edge in (1, 3):
                        bounds[edge] += (bounds[edge] - bounds[edge - 1]) * 1e-9
                    dim = max(2048, 2 ** math.ceil(math.log2(math.sqrt(max(2, n / 16)))))
                    require(
                        n >= 2_000_000
                        and geometry["domain"] == bounds
                        and geometry["dimension"] == min(16384, dim),
                        "pyramid geometry differs from source/policy",
                    )
            continue
        out = cps[name]["host_observation"]["last_output"]
        require(near(out["domain"], target), "backend actual output domain mismatch")
        if arm == "datashader-aggregate":
            check_oracle(out, count)
            require(
                digest(out["grid_sha256"])
                and out["grid_shape"] == paint["state"]["output"]["raster_shape"]
                and integer(out["backend_revision"], 1),
                "Bokeh actual backend output mismatch",
            )
        else:
            check_oracle(out["oracle"], count)
            require(
                out["png_sha256"] == paint["state"]["output"]["png_sha256"]
                and out["seq"] == paint["state"]["output"]["revision"]
                and out["grid_shape"] == paint["state"]["output"]["raster_shape"]
                and (name == "visible-complete" or number(out["aggregate_encode_oracle_ms"])),
                "Plotly actual served PNG differs from adopted output",
            )


def check_failure(c: dict) -> None:
    """Accept recorded failures as failures, including guard overshoot observations."""
    status = c["status"]
    require(
        status in FAILURES or re.fullmatch(r"failed\([A-Za-z_][A-Za-z_0-9]*\)", status),
        "unknown/nonempty failure status required",
    )
    measured = [v for k, v in c.items() if k.endswith("peak_rss_bytes")]
    require(
        measured and all(integer(v) for v in measured),
        "failure must retain sampled guard observations",
    )
    diagnostics = any(text(c.get(k)) for k in ("reason", "error", "detail", "host_stderr"))
    failed_probe = any(
        p.get("ok") is False and (text(p.get("reason")) or p.get("diag"))
        for p in [c.get("cold", {}), *c.get("steps", []), c.get("empty_control", {})]
    )
    require(
        diagnostics or failed_probe or status.endswith(("timeout", "memory_limit")),
        "failure must retain reason/diagnostics",
    )
    for cp in c.get("transport", {}).get("checkpoints", {}).values():
        for key, value in cp.items():
            if key.endswith("rss_bytes"):
                require(integer(value), "negative/invalid failed-cell RSS observation")
        if "cdp_application_bytes" in cp:
            check_bytes(cp["cdp_application_bytes"])
    for p in c.get("steps", []):
        if "application_body_bytes" in p:
            check_bytes(p["application_body_bytes"])


def validate(
    report: Any,
    *,
    expected_sha: str | None = None,
    expected_sizes: list[int] | None = None,
    expected_arms: list[str] | None = None,
    artifact_root: Path | None = None,
    environ: dict | None = None,
    host: tuple[str, str] | None = None,
    historical: str | None = None,
) -> list[str]:
    try:
        _validate(
            report,
            expected_sha,
            expected_sizes,
            expected_arms,
            artifact_root,
            dict(os.environ) if environ is None else environ,
            host or (platform.system(), platform.machine()),
            historical,
        )
    except (KeyError, TypeError, ValueError, AttributeError, OSError, OverflowError) as exc:
        return [str(exc) or type(exc).__name__]
    return []


def _validate(r, sha, sizes, arms, root, env, host, historical):
    if not historical:
        require(
            r["numerical_contract"] == "source-cell-compose-v1",
            "missing current numerical contract",
        )
    require(
        r["schema_version"] == 1
        and r["experiment"] == "programmatic-equal-window-no-gesture-claim",
        "not a programmatic equal-window v1 report",
    )
    require(
        r["plot_css_px"] == [512, 512] and integer(r["repetitions"], 2, 3),
        "plot size/repetitions changed",
    )
    require(
        isinstance(r["sizes"], list)
        and r["sizes"]
        and all(integer(n, 5, 1_000_000_000) for n in r["sizes"])
        and len(set(r["sizes"])) == len(r["sizes"]),
        "invalid actual size list",
    )
    require(
        isinstance(r["arms"], list)
        and r["arms"]
        and all(a in ARMS for a in r["arms"])
        and len(set(r["arms"])) == len(r["arms"]),
        "invalid arm list",
    )
    require(
        sizes is None or set(sizes) == set(r["sizes"]), "sizes differ from external expected sizes"
    )
    require(arms is None or set(arms) == set(r["arms"]), "arms differ from external expected arms")
    require(r["profile"] in ("f32", "f64-memmap"), "unknown profile")
    require(r["timing_contract"] == TIMING_CONTRACT, "programmatic timing contract changed")
    require(
        isinstance(r["argv"], list)
        and r["argv"]
        and all(isinstance(v, str) for v in r["argv"])
        and text(r["runtime"]["temp_root"]),
        "missing argv/runtime",
    )
    require(
        set(r["runtime"]["thread_environment"])
        == {"NUMBA_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"},
        "missing thread environment",
    )
    environment = r["environment"]
    require(
        environment["xy_backend"] == "native"
        and digest(environment["git"]["commit"], 40)
        and isinstance(environment["git"]["dirty"], bool),
        "missing native/git environment",
    )
    require(
        text(environment["generated_at_utc"])
        and text(environment["python"]["version"])
        and text(environment["python"]["implementation"])
        and text(environment["platform"]["system"])
        and text(environment["platform"]["machine"])
        and integer(environment["cpu_count"], 1)
        and text(environment["executables"]["chromium"])
        and text(environment["browser_renderer"]),
        "missing measured environment",
    )
    require(
        all(
            k in environment["package_versions"]
            for k in (
                "numpy",
                "plotly",
                "datashader",
                "hvplot",
                "holoviews",
                "bokeh",
                "panel",
                "pandas",
                "numba",
                "llvmlite",
                "tornado",
                "psutil",
                "websocket-client",
            )
        ),
        "missing component versions",
    )
    if historical is None:
        requested = "hardware" if "--hardware" in r["argv"] else "software-gl"
        require(
            environment.get("browser_renderer_requested") == requested
            and environment["browser_renderer"] == requested
            and "browser_renderer_observed" in environment
            and environment["browser_renderer_observed"] is None
            and environment.get("browser_renderer_scope")
            == "launch-request; actual renderer not measured",
            "renderer launch request differs from CLI or claims unmeasured observation",
        )
    if sha is not None:
        require(
            digest(sha, 40) and environment["git"]["commit"] == sha,
            "expected external SHA mismatch",
        )
    hosted = any(n > 1_000_000 for n in r["sizes"]) or any(
        a.get("authority") == "manual-main-macos-M4" for a in r["authority"]
    )
    if hosted:
        require(
            r["profile"] == "f64-memmap"
            and sha is not None
            and environment["git"]["dirty"] is False,
            "large evidence requires f64 maps and external clean SHA",
        )
        require(
            all(env.get(k) == v for k, v in CONTEXT.items())
            and env.get("GITHUB_SHA") == sha
            and host == ("Darwin", "arm64"),
            "large evidence requires actual ambient manual-main Darwin-arm64 context",
        )
        require(
            environment["platform"]["system"] == "Darwin"
            and environment["platform"]["machine"] == "arm64",
            "recorded platform differs from hosted lane",
        )
    limits = r["limits"]
    cap = limits["rss_bytes_per_tree"]
    require(
        integer(cap, 1, (20 if hosted else 2) * GIB)
        and limits["rss_poll_ms"] == 50
        and number(limits["host_or_browser_timeout_s"], 0.001, 300)
        and number(limits["step_timeout_s"], 0.001, 15),
        "resource policy exceeds independent finite limits",
    )
    check_provenance(r["provenance_sha256"], root, historical)
    require(len(r["authority"]) == len(r["sizes"]), "missing authority entries")
    require(set(r["sources"]) <= {str(n) for n in r["sizes"]}, "unexpected source rows")
    for n, a in zip(r["sizes"], r["authority"], strict=True):
        check_authority(a, n, r["profile"], cap, hosted)
        if str(n) in r["sources"]:
            check_source(r["sources"][str(n)], n, r["profile"], a, cap)
            if not historical:
                s = r["sources"][str(n)]
                require(domain(s["source_bounds"]), "missing exact source extrema")
                repeated_counts = {}
                for w in s["windows"]:
                    counts = w["source_counts"]
                    require(
                        counts["inclusive"] == w["expected_count"]
                        and integer(counts["half_open"], 0, counts["inclusive"])
                        and counts["upper_boundary_excluded"]
                        == counts["inclusive"] - counts["half_open"],
                        "source endpoint counts inconsistent",
                    )
                    key = tuple(w["window"])
                    require(
                        key not in repeated_counts or repeated_counts[key] == counts,
                        "repeated source endpoint counts changed",
                    )
                    repeated_counts[key] = counts
            require(
                r["sources"][str(n)]["creation_wall_ms"]
                <= limits["host_or_browser_timeout_s"] * 1000,
                "successful source creation exceeds phase deadline",
            )
    expected = {
        (n, a, rep) for n in r["sizes"] for a in r["arms"] for rep in range(r["repetitions"])
    }
    actual = set()
    for c in r["results"]:
        key = c["n"], c["arm"], c["repetition"]
        require(
            integer(c["n"], 5, 1_000_000_000)
            and integer(c["repetition"], 0, 2)
            and key in expected
            and key not in actual,
            "duplicate/unexpected cell",
        )
        actual.add(key)
        require(text(c["status"]), "missing cell status")
        if c["status"] == "ok":
            require(
                number(c["host_prepare_wall_ms"], 0, limits["host_or_browser_timeout_s"] * 1000),
                "successful host preparation exceeds phase deadline",
            )
            require(
                c["host_meta"]["build_ms"] <= c["host_prepare_wall_ms"],
                "host build subclock exceeds preparation clock",
            )
            check_cell(
                c, r["sources"][str(c["n"])], cap, limits["step_timeout_s"], bool(historical)
            )
        else:
            check_failure(c)
            source_failure = c["status"] in (
                "source_memory_limit",
                "source_timeout",
                "source_failed",
            )
            require(
                (str(c["n"]) not in r["sources"]) == source_failure,
                "source presence differs from failure stage",
            )
            if source_failure:
                require(integer(c["source_peak_rss_bytes"]), "missing source guard observation")
    require(actual == expected, "incomplete cell coverage (all repetitions required)")


def load_report(path: Path) -> tuple[dict, str | None]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    require(len(raw) <= MAX_REPORT_BYTES, "report exceeds 64 MiB decoded bound")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise InvalidReport(f"nonfinite JSON constant: {value}")

    return json.loads(
        raw, object_pairs_hook=unique_object, parse_constant=invalid_constant
    ), HISTORICAL.get(hashlib.sha256(raw).hexdigest())


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("report", type=Path)
    p.add_argument("--sha")
    p.add_argument("--sizes", help="external expected actual row counts, CSV")
    p.add_argument("--arms", help="external expected arms, CSV")
    p.add_argument("--artifact-root", type=Path)
    args = p.parse_args()
    try:
        sizes = [int(v) for v in args.sizes.split(",")] if args.sizes is not None else None
        arms = args.arms.split(",") if args.arms is not None else None
        require(
            sizes is None or (sizes and len(sizes) == len(set(sizes))), "invalid external sizes"
        )
        require(arms is None or (arms and len(arms) == len(set(arms))), "invalid external arms")
        r, historical = load_report(args.report)
        errors = validate(
            r,
            expected_sha=args.sha,
            expected_sizes=sizes,
            expected_arms=arms,
            artifact_root=args.artifact_root,
            historical=historical,
        )
        if errors:
            raise InvalidReport("; ".join(errors))
        successes = sum(c["status"] == "ok" for c in r["results"])
        print(
            f"Valid evidence: {successes} successful cells, {len(r['results']) - successes} failed cells. Programmatic clocks only; no gesture, kernel-win or competitive acceptance claim."
        )
        if historical and args.artifact_root:
            print(
                "Historical raw archive: retained producer binding checked; current product/native/client artifacts are not historical proof."
            )
        return 0
    except (ValueError, OSError, TypeError, EOFError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
