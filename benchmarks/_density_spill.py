"""Distinct #11 colored-spill host/kernel evidence under the #876 supervisor.

Dossier §§5/27/28/32b. No browser or whole-Phase-4 completion is claimed here.
"""

from __future__ import annotations

import gc
import hashlib
import math
import os
import re
import struct
import tempfile
import time
import weakref
from pathlib import Path
from typing import Any
from unittest.mock import patch

from benchmarks import bench_density_e2e as supervisor

ROOT = supervisor.ROOT
KIND = "density-colored-spill"
WORKLOAD = "colored-spill"
SCOPE = "host-kernel-only"
MAX_RSS = 12 * 1024**3
MAX_DISK = 4 * 1024**3
MAX_SECONDS = 3600
TILE_BUDGET = 16 * 1024**2
SCREEN = 512
PAN_COUNT = 24
ZOOM_COUNT = 8
TIMING_SCOPE = (
    "tile_store_paint ABI wrapper only; excludes host dispatch, stats, parsing and oracles"
)
COLORMAP = [[240, 50, 40], [20, 90, 230]]
AUTH_ENV = (
    "GITHUB_ACTIONS",
    "GITHUB_REF",
    "GITHUB_EVENT_NAME",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_SHA",
    "XYG_DENSITY_100M_AUTHORITY",
)


def authority_context(environ: dict[str, str]) -> dict[str, str | None]:
    return {key: environ.get(key) for key in AUTH_ENV}


def guard(
    points: int, authority: bool, environ: dict[str, str], timeout: float, rss: float, disk: float
) -> None:
    """Validate before allocation, including the internal worker entry point."""
    if not __debug__:
        raise ValueError("colored-spill evidence requires Python assertions enabled")
    if not isinstance(points, int) or isinstance(points, bool) or points <= 0:
        raise ValueError("colored-spill points must be a positive integer")
    if not authority and points > 1_000_000:
        raise ValueError("colored-spill controls are limited to 1M points")
    if authority:
        supervisor._authority_guard(points, authority, environ)
        if (
            environ.get("GITHUB_ACTIONS") != "true"
            or not re.fullmatch(r"[1-9][0-9]*", environ.get("GITHUB_RUN_ID", ""))
            or not re.fullmatch(r"[1-9][0-9]*", environ.get("GITHUB_RUN_ATTEMPT", ""))
            or not re.fullmatch(r"[0-9a-f]{40}", environ.get("GITHUB_SHA", ""))
        ):
            raise ValueError("colored-spill authority requires actual GitHub Actions run context")
    if any(
        not math.isfinite(v) or not 0 < v <= cap
        for v, cap in ((timeout, MAX_SECONDS), (rss, 12), (disk, 4))
    ):
        raise ValueError("colored-spill ceilings are pinned at 12GiB RSS / 4GiB disk / 3600s")


