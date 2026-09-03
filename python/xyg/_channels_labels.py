"""Category label factorization and categorical admit probes."""

from __future__ import annotations

import numbers
from typing import Any, Optional

import numpy as np
import numpy.typing as npt

from . import kernels

MAX_CATEGORIES = 256
_FACTORIZE_PROBE_ROWS = 4096
_FACTORIZE_NATIVE_MAX_PROBE_CATEGORIES = 512
_FACTORIZE_NEAR_UNIQUE_RATIO = 0.95
_FACTORIZE_NARROW_ITEMSIZE = 32


def _is_categorical(arr: np.ndarray) -> bool:
    kind = ord(arr.dtype.kind)
    if arr.dtype == object:
        probe = 1 if _object_array_is_real_numeric(arr) else 0
        return kernels.array_is_categorical(kind, probe)
    return kernels.array_is_categorical(kind, -1)


# `#rrggbb` and `rgb()/hsl()` cannot be mistaken for data; a bare `red` can.


def _literal_color_rgba(arr: np.ndarray) -> Optional[npt.NDArray[np.float64]]:
    """Straight-alpha RGBA when every entry is a written-out CSS color, else None.

    `["#ff0000", "#00ff00"]` is paint, not data: factorizing it sorted the two
    hex strings into categories and repainted them from the palette, so the
    caller asked for red and green and got the palette's first two colors in
    alphabetical order.

    Deliberately restricted to `#rrggbb` / `rgb()` / `hsl()`. A bare `red` also
    parses as a color, but a column of `["red", "green", "blue"]` is a perfectly
    ordinary category column, and guessing wrong there would silently change an
    encoding into a paint. Unambiguous syntax only, so nothing is guessed."""
    if arr.dtype.kind not in ("U", "O") or arr.size == 0:
        return None
    # Gate on the first entry before materializing anything. `_factorize_
    # categories` goes to real trouble to identify equal records in Rust
    # WITHOUT creating N Python objects, and an unconditional `tolist()` here
    # threw that away for every categorical scatter — measured at ~39% of the
    # payload build for a 500k-row species column. A category column fails this
    # test on its very first value, so it pays O(1); only an array that already
    # looks like paint pays for the full scan below.
    #
    # Requiring entry zero to match is exactly as strict as the `all(...)`
    # below, which already demands every entry be a color string.
    first = arr.flat[0]
    if not isinstance(first, str) or not kernels.css_is_functional(first):
        return None
    values = arr.tolist()
    if not all(isinstance(v, str) and kernels.css_is_functional(v) for v in values):
        return None
    # ABI 344 packs the column in Rust so every host parses with the same
    # functional-color gate and static CSS grammar.
    return kernels.literal_color_rgba_f64(values)


def _is_missing_category(value: Any) -> bool:
    if value is None:
        return True
    if value.__class__.__name__ in {"NAType", "NaTType"}:
        return True
    try:
        # Covers float NaN, numpy scalar NaN/NaT, and pandas.NA-like values
        # without importing pandas. Object comparisons can return arrays or
        # raise, so keep this deliberately defensive.
        return bool(value != value)
    except Exception:
        return False


def _category_label_payload(value: Any, probe: int) -> bytes:
    if probe == 0:
        return b""
    if probe == 3:
        if isinstance(value, bytes):
            return value
        if isinstance(value, np.bytes_):
            return bytes(value)
    if probe == 2 and isinstance(value, (str, np.str_)):
        return str(value).encode("utf-8")
    return str(value).encode("utf-8")


def _category_label_kind_and_bytes(value: Any) -> tuple[int, bytes]:
    probe = _value_probe(value)
    kind = kernels.category_label_kind_from_probe(probe)
    return kind, _category_label_payload(value, probe)


def category_label(value: Any) -> str:
    """Canonical display label for category-like data.

    Shared by categorical color channels and categorical axes so legends,
    ticks, and composed marks agree on how messy labels display.
    """
    kind, payload = _category_label_kind_and_bytes(value)
    return kernels.category_labels([kind], [payload])[0]


def _category_labels(values: Any) -> list[str]:
    values_list = values.tolist() if isinstance(values, np.ndarray) else list(values)
    if not values_list:
        return []
    probes = np.fromiter(
        (_value_probe(value) for value in values_list),
        dtype=np.uint8,
        count=len(values_list),
    )
    kinds = kernels.category_label_kinds_from_probes(probes)
    payloads = [
        _category_label_payload(value, int(probe))
        for value, probe in zip(values_list, probes, strict=True)
    ]
    return kernels.category_labels(kinds.tolist(), payloads)


def _value_probe(value: Any) -> int:
    if _is_missing_category(value):
        return 0
    if isinstance(value, (bool, np.bool_)):
        return 1
    if isinstance(value, (str, np.str_)):
        return 2
    if isinstance(value, (bytes, np.bytes_)):
        return 3
    if isinstance(value, numbers.Real):
        return 4
    try:
        float(value)
    except (TypeError, ValueError):
        return 6
    return 5


