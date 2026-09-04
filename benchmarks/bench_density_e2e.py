#!/usr/bin/env python3
"""Cost-bounded end-to-end density evidence (#876).

The public command is a supervisor.  A fresh worker owns the mmap source,
Figure, loopback server, and Chromium tree; the supervisor samples the entire
process group, applies wall/RSS limits, and can therefore prove teardown even
when the worker fails.  The 100M authority is deliberately unavailable away
from scheduled/manual ``main`` runs.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import gc
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import weakref
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))

SCHEMA_VERSION = 1
AUTHORITY_POINTS = 100_000_000
CANONICAL_POINT_COUNTS = {250_000, 1_000_000, AUTHORITY_POINTS}
MAX_CHUNK_POINTS = 1_000_000
PYRAMID_MIN_POINTS = 2_000_000
PYRAMID_BASE_DIM = 2048
PYRAMID_MAX_DIM = 16384
PYRAMID_TARGET_POINTS_PER_CELL = 16.0
PYRAMID_RESIDENT_BYTES = 512 * (1 << 20)
DEFAULT_PAYLOAD_CEILING = 4 * 1024 * 1024
SOURCE_RATIO_CEILING = 0.10
DERIVED_CACHE_RATIO_CEILING = 0.10
CSP = "; ".join(
    (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "connect-src 'self'",
        "img-src 'self' data:",
        "object-src 'none'",
        "base-uri 'none'",
    )
)


def _sha256(data: bytes | memoryview) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _atomic_write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    try:
        temporary.write_text(data, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(OSError):
            temporary.unlink()


def _rss_snapshot() -> dict[str, int]:
    values = {"rss_bytes": 0, "peak_rss_bytes": 0}
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                values["rss_bytes"] = int(line.split()[1]) * 1024
            elif line.startswith("VmHWM:"):
                values["peak_rss_bytes"] = int(line.split()[1]) * 1024
    except OSError:
        import resource

        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform != "darwin":
            peak *= 1024
        values = {"rss_bytes": peak, "peak_rss_bytes": peak}
    return values


def _process_group_rss(pgid: int) -> tuple[int, list[int]]:
    """Return resident bytes and live pids for one Linux process group."""
    total = 0
    pids: list[int] = []
    page = os.sysconf("SC_PAGE_SIZE")
    proc = Path("/proc")
    if not proc.is_dir():
        return 0, pids
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "stat").read_text(encoding="utf-8")
            fields = raw[raw.rfind(")") + 2 :].split()
            # Fields after comm begin at process-state (field 3).
            if int(fields[2]) != pgid or fields[0] == "Z":
                continue
            total += int(fields[21]) * page
            pids.append(int(entry.name))
        except (OSError, ValueError, IndexError):
            continue
    return total, sorted(pids)


def _process_name(pid: int) -> str | None:
    try:
        name = (Path("/proc") / str(pid) / "comm").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return name or None


def _pid_peak_rss_bytes(pid: int) -> int:
    try:
        for line in (Path("/proc") / str(pid) / "status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def _tree_disk_usage(path: Path) -> int:
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file() and not entry.is_symlink():
                    total += entry.stat().st_size
            except OSError:
                continue
    except OSError:
        return total
    return total


def _authority_guard(points: int, authority: bool, environ: dict[str, str]) -> None:
    if points not in CANONICAL_POINT_COUNTS:
        raise ValueError("point count must be a canonical 250k, 1M, or 100M lane")
    if points >= AUTHORITY_POINTS and not authority:
        raise ValueError("100M runs require --authority")
    if authority and points != AUTHORITY_POINTS:
        raise ValueError(f"--authority requires exactly {AUTHORITY_POINTS} points")
    if not authority:
        return
    if environ.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("100M authority is restricted to refs/heads/main")
    if environ.get("GITHUB_EVENT_NAME") not in {"schedule", "workflow_dispatch"}:
        raise ValueError("100M authority requires a scheduled or manual workflow event")
    if environ.get("XYG_DENSITY_100M_AUTHORITY") != "1":
        raise ValueError("100M authority requires XYG_DENSITY_100M_AUTHORITY=1")


def _generate_sources(tmp: Path, points: int, chunk_points: int) -> tuple[Any, Any, dict[str, Any]]:
    import numpy as np

    x_path = tmp / "x.f64"
    y_path = tmp / "y.f64"
    x = np.memmap(x_path, dtype=np.float64, mode="w+", shape=(points,))
    y = np.memmap(y_path, dtype=np.float64, mode="w+", shape=(points,))
    x_hash = hashlib.sha256()
    y_hash = hashlib.sha256()
    for start in range(0, points, chunk_points):
        stop = min(points, start + chunk_points)
        row = np.arange(start, stop, dtype=np.uint64)
        x_values = ((row * 48_271 + 11) % 1_000_003).astype(np.float64)
        x_values /= 1_000_003.0
        x[start:stop] = x_values
        x_hash.update(memoryview(x_values))
        # Seven deterministic diagonal bands make the browser's panned
        # refinement visually distinguishable from first paint. An independent
        # uniform x/y lattice can legitimately rasterize byte-identically after
        # translation and would be weak visual journey evidence.
        band = (row % 7).astype(np.float64)
        y_values = np.remainder(x_values * 0.82 + band * 0.031, 1.0)
        y[start:stop] = y_values
        y_hash.update(memoryview(y_values))
    x.flush()
    y.flush()
    return (
        x,
        y,
        {
            "generator": "diagonal-band-v1",
            "chunk_points": chunk_points,
            "x_sha256": x_hash.hexdigest(),
            "y_sha256": y_hash.hexdigest(),
            "x_bytes": x_path.stat().st_size,
            "y_bytes": y_path.stat().st_size,
        },
    )


def _buffer_inventory(spec: dict[str, Any], buffers: list[bytes]) -> dict[str, Any]:
    classes: dict[str, dict[str, int]] = {}
    kinds_by_buffer: dict[int, set[str]] = {}
    for column in spec.get("columns", []):
        index = int(column["buf"])
        kind = str(column.get("dtype") or ("offset-f32" if "offset" in column else "unknown"))
        if index < 0 or index >= len(buffers):
            raise RuntimeError(f"column references missing split buffer {index}")
        kinds_by_buffer.setdefault(index, set()).add(kind)
    for index, buffer in enumerate(buffers):
        kinds = kinds_by_buffer.get(index, {"unreferenced"})
        kind = "+".join(sorted(kinds))
        entry = classes.setdefault(kind, {"buffers": 0, "bytes": 0})
        entry["buffers"] += 1
        entry["bytes"] += len(buffer)
    return {
        "classes": classes,
        "buffer_count": len(buffers),
        "bytes": sum(len(buffer) for buffer in buffers),
        "canonical_f64_buffers": sum(
            entry["buffers"] for kind, entry in classes.items() if "f64" in kind.split("+")
        ),
    }


def _reply_buffer_inventory(message: dict[str, Any], buffers: list[bytes]) -> dict[str, Any]:
    kinds_by_buffer: dict[int, set[str]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            index = value.get("buf")
            if isinstance(index, int) and not isinstance(index, bool):
                if index < 0 or index >= len(buffers):
                    raise RuntimeError(f"reply references missing buffer {index}")
                kind = value.get("dtype")
                if not isinstance(kind, str):
                    kind = "u8" if value.get("enc") == "log-u8" else "unknown"
                kinds_by_buffer.setdefault(index, set()).add(kind)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(message)
    classes: dict[str, dict[str, int]] = {}
    for index, buffer in enumerate(buffers):
        kind = "+".join(sorted(kinds_by_buffer.get(index, {"unreferenced"})))
        entry = classes.setdefault(kind, {"buffers": 0, "bytes": 0})
        entry["buffers"] += 1
        entry["bytes"] += len(buffer)
    return {
        "classes": classes,
        "buffer_count": len(buffers),
        "bytes": sum(len(buffer) for buffer in buffers),
        "buffer_sha256": [_sha256(buffer) for buffer in buffers],
    }


def _initial_density_semantics(spec: dict[str, Any]) -> dict[str, Any]:
    traces = spec.get("traces")
    if not isinstance(traces, list) or len(traces) != 1 or not isinstance(traces[0], dict):
        raise RuntimeError("density authority requires exactly one compiled trace")
    trace = traces[0]
    density = trace.get("density")
    if not isinstance(density, dict):
        raise RuntimeError("density authority trace has no density semantics")
    sample = density.get("sample")
    if not isinstance(sample, dict):
        raise RuntimeError("density authority trace has no bounded sample semantics")
    width, height = density.get("w"), density.get("h")
    return {
        "trace_count": 1,
        "trace_id": trace.get("id"),
        "kind": trace.get("kind"),
        "tier": trace.get("tier"),
        "n_points": trace.get("n_points"),
        "visible": trace.get("visible"),
        "n_marks": trace.get("n_marks"),
        "reduction": density.get("reduction"),
        "binning": density.get("binning"),
        "encoding": density.get("enc"),
        "grid_width": width,
        "grid_height": height,
        "grid_cells": width * height
        if isinstance(width, int) and isinstance(height, int)
        else None,
        "sample_mode": sample.get("mode"),
        "sample_points": sample.get("n"),
        "sample_visible": sample.get("visible"),
    }


def _refine_density_semantics(message: dict[str, Any]) -> dict[str, Any]:
    traces = message.get("traces")
    if not isinstance(traces, list) or len(traces) != 1 or not isinstance(traces[0], dict):
        raise RuntimeError("density refine requires exactly one trace")
    trace = traces[0]
    density = trace.get("density")
    if not isinstance(density, dict):
        raise RuntimeError("density refine is missing its grid semantics")
    return {
        "message_type": message.get("type"),
        "trace_count": 1,
        "trace_id": trace.get("id"),
        "mode": trace.get("mode"),
        "tier": trace.get("tier"),
        "visible": trace.get("visible"),
        "reduction": trace.get("reduction"),
        "binning": trace.get("binning"),
        "encoding": density.get("enc"),
        "grid_width": density.get("w"),
        "grid_height": density.get("h"),
    }


def _resident_pyramid_relation(binning: Any, reduction: Any, points: int) -> bool:
    match = re.fullmatch(r"pyramid-L(\d+)", binning) if isinstance(binning, str) else None
    if match is None or reduction != "pyramid-count":
        return False
    _, base_dim = _expected_pyramid_residency(points)
    return 0 <= int(match.group(1)) <= int(math.log2(base_dim))


def _initial_density_relation(binning: Any, reduction: Any, points: int) -> bool:
    if points < PYRAMID_MIN_POINTS:
        return binning == "exact" and reduction == "bin2d"
    return _resident_pyramid_relation(binning, reduction, points)


def _refine_density_relation(binning: Any, reduction: Any, points: int) -> bool:
    if points < PYRAMID_MIN_POINTS:
        return binning == "bin2d-oversized" and reduction == "bin2d-oversized"
    return _resident_pyramid_relation(binning, reduction, points)


def _expected_pyramid_residency(points: int) -> tuple[int, int]:
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
    if resident_bytes > PYRAMID_RESIDENT_BYTES:
        raise RuntimeError("density authority unexpectedly requires a spilled pyramid")
    return resident_bytes, base_dim


def _require_initial_density_semantics(semantics: dict[str, Any], points: int) -> None:
    required = {
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
    if any(semantics.get(key) != value for key, value in required.items()):
        raise RuntimeError("initial payload did not preserve native density semantics")
    if not _initial_density_relation(semantics.get("binning"), semantics.get("reduction"), points):
        raise RuntimeError("initial payload did not use its scale-required density route")
    if semantics.get("n_marks") != semantics.get("grid_cells"):
        raise RuntimeError("initial density mark count did not match its grid")
    sample_points = semantics.get("sample_points")
    if not isinstance(sample_points, int) or not 0 < sample_points <= semantics["n_marks"]:
        raise RuntimeError("initial density sample was not positively bounded")


def _require_refine_density_semantics(semantics: dict[str, Any], points: int) -> None:
    required = {
        "message_type": "density_update",
        "trace_count": 1,
        "trace_id": 0,
        "mode": "density",
        "tier": "density",
        "encoding": "log-u8",
    }
    if any(semantics.get(key) != value for key, value in required.items()):
        raise RuntimeError("refine did not preserve native density semantics")
    if not _refine_density_relation(semantics.get("binning"), semantics.get("reduction"), points):
        raise RuntimeError("refine did not use its scale-required density route")
    visible = semantics.get("visible")
    width, height = semantics.get("grid_width"), semantics.get("grid_height")
    if (
        not isinstance(visible, int)
        or not 0 < visible <= points
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width <= 0
        or height <= 0
    ):
        raise RuntimeError("refine density counts or grid dimensions were invalid")


def _native_count_oracle(
    x: Any,
    y: Any,
    fig: Any,
    spec: dict[str, Any],
    buffers: list[bytes],
    points: int,
) -> dict[str, Any]:
    import numpy as np

    import xyg.kernels as kernels

    trace = spec["traces"][0]
    density = trace["density"]
    x_range, y_range = density["x_range"], density["y_range"]
    width, height = int(density["w"]), int(density["h"])
    x0, x1 = float(x_range[0]), float(x_range[1])
    y0, y1 = float(y_range[0]), float(y_range[1])
    emitted_index = density.get("buf")
    if not isinstance(emitted_index, int) or not 0 <= emitted_index < len(buffers):
        raise RuntimeError("initial density did not reference a valid split buffer")
    emitted = buffers[emitted_index]
    pyramid_level: int | None = None
    pyramid_base_dim = 0
    if points < PYRAMID_MIN_POINTS:
        route = "exact-bin2d"
        grid = kernels.bin_2d(x, y, x0, x1, y0, y1, width, height)
        observed = int(np.asarray(grid).sum(dtype=np.float64))
    else:
        route = "resident-pyramid"
        handle = getattr(fig.traces[0], "_pyr_handle", None)
        if (
            not isinstance(handle, int)
            or handle <= 0
            or getattr(fig.traces[0], "_tile_store", None)
        ):
            raise RuntimeError("initial density did not retain its required resident pyramid")
        counted = kernels.pyramid_count(handle, x0, x1, y0, y1)
        composed = kernels.pyramid_compose(handle, x0, x1, y0, y1, width, height, 1 << 30)
        if counted is None or composed is None:
            raise RuntimeError("resident pyramid could not count and recompose the emitted range")
        grid, pyramid_level = composed
        observed = int(counted)
        _, pyramid_base_dim = _expected_pyramid_residency(points)
    encoded, encoded_max = kernels.density_log_u8(np.asarray(grid, dtype=np.float32))
    encoded_bytes = memoryview(np.ascontiguousarray(encoded)).tobytes()
    emitted_max = density.get("max")
    recomposed_count = float(np.asarray(grid).sum(dtype=np.float64))
    recomposed_absolute_error = abs(recomposed_count - points)
    recomposed_binning = "exact" if pyramid_level is None else f"pyramid-L{pyramid_level}"
    return {
        "backend": "native-bin2d" if route == "exact-bin2d" else "native-resident-pyramid",
        "expected_count": points,
        "observed_count": observed,
        "recomposed_count": recomposed_count,
        "match": observed == points and recomposed_absolute_error < 0.5,
        "grid_width": width,
        "grid_height": height,
        "grid_bytes": int(grid.nbytes),
        "grid_sha256": _sha256(memoryview(grid)),
        "recomposed_absolute_error": recomposed_absolute_error,
        "product_link": {
            "route": route,
            "emitted_buffer_index": emitted_index,
            "emitted_buffer_bytes": len(emitted),
            "emitted_buffer_sha256": _sha256(emitted),
            "oracle_encoded_bytes": len(encoded_bytes),
            "oracle_encoded_sha256": _sha256(encoded_bytes),
            "emitted_max": emitted_max,
            "oracle_max": float(encoded_max),
            "encoded_match": emitted == encoded_bytes,
            "max_match": emitted_max == float(encoded_max),
            "emitted_binning": density.get("binning"),
            "recomposed_binning": recomposed_binning,
            "pyramid_level": pyramid_level,
            "pyramid_base_dim": pyramid_base_dim,
        },
    }


def _native_refine_oracle(
    x: Any,
    y: Any,
    fig: Any,
    message: dict[str, Any],
    buffers: list[bytes],
    points: int,
) -> dict[str, Any]:
    import numpy as np

    import xyg.kernels as kernels

    trace = message["traces"][0]
    density = trace["density"]
    width, height = int(density["w"]), int(density["h"])
    x0, x1 = (float(value) for value in density["x_range"])
    y0, y1 = (float(value) for value in density["y_range"])
    emitted_index = density.get("buf")
    if not isinstance(emitted_index, int) or not 0 <= emitted_index < len(buffers):
        raise RuntimeError("density refine did not reference a valid reply buffer")
    emitted = buffers[emitted_index]
    pyramid_level: int | None = None
    pyramid_base_dim = 0
    if points < PYRAMID_MIN_POINTS:
        route = "exact-bin2d"
        grid = kernels.bin_2d(x, y, x0, x1, y0, y1, width, height)
        observed = float(np.asarray(grid).sum(dtype=np.float64))
    else:
        route = "resident-pyramid"
        handle = getattr(fig.traces[0], "_pyr_handle", None)
        if (
            not isinstance(handle, int)
            or handle <= 0
            or getattr(fig.traces[0], "_tile_store", None)
        ):
            raise RuntimeError("density refine did not retain its required resident pyramid")
        counted = kernels.pyramid_count(handle, x0, x1, y0, y1)
        composed = kernels.pyramid_compose(handle, x0, x1, y0, y1, width, height, 1 << 30)
        if counted is None or composed is None:
            raise RuntimeError("resident pyramid could not count and recompose the refine range")
        grid, pyramid_level = composed
        observed = float(counted)
        _, pyramid_base_dim = _expected_pyramid_residency(points)
    encoded, encoded_max = kernels.density_log_u8(np.asarray(grid, dtype=np.float32))
    encoded_bytes = memoryview(np.ascontiguousarray(encoded)).tobytes()
    recomposed_count = float(np.asarray(grid).sum(dtype=np.float64))
    expected_count = int(trace["visible"])
    absolute_error = abs(recomposed_count - observed)
    recomposed_binning = "bin2d-oversized" if pyramid_level is None else f"pyramid-L{pyramid_level}"
    return {
        "backend": "native-bin2d" if route == "exact-bin2d" else "native-resident-pyramid",
        "expected_visible": expected_count,
        "observed_count": observed,
        "recomposed_count": recomposed_count,
        "recomposed_absolute_error": absolute_error,
        "count_match": observed == expected_count
        and (route == "resident-pyramid" or absolute_error == 0.0),
        "grid_width": width,
        "grid_height": height,
        "grid_bytes": int(grid.nbytes),
        "grid_sha256": _sha256(memoryview(grid)),
        "product_link": {
            "route": route,
            "emitted_buffer_index": emitted_index,
            "emitted_buffer_bytes": len(emitted),
            "emitted_buffer_sha256": _sha256(emitted),
            "oracle_encoded_bytes": len(encoded_bytes),
            "oracle_encoded_sha256": _sha256(encoded_bytes),
            "emitted_max": density.get("max"),
            "oracle_max": float(encoded_max),
            "encoded_match": emitted == encoded_bytes,
            "max_match": density.get("max") == float(encoded_max),
            "emitted_binning": trace.get("binning"),
            "emitted_reduction": trace.get("reduction"),
            "recomposed_binning": recomposed_binning,
            "pyramid_level": pyramid_level,
            "pyramid_base_dim": pyramid_base_dim,
        },
    }


PROBE_JS = r"""
import {ChartView} from "/assets/index.js";
const state={failures:[],requests:[]};
addEventListener("error",e=>state.failures.push(String(e.error||e.message)));
addEventListener("unhandledrejection",e=>state.failures.push(String(e.reason)));
let inlineViolation=false;
document.addEventListener("securitypolicyviolation",event=>{if(String(event.violatedDirective).startsWith("script-src"))inlineViolation=true});
const forbiddenInline=document.createElement("script"); forbiddenInline.textContent="globalThis.__xygForbiddenInlineRan=true"; document.body.append(forbiddenInline);
await new Promise(resolve=>setTimeout(resolve,0));
state.csp_inline_blocked=inlineViolation&&globalThis.__xygForbiddenInlineRan!==true;
const twoFrames=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
const awaitSettled=async view=>{
  const deadline=performance.now()+2000;
  while(view._interactionTransitionActive()) {
    if(performance.now()>deadline) throw new Error("density transition did not settle");
    await twoFrames();
  }
  view._drawNow(); view.gl.finish();
};
const capturePixels=async view=>{
  view._drawNow(); view.gl.finish();
  const dpr=view.dpr||1, fullHeight=view.gl.drawingBufferHeight;
  const x=Math.max(0,Math.floor(view.plot.x*dpr));
  const y=Math.max(0,Math.floor(fullHeight-(view.plot.y+view.plot.h)*dpr));
  const width=Math.min(view.gl.drawingBufferWidth-x,Math.max(1,Math.floor(view.plot.w*dpr)));
  const height=Math.min(fullHeight-y,Math.max(1,Math.floor(view.plot.h*dpr)));
  const pixels=new Uint8Array(width*height*4);
  view.gl.readPixels(x,y,width,height,view.gl.RGBA,view.gl.UNSIGNED_BYTE,pixels);
  const corner=pixels.slice(0,4); let nonBackground=0;
  for(let i=0;i<pixels.length;i+=4) if(pixels[i]!==corner[0]||pixels[i+1]!==corner[1]||pixels[i+2]!==corner[2]||pixels[i+3]!==corner[3]) nonBackground++;
  const digest=await crypto.subtle.digest("SHA-256",pixels);
  return {region:"plot",x,y,width,height,bytes:pixels.byteLength,non_background_pixels:nonBackground,sha256:Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,"0")).join("")};
};
const upload={calls:0,bytes:0,call_ms:0};
const bytesOf=value=>value&&Number.isFinite(value.byteLength)?value.byteLength:0;
const textureAllocationBytes=(gl,args)=>{
  const width=Number(args[3]), height=Number(args[4]), format=args[6], type=args[7];
  if(!Number.isFinite(width)||!Number.isFinite(height)||width<0||height<0) return 0;
  let components=4;
  if([gl.RED,gl.RED_INTEGER,gl.ALPHA,gl.LUMINANCE].includes(format)) components=1;
  else if([gl.RG,gl.RG_INTEGER,gl.LUMINANCE_ALPHA].includes(format)) components=2;
  else if([gl.RGB,gl.RGB_INTEGER].includes(format)) components=3;
  let componentBytes=1;
  if([gl.SHORT,gl.UNSIGNED_SHORT,gl.HALF_FLOAT].includes(type)) componentBytes=2;
  else if([gl.INT,gl.UNSIGNED_INT,gl.FLOAT].includes(type)) componentBytes=4;
  if([gl.UNSIGNED_SHORT_5_6_5,gl.UNSIGNED_SHORT_4_4_4_4,gl.UNSIGNED_SHORT_5_5_5_1].includes(type)) return width*height*2;
  if([gl.UNSIGNED_INT_2_10_10_10_REV,gl.UNSIGNED_INT_10F_11F_11F_REV,gl.UNSIGNED_INT_5_9_9_9_REV,gl.UNSIGNED_INT_24_8].includes(type)) return width*height*4;
  return width*height*components*componentBytes;
};
const uploadBytes=(gl,name,args)=>{
  if(name==="bufferData") return typeof args[1]==="number"?args[1]:bytesOf(args[1]);
  if(name==="bufferSubData") return bytesOf(args[2]);
  const supplied=Math.max(0,...args.map(bytesOf));
  if(supplied) return supplied;
  return name==="texImage2D"?textureAllocationBytes(gl,args):0;
};
const snapshotUpload=()=>({...upload});
const uploadDelta=(before,after)=>({calls:after.calls-before.calls,bytes:after.bytes-before.bytes,call_ms:after.call_ms-before.call_ms});
for (const name of ["bufferData","bufferSubData","texImage2D","texSubImage2D"]) {
  const original=WebGL2RenderingContext.prototype[name];
  WebGL2RenderingContext.prototype[name]=function(...args) {
    const start=performance.now(); const result=original.apply(this,args);
    upload.calls++; upload.call_ms+=performance.now()-start;
    upload.bytes+=uploadBytes(this,name,args); return result;
  };
}
try {
  const manifestWire=new Uint8Array(await (await fetch("/spec.json",{cache:"no-store"})).arrayBuffer());
  const manifest=JSON.parse(new TextDecoder().decode(manifestWire));
  const spec=manifest.spec;
  const buffers=await Promise.all(Array.from({length:manifest.buffer_count},(_,i)=>fetch(`/buffer/${i}`,{cache:"no-store"}).then(r=>r.arrayBuffer()).then(b=>new Uint8Array(b))));
  let receiver=null, resolveRefine, view=null;
  const refineDone=new Promise(resolve=>{resolveRefine=resolve});
  const comm={
    onMessage:cb=>{receiver=cb;return ()=>{receiver=null}}, wantsViewChange:()=>false,
    send:async message=>{
      state.requests.push(message.type);
      state.request_window={trace:message.trace,x0:message.x0,x1:message.x1,y0:message.y0,y1:message.y1,w:message.w,h:message.h};
      const started=performance.now();
      const response=await fetch("/density",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(message)});
      if (!response.ok) throw new Error(`density response ${response.status}: ${await response.text()}`);
      const responseWire=new Uint8Array(await response.arrayBuffer());
      const envelope=JSON.parse(new TextDecoder().decode(responseWire));
      const replyBuffers=envelope.buffers.map(text=>Uint8Array.from(atob(text),c=>c.charCodeAt(0)));
      const replyHashes=await Promise.all(replyBuffers.map(async buffer=>{
        const digest=await crypto.subtle.digest("SHA-256",buffer);
        return Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,"0")).join("");
      }));
      const received=performance.now(), beforeApply=snapshotUpload();
      const trace=envelope.message.traces[0], density=trace.density;
      const gpu=view.gpuTraces.find(item=>item.trace.id===trace?.id)||view.gpuTraces[0];
      const beforeTexture=gpu?.density?.tex||null, beforeFacts=Array.isArray(gpu?.densityCache)?gpu.densityCache.length:0;
      receiver(envelope.message,replyBuffers); await awaitSettled(view); const afterApply=snapshotUpload();
      const semantics={message_type:envelope.message.type,trace_count:envelope.message.traces.length,trace_id:trace.id,mode:trace.mode,tier:trace.tier,visible:trace.visible,reduction:trace.reduction,binning:trace.binning,encoding:density.enc,grid_width:density.w,grid_height:density.h};
      const afterTexture=gpu?.density?.tex||null, afterFacts=Array.isArray(gpu?.densityCache)?gpu.densityCache.length:0;
      const textureChanged=afterTexture!==beforeTexture, factsDelta=afterFacts-beforeFacts;
      const application=textureChanged?"texture":factsDelta>0?"facts-only":"none";
      state.refine={roundtrip_ms:received-started,apply_paint_ms:performance.now()-received,reply_bytes:replyBuffers.reduce((n,b)=>n+b.byteLength,0),wire_bytes:responseWire.byteLength,buffer_sha256:replyHashes,semantics,upload:uploadDelta(beforeApply,afterApply),application,texture_changed:textureChanged,facts_cache_delta:factsDelta,mode:trace.mode,binning:trace.binning,transition_mode:"normal",transition_settled:!view._interactionTransitionActive()};
      resolveRefine();
    }
  };
  const beforeInitial=snapshotUpload(), started=performance.now();
  view=new ChartView(document.getElementById("chart"),spec,buffers,comm);
  state.prefers_reduced_motion=view._prefersReducedMotion();
  if(state.prefers_reduced_motion) throw new Error("authority requires the normal transition path");
  const constructed=performance.now(), afterInitial=snapshotUpload(); await twoFrames();
  state.first_paint={construct_upload_ms:constructed-started,settle_ms:performance.now()-constructed};
  state.initial_upload=uploadDelta(beforeInitial,afterInitial);
  state.first_pixels=await capturePixels(view);
  state.renderer=view.gl.getParameter(view.gl.RENDERER);
  state.initial_payload_bytes=buffers.reduce((n,b)=>n+b.byteLength,0);
  state.initial_spec_json_bytes=manifestWire.byteLength;
  state.initial_wire_bytes=manifestWire.byteLength+state.initial_payload_bytes;
  const home=view.view, spanFraction=spec.traces[0].n_points>=1000000?0.20:0.25, offsetFraction=0.25;
  const span=home.x1-home.x0;
  const target={x0:home.x0+span*offsetFraction,x1:home.x0+span*(offsetFraction+spanFraction),y0:home.y0,y1:home.y1};
  view.view=view._viewFrom(target,home);
  const tolerance=Math.max(1,Math.abs(span))*1e-12;
  const appliedMatches=Math.abs(view.view.x0-target.x0)<=tolerance&&Math.abs(view.view.x1-target.x1)<=tolerance&&Math.abs(view.view.y0-target.y0)<=tolerance&&Math.abs(view.view.y1-target.y1)<=tolerance;
  state.view_transform={kind:"in-domain-x-zoom-pan",x_span_fraction:spanFraction,x_offset_fraction:offsetFraction,y_span_fraction:1,home:{x0:home.x0,x1:home.x1,y0:home.y0,y1:home.y1},requested:target,applied:{x0:view.view.x0,x1:view.view.x1,y0:view.view.y0,y1:view.view.y1},applied_matches_requested:appliedMatches};
  if(!appliedMatches) throw new Error("required density view transform was clamped");
  view._scheduleViewRequest(view.view,{delay:0});
  await Promise.race([refineDone,new Promise((_,reject)=>setTimeout(()=>reject(new Error("required in-domain density_view did not complete")),30000))]);
  state.refined_pixels=await capturePixels(view);
  state.upload_total=snapshotUpload();
  view.destroy(); state.view_destroyed=true; state.done=true;
} catch (error) { state.failure=String(error?.stack||error); state.done=true; }
globalThis.__xygDensityEvidence=state;
"""

STYLE_CSS = "html,body{margin:0;background:#fff}#chart{width:640px;height:400px}"
INDEX_HTML = (
    '<!doctype html><meta charset="utf-8"><link rel="icon" href="data:,">'
    '<link rel="stylesheet" href="/style.css">'
    '<div id="chart"></div><script type="module" src="/probe.js"></script>'
)


def _run_browser(
    x: Any,
    y: Any,
    fig: Any,
    spec: dict[str, Any],
    buffers: list[bytes],
    chrome: str,
    host_metrics: dict[str, Any],
) -> dict[str, Any]:
    from xyg._chromium import ChromiumSession
    from xyg.channel import handle_message

    spec_bytes = _json_bytes({"spec": spec, "buffer_count": len(buffers)})
    requests: list[str] = []
    refine_contexts: list[tuple[bytes, bytes, tuple[bytes, ...], float]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args
            return

        def _send(self, status: int, kind: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

        def do_GET(self) -> None:
            requests.append(self.path)
            if self.path == "/":
                self._send(200, "text/html", INDEX_HTML.encode())
            elif self.path == "/probe.js":
                self._send(200, "text/javascript", PROBE_JS.encode())
            elif self.path == "/style.css":
                self._send(200, "text/css", STYLE_CSS.encode())
            elif self.path == "/assets/index.js":
                self._send(
                    200, "text/javascript", (ROOT / "packages/xy-client/dist/index.js").read_bytes()
                )
            elif self.path == "/spec.json":
                self._send(200, "application/json", spec_bytes)
            elif self.path.startswith("/buffer/"):
                try:
                    index = int(self.path.removeprefix("/buffer/"))
                    body = buffers[index]
                except (ValueError, IndexError):
                    self._send(404, "text/plain", b"not found")
                else:
                    self._send(200, "application/octet-stream", body)
            else:
                self._send(404, "text/plain", b"not found")

        def do_POST(self) -> None:
            requests.append(self.path)
            if self.path != "/density":
                self._send(404, "text/plain", b"not found")
                return
            try:
                length = int(self.headers.get("content-length", "0"))
                if not 0 < length <= 65_536:
                    raise ValueError("invalid request length")
                request_body = self.rfile.read(length)
                message = json.loads(request_body)
                started = time.perf_counter()
                reply = handle_message(fig, message)
                elapsed = time.perf_counter() - started
                if reply is None:
                    raise ValueError("density request produced no reply")
                metadata, out = reply
                if out is None:
                    raise ValueError("density request produced no buffers")
                out = tuple(bytes(item) for item in out)
                body = _json_bytes(
                    {
                        "message": metadata,
                        "buffers": [base64.b64encode(item).decode("ascii") for item in out],
                    }
                )
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._send(400, "text/plain", str(exc).encode())
                return

            # Retain only immutable product inputs/results. The controlling
            # thread audits these after browser apply, paint capture, timing,
            # and view destruction have all completed; this request thread
            # performs no benchmark-only hashing, inventory, RSS, or oracle
            # work that could contend with the measured browser journey.
            refine_contexts.append((request_body, body, out, elapsed))
            self._send(200, "application/json", body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, name="density-e2e-http", daemon=True)
    thread.start()
    browser_exited = False
    try:
        with ChromiumSession(chrome, gl="software", sandbox=False, launch_timeout_s=30) as browser:
            _, sid, _ = browser._page_session("<html></html>", 30)
            browser._call(
                "Page.navigate",
                {"url": f"http://127.0.0.1:{server.server_address[1]}/"},
                session_id=sid,
                timeout_s=30,
            )
            deadline = time.monotonic() + 120
            state: dict[str, Any] = {}
            while time.monotonic() < deadline:
                reply = browser._call(
                    "Runtime.evaluate",
                    {
                        "expression": "JSON.stringify(globalThis.__xygDensityEvidence||null)",
                        "returnByValue": True,
                    },
                    session_id=sid,
                    timeout_s=10,
                )
                value = reply.get("result", {}).get("value")
                decoded = json.loads(value) if isinstance(value, str) else None
                state = decoded if isinstance(decoded, dict) else {}
                if state.get("done"):
                    break
                time.sleep(0.05)
            if not state.get("done"):
                raise RuntimeError("browser density evidence timed out")
            if state.get("failure") or state.get("failures"):
                raise RuntimeError(f"browser density evidence failed: {state}")
            if len(refine_contexts) != 1:
                raise RuntimeError("browser journey did not retain exactly one refine context")
            request_wire, response_wire, out, elapsed = refine_contexts[0]
            try:
                message = json.loads(request_wire)
                envelope = json.loads(response_wire)
                metadata = envelope["message"]
                host_metrics.update(
                    {
                        "seconds": elapsed,
                        "reply_bytes": sum(len(item) for item in out),
                        "wire_bytes": len(response_wire),
                        "semantics": _refine_density_semantics(metadata),
                        "request_window": {
                            key: message.get(key)
                            for key in ("trace", "x0", "x1", "y0", "y1", "w", "h")
                        },
                        "buffer_inventory": _reply_buffer_inventory(metadata, out),
                        "rss": _rss_snapshot(),
                        "audit_after_browser_done": True,
                    }
                )
                oracle_started = time.perf_counter()
                refine_oracle = _native_refine_oracle(x, y, fig, metadata, list(out), len(x))
                refine_link = refine_oracle["product_link"]
                if (
                    refine_oracle["count_match"] is not True
                    or refine_link["encoded_match"] is not True
                    or refine_link["max_match"] is not True
                    or refine_link["emitted_binning"] != refine_link["recomposed_binning"]
                ):
                    raise ValueError(
                        "native refine oracle did not reproduce the density_view product"
                    )
                host_metrics["product_link_oracle"] = refine_oracle
                host_metrics["oracle_seconds"] = time.perf_counter() - oracle_started
            except (IndexError, KeyError, RuntimeError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"post-browser native refine audit failed: {type(exc).__name__}: {exc}"
                ) from exc
        browser_exited = browser._proc.poll() is not None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    allowed = {"/", "/probe.js", "/style.css", "/assets/index.js", "/spec.json", "/density"}
    allowed.update(f"/buffer/{index}" for index in range(len(buffers)))
    state["strict_csp"] = True
    state["unexpected_requests"] = sorted(set(requests) - allowed)
    state["server_stopped"] = not thread.is_alive()
    state["browser_exited"] = browser_exited
    return state


def _payload_fingerprint(spec: dict[str, Any], buffers: list[bytes]) -> str:
    digest = hashlib.sha256(_json_bytes(spec))
    for buffer in buffers:
        digest.update(buffer)
    return digest.hexdigest()


def _worker(config_path: Path) -> int:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    tmp = Path(config["tmp"])
    runtime_tmp = tmp / "runtime-tmp"
    runtime_tmp.mkdir()
    # Figure spill stores and ChromiumSession profiles must live under the
    # supervisor-owned tree. Merely deleting x.f64/y.f64 would otherwise leave
    # Chrome's sibling `xy-export-*` profile behind after cancellation.
    os.environ["TMPDIR"] = str(runtime_tmp)
    tempfile.tempdir = str(runtime_tmp)
    result_path = Path(config["result"])
    points = int(config["points"])
    phases: dict[str, Any] = {}
    cleanup = {"mmap_closed": False, "figure_released": False}
    x = y = fig = None
    try:
        import xyg
        from benchmarks.environment import collect_environment_metadata

        started = time.perf_counter()
        x, y, source = _generate_sources(tmp, points, int(config["chunk_points"]))
        phases["source_creation"] = {
            "seconds": time.perf_counter() - started,
            "rss": _rss_snapshot(),
        }

        started = time.perf_counter()
        fig = xyg.scatter_chart(xyg.scatter(x, y, density=True), width=640, height=400).figure()
        phases["source_admission"] = {
            "seconds": time.perf_counter() - started,
            "rss": _rss_snapshot(),
        }

        started = time.perf_counter()
        spec, raw_buffers = fig.build_payload_split()
        buffers = [bytes(item) for item in raw_buffers]
        phases["native_aggregation_build"] = {
            "seconds": time.perf_counter() - started,
            "rss": _rss_snapshot(),
        }
        inventory = _buffer_inventory(spec, buffers)
        initial_semantics = _initial_density_semantics(spec)
        _require_initial_density_semantics(initial_semantics, points)
        initial_spec_json_bytes = len(_json_bytes({"spec": spec, "buffer_count": len(buffers)}))
        initial_wire_bytes = initial_spec_json_bytes + inventory["bytes"]
        started = time.perf_counter()
        count_oracle = _native_count_oracle(x, y, fig, spec, buffers, points)
        phases["native_count_oracle"] = {
            "seconds": time.perf_counter() - started,
            "rss": _rss_snapshot(),
        }
        if count_oracle["match"] is not True:
            raise RuntimeError("native count-grid oracle did not conserve the source count")
        if (
            count_oracle["product_link"]["encoded_match"] is not True
            or count_oracle["product_link"]["max_match"] is not True
            or count_oracle["product_link"]["emitted_binning"]
            != count_oracle["product_link"]["recomposed_binning"]
        ):
            raise RuntimeError("native oracle did not reproduce the emitted density product")
        fingerprint = _payload_fingerprint(spec, buffers)
        started = time.perf_counter()
        second_spec, second_raw = fig.build_payload_split()
        second_buffers = [bytes(item) for item in second_raw]
        second_fingerprint = _payload_fingerprint(second_spec, second_buffers)
        phases["determinism_rebuild"] = {
            "seconds": time.perf_counter() - started,
            "rss": _rss_snapshot(),
        }
        if fingerprint != second_fingerprint:
            raise RuntimeError("two builds from unchanged canonical source were not deterministic")
        source_bytes = source["x_bytes"] + source["y_bytes"]
        if inventory["canonical_f64_buffers"] != 0:
            raise RuntimeError("ordinary first paint shipped canonical f64")
        if initial_wire_bytes > int(config["payload_ceiling"]):
            raise RuntimeError("first-paint wire payload exceeded byte ceiling")
        if initial_wire_bytes > source_bytes * SOURCE_RATIO_CEILING:
            raise RuntimeError("first-paint payload was not materially smaller than source")

        host_refine: dict[str, Any] = {}
        started = time.perf_counter()
        browser = _run_browser(x, y, fig, spec, buffers, config["chrome"], host_refine)
        _require_refine_density_semantics(host_refine["semantics"], points)
        host_refine["raw_source_ratio"] = host_refine["reply_bytes"] / source_bytes
        host_refine["source_ratio"] = host_refine["wire_bytes"] / source_bytes
        phases["browser_journey"] = {
            "seconds": time.perf_counter() - started,
            "rss": _rss_snapshot(),
        }
        if browser["initial_payload_bytes"] != inventory["bytes"]:
            raise RuntimeError("browser did not consume the complete first-paint payload")
        if browser["initial_spec_json_bytes"] != initial_spec_json_bytes:
            raise RuntimeError("browser spec JSON bytes did not match the served manifest")
        if browser["initial_wire_bytes"] != initial_wire_bytes:
            raise RuntimeError("browser initial wire bytes did not match the served payload")
        if browser.get("refine", {}).get("wire_bytes") != host_refine["wire_bytes"]:
            raise RuntimeError("browser refine wire bytes did not match the host envelope")
        if browser.get("refine", {}).get("semantics") != host_refine["semantics"]:
            raise RuntimeError("browser refine semantics did not match the native host")
        if browser["unexpected_requests"]:
            raise RuntimeError(
                f"browser escaped bounded loopback routes: {browser['unexpected_requests']}"
            )
        if host_refine["wire_bytes"] > int(config["payload_ceiling"]):
            raise RuntimeError("density refine wire payload exceeded byte ceiling")

        memory = fig.memory_report()
        expected_pyramid_bytes, expected_pyramid_base_dim = _expected_pyramid_residency(points)
        if (
            memory.get("pyramid_bytes") != expected_pyramid_bytes
            or memory.get("pyramid_spilled_bytes") != 0
        ):
            raise RuntimeError(
                "density journey did not retain the scale-required resident pyramid "
                f"(base_dim={expected_pyramid_base_dim})"
            )
        # resident_array_bytes already includes the live resident pyramid.
        derived_cache_bytes = int(memory.get("resident_array_bytes", 0)) + int(
            memory.get("pyramid_spilled_bytes", 0)
        )
        if derived_cache_bytes > source_bytes * DERIVED_CACHE_RATIO_CEILING:
            raise RuntimeError("live derived cache was source-sized")
        report = {
            "schema_version": SCHEMA_VERSION,
            "report_kind": "density-e2e",
            "status": "ok",
            "authority": bool(config["authority"]),
            "authority_context": {
                "github_ref": os.environ.get("GITHUB_REF"),
                "github_event_name": os.environ.get("GITHUB_EVENT_NAME"),
                "capability": os.environ.get("XYG_DENSITY_100M_AUTHORITY") == "1",
            },
            "point_count": points,
            "environment": collect_environment_metadata(
                chromium=config["chrome"], xy_backend=str(memory.get("backend"))
            ),
            "limits": {
                "timeout_seconds": float(config["timeout"]),
                "max_tree_rss_bytes": int(config["max_rss_bytes"]),
                "max_disk_bytes": int(config["max_disk_bytes"]),
                "first_payload_bytes": int(config["payload_ceiling"]),
                "refine_payload_bytes": int(config["payload_ceiling"]),
                "source_ratio": SOURCE_RATIO_CEILING,
                "derived_cache_ratio": DERIVED_CACHE_RATIO_CEILING,
            },
            "source": {**source, "bytes": source_bytes, "backing": "mmap-f64"},
            "count_oracle": count_oracle,
            "phases": phases,
            "payload": {
                **inventory,
                "raw_source_ratio": inventory["bytes"] / source_bytes,
                "spec_json_bytes": initial_spec_json_bytes,
                "wire_bytes": initial_wire_bytes,
                "source_ratio": initial_wire_bytes / source_bytes,
                "semantics": initial_semantics,
                "spec_sha256": _sha256(_json_bytes(spec)),
                "buffer_sha256": [_sha256(item) for item in buffers],
                "fingerprint_sha256": fingerprint,
                "determinism": {"checked": True, "match": True},
            },
            "host_memory_report": memory,
            "host_refine": host_refine,
            "browser": browser,
            "cleanup": cleanup,
        }
        _atomic_write_json(result_path, report)
        return 0
    except BaseException as exc:
        failed = {
            "schema_version": SCHEMA_VERSION,
            "report_kind": "density-e2e",
            "status": "failed",
            "authority": bool(config["authority"]),
            "point_count": points,
            "failure": f"{type(exc).__name__}: {exc}",
            "phases": phases,
            "cleanup": cleanup,
        }
        with contextlib.suppress(OSError):
            _atomic_write_json(result_path, failed)
        raise
    finally:
        figure_ref = weakref.ref(fig) if fig is not None else None
        fig = None
        gc.collect()
        cleanup["figure_released"] = figure_ref is None or figure_ref() is None
        mmap_closed = True
        for mapping in (x, y):
            mapped = getattr(mapping, "_mmap", None)
            if mapped is not None:
                try:
                    mapped.close()
                except (BufferError, OSError):
                    mmap_closed = False
        cleanup["mmap_closed"] = mmap_closed
        if result_path.is_file():
            try:
                value = json.loads(result_path.read_text(encoding="utf-8"))
                value["cleanup"].update(cleanup)
                _atomic_write_json(result_path, value)
            except (OSError, ValueError, KeyError):
                pass


def _terminate_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not _process_group_rss(pgid)[1]:
            return
        time.sleep(0.05)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pgid, signal.SIGKILL)


def _run_supervisor(args: argparse.Namespace, tmp: Path) -> tuple[dict[str, Any], bool]:
    result_path = tmp / "worker-report.json"
    config = {
        "tmp": str(tmp),
        "result": str(result_path),
        "points": args.points,
        "authority": args.authority,
        "chunk_points": args.chunk_points,
        "chrome": str(args.chrome.resolve()),
        "timeout": args.timeout,
        "max_rss_bytes": int(args.max_rss_gib * 1024**3),
        "max_disk_bytes": int(args.max_disk_gib * 1024**3),
        "payload_ceiling": args.payload_ceiling_bytes,
    }
    config_path = tmp / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--worker-config", str(config_path)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    pgid = proc.pid
    peak_tree_rss = 0
    peak_temp_bytes = 0
    peak_pids: list[int] = []
    max_live_process_count = 0
    observed_processes: dict[int, str] = {}
    worker_peak_rss_bytes = 0
    reason: str | None = None
    start = time.monotonic()
    cancelled = False

    def cancel(_signum: int, _frame: Any) -> None:
        nonlocal cancelled
        cancelled = True

    old_handlers = {
        signum: signal.signal(signum, cancel) for signum in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        while proc.poll() is None:
            rss, pids = _process_group_rss(pgid)
            temp_bytes = _tree_disk_usage(tmp)
            max_live_process_count = max(max_live_process_count, len(pids))
            worker_peak_rss_bytes = max(worker_peak_rss_bytes, _pid_peak_rss_bytes(proc.pid))
            for pid in pids:
                observed_processes[pid] = _process_name(pid) or "unknown"
            if rss > peak_tree_rss:
                peak_tree_rss, peak_pids = rss, pids
            peak_temp_bytes = max(peak_temp_bytes, temp_bytes)
            if cancelled:
                reason = "cancelled"
                break
            if rss > config["max_rss_bytes"]:
                reason = "rss_limit"
                break
            if temp_bytes > config["max_disk_bytes"]:
                reason = "disk_limit"
                break
            if time.monotonic() - start > args.timeout:
                reason = "timeout"
                break
            time.sleep(0.05)
        if reason is not None:
            _terminate_group(pgid)
        stdout, stderr = proc.communicate(timeout=10)
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        orphan_before = _process_group_rss(pgid)[1]
        if orphan_before:
            _terminate_group(pgid)
        orphan_after = _process_group_rss(pgid)[1]

    report: dict[str, Any]
    if result_path.is_file():
        try:
            decoded = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(decoded, dict):
                raise ValueError("worker report root is not an object")
            report = decoded
        except (OSError, ValueError) as exc:
            report = {
                "schema_version": SCHEMA_VERSION,
                "report_kind": "density-e2e",
                "status": "failed",
                "authority": args.authority,
                "point_count": args.points,
                "failure": f"malformed_worker_report: {exc}",
            }
    else:
        report = {
            "schema_version": SCHEMA_VERSION,
            "report_kind": "density-e2e",
            "status": "failed",
            "authority": args.authority,
            "point_count": args.points,
            "failure": reason or f"worker_exit_{proc.returncode}",
        }
    cleanup = report.setdefault("cleanup", {})
    cleanup.update(
        {
            "worker_exit_code": proc.returncode,
            "orphan_pids_before_reap": orphan_before,
            "orphan_pids_after_reap": orphan_after,
            "temp_tree_removed": False,
        }
    )
    report["process_tree"] = {
        "peak_rss_bytes": peak_tree_rss,
        "peak_temp_bytes": peak_temp_bytes,
        "peak_process_count": len(peak_pids),
        "peak_pids": peak_pids,
        "max_live_process_count": max_live_process_count,
        "observed_process_count": len(observed_processes),
        "observed_processes": [
            {"pid": pid, "name": name} for pid, name in sorted(observed_processes.items())
        ],
        "browser_process_observed": any(
            "chrome" in name.lower() or "chromium" in name.lower()
            for name in observed_processes.values()
        ),
        "worker_peak_rss_bytes": worker_peak_rss_bytes,
    }
    if stdout.strip():
        report["worker_stdout_tail"] = stdout[-4000:]
    if stderr.strip():
        report["worker_stderr_tail"] = stderr[-4000:]
    failed = reason is not None or proc.returncode != 0 or report.get("status") != "ok"
    failed = failed or bool(orphan_after)
    return report, failed


def _supervise(args: argparse.Namespace) -> int:
    _authority_guard(args.points, args.authority, dict(os.environ))
    source_bytes = args.points * 16
    if source_bytes > args.max_disk_gib * 1024**3:
        raise ValueError("configured disk ceiling is smaller than the two canonical f64 sources")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_parent = args.temp_root.resolve() if args.temp_root else None
    tmp = Path(tempfile.mkdtemp(prefix="xyg-density-e2e-", dir=temp_parent))
    report: dict[str, Any] | None = None
    failed = True
    try:
        report, failed = _run_supervisor(args, tmp)
    except Exception as exc:
        report = {
            "schema_version": SCHEMA_VERSION,
            "report_kind": "density-e2e",
            "status": "failed",
            "authority": args.authority,
            "point_count": args.points,
            "failure": f"supervisor_error: {type(exc).__name__}: {exc}",
            "cleanup": {},
        }
    finally:
        cleanup_error = None
        try:
            shutil.rmtree(tmp)
        except OSError as exc:
            cleanup_error = str(exc)

    assert report is not None
    cleanup = report.setdefault("cleanup", {})
    cleanup["temp_tree_removed"] = not tmp.exists()
    if cleanup_error is not None:
        report["temp_cleanup_error"] = cleanup_error
        failed = True
    if not cleanup["temp_tree_removed"]:
        failed = True
    _atomic_write_json(output, report)
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", type=int, default=1_000_000)
    parser.add_argument("--output", type=Path, default=Path("density-e2e.json"))
    parser.add_argument("--chrome", type=Path)
    parser.add_argument("--authority", action="store_true")
    parser.add_argument("--chunk-points", type=int, default=1_000_000)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--max-rss-gib", type=float, default=12)
    parser.add_argument("--max-disk-gib", type=float, default=4)
    parser.add_argument("--payload-ceiling-bytes", type=int, default=DEFAULT_PAYLOAD_CEILING)
    parser.add_argument("--temp-root", type=Path)
    parser.add_argument("--worker-config", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_config is not None:
        return _worker(args.worker_config)
    if args.chrome is None or not args.chrome.is_file():
        parser.error("--chrome must name an existing Chromium executable")
    bounded_numbers = (args.timeout, args.max_rss_gib, args.max_disk_gib)
    if (
        args.chunk_points <= 0
        or args.chunk_points > MAX_CHUNK_POINTS
        or args.payload_ceiling_bytes <= 0
        or any(not math.isfinite(value) or value <= 0 for value in bounded_numbers)
    ):
        parser.error(
            f"chunk must be between 1 and {MAX_CHUNK_POINTS}; "
            "timeout, RSS, and disk limits must be positive"
        )
    try:
        return _supervise(args)
    except ValueError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