def browser_guard(config: dict) -> None:
    """Optional browser admission, run by both entries before source allocation."""
    mode = config.get("colored_browser_gl", "software")
    if mode not in {"software", "hardware"}:
        raise ValueError("colored browser GL must be software or hardware")
    if mode == "hardware" and not config.get("colored_browser_report"):
        raise ValueError("hardware requires the colored browser companion")
    if not config.get("colored_browser_report"):
        return
    if config.get("workload") != WORKLOAD:
        raise ValueError("--colored-browser-report requires --workload colored-spill")
    chrome = Path(config.get("chrome") or "")
    if not chrome.is_file() or not os.access(chrome, os.X_OK):
        raise ValueError("browser companion requires an executable --chrome")
    import subprocess

    try:
        version = subprocess.run(
            [str(chrome), "--version"], capture_output=True, text=True, timeout=10, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("browser companion --chrome could not report its version") from exc
    if not re.search(r"Chrom(?:e|ium)", version):
        raise ValueError("browser companion --chrome must identify Chrome/Chromium")
    if config.get("authority"):
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()
        if commit != os.environ.get("GITHUB_SHA") or dirty:
            raise ValueError("authority browser requires a clean checkout at the actual run SHA")
    if mode == "hardware":
        hardware_context_guard(dict(os.environ), authority=bool(config.get("authority")))
    output = Path(config["colored_browser_report"]).resolve()
    if output == Path(config["host_output"]).resolve():
        raise ValueError("browser companion and host outputs must be distinct")
    if output.exists() and not output.is_file():
        raise ValueError("browser companion output must be a file")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Probe actual output access before allocating mappings or native stores.
    with tempfile.TemporaryFile(dir=output.parent):
        pass


def hardware_context_guard(
    environ: dict[str, str],
    *,
    authority: bool,
    system: str | None = None,
    machine: str | None = None,
) -> None:
    import platform

    if (system or platform.system()) != "Darwin" or (machine or platform.machine()) != "arm64":
        raise ValueError(
            "colored hardware experiment requires Darwin arm64 on the existing M4 runner"
        )
    if authority and (
        environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or environ.get("GITHUB_WORKFLOW_REF")
        != f"{environ.get('GITHUB_REPOSITORY')}/.github/workflows/ceiling-benchmark.yml@refs/heads/main"
        or environ.get("GITHUB_WORKFLOW_SHA") != environ.get("GITHUB_SHA")
        or environ.get("GITHUB_REPOSITORY") != "CurateLabs/xyg"
    ):
        raise ValueError(
            "hardware authority requires the exact manual-main ceiling workflow identity"
        )


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def provenance(environment: dict[str, Any]) -> dict[str, Any]:
    from xyg import _native
    from xyg._abi_generated import ABI_VERSION

    files = {}
    for directory, suffixes in (
        ("python/xyg", {".py"}),
        ("crates", {".rs", ".toml"}),
        ("js/src", {".ts"}),
    ):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and path.suffix in suffixes:
                files[str(path.relative_to(ROOT))] = file_hash(path)
    harness_files = (
        "benchmarks/bench_density_e2e.py",
        "benchmarks/_density_spill.py",
        "scripts/verify_density_spill_report.py",
        "benchmarks/environment.py",
        "Cargo.lock",
        "package-lock.json",
        "uv.lock",
        "rust-toolchain.toml",
    )
    harness = {name: file_hash(ROOT / name) for name in harness_files}
    return {
        "native_path": str(Path(_native._lib._name).resolve().relative_to(ROOT)),
        "client_path": "python/xyg/static/standalone.js",
        "source_files": files,
        "source_sha256": supervisor._sha256(supervisor._json_bytes(files)),
        "harness_files": harness,
        "harness_sha256": supervisor._sha256(supervisor._json_bytes(harness)),
        "environment_sha256": supervisor._sha256(supervisor._json_bytes(environment)),
        "native_sha256": file_hash(Path(_native._lib._name)),
        "native_abi": ABI_VERSION,
        "client_sha256": file_hash(ROOT / "python/xyg/static/standalone.js"),
    }


def generate(tmp: Path, points: int, chunk: int) -> tuple[Any, Any, Any, dict[str, Any]]:
    """All three canonical inputs are f64 mappings; scratch is chunk-bounded.

    Public continuous color admission borrows the mapping. Native color build
    uses an explicitly accounted N-byte index plus a 1024-byte RGBA LUT, never
    an N-by-4 f64 RGBA expansion. Only the two endpoint LUT indices are used.
    """
    import numpy as np

    if not 1 <= chunk <= 1_000_000:
        raise ValueError("colored-spill chunk must be within 1..1M")
    maps = [
        np.memmap(tmp / f"{name}.f64", dtype="float64", mode="w+", shape=(points,))
        for name in ("x", "y", "color")
    ]
    hashes = [hashlib.sha256() for _ in maps]
    for start in range(0, points, chunk):
        stop = min(start + chunk, points)
        row = np.arange(start, stop, dtype=np.uint64)
        xv = ((row * 48_271 + 11) % 1_000_003).astype(np.float64) / 1_000_003
        yv = np.remainder(xv * 0.82 + (row % 7) * 0.031, 1.0)
        # Spatially distinct, overlapping band colors remain distinguishable
        # even after many source-period repeats at 100M. Row parity alone
        # converges to one uniform mean and is a weak colored workload.
        cv = ((row % 7) >= 3).astype(np.float64)
        for mapping, values, digest in zip(maps, (xv, yv, cv), hashes, strict=True):
            mapping[start:stop] = values
            digest.update(memoryview(values))
    for mapping in maps:
        mapping.flush()
    source = {
        "generator": "diagonal-band-two-color-v1",
        "backing": "mmap-f64",
        "chunk_points": chunk,
        "bytes": points * 24,
        "columns": {
            name: {"bytes": points * 8, "sha256": digest.hexdigest()}
            for name, digest in zip(("x", "y", "color"), hashes, strict=True)
        },
        "color_mode": "continuous-mapped-to-u8-index",
        "colormap": COLORMAP,
    }
    return maps[0], maps[1], maps[2], source


def mapping_inventory(fig: Any, sources: tuple[Any, Any, Any]) -> dict[str, Any]:
    import numpy as np

    from xyg._ooc import is_memmapped

    trace = fig.traces[0]
    held = (trace.x.values, trace.y.values, trace.color_ch.values)
    entries = {}
    for name, original, value in zip(("x", "y", "color"), sources, held, strict=True):
        assert value is not None and value.dtype == np.float64
        assert is_memmapped(value) and np.shares_memory(original, value)
        assert value.ctypes.data == original.ctypes.data
        entries[name] = {"bytes": value.nbytes, "pointer_equal": True, "mapped": True}
    assert not trace._bin_colors, "memmap trace retained a row-sized derived color cache"
    return entries


def windows(domain: list[float]) -> list[dict[str, Any]]:
    x0, x1, y0, y1 = domain
    dx, dy = x1 - x0, y1 - y0
    # Half-domain viewport gives 512 source cells at base=1024, etc. Offsets
    # overlap and reverse deterministically. Actual levels must be observed.
    result = []
    for offset in [0, 1, 2, 3, 4, 3, 2, 1] * (PAN_COUNT // 8):
        lo = offset / 16
        result.append(
            {"kind": "pan", "window": [x0 + lo * dx, x0 + (lo + 0.5) * dx, y0, y0 + 0.5 * dy]}
        )
    # Halving/doubling the pan span requests neighboring levels. Both spans
    # fit the paint budget including source-cell gutters.
    for index in range(ZOOM_COUNT):
        span = 0.25 if index % 2 == 0 else 0.5
        result.append(
            {
                "kind": "zoom",
                "window": [
                    x0 + 0.125 * dx,
                    x0 + (0.125 + span) * dx,
                    y0 + 0.125 * dy,
                    y0 + (0.125 + span) * dy,
                ],
            }
        )
    return result


def control(state: dict[str, Any] | None) -> bytes:
    if state is None:
        return struct.pack("<4sIQdiI", b"XYDC", 1, 0, -1.0, -1, 0)
    return struct.pack(
        "<4sIQdiI",
        b"XYDC",
        1,
        state["generation"],
        state["opacity"],
        state["level"],
        len(state["inventory"]),
    ) + b"".join(struct.pack("<3I", *tile["key"]) for tile in state["inventory"])


def parse_frame(packet: bytes, pool: dict[tuple[int, int, int], str]) -> tuple[dict, dict]:
    """Observe every Rust-retained tile, never invent a client cache key."""
    assert packet[:8] == b"XYDT\x01\0\0\0" and len(packet) >= 128
    level, flags, count, active, missing, stride = struct.unpack_from("<6I", packet, 8)
    generation = struct.unpack_from("<Q", packet, 32)[0]
    maximum, source_log_max, opacity = struct.unpack_from("<3d", packet, 40)
    gpu_budget, gpu_bytes, width, height, fetches, target = struct.unpack_from("<6I", packet, 64)
    assert flags & 1 and flags & ~7 == 0, "tile paint lost mean color"
    assert stride == 96 and 0 < active <= count <= 256
    assert width == height == SCREEN and gpu_bytes <= gpu_budget == SCREEN * SCREEN * 4 * 8
    assert all(math.isfinite(v) for v in (maximum, source_log_max, opacity))
    kept, inventory = {}, []
    offset_expected = 128 + count * stride
    transfers = logical = 0
    for index in range(count):
        at = 128 + index * stride
        lev, tx, ty, w, h, offset, length, visible = struct.unpack_from("<8I", packet, at)
        key = (lev, tx, ty)
        assert key not in kept and 3 <= w <= 258 and 3 <= h <= 258
        assert visible == int(index < active)
        logical += w * h * 4
        if length:
            assert (
                visible
                and length == w * h * 4
                and offset == offset_expected
                and offset + length <= len(packet)
            )
            offset_expected += length
            digest = supervisor._sha256(packet[offset : offset + length])
            transfers += 1
        else:
            assert offset == 0 and key in pool, "omitted texture was never held"
            digest = pool[key]
        assert not visible or lev == level
        kept[key] = digest
        inventory.append(
            {
                "key": list(key),
                "width": w,
                "height": h,
                "active": bool(visible),
                "body_bytes": length,
                "sha256": digest,
                "geometry": list(struct.unpack_from("<8d", packet, at + 32)),
            }
        )
    assert (
        offset_expected == len(packet) and transfers == missing == fetches and logical == gpu_bytes
    )
    return kept, {
        "generation": generation,
        "level": level,
        "flags": flags,
        "target_level": target,
        "opacity": opacity,
        "window_max": maximum,
        "source_log_max": source_log_max,
        "gpu_budget_bytes": gpu_budget,
        "gpu_bytes": gpu_bytes,
        "transferred_tiles": transfers,
        "reply_bytes": len(packet),
        "packet_sha256": supervisor._sha256(packet),
        "inventory": inventory,
    }


def stats(store: int) -> dict[str, Any]:
    from xyg import kernels

    raw = kernels.tile_store_stats(store)
    assert raw is not None
    hit, miss, resident, spilled, budget, over = raw
    assert spilled > 0 and resident <= budget == TILE_BUDGET and not over
    return dict(
        hit=hit,
        miss=miss,
        resident_bytes=resident,
        spilled_bytes=spilled,
        budget_bytes=budget,
        over_budget=over,
    )


def count_color_oracle(
    sources: tuple[Any, Any, Any], store: int, domain: list[float], base: int, chunk: int
) -> dict[str, Any]:
    """Independent chunked histogram + linear-light mean; outside timed path.

    A 64-square aligned overview uses exact 4->1 count conservation. Quantized
    u16 means at intermediate native levels may differ by at most 2 sRGB bytes.
    """
    import numpy as np

    from xyg import kernels

    dim = 64
    expected = np.zeros((dim, dim), dtype=np.float64)
    reds = expected.copy()
    x, y, color = sources
    x0, x1, y0, y1 = domain
    for start in range(0, len(x), chunk):
        stop = min(start + chunk, len(x))
        coords = (y[start:stop], x[start:stop])
        ranges = ((y0, y1), (x0, x1))
        expected += np.histogram2d(*coords, bins=dim, range=ranges)[0]
        reds += np.histogram2d(*coords, weights=1.0 - color[start:stop], bins=dim, range=ranges)[0]
    actual = kernels.tile_store_compose_color(store, x0, x1, y0, y1, dim, dim, 1_000_000)
    assert actual is not None
    counts, rgba, level = actual
    assert level == int(math.log2(base // dim))
    np.testing.assert_array_equal(counts.reshape(dim, dim), expected)
    assert int(expected.sum()) == len(x)
    endpoint = np.asarray(COLORMAP, dtype=float) / 255
    linear = np.where(endpoint <= 0.04045, endpoint / 12.92, ((endpoint + 0.055) / 1.055) ** 2.4)
    linear = np.floor(linear * 65535 + 0.5)
    occupied = expected > 0
    red_fraction = reds[occupied] / expected[occupied]
    means = (red_fraction[:, None] * linear[0] + (1 - red_fraction[:, None]) * linear[1]) / 65535
    encoded = np.where(means <= 0.0031308, means * 12.92, 1.055 * means ** (1 / 2.4) - 0.055)
    rgb = np.floor(encoded * 255 + 0.5).astype(np.int16)
    error = int(np.max(np.abs(rgba[occupied, :3].astype(np.int16) - rgb)))
    assert error <= 2 and np.all(rgba[occupied, 3] == 255)
    assert np.all(rgba[~occupied] == 0)
    assert len(np.unique(rgba[occupied, :3], axis=0)) > 1
    return {
        "method": "chunked-numpy-histogram-linear-srgb",
        "grid_dim": dim,
        "level": level,
        "count": int(counts.sum()),
        "expected_count": len(x),
        "max_count_error": float(np.max(np.abs(counts.reshape(dim, dim) - expected))),
        "max_rgb_error": error,
        "rgb_tolerance": 2,
        "occupied_cells": int(occupied.sum()),
        "nonopaque_occupied_cells": int(np.count_nonzero(rgba[occupied, 3] != 255)),
        "counts_sha256": supervisor._sha256(memoryview(counts)),
        "rgba_sha256": supervisor._sha256(memoryview(rgba)),
    }


def run_host(config: dict, tmp: Path, cleanup: dict) -> dict:
    import numpy as np

    import xyg
    from benchmarks.environment import collect_environment_metadata
    from xyg import interaction, kernels

    points, chunk = config["points"], config["chunk_points"]
    x = y = color = fig = trace = store = None
    old_budget = interaction.PYRAMID_RESIDENT_BYTES
    started = time.perf_counter()
    try:
        supervisor._observer_preflight()
        preflight = None
        if config.get("colored_browser_report"):
            from scripts.density_spill_browser_smoke import renderer_preflight

            preflight = renderer_preflight(
                config["chrome"],
                config.get("colored_browser_gl", "software"),
                Path(config["browser_socket_parent"]),
                min(config["timeout"], 30),
            )
        started = time.perf_counter()  # Preflights are not source-generation timing.
        x, y, color, source = generate(tmp, points, chunk)
        creation_seconds = time.perf_counter() - started
        sources = (x, y, color)
        # Test-only eligibility override. Authority uses production policy.
        threshold = 1 if not config["authority"] else interaction.PYRAMID_MIN_POINTS
        with patch.object(interaction, "PYRAMID_MIN_POINTS", threshold):
            interaction.sync_tile_budget(TILE_BUDGET)
            started = time.perf_counter()
            fig = xyg.scatter_chart(
                xyg.scatter(
                    x,
                    y,
                    color=color,
                    opacity=1.0,
                    color_domain=(0.0, 1.0),
                    colormap=COLORMAP,
                    density=True,
                    pyramid_spill=True,
                ),
                width=640,
                height=400,
            ).figure()
            admission_seconds = time.perf_counter() - started
            trace = fig.traces[0]
            mapped = {"admission": mapping_inventory(fig, sources)}
            native_inputs = []
            build_color = kernels.pyramid_build_color

            def observed_build(bx, by, *args, **kwargs):
                assert bx.ctypes.data == x.ctypes.data and by.ctypes.data == y.ctypes.data
                idx, lut = kwargs["idx"], kwargs["lut"]
                assert idx.dtype == np.uint8 and idx.nbytes == points
                assert lut.dtype == np.uint8 and lut.nbytes == 1024 and "rgba" not in kwargs
                assert np.array_equal(lut[0, :3], COLORMAP[0]) and np.array_equal(
                    lut[-1, :3], COLORMAP[1]
                )
                native_inputs.append(
                    {
                        "x_pointer_equal": True,
                        "y_pointer_equal": True,
                        "index_bytes": idx.nbytes,
                        "lut_bytes": lut.nbytes,
                        "index_sha256": supervisor._sha256(memoryview(idx)),
                        "lut_sha256": supervisor._sha256(memoryview(lut)),
                    }
                )
                return build_color(bx, by, *args, **kwargs)

            started = time.perf_counter()
            with patch.object(kernels, "pyramid_build_color", observed_build):
                if not config["authority"]:
                    interaction._ensure_pyramid(trace)
                spec, buffers = fig.build_payload_split()
            build_seconds = time.perf_counter() - started
            assert len(native_inputs) == 1 and trace._pyr_handle == 0 and trace._pyr_colored
            store = interaction._tile_store_of(trace)
            assert store and trace.pyramid_spill
            spill_paths = list(tmp.rglob("xy-tiles-*.xyts"))
            assert len(spill_paths) == 1
            spill_file = {
                "bytes": spill_paths[0].stat().st_size,
                "sha256": file_hash(spill_paths[0]),
            }
            assert spill_file["bytes"] == stats(store)["spilled_bytes"]
            initial = spec["traces"][0]["density"]
            if config["authority"]:
                assert "-tiles" in initial["binning"] and initial["reduction"] == "pyramid-count"
            else:
                assert initial["binning"] == "exact" and initial["reduction"] == "bin2d"
            assert initial.get("rgba"), "first paint lacks mean-color plane"
            payload = supervisor._buffer_inventory(spec, buffers)
            assert payload["canonical_f64_buffers"] == 0
            mapped["after_build"] = mapping_inventory(fig, sources)
            base = trace._pyr_base_dim
            domain = [trace.x.min, trace.x.max, trace.y.min, trace.y.max]
            domain[1] += (domain[1] - domain[0]) * 1e-9
            domain[3] += (domain[3] - domain[2]) * 1e-9
            samples: list[dict[str, Any]] = []
            pool, state = {}, None
            paint = kernels.tile_store_paint
            times = []

            def timed_paint(*args, **kwargs):
                start = time.perf_counter_ns()
                packet = paint(*args, **kwargs)
                times.append((time.perf_counter_ns() - start) / 1e6)
                return packet

            # Seed a genuine client inventory before the measured pan sequence.
            sx0, sx1, sy0, sy1 = windows(domain)[0]["window"]
            seed_packet = paint(store, sx0, sx1, sy0, sy1, SCREEN, SCREEN)
            assert seed_packet is not None
            pool, state = parse_frame(seed_packet, {})
            seed = {**state, "stats": stats(store)}
            for request in windows(domain):
                previous = state
                rx0, rx1, ry0, ry1 = request["window"]
                with patch.object(kernels, "tile_store_paint", timed_paint):
                    message, replies = fig.density_view(
                        trace.id, rx0, rx1, ry0, ry1, SCREEN, SCREEN, tile_cache=control(previous)
                    )
                assert len(times) == len(samples) + 1 and len(replies) == 1
                pool, state = parse_frame(replies[0], pool)
                entry = message["traces"][0]
                assert (
                    entry["binning"] == f"pyramid-L{state['level']}-tiles"
                    and entry["reduction"] == "pyramid-count"
                )
                delta = abs(state["level"] - previous["level"])
                assert delta == (1 if request["kind"] == "zoom" else 0), (
                    f"journey did not pan/reach an actual adjacent zoom level: kind={request['kind']} window={request['window']} previous={previous['level']} served={state['level']} flags={state['flags']} target={state['target_level']}"
                )
                assert state["flags"] == 1, (
                    "unexpected resource-coarsening/unfinished refine in fixed journey"
                )
                samples.append(
                    {
                        **request,
                        **state,
                        "kernel_ms": times[-1],
                        "previous_level": previous["level"],
                        "binning": entry["binning"],
                        "reduction": entry["reduction"],
                        "stats": stats(store),
                    }
                )
            # Separate fetch-all replay observes byte identity at each same
            # Rust level, framing, opacity and exposure; outside kernel timing.
            uncached: list[dict[str, Any]] = []
            for sample in samples:
                rx0, rx1, ry0, ry1 = sample["window"]
                packet = paint(store, rx0, rx1, ry0, ry1, SCREEN, SCREEN)
                assert packet is not None
                _, fresh = parse_frame(packet, {})

                def active(frame):
                    return [
                        {key: value for key, value in tile.items() if key != "body_bytes"}
                        for tile in frame["inventory"]
                        if tile["active"]
                    ]

                assert active(fresh) == active(sample)
                assert all(
                    fresh[key] == sample[key]
                    for key in ("generation", "level", "opacity", "source_log_max", "window_max")
                )
                uncached.append({**fresh, "stats": stats(store)})
            assert sum(s["transferred_tiles"] for s in samples) < sum(
                s["transferred_tiles"] for s in uncached
            )
            final_stats = stats(store)
            assert final_stats["hit"] > 0 and final_stats["miss"] > 0
            oracle = count_color_oracle(sources, store, domain, base, chunk)
            mapped["after_samples"] = mapping_inventory(fig, sources)
            memory = fig.memory_report()
            assert (
                memory["canonical_bytes"] == 0 and memory["canonical_mapped_bytes"] == points * 16
            )
            assert (
                memory["pyramid_spilled_bytes"] == final_stats["spilled_bytes"]
                and memory["bin_color_bytes"] == 0
            )
            pan_p95 = float(
                np.percentile([s["kernel_ms"] for s in samples if s["kind"] == "pan"], 95)
            )
            zoom_max = max(s["kernel_ms"] for s in samples if s["kind"] == "zoom")
            if config["authority"]:
                assert pan_p95 < 16, "authority pan p95 must be strictly below 16ms"
                assert zoom_max < 50, "every authority zoom must be strictly below 50ms"
            environment = collect_environment_metadata(xy_backend="native")
            if config["authority"]:
                assert environment["git"]["dirty"] is False
                assert environment["git"]["commit"] == os.environ["GITHUB_SHA"]
            report = {
                "schema_version": 1,
                "report_kind": KIND,
                "workload": WORKLOAD,
                "status": "ok",
                "scope": SCOPE,
                "authority": bool(config["authority"]),
                "authority_context": authority_context(dict(os.environ)),
                "point_count": points,
                "limits": {
                    "max_tree_rss_bytes": config["max_rss_bytes"],
                    "max_disk_bytes": config["max_disk_bytes"],
                    "timeout_seconds": config["timeout"],
                },
                "latency_policy": {
                    "pan_p95_ms": 16,
                    "each_zoom_ms": 50,
                    "enforcement": "hard" if config["authority"] else "advisory",
                },
                "timing_scope": TIMING_SCOPE,
                "pan_p95_ms": pan_p95,
                "zoom_max_ms": zoom_max,
                "source": source,
                "allocation_proof": "canonical pointer identity and retained-cache accounting; not a complete transient allocator audit",
                "mapping_inventory": mapped,
                "native_build_inputs": native_inputs,
                "decisions": {
                    "pyramid_min_points": threshold,
                    "production_pyramid_min_points": 2_000_000,
                    "test_override": not config["authority"],
                    "control_prewarm": not config["authority"],
                    "first_payload_policy": "production-native",
                    "base_dim": base,
                    "domain": domain,
                    "screen": [SCREEN, SCREEN],
                    "tile_budget_bytes": TILE_BUDGET,
                    "force_spill": True,
                    "color_source": "u8-index+RGBA-LUT",
                    "color_index_max_bytes": points,
                    "color_lut_bytes": 1024,
                    "color_resolution": "native-u8-output-borrowed-f64-input",
                },
                "phases": {
                    "source_creation_seconds": creation_seconds,
                    "admission_seconds": admission_seconds,
                    "build_spill_first_payload_seconds": build_seconds,
                },
                "initial_payload": {
                    **payload,
                    "binning": initial["binning"],
                    "reduction": initial["reduction"],
                    "mean_color": True,
                },
                "spill_file": spill_file,
                "seed": seed,
                "samples": samples,
                "fetch_all": uncached,
                "count_color_oracle": oracle,
                "final_stats": final_stats,
                "host_memory_report": memory,
                "environment": environment,
                "provenance": provenance(environment),
                "browser": {
                    "status": "not-run",
                    "reason": "host-kernel slice; real-browser colored-spill journey and nonblank/seam/cached-vs-fetch-all pixels remain open",
                },
                "cleanup": cleanup,
            }
            if config.get("colored_browser_report"):
                from scripts.density_spill_browser_smoke import run_existing

                browser_failure = None
                try:
                    companion = run_existing(
                        fig=fig,
                        sources=sources,
                        source=source,
                        spec=spec,
                        buffers=buffers,
                        domain=domain,
                        journey=windows(domain),
                        spill_file=spill_file,
                        chromium=config["chrome"],
                        timeout=config["timeout"],
                        socket_parent=Path(config["browser_socket_parent"]),
                        authority=config["authority"],
                        gl_mode=config.get("colored_browser_gl", "software"),
                        preflight=preflight,
                    )
                except BaseException as exc:
                    # Do not retain the helper traceback's borrowed figure in
                    # the host finally block. It already stopped HTTP/Chrome.
                    browser_failure = f"{type(exc).__name__}: {exc}"
                if browser_failure is not None:
                    raise RuntimeError(browser_failure)
                companion.update(
                    {
                        "authority": report["authority"],
                        "authority_context": report["authority_context"],
                        "environment": environment,
                        "provenance": report["provenance"],
                        "limits": report["limits"],
                        "browser_artifacts": {
                            "harness_sha256": file_hash(
                                ROOT / "scripts/density_spill_browser_smoke.py"
                            ),
                            "verifier_sha256": file_hash(
                                ROOT / "scripts/verify_density_spill_browser_report.py"
                            ),
                            "chromium_sha256": file_hash(Path(config["chrome"])),
                        },
                        "count_color_oracle": oracle,
                    }
                )
                supervisor._atomic_write_json(Path(config["browser_result"]), companion)
            return report
    finally:
        reference = weakref.ref(fig) if fig is not None else None
        if trace is not None:
            interaction._free_pyramid(trace)
        trace = fig = None
        gc.collect()
        cleanup["figure_released"] = reference is None or reference() is None
        # Figure/Trace finalizers must have removed the native store and file.
        spill_files = list(tmp.rglob("xy-tiles-*.xyts"))
        cleanup["spill_files_remaining"] = [str(path.relative_to(tmp)) for path in spill_files]
        cleanup["spill_store_released"] = not spill_files and (
            store is None or kernels.tile_store_stats(store) is None
        )
        closed = True
        for mapping in (x, y, color):
            if mapping is not None:
                try:
                    mapping._mmap.close()
                except (BufferError, OSError):
                    closed = False
        cleanup["mmap_closed"] = closed
        interaction.sync_tile_budget(old_budget)
        cleanup["tile_budget_restored"] = True


def worker(config: dict) -> int:
    guard(
        config["points"],
        config["authority"],
        dict(os.environ),
        config["timeout"],
        config["max_rss_bytes"] / 1024**3,
        config["max_disk_bytes"] / 1024**3,
    )
    browser_guard(config)
    tmp, result = Path(config["tmp"]), Path(config["result"])
    runtime = tmp / "runtime-tmp"
    runtime.mkdir()
    os.environ["TMPDIR"] = str(runtime)
    tempfile.tempdir = str(runtime)
    cleanup: dict[str, Any] = {}
    try:
        report = run_host(config, tmp, cleanup)
        assert all(
            cleanup.get(key) is True
            for key in (
                "figure_released",
                "spill_store_released",
                "mmap_closed",
                "tile_budget_restored",
            )
        )
    except BaseException as exc:
        report = {
            "schema_version": 1,
            "report_kind": KIND,
            "workload": WORKLOAD,
            "scope": SCOPE,
            "status": "failed",
            "authority": bool(config["authority"]),
            "point_count": config["points"],
            "failure": f"{type(exc).__name__}: {exc}",
            "cleanup": cleanup,
        }
        if hasattr(exc, "evidence"):
            report["renderer_preflight"] = exc.evidence
        supervisor._atomic_write_json(result, report)
        raise
    supervisor._atomic_write_json(result, report)
    return 0