def _object_column_is_stringlike(arr: np.ndarray) -> bool:
    """True when every row is missing or a string/bytes value."""
    if arr.dtype != object:
        return False
    probes = np.fromiter((_value_probe(value) for value in arr), dtype=np.uint8, count=len(arr))
    tags = kernels.object_row_stringlike_tags_from_probes(probes)
    return kernels.object_rows_all_stringlike(tags)


def _use_native_fixed_factorizer(arr: np.ndarray) -> bool:
    """Choose the O(N) hash path unless a bounded global probe says it cannot pay.

    The native pass earns its keep by keeping N records out of Python: only the
    compact unique set crosses the label-policy path. It stops paying when the
    column is near-unique, because then Python must materialize and sort
    essentially the whole label set anyway and hashing the records first is
    redundant. What decides that is how *repetitive* the probe is, not how many
    categories it happens to contain — a few hundred categories spread over
    millions of rows is an ordinary categorical column and keeps the fast path.
    Wide records cross over sooner, so they hand back the fast path as soon as
    repeats get scarce while narrow ones hold it until the probe is entirely
    distinct. Sampling across the full array keeps the decision independent of N.
    """
    return kernels.factorize_use_native_fixed(arr)


def _factorize_categories(
    arr: np.ndarray,
) -> tuple[
    list[str],
    npt.NDArray[np.uint8] | npt.NDArray[np.uint32],
    Optional[npt.NDArray[np.uint64]],
]:
    """Factorize categorical data without relying on object sorting.

    `np.unique(..., return_inverse=True)` sorts the raw Python objects; mixed
    object arrays (`"a"`, `None`, `1`) raise in NumPy because those values are
    not mutually orderable. Chart labels are strings on the client anyway, so
    canonicalize to display labels first, sort those labels for deterministic
    palettes, and then map each row back to its code. Fixed-width NumPy
    strings/bytes/bools/fixed-width integers can identify equal records in Rust
    without creating N Python objects; only their compact unique set crosses the
    label-policy path.
    """
    if arr.dtype == object and _object_column_is_stringlike(arr):
        arr = np.asarray(_category_labels(arr), dtype=np.str_)
    if arr.dtype.kind in ("U", "S", "b", "u", "i") and _use_native_fixed_factorizer(arr):
        compact = (
            kernels.factorize_unicode1_u8_counts(arr, MAX_CATEGORIES)
            if arr.dtype.kind == "U" and arr.dtype.itemsize == 4
            else kernels.factorize_fixed_u8_counts(arr, MAX_CATEGORIES)
        )
        if compact is not None:
            raw_codes, unique_indices, raw_counts = compact
            unique_labels = _category_labels(arr[unique_indices])
            categories, remap, counts = kernels.sorted_display_label_remap(
                unique_labels, raw_counts
            )
            if not np.array_equal(remap, np.arange(len(remap), dtype=remap.dtype)):
                kernels.remap_u8(raw_codes, np.asarray(remap, dtype=np.uint8))
            return categories, raw_codes, counts

        raw_codes, unique_indices = kernels.factorize_fixed(arr)
        unique_labels = _category_labels(arr[unique_indices])
        categories, remap, _counts = kernels.sorted_display_label_remap(unique_labels)
        if int(remap.dtype.itemsize) == 1:
            return categories, remap[raw_codes.astype(np.intp, copy=False)], None
        return categories, remap[raw_codes], None

    labels = _category_labels(arr)
    return (*kernels.factorize_display_labels(labels), None)


def _object_array_is_real_numeric(arr: np.ndarray) -> bool:
    if arr.dtype != object:
        return False
    probes = np.fromiter((_value_probe(value) for value in arr), dtype=np.uint8, count=len(arr))
    tags = kernels.object_row_real_numeric_tags_from_probes(probes)
    return kernels.object_rows_all_real_numeric(tags)


def _as_real_array(values: np.ndarray, label: str) -> npt.NDArray[np.float64]:
    try:
        kernels.real_numeric_dtype_admit(ord(values.dtype.kind))
    except ValueError as exc:
        raise ValueError(str(exc).replace("values", label)) from exc
    if values.dtype == object and not _object_array_is_real_numeric(values):
        raise ValueError(f"{label} must be real numeric")
    try:
        return values.astype(np.float64, copy=False)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{label} must be real numeric") from e


def _size_range(range_px: tuple[float, float]) -> tuple[float, float]:
    try:
        lo_raw, hi_raw = range_px
    except (TypeError, ValueError) as e:
        raise ValueError("size_range must contain exactly two finite pixel values") from e
    return kernels.size_range_admit(lo_raw, hi_raw)


def _continuous_domain(values: npt.NDArray[np.float64]) -> tuple[float, float]:
    return kernels.continuous_domain(values)
