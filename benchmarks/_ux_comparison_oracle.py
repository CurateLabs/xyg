"""Independent, source-derived comparison oracle (never a product renderer).

Preparation scans bounded chunks before META, under the existing host watchdog.
Warm checks use only prepared screen grids. No native aggregation/count/compose
answer is an expectation. See spec/design/comparison-count-oracle.md.
"""

from __future__ import annotations

import base64
import hashlib
import math
import time
from types import SimpleNamespace

import numpy as np

VERSION = "source-cell-compose-v1"
CHUNK = 65_536


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def center_range(lo, hi, full_lo, full_hi, dim):
    cell = (full_hi - full_lo) / dim
    return (
        min(dim, max(0, math.ceil((lo - full_lo) / cell - 0.5))),
        min(dim, max(0, math.floor((hi - full_lo) / cell - 0.5) + 1)),
    )


def histogram(x, y, domain, shape):
    """Exact integer half-open source histogram; heap scratch is O(CHUNK)."""
    h, w = shape
    grid = np.zeros((h, w), dtype=np.uint32)
    sx, sy = w / (domain[1] - domain[0]), h / (domain[3] - domain[2])
    for start in range(0, len(x), CHUNK):
        a = np.asarray(x[start : start + CHUNK], dtype=np.float64)
        b = np.asarray(y[start : start + CHUNK], dtype=np.float64)
        valid = (
            np.isfinite(a)
            & np.isfinite(b)
            & (a >= domain[0])
            & (a < domain[1])
            & (b >= domain[2])
            & (b < domain[3])
        )
        cx = np.minimum(((a[valid] - domain[0]) * sx).astype(np.int64), w - 1)
        cy = np.minimum(((b[valid] - domain[2]) * sy).astype(np.int64), h - 1)
        np.add.at(grid.ravel(), cy * w + cx, 1)
    return grid


def axis_taps(lo, hi, origin, end, dim, output):
    """Source interval overlaps, folded at the rim; source-order f32 weights."""
    first, last = center_range(lo, hi, origin, end, dim)
    cell, scale = (end - origin) / dim, output / (hi - lo)
    taps = [[] for _ in range(output)]
    rows = []
    for source in range(first, last):
        left = (origin + source * cell - lo) * scale
        right = (origin + (source + 1) * cell - lo) * scale
        primary = min(output - 1, max(0, math.floor((left + right) / 2)))
        lower, upper = primary - left, right - (primary + 1)
        neighbor, spill = (primary - 1, lower) if lower >= upper else (primary + 1, upper)
        fraction = min(1.0, max(0.0, spill / (right - left))) if right > left else 0.0
        # This 1e-6 is the documented product edge-snap rule, NOT an error allowance.
        weights = [(primary, np.float32(1))]
        if fraction > 1e-6 and 0 <= neighbor < output:
            weights = [(primary, np.float32(1 - fraction)), (neighbor, np.float32(fraction))]
        rows.append(weights)
        for target, weight in weights:
            taps[target].append((source - first, weight))
    return first, last, taps, rows


def compose(levels, bounds, domain, shape):
    """Independent separable area resampling, preserving specified f32 order."""
    h, w = shape
    selected = None
    for index in range(len(levels) - 1, -1, -1):
        dim = levels[index].shape[0]
        ax = center_range(*domain[:2], *bounds[:2], dim)
        ay = center_range(*domain[2:], *bounds[2:], dim)
        if ax[1] - ax[0] >= w and ay[1] - ay[0] >= h:
            selected = index
            break
    selected = 0 if selected is None else selected
    source = levels[selected]
    dim = source.shape[0]
    x0, x1, xtaps, _ = axis_taps(*domain[:2], *bounds[:2], dim, w)
    y0, y1, _, ytaps = axis_taps(*domain[2:], *bounds[2:], dim, h)
    out = np.zeros((h, w), dtype=np.float32)
    if x1 - x0 < w or y1 - y0 < h:
        # Pixel-center pull. Integer conversion truncates toward zero, as specified
        # by the current compose implementation; out-of-domain indices stay zero.
        cx = np.trunc(
            (domain[0] + (np.arange(w) + 0.5) / (w / (domain[1] - domain[0])) - bounds[0])
            * (dim / (bounds[1] - bounds[0]))
        ).astype(np.int64)
        cy = np.trunc(
            (domain[2] + (np.arange(h) + 0.5) / (h / (domain[3] - domain[2])) - bounds[2])
            * (dim / (bounds[3] - bounds[2]))
        ).astype(np.int64)
        ix, iy = np.flatnonzero((cx >= 0) & (cx < dim)), np.flatnonzero((cy >= 0) & (cy < dim))
        out[np.ix_(iy, ix)] = source[np.ix_(cy[iy], cx[ix])]
    else:
        longest = max(map(len, xtaps), default=0)
        indices = np.zeros((longest, w), dtype=np.int64)
        weights = np.zeros((longest, w), dtype=np.float32)
        for target, taps in enumerate(xtaps):
            for rank, (offset, weight) in enumerate(taps):
                indices[rank, target], weights[rank, target] = offset, weight
        for offset, row_weights in enumerate(ytaps):
            row = source[y0 + offset, x0:x1].astype(np.float32)
            values = np.zeros(w, dtype=np.float32)
            for index, weight in zip(indices, weights, strict=True):
                values += row[index] * weight
            for target, weight in row_weights:
                out[target] += values * weight
    return out, selected


