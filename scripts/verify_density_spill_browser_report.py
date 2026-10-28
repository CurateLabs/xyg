#!/usr/bin/env python3
"""Validate a same-source browser companion against immutable host report bytes.

The host verifier independently enforces authority, limits and kernel latency.
This verifier adds browser continuity, never FPS or end-to-end latency claims.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import struct
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import verify_density_spill_report as host  # noqa: E402

require = host.require
integer = host.integer
digest = host.digest
number = host.number


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def active(frame: dict) -> list:
    return [
        {k: v for k, v in t.items() if k != "body_bytes"} for t in frame["inventory"] if t["active"]
    ]


def ink(sample: dict) -> None:
    require(
        integer(sample["densityPixels"], 101)
        and integer(sample["redPixels"], 21)
        and integer(sample["bluePixels"], 21)
        and sample["redPixels"] + sample["bluePixels"] <= sample["densityPixels"],
        "blank/missing endpoint color ink",
    )


def same_frame(a: dict, b: dict) -> None:
    require(
        active(a) == active(b)
        and all(
            a[k] == b[k] for k in ("generation", "level", "opacity", "source_log_max", "window_max")
        ),
        "native active tile bytes/geometry/exposure differ",
    )


def owned_gpu(gpu: dict) -> None:
    resources, events = gpu["resources"], gpu["events"]
    require(isinstance(resources, list) and bool(resources), "missing owned resource inventory")
    by_id = {r["id"]: r for r in resources}
    require(len(by_id) == len(resources), "duplicate owned resource identity")
    live, created, deleted = {}, set(), set()
    peak = tile_peak = uploads = 0
    for event in events:
        key, op, size = event["id"], event["op"], event["bytes"]
        require(key in by_id and integer(size, 0), "invalid owned allocation event")
        if op == "create":
            require(key not in created and size == 0, "owned creation identity/size")
            created.add(key)
            live[key] = 0
        elif op == "storage":
            require(key in created - deleted, "storage after deletion/before creation")
            live[key] = size  # Reallocation replaces capacity, including shrink.
            uploads += by_id[key]["kind"] == "texture"
        elif op == "delete":
            require(
                key in created - deleted and size == live[key], "missing/repeated owned deletion"
            )
            deleted.add(key)
            live[key] = 0
        else:
            raise ValueError("unknown owned allocation event")
        peak = max(peak, sum(live.values()))
        tile_peak = max(
            tile_peak, sum(v for k, v in live.items() if by_id[k]["category"] == "tiles")
        )
    require(created == deleted == set(by_id) and not any(live.values()), "owned resource leak")
    require(
        all(
            integer(r["id"], 1)
            and r["deleted"] is True
            and r["kind"] in {"texture", "buffer"}
            and r["category"] in {"initial", "LUT", "pick", "chart", "oracle", "tiles"}
            and integer(r["bytes"], 0)
            and (
                r["kind"] != "buffer"
                or (
                    integer(r["logicalBytes"], 0)
                    and r["bytes"] == math.ceil(r["logicalBytes"] / 256) * 256
                )
            )
            and r["bytes"] == next(e["bytes"] for e in reversed(events) if e["id"] == r["id"])
            for r in resources
        ),
        "owned inventory/category differs from events",
    )
    for kind in ("texture", "buffer"):
        name = "Textures" if kind == "texture" else "Buffers"
        require(
            gpu["created" + name]
            == gpu["deleted" + name]
            == sum(r["kind"] == kind for r in resources)
            > 0,
            "owned creation/deletion counts",
        )
    require(
        any(r["category"] == "initial" for r in resources)
        and any(r["category"] == "LUT" for r in resources)
        and gpu["categories"]
        == {
            category: {
                "created": sum(r["category"] == category for r in resources),
                "deleted": sum(r["category"] == category and r["deleted"] for r in resources),
            }
            for category in ("initial", "LUT", "pick", "chart", "oracle", "tiles")
        },
        "initial/LUT/pick/category accounting absent",
    )
    require(
        gpu["peakInstrumentedBytes"] == peak
        and gpu["tilePeakBytes"] == tile_peak
        and 0 < tile_peak <= 8 * 512 * 512 * 4
        and gpu["uploads"] == uploads
        and gpu["remainingTextures"] == 0,
        "owned peak/reallocation/tile budget accounting",
    )
    require(
        all(
            gpu[k] is True
            for k in ("explicitDeletionBeforeContextLoss", "noReferences", "noGLError")
        )
        and gpu["staleReplyEvents"] == 0,
        "owned destroy/context loss/stale reply failure",
    )


def normal_sample(sample: dict, cached: dict, previous: dict, frame: dict) -> None:
    frames, adoption = sample["frames"], sample["adoption"]
    require(
        number(sample["startedAt"], 0)
        and number(adoption["at"], sample["startedAt"])
        and adoption["level"] == frame["level"]
        and integer(adoption["seq"], 0),
        "normal asynchronous adoption missing",
    )
    require(bool(frames), "normal RAF draws absent")
    last_at = sample["startedAt"]
    transition_count = 0
    previous_keys = {"/".join(map(str, t["key"])) for t in previous["inventory"] if t["active"]}
    for draw in frames:
        require(
            number(draw["at"], last_at)
            and draw["at"] > last_at
            and number(draw["clock"], draw["at"])
            and number(draw["clockEnd"], draw["clock"]),
            "normal draws require monotonic product clock",
        )
        last_at = draw["at"]
        require(digest(draw["pixelSha256"]) and bool(draw["drawn"]), "normal nonblank draw missing")
        ink(draw["ink"])
        for d in draw["drawn"]:
            require(
                d["sourceAlive"] is True and number(d["opacity"], 0, 1) and bool(d["keys"]),
                "normal outgoing source reference lost",
            )
        outgoing = [
            d for d in draw["drawn"] if d["level"] == previous["level"] and 0 < d["opacity"] < 1
        ]
        incoming = [
            d for d in draw["drawn"] if d["level"] == frame["level"] and 0 < d["opacity"] < 1
        ]
        if sample["kind"] == "zoom" and outgoing and incoming:
            require(
                all(set(d["keys"]) == previous_keys for d in outgoing),
                "normal outgoing keys differ",
            )
            transition_count += 1
    require(
        sample["transitionFrames"] == transition_count
        and (transition_count > 0 if sample["kind"] == "zoom" else transition_count == 0),
        "normal adjacent transition draws missing",
    )
    require(
        frames[-1]["retired"] is True
        and frames[-1]["outgoingKeys"] == []
        and frames[-1]["at"] >= adoption["at"]
        and sample["cachedPixelEquality"] is True
        and sample["settledPixelSha256"] == frames[-1]["pixelSha256"] == cached["pixelSha256"],
        "normal settled pixels/retirement differ from deterministic oracle",
    )
    if sample["kind"] == "zoom":
        require(len({d["pixelSha256"] for d in frames}) > 1, "normal transition pixels unchanged")


def validate(
    report: Any,
    host_bytes: bytes,
    *,
    expected_sha: str | None = None,
    environ: dict[str, str] | None = None,
    artifact_root: Path | None = None,
    require_hardware: bool = False,
) -> list[str]:
    try:
        _validate(
            report,
            host_bytes,
            expected_sha,
            dict(os.environ) if environ is None else environ,
            artifact_root,
        )
        if require_hardware:
            require(
                report["schema_version"] == 3 and report["browser"]["requested_gl"] == "hardware",
                "hardware evidence requires the owned/normal accelerated contract",
            )
    except (
        ValueError,
        KeyError,
        TypeError,
        OverflowError,
        AttributeError,
        OSError,
        struct.error,
    ) as exc:
        return [str(exc) or type(exc).__name__]
    return []


def _validate(r: dict, host_bytes: bytes, expected_sha, environ, artifact_root) -> None:
    h = json.loads(host_bytes)
    errors = host.validate(
        h, expected_sha=expected_sha, environ=environ, artifact_root=artifact_root
    )
    require(not errors, "matching host report invalid: " + "; ".join(errors))
    require(r["host_report_sha256"] == sha(host_bytes), "immutable host report SHA-256 differs")
    modern = r["schema_version"] == 3
    require(
        r["schema_version"] == 3
        and r["report_kind"] == "density-colored-spill-browser-companion"
        and r["scope"]
        == (
            "same-source-real-browser-owned-resources-and-normal-cadence"
            if modern
            else "same-source-real-browser-deterministic-cadence"
        )
        and r["status"] == "ok",
        "must pass the distinct browser companion contract",
    )
    for key in (
        "authority",
        "authority_context",
        "request_path",
        "point_count",
        "source",
        "environment",
        "provenance",
        "spill_file",
        "count_color_oracle",
        "limits",
        "process_tree",
    ):
        require(r[key] == h[key], "companion differs from actual host " + key)
    require(
        r["host_cleanup"] == h["cleanup"]
        and r["host_cleanup"]["browser_socket_alias_removed"] is True,
        "supervisor cleanup missing/different",
    )
    require(r["cleanup"]["server_stopped"] is True, "HTTP server/thread not stopped")
    tree = r["process_tree"]
    browser = r["browser"]
    require(
        tree["browser_process_observed"] is True
        and integer(browser["pid"], 1)
        and integer(browser["pgid"], 1)
        and browser["pid"] != browser["pgid"],
        "browser must be a child of supervised worker group",
    )
    observed = tree["observed_processes"]
    require(
        len(observed) == tree["observed_process_count"]
        and len({p["pid"] for p in observed}) == len(observed)
        and any(
            p["pid"] == browser["pid"]
            and ("chrome" in p["name"].lower() or "chromium" in p["name"].lower())
            for p in observed
        )
        and any(p["pid"] == browser["pgid"] for p in observed),
        "actual browser/worker process absent from supervisor observations",
    )
    require(
        browser["process_reaped"] is True and browser["profile_removed"] is True,
        "browser process/profile leaked",
    )
    require(
        isinstance(browser["cdp_version"]["product"], str)
        and (
            "Chrome/" in browser["cdp_version"]["product"]
            or "Chromium/" in browser["cdp_version"]["product"]
        )
        and isinstance(browser["userAgent"], str)
        and "Chrome/" in browser["userAgent"]
        and number(browser["devicePixelRatio"], 0.1, 10),
        "missing real browser version",
    )
    for name, path in (
        ("harness", "scripts/density_spill_browser_smoke.py"),
        ("verifier", "scripts/verify_density_spill_browser_report.py"),
        ("chromium", None),
    ):
        expected = r["browser_artifacts"][name + "_sha256"]
        require(digest(expected), "missing browser artifact hash")
        if artifact_root is not None and path:
            require(
                sha((artifact_root / path).read_bytes()) == expected,
                "browser artifact hash differs: " + path,
            )
    n, d, domain = r["point_count"], r["decisions"], r["domain"]
    require(domain == h["decisions"]["domain"], "browser domain differs from production host")
    require(
        d["base_dim"] == h["decisions"]["base_dim"]
        and d["screen"] == [512, 512]
        and d["tile_budget_bytes"] == 16 * 1024**2
        and d["native_tile_bootstrap"] is True
        and d["first_payload_binning"] == h["initial_payload"]["binning"]
        and d["first_payload_reduction"] == h["initial_payload"]["reduction"]
        and d["presentation"]
        == (
            "deterministic oracle plus separate product RAF/monotonic-clock journey; readback is not production FPS"
            if modern
            else "manual draw cadence and frozen clock; product fade/source selection unchanged"
        ),
        "browser decisions/presentation scope changed",
    )
    windows = [{"kind": s["kind"], "window": s["window"]} for s in h["samples"]]
    require(
        r["windows"] == windows and len(windows) == 32, "browser must replay all exact host windows"
    )
    for phase in ("before_browser", "after_browser"):
        require(
            r["mapping_inventory"][phase] == h["mapping_inventory"]["after_samples"],
            "browser copied/replaced canonical mappings",
        )
    p = r["initial_payload"]
    require(
        p["blob_bytes"] == h["initial_payload"]["bytes"]
        and integer(p["blob_bytes"], 1, 4 * 1024**2)
        and all(digest(p[k]) for k in ("spec_sha256", "blob_sha256", "split_spec_sha256"))
        and len(p["split_buffer_sha256"]) == h["initial_payload"]["buffer_count"]
        and all(digest(v) for v in p["split_buffer_sha256"]),
        "invalid bounded initial payload hashes",
    )
    require(n == 100_000_000 if r["authority"] else n <= 1_000_000, "invalid browser scale")
    base = 4096 if r["authority"] else 2048
    bootstrap = r["bootstrap"]
    pool = host.check_frame(bootstrap, {}, domain, base)
    same_frame(bootstrap, h["seed"])
    require(
        len(r["requests"]) == (99 if modern else 66), "require all 33 cached and fresh requests"
    )
    runs = browser["runs"]
    require(
        set(runs) == ({"cached", "fetch-all", "normal"} if modern else {"cached", "fetch-all"}),
        "require both actual browser runs",
    )
    transferred = {}
    cached_frames = []
    if modern:
        from scripts.density_spill_browser_smoke import renderer_guard

        mode = browser["requested_gl"]
        probe = browser["preflight"]
        require(
            probe["requested_gl"] == mode
            and probe["status"] == "ok"
            and probe["contextLost"] is False
            and probe["process_reaped"] is True
            and probe["profile_removed"] is True,
            "preallocation renderer preflight failed",
        )
        renderer_guard(probe["renderer"], probe["gpu_info"], mode)
        if mode == "hardware":
            require(
                browser["hardware_context"] == probe["hardware_context"],
                "hardware workflow identity differs between preflight and journey",
            )
            require(
                h["environment"]["platform"]["system"] == "Darwin"
                and h["environment"]["platform"]["machine"] == "arm64",
                "hardware evidence requires Darwin arm64",
            )
            if r["authority"]:
                require(
                    browser["hardware_context"]
                    == {
                        key: environ.get(key)
                        for key in (
                            "GITHUB_REPOSITORY",
                            "GITHUB_WORKFLOW_REF",
                            "GITHUB_WORKFLOW_SHA",
                        )
                    },
                    "hardware workflow identity differs from trusted ambient run",
                )
                from benchmarks._density_spill import hardware_context_guard

                hardware_context_guard(
                    environ,
                    authority=True,
                    system=h["environment"]["platform"]["system"],
                    machine=h["environment"]["platform"]["machine"],
                )
    for mode_index, mode in enumerate(
        ("cached", "fetch-all", "normal") if modern else ("cached", "fetch-all")
    ):
        run = runs[mode]
        require(
            run["destroyed"] is True and run["lateReplyIgnored"] is True,
            "destroy/stale reply lifecycle failed",
        )
        require(
            len(run["canvas"]) == 2 and all(integer(v, 512, 4096) for v in run["canvas"]),
            "invalid framebuffer extent",
        )
        pixel_bytes = math.prod(run["canvas"]) * 4
        require(
            all(
                isinstance(run["renderer"][k], str) and run["renderer"][k]
                for k in ("vendor", "renderer", "version")
            ),
            "missing WebGL renderer",
        )
        gpu = run["gpu"]
        if modern:
            renderer_guard(run["renderer"], browser["gpu_info"], browser["requested_gl"])
            owned_gpu(gpu)
        else:
            require(
                integer(gpu["createdTextures"], 34)
                and gpu["deletedTextures"] == gpu["createdTextures"] == gpu["uploads"]
                and gpu["remainingTextures"] == 0
                and integer(gpu["peakInstrumentedBytes"], 1, 512 * 512 * 4 * 8 + 2048 * 2048 * 4),
                "actual GPU allocation/deletion accounting failed",
            )
        samples = run["samples"]
        require(len(samples) == 33, "missing browser framebuffer samples")
        previous, held = bootstrap, dict(pool)
        transferred[mode] = 0
        for at, sample in enumerate(samples):
            index = at - 1
            frame = r["requests"][mode_index * 33 + at]
            step = {"kind": "seed", "window": windows[0]["window"]} if index < 0 else windows[index]
            require(
                sample["index"] == frame["index"] == index
                and frame["mode"] == mode
                and sample["kind"] == step["kind"]
                and sample["window"] == frame["window"] == step["window"],
                "browser request/sample program differs",
            )
            control = base64.b64decode(frame["control_base64"], validate=True)
            require(
                sha(control) == frame["control_sha256"] and len(control) >= 32,
                "control digest differs",
            )
            magic, version, generation, opacity, level, count = struct.unpack_from(
                "<4sIQdiI", control
            )
            require(
                magic == b"XYDC"
                and version == 1
                and generation == previous["generation"]
                and opacity == previous["opacity"]
                and level == previous["level"]
                and len(control) == 32 + count * 12,
                "invalid actual XYDC control",
            )
            keys = [struct.unpack_from("<3I", control, 32 + i * 12) for i in range(count)]
            require(
                len(set(keys)) == count
                and set(keys) == (set(held) if mode != "fetch-all" else set()),
                "client control inventory differs from actual previous ownership",
            )
            held = host.check_frame(frame, held if mode != "fetch-all" else {}, domain, base)
            host.check_stats(frame["stats"])
            same_frame(frame, h["seed"] if index < 0 else h["samples"][index])
            stats = sample["stats"]
            require(
                stats["resourceCoarsened"] is False
                and stats["level"] == frame["level"]
                and stats["budget"] == frame["gpu_budget_bytes"]
                and stats["gpuBytes"] == stats["allocatedTileBytes"] == frame["gpu_bytes"]
                and stats["liveTextures"] == len(frame["inventory"])
                and stats["received"] == stats["uploads"] == frame["transferred_tiles"],
                "GPU ownership differs from native inventory",
            )
            require(
                abs(frame["level"] - previous["level"]) == (1 if step["kind"] == "zoom" else 0),
                "browser failed adjacent level journey",
            )
            transferred[mode] += stats["received"]
            if mode == "normal":
                normal_sample(sample, runs["cached"]["samples"][at], previous, frame)
                previous = frame
                continue
            require(
                digest(sample["pixelSha256"])
                and digest(sample["backgroundPixelSha256"])
                and sample["pixelSha256"] != sample["backgroundPixelSha256"],
                "blank/invalid framebuffer hash",
            )
            ink(sample)
            seam = sample["seam"]
            require(
                seam["method"] == "native-gutters-to-monolithic-texture"
                and seam["tolerance"] == 2
                and integer(seam["maxError"], 0, 2)
                and integer(seam["overlappingCells"], 1)
                and integer(seam["examinedPixels"], 1, pixel_bytes // 4)
                and integer(seam["densityPixels"], 21, seam["examinedPixels"])
                and integer(seam["width"], 1, 2048)
                and integer(seam["height"], 1, 2048)
                and seam["width"] * seam["height"] <= 2048**2
                and digest(seam["monolithicPixelSha256"]),
                "nonblank seam oracle failed",
            )
            for edges, lo, hi in (
                (seam["edgeX"], step["window"][0], step["window"][1]),
                (seam["edgeY"], step["window"][2], step["window"][3]),
            ):
                require(
                    isinstance(edges, list)
                    and all(number(v, lo, hi) and lo < v < hi for v in edges),
                    "invalid seam boundary",
                )
            require(seam["edgeX"] or seam["edgeY"], "missing internal seams")
            require(
                integer(seam["wholeImage"]["changedBytes"], 0, pixel_bytes)
                and integer(seam["wholeImage"]["maxError"], 0, 255),
                "invalid seam image comparison",
            )
            if mode == "fetch-all":
                cached = runs["cached"]["samples"][at]
                require(
                    sample["cachedPixelEquality"] is True
                    and sample["pixelSha256"] == cached["pixelSha256"],
                    "cached/fresh framebuffer pixels differ",
                )
                same_frame(frame, cached_frames[at])
            else:
                cached_frames.append(frame)
            fade = sample["fade"]
            if mode == "cached" and step["kind"] == "zoom":
                require(
                    fade["sourceLevel"] == previous["level"]
                    and fade["targetLevel"] == frame["level"]
                    and fade["sourceSurvived"] is True
                    and fade["retired"] is True,
                    "fade source/retirement failed",
                )
                previous_active = {
                    "/".join(map(str, t["key"])) for t in previous["inventory"] if t["active"]
                }
                retained = {"/".join(map(str, t["key"])) for t in frame["inventory"]}
                require(
                    set(fade["sourceKeys"]) == previous_active and previous_active <= retained,
                    "fade source keys did not survive",
                )
                require(
                    all(digest(fade[k + "PixelSha256"]) for k in ("start", "middle", "end"))
                    and fade["startPixelSha256"]
                    != fade["middlePixelSha256"]
                    != fade["endPixelSha256"],
                    "fade pixels did not change",
                )
                for k in ("startMid", "midEnd"):
                    require(
                        integer(fade[k]["changedBytes"], 1, pixel_bytes)
                        and integer(fade[k]["maxError"], 1, 255),
                        "fade intermediate image unchanged",
                    )
                ink(fade["middleInk"])
                drawn = fade["drawn"]
                require(
                    len(drawn) == 2
                    and {d["level"] for d in drawn} == {previous["level"], frame["level"]}
                    and all(number(d["opacity"], 0, 1) and 0 < d["opacity"] < 1 for d in drawn),
                    "both adjacent levels must actually draw",
                )
            else:
                require(fade is None, "unexpected fade scope")
            previous = frame
        require(
            gpu["peakInstrumentedBytes"] >= max(s["stats"]["gpuBytes"] for s in samples),
            "GPU peak below live allocation",
        )
        if modern:
            require(
                gpu["tilePeakBytes"] >= max(s["stats"]["allocatedTileBytes"] for s in samples),
                "owned tile peak below native inventory",
            )
    require(
        0 <= transferred["cached"] < transferred["fetch-all"],
        "cache must reduce actual tile transfers",
    )
    captures = browser["captures"]
    require(
        set(captures) == {"pan.png", "zoom.png", "adjacent-fade.png"},
        "missing framebuffer captures",
    )
    require(set(browser["capture_sha256"]) == set(captures), "capture hashes missing")
    for name, encoded in captures.items():
        require(
            encoded.startswith("data:image/png;base64,")
            and base64.b64decode(encoded.split(",", 1)[1], validate=True).startswith(
                b"\x89PNG\r\n\x1a\n"
            ),
            "invalid PNG capture",
        )
        require(
            sha(base64.b64decode(encoded.split(",", 1)[1], validate=True))
            == browser["capture_sha256"][name],
            "framebuffer capture hash differs",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--host-report", type=Path, required=True)
    parser.add_argument("--require-hardware", action="store_true")
    parser.add_argument("--sha")
    parser.add_argument("--artifact-root", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(
            json.loads(args.report.read_bytes()),
            args.host_report.read_bytes(),
            expected_sha=args.sha,
            artifact_root=args.artifact_root,
            require_hardware=args.require_hardware,
        )
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    for error in errors:
        print("- " + error, file=sys.stderr)
    if not errors:
        print("same-source colored-spill browser companion OK; scope is recorded in its schema")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
