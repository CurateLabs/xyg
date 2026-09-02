"""Deterministic sampling tiers for LOD overlays."""

from __future__ import annotations

from typing import Any

import numpy as np

from . import kernels
from ._lod_params import _float_param, _integer_param
from ._lod_types import _DEFAULT_SAMPLE_BASE_FRACTION, _MAX_DIRECT_CATEGORY_CODE, _UINT64_MAX_INT
from .config import MAX_SCREEN_DIM


def _row_ids(row_ids: Any, label: str = "row_ids") -> np.ndarray:
    """Validate unsigned row ids without widening native u32 selections."""
    ids = np.asarray(row_ids)
    if ids.ndim != 1:
        raise ValueError(f"{label} must be a one-dimensional integer array")
    if ids.dtype.kind == "b":
        raise ValueError(f"{label} must be a one-dimensional integer array")
    if ids.dtype.kind == "i":
        if len(ids) and bool(np.any(ids < 0)):
            raise ValueError(f"{label} must not contain negative values")
        return ids.astype(np.uint64, copy=False)
    if ids.dtype.kind == "u":
        if ids.dtype == np.uint32:
            return ids
        return ids.astype(np.uint64, copy=False)
    raise ValueError(f"{label} must be a one-dimensional integer array")


def _sample_fraction(
    level: object,
    base_fraction: object,
    growth: object,
    *,
    label: str = "sample",
) -> float:
    level_i = _integer_param(level, f"{label} level")
    base = _float_param(
        base_fraction,
        f"{label} base_fraction",
        min_exclusive=0.0,
        max_inclusive=1.0,
    )
    growth_f = _float_param(growth, f"{label} growth", min_inclusive=1.0)
    return kernels.sample_fraction(level_i, base, growth_f)


def _sample_threshold(fraction: float) -> np.uint64:
    return np.uint64(kernels.sample_threshold(fraction))


def hash_row_ids(row_ids: Any, *, seed: int = 0) -> np.ndarray:
    """SplitMix64 row-id hash used by sampling tiers.

    The output is a pure function of `(row_id, seed)` and therefore independent
    of array order, viewport pan position, Python hash randomization, or runtime
    RNG state. Sampling tiers use this as the stable row ordering that prevents
    shimmer when zooming or panning.
    """
    ids = _row_ids(row_ids)
    seed_i = _integer_param(seed, "sample seed", max_value=_UINT64_MAX_INT)
    return kernels.hash_row_ids(ids, seed_i)


def sample_keep_mask(
    row_ids: Any,
    level: int,
    *,
    base_fraction: float = _DEFAULT_SAMPLE_BASE_FRACTION,
    growth: float = 2.0,
    seed: int = 0,
) -> np.ndarray:
    """Deterministic subset mask for sampled LOD overlays.

    `level` is a zoom/detail level: increasing it can only add rows because the
    hash threshold monotonically increases. That gives a future density+sample
    overlay stable anti-shimmer behavior: panning does not reshuffle points,
    and zooming in reveals more of the same row-id ordering instead of swapping
    one random subset for another.
    """
    ids = _row_ids(row_ids)
    fraction = _sample_fraction(level, base_fraction, growth)
    if len(ids) == 0:
        return np.zeros(0, dtype=bool)
    if fraction >= 1.0:
        return np.ones(len(ids), dtype=bool)
    seed_i = _integer_param(seed, "sample seed", max_value=_UINT64_MAX_INT)
    # Fused native pass — bit-identical to
    # `hash_row_ids(ids, seed=seed) <= _sample_threshold(fraction)` (the NumPy
    # reference, parity-tested), but without five full-width u64 temporaries.
    # At 10M rows this was ~68% of the density payload build.
    return kernels.sample_mask(ids, seed_i, int(_sample_threshold(fraction)))


def stratified_sample_keep_mask(
    row_ids: Any,
    categories: Any,
    level: int,
    *,
    base_fraction: float = _DEFAULT_SAMPLE_BASE_FRACTION,
    growth: float = 2.0,
    seed: int = 0,
    min_per_category: int = 1,
) -> np.ndarray:
    """Deterministic category-aware sampled LOD mask.

    Expected kept rows per category scale sublinearly with category size
    (`~sqrt(count)`) while `min_per_category` pins rare categories into view.
    The lowest-hash rows satisfy that floor at every level, so the mask remains
    monotonic as zoom/detail increases.
    """
    ids = _row_ids(row_ids)
    cats = np.asarray(categories)
    if cats.ndim != 1 or len(cats) != len(ids):
        raise ValueError("categories must be a one-dimensional array matching row_ids")
    min_count = _integer_param(min_per_category, "sample min_per_category")
    fraction = _sample_fraction(level, base_fraction, growth, label="stratified sample")
    if len(ids) == 0:
        return np.zeros(0, dtype=bool)
    if fraction >= 1.0:
        return np.ones(len(ids), dtype=bool)

    seed_i = _integer_param(seed, "sample seed", max_value=_UINT64_MAX_INT)
    # Fused native pass — bit-identical to the per-category NumPy loop this
    # replaced (hash-threshold per category plus an argpartition floor fill;
    # parity-tested), but without the O(n · n_categories) `inverse == group`
    # rescans that dominated categorical density builds. Small non-negative
    # integer categories (the channel-codes hot path) go straight in as group
    # codes: empty codes form zero-count groups no row maps to, so the mask is
    # identical to the dense `np.unique` ranking without its O(n log n) sort.
    if np.issubdtype(cats.dtype, np.integer):
        lo, hi = int(cats.min()), int(cats.max())
        if lo >= 0 and hi < _MAX_DIRECT_CATEGORY_CODE:
            return kernels.stratified_sample_mask(
                ids, cats.astype(np.uint32, copy=False), hi + 1, seed_i, fraction, min_count
            )
    _, inverse, counts = np.unique(cats, return_inverse=True, return_counts=True)
    return kernels.stratified_sample_mask(
        ids, inverse.astype(np.uint32, copy=False), len(counts), seed_i, fraction, min_count
    )