def encode(grid):
    maximum = float(grid.max(initial=0))
    out = np.zeros(grid.shape, dtype=np.uint8)
    positive = grid > 0
    if maximum:
        out[positive] = np.clip(
            np.rint(255 * np.log1p(grid[positive].astype(np.float64)) / math.log1p(maximum)), 1, 255
        ).astype(np.uint8)
    return out.tobytes(), maximum


class SourceOracle:
    def __init__(self, x, y, meta, *, base_dim=None):
        from benchmarks._ux_comparison_source import allocation_guard
        from xyg import config, interaction, kernels

        started = time.perf_counter()
        allocation_guard(
            len(x),
            meta["profile"],
            meta["authority"]["per_tree_rss_guard_bytes"] / 2**30,
            meta["authority"]["disk_guard_bytes"] / 2**30,
        )
        self.meta, self.records = meta, {}
        self.bounds = list(meta["source_bounds"])
        for index in (1, 3):
            self.bounds[index] += (self.bounds[index] - self.bounds[index - 1]) * 1e-9
        eligible = len(x) >= config.PYRAMID_MIN_POINTS or base_dim is not None
        if eligible and base_dim is None:

            class ColumnView:
                values = x

                def __len__(self):
                    return len(x)

            # Geometry/policy query only; no aggregation answer is consulted.
            base_dim = interaction._pyramid_base_dim_for(SimpleNamespace(x=ColumnView()))
        levels = []
        level_bytes = (
            sum(4 * (base_dim >> level) ** 2 for level in range(base_dim.bit_length()))
            if eligible
            else 0
        )
        # Includes reduction temporaries, screen encoding/decoding and chunks.
        storage_bound = 3 * level_bytes + 128 * 512 * 512 + 64 * CHUNK
        if storage_bound > meta["authority"]["per_tree_rss_guard_bytes"]:
            raise ValueError("independent oracle grid storage bound exceeds RSS cap")
        if eligible:
            levels.append(histogram(x, y, self.bounds, (base_dim, base_dim)))
            while levels[-1].shape[0] > 1:
                a = levels[-1]
                levels.append(a[::2, ::2] + a[1::2, ::2] + a[::2, 1::2] + a[1::2, 1::2])
        extents = meta["extents"]
        dx, dy = extents[1] - extents[0], extents[3] - extents[2]
        empty = [extents[1] + dx, extents[1] + 1.5 * dx, extents[3] + dy, extents[3] + 1.5 * dy]
        entries = [
            (
                extents,
                {"inclusive": len(x), "half_open": len(x), "upper_boundary_excluded": 0},
                True,
            )
        ]
        entries += [(s["window"], s["source_counts"], False) for s in meta["windows"]]
        entries.append(
            (empty, {"inclusive": 0, "half_open": 0, "upper_boundary_excluded": 0}, False)
        )
        mapped = meta["profile"] == "f64-memmap"
        for domain, counts, cold in entries:
            key = (tuple(domain), cold)
            if key in self.records:
                continue
            estimate = counts["inclusive"]
            boundary = 0
            if eligible:
                ax = center_range(*domain[:2], *self.bounds[:2], base_dim)
                ay = center_range(*domain[2:], *self.bounds[2:], base_dim)
                estimate = int(levels[0][ay[0] : ay[1], ax[0] : ax[1]].sum(dtype=np.uint64))
                ranges = []
                for axis in (0, 2):
                    cell = (self.bounds[axis + 1] - self.bounds[axis]) / base_dim
                    low, high = (
                        (domain[axis] - self.bounds[axis]) / cell,
                        (domain[axis + 1] - self.bounds[axis]) / cell,
                    )
                    # Outer cells intersect the closed window; inner cells are
                    # strictly contained, conservatively including edge rows in B.
                    ranges.append(
                        (
                            min(base_dim, max(0, math.ceil(low) - 1)),
                            max(0, min(base_dim, math.floor(high) + 1)),
                            min(base_dim, max(0, math.floor(low) + 1)),
                            min(base_dim, max(0, math.ceil(high) - 1)),
                        )
                    )
                xa, xb = ranges
                outer = int(levels[0][xb[0] : xb[1], xa[0] : xa[1]].sum(dtype=np.uint64))
                inner = int(levels[0][xb[2] : xb[3], xa[2] : xa[3]].sum(dtype=np.uint64))
                boundary = outer - inner
                if abs(estimate - counts["inclusive"]) > boundary:
                    raise ValueError("source count lies outside independent boundary-mass bound")
            available = eligible and ax[1] > ax[0] and ay[1] > ay[0]
            visible = estimate if available and not cold else counts["inclusive"]
            planning = (
                (
                    visible
                    if available
                    else max(estimate if eligible else len(x), config.SCATTER_DENSITY_THRESHOLD + 1)
                )
                if mapped
                else visible
            )
            exact, _, gw, gh = kernels.lod_plan(
                planning, config.SCATTER_DENSITY_THRESHOLD, False, width=512, height=512
            )
            shape = (config.DENSITY_GRID[1], config.DENSITY_GRID[0]) if cold else (gh, gw)
            if available and not cold:
                ax = center_range(*domain[:2], *self.bounds[:2], base_dim)
                ay = center_range(*domain[2:], *self.bounds[2:], base_dim)
                shape = (max(16, min(gh, ay[1] - ay[0])), max(16, min(gw, ax[1] - ax[0])))
            grid, level = (
                compose(levels, self.bounds, domain, shape)
                if available
                else (histogram(x, y, domain, shape).astype(np.float32), None)
            )
            wire, maximum = encode(grid)
            decoded = (
                np.expm1(
                    np.frombuffer(wire, dtype=np.uint8).astype(np.float64)
                    / 255
                    * math.log1p(maximum)
                )
                .astype("<f4")
                .tobytes()
            )
            expected_visible = visible if available or not mapped or cold else counts["half_open"]
            record = {
                "version": VERSION,
                "domain": list(domain),
                "exact_source_count": counts["inclusive"],
                "half_open_source_count": counts["half_open"],
                "upper_boundary_excluded": counts["upper_boundary_excluded"],
                "count_method": "whole-cell-center"
                if available and not cold
                else "inclusive-source"
                if cold or not mapped
                else "half-open-source",
                "count_exact": not (available and not cold),
                "expected_visible": expected_visible,
                "boundary_mass_bound": boundary,
                "base_geometry": {
                    "domain": self.bounds,
                    "dimension": base_dim,
                    "upper_edge_relative_epsilon": 1e-9,
                }
                if available
                else None,
                "served_level": level,
                "raster_shape": list(shape),
                "upsampled": bool(
                    available
                    and level == 0
                    and not cold
                    and (ax[1] - ax[0] < gw or ay[1] - ay[0] < gh)
                ),
                "expected_encoded_sha256": sha(wire),
                "expected_decoded_sha256": sha(decoded),
                "expected_max": maximum,
                "encoded_bytes": len(wire),
                "grid_sha256": sha(grid.astype("<f4").tobytes()),
                "grid_mass_diagnostic": float(grid.sum(dtype=np.float64)),
                "points_allowed": bool(
                    counts["inclusive"]
                    <= config.SCATTER_DENSITY_THRESHOLD * config.DRILL_EXIT_FACTOR
                    and not mapped
                    and not cold
                ),
            }
            self.records[key] = record
        self.preparation = {
            "version": VERSION,
            "wall_ms": (time.perf_counter() - started) * 1000,
            "chunk_rows": CHUNK,
            "grid_storage_upper_bound_bytes": storage_bound,
            "scope": "host_prepare before META; host process-tree RSS/watchdog includes oracle",
        }

    def validate(self, output, wire=b"", decoded=b"", *, cold=False, target=None):
        expected = dict(
            self.records[(tuple(target if target is not None else output["domain"]), cold)]
        )
        points = output["mode"] == "points"
        passed = output["visible"] == expected["expected_visible"]
        if points:
            passed = (
                expected["points_allowed"]
                and output["exact_count"] == expected["exact_source_count"]
            )
            passed = passed and output["tier"] == "direct" and output["reduction"] == "none"
        else:
            label = output["binning"]
            pyramid = expected["base_geometry"] is not None
            suffix = "-upsampled" if expected["upsampled"] else ""
            passed = (
                passed
                and output["tier"] == "density"
                and output["raster_shape"] == expected["raster_shape"]
                and output["domain"] == expected["domain"]
            )
            passed = passed and (
                label == f"pyramid-L{expected['served_level']}{suffix}"
                and output["reduction"] == "pyramid-count"
                if pyramid
                else (label, output["reduction"])
                in (("exact", "bin2d"), ("exact", "count"), ("bin2d-oversized", "bin2d-oversized"))
            )
            passed = (
                passed
                and sha(wire) == expected["expected_encoded_sha256"]
                and sha(decoded) == expected["expected_decoded_sha256"]
            )
            passed = (
                passed
                and output["encoding"] == "log-u8"
                and output["reply_max"] == output["adopted_max"] == expected["expected_max"]
            )
        expected.update(
            passed=bool(passed),
            emitted_visible=output["visible"],
            actual_encoded_sha256=sha(wire),
            adopted_decoded_sha256=sha(decoded),
            actual_max=output.get("reply_max"),
            source_sha256=self.meta["sha256_x_then_y"],
        )
        return expected


def decode_attachment(value):
    return base64.b64decode(value, validate=True)