def sample_rows_for_target(
    row_ids: Any,
    target: object,
    *,
    categories: Any | None = None,
    level: int = 0,
    growth: float = 2.0,
    seed: int = 0,
    min_per_category: int = 1,
) -> np.ndarray:
    """Return a deterministic, target-sized representative subset of rows.

    Density overlays and future sampled tiers should share this wrapper instead
    of reimplementing "target N rows from this viewport" math. The returned
    rows preserve the caller's integer dtype, while hashing uses validated
    uint64 row ids internally. Subsets are stable across row order and viewport
    pans because row identity, not position in the current array, drives the
    decision.
    """
    raw_ids = np.asarray(row_ids)
    ids = _row_ids(raw_ids)
    target_i = _integer_param(target, "sample target", min_value=1)
    if len(ids) == 0:
        return raw_ids[:0]
    base_fraction = min(1.0, target_i / max(1, len(ids)))
    if categories is None:
        mask = sample_keep_mask(
            ids,
            level,
            base_fraction=base_fraction,
            growth=growth,
            seed=seed,
        )
    else:
        mask = stratified_sample_keep_mask(
            ids,
            categories,
            level,
            base_fraction=base_fraction,
            growth=growth,
            seed=seed,
            min_per_category=min_per_category,
        )
    return raw_ids[mask]


def sample_row_range_for_target(
    size: object,
    target: object,
    *,
    level: int = 0,
    growth: float = 2.0,
    seed: int = 0,
) -> np.ndarray:
    """Sample implicit row ids ``range(size)`` without materializing them all.

    A full-view density trace commonly has identity row ids. Building an
    ``arange(size)`` plus its u64 hash input and byte mask makes transient
    memory scale with the dataset just to retain a screen-bounded overlay.
    Chunking the same native SplitMix64 predicate keeps peak scratch bounded
    while returning exactly the rows :func:`sample_rows_for_target` would.
    """
    size_i = _integer_param(size, "sample range size", max_value=(1 << 32) - 1)
    target_i = _integer_param(target, "sample target", min_value=1)
    if size_i == 0:
        return np.empty(0, dtype=np.uint32)
    level_i = _integer_param(level, "sample level")
    growth_f = _float_param(growth, "sample growth", min_inclusive=1.0)
    seed_i = _integer_param(seed, "sample seed", max_value=_UINT64_MAX_INT)
    keep_all, idx = kernels.payload_sample_target_indices(
        size_i, target_i, seed_i, level_i, growth_f
    )
    if keep_all:
        return np.arange(size_i, dtype=np.uint32)
    return idx


def bin_2d_sample_row_range_for_target(
    x: Any,
    y: Any,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    width: object,
    height: object,
    target: object,
    *,
    level: int = 0,
    growth: float = 2.0,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Bin a full-domain view and sample its implicit rows in one scan.

    The caller must have established that every row is visible. Both outputs
    remain exactly equivalent to :func:`kernels.bin_2d` followed by
    :func:`sample_row_range_for_target`; this helper only selects the fused
    native execution path.
    """
    size_i = _integer_param(len(x), "sample range size", max_value=(1 << 32) - 1)
    target_i = _integer_param(target, "sample target", min_value=1)
    width_i = _integer_param(width, "density width", min_value=1, max_value=MAX_SCREEN_DIM)
    height_i = _integer_param(height, "density height", min_value=1, max_value=MAX_SCREEN_DIM)
    base_fraction = min(1.0, target_i / size_i) if size_i else 1.0
    fraction = _sample_fraction(level, base_fraction, growth)
    if fraction >= 1.0:
        return (
            kernels.bin_2d(x, y, x0, x1, y0, y1, width_i, height_i),
            np.arange(size_i, dtype=np.uint32),
        )
    seed_i = _integer_param(seed, "sample seed", max_value=_UINT64_MAX_INT)
    threshold = int(_sample_threshold(fraction))
    capacity = min(size_i, max(64, target_i * 2))
    return kernels.bin_2d_sample_range(
        x,
        y,
        x0,
        x1,
        y0,
        y1,
        width_i,
        height_i,
        seed_i,
        threshold,
        capacity,
    )


def stratified_sample_row_range_for_target(
    groups: Any,
    n_groups: object,
    target: object,
    *,
    counts: Any | None = None,
    level: int = 0,
    growth: float = 2.0,
    seed: int = 0,
    min_per_category: int = 1,
) -> np.ndarray:
    """Category-aware sample of implicit row ids without source-sized scratch.

    This is exactly the compact-u8, full-domain equivalent of
    :func:`sample_rows_for_target` with ``categories=groups``. It avoids an
    ``arange``, its u64 conversion, the category gather, and the keep mask;
    live scratch instead scales with the screen-bounded returned sample.
    """
    codes, group_counts, n_groups_i, fraction, seed_i, min_count, capacity = (
        _stratified_sample_range_plan(
            groups,
            n_groups,
            target,
            counts=counts,
            level=level,
            growth=growth,
            seed=seed,
            min_per_category=min_per_category,
        )
    )
    if len(codes) == 0:
        return np.empty(0, dtype=np.uint32)
    if fraction >= 1.0:
        return np.arange(len(codes), dtype=np.uint32)
    return kernels.stratified_sample_range_u8(
        codes,
        n_groups_i,
        seed_i,
        fraction,
        min_count,
        capacity,
        counts=group_counts,
    )


def _stratified_sample_range_plan(
    groups: Any,
    n_groups: object,
    target: object,
    *,
    counts: Any | None,
    level: int,
    growth: float,
    seed: int,
    min_per_category: int,
) -> tuple[np.ndarray, np.ndarray | None, int, float, int, int, int]:
    """Validate categorical sampling policy and size its bounded output."""
    codes = np.asarray(groups)
    if codes.ndim != 1 or codes.dtype != np.uint8:
        raise ValueError("groups must be a one-dimensional uint8 array")
    n_groups_i = _integer_param(n_groups, "sample n_groups", min_value=1, max_value=256)
    target_i = _integer_param(target, "sample target", min_value=1)
    min_count = _integer_param(min_per_category, "sample min_per_category")
    if len(codes) == 0:
        return codes, None, n_groups_i, 1.0, 0, min_count, 0
    if int(codes.max()) >= n_groups_i:
        raise ValueError("groups must contain codes below n_groups")
    group_counts = None
    if counts is not None:
        group_counts = np.asarray(counts)
        if (
            group_counts.ndim != 1
            or group_counts.dtype != np.uint64
            or len(group_counts) != n_groups_i
            or int(group_counts.sum(dtype=np.uint64)) != len(codes)
        ):
            raise ValueError("counts must be exact uint64 counts for every group")
    plan = kernels.stratified_sample_range_plan(
        len(codes),
        n_groups_i,
        target_i,
        level,
        growth,
        0,
        min_count,
    )
    if plan["keep_all"]:
        return codes, group_counts, n_groups_i, plan["fraction"], 0, min_count, plan["capacity"]
    seed_i = _integer_param(seed, "sample seed", max_value=_UINT64_MAX_INT)
    return (
        codes,
        group_counts,
        n_groups_i,
        plan["fraction"],
        seed_i,
        min_count,
        plan["capacity"],
    )


def bin_2d_stratified_sample_row_range_for_target(
    x: Any,
    y: Any,
    groups: Any,
    n_groups: object,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    width: object,
    height: object,
    target: object,
    *,
    counts: Any,
    level: int = 0,
    growth: float = 2.0,
    seed: int = 0,
    min_per_category: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Bin a full-domain view and build its exact categorical overlay."""
    width_i = _integer_param(width, "density width", min_value=1, max_value=MAX_SCREEN_DIM)
    height_i = _integer_param(height, "density height", min_value=1, max_value=MAX_SCREEN_DIM)
    codes, group_counts, _, fraction, seed_i, min_count, capacity = _stratified_sample_range_plan(
        groups,
        n_groups,
        target,
        counts=counts,
        level=level,
        growth=growth,
        seed=seed,
        min_per_category=min_per_category,
    )
    if len(x) != len(codes):
        raise ValueError("groups must match the x and y row count")
    if fraction >= 1.0:
        return (
            kernels.bin_2d(x, y, x0, x1, y0, y1, width_i, height_i),
            np.arange(len(codes), dtype=np.uint32),
        )
    if group_counts is None:
        raise ValueError("counts are required for fused categorical sampling")
    return kernels.bin_2d_stratified_sample_range_u8_counted(
        x,
        y,
        codes,
        group_counts,
        x0,
        x1,
        y0,
        y1,
        width_i,
        height_i,
        seed_i,
        fraction,
        min_count,
        capacity,
    )
