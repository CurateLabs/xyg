"""ctypes binding to the native Rust core (design dossier §32).

The core is a C-ABI cdylib; every call here passes NumPy buffer pointers
directly — zero copies across the Python/Rust boundary (§4: one
physical copy of every value; §29: in-process transport is 0-copy).

This module raises ImportError if the library is missing or ABI-mismatched;
`xyg.kernels` re-raises that with remediation guidance. There is no
pure-Python fallback — the native core is required (§33: no-wheel behavior is
defined, and it is a loud failure, never a silent degrade).
"""

from __future__ import annotations

import contextlib
import ctypes
import math
import numbers
import operator
import os
import struct
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar, Optional, cast

import numpy as np
import numpy.typing as npt

from ._abi_generated import ABI_VERSION, bind_abi_version, bind_generated_abi
from .config import MAX_CONTOUR_WORK, MAX_SCREEN_DIM

_MAX_SCENE_MARKS = 2_000_000
_MAX_SCENE_STYLES = 65_536
_MAX_SCENE_TEXT_BYTES = 4_096
MAX_SCENE_LEGEND_INPUT_BYTES = 48 + 128 * 24 + 16_384
MAX_SCENE_COLORBAR_INPUT_BYTES = 56 + 16 * 12 + 32 * 8 + 4_096
MAX_SCENE_ANNOTATION_INPUT_BYTES = (
    28
    + 12
    + 128 * 40
    + 4_096
    + 12
    + 128 * 32
    + 4_096
    + 12
    + 128 * 60
    + 12
    + 128 * 76
    + 8_192
    + 12
    + 128 * 68
    + 8_192
)


class _GraphProjectionDescriptor(ctypes.Structure):
    _fields_ = [
        ("node_ids", ctypes.c_void_p),
        ("node_count", ctypes.c_uint64),
        ("edge_ids", ctypes.c_void_p),
        ("edge_count", ctypes.c_uint64),
        ("source_ids", ctypes.c_void_p),
        ("target_ids", ctypes.c_void_p),
        ("parent_ids", ctypes.c_void_p),
        ("parent_validity", ctypes.c_void_p),
        ("directed", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
    ]


class _GraphCompoundSceneDescriptor(ctypes.Structure):
    _fields_ = [
        (name, kind)
        for name, kind in [
            ("version", ctypes.c_uint32),
            ("theme", ctypes.c_uint32),
            ("width", ctypes.c_double),
            ("height", ctypes.c_double),
            ("node_count", ctypes.c_uint64),
            ("edge_count", ctypes.c_uint64),
            ("title", ctypes.c_void_p),
            ("title_len", ctypes.c_uint64),
            *[
                (name, ctypes.c_void_p)
                for name in (
                    "x",
                    "y",
                    "node_classes",
                    "node_epistemic",
                    "node_statuses",
                    "node_metric",
                    "node_flags",
                    "node_label_lengths",
                    "sources",
                    "targets",
                    "edge_classes",
                    "edge_epistemic",
                    "edge_statuses",
                    "edge_metric",
                    "edge_flags",
                    "edge_label_lengths",
                    "label_payload",
                )
            ],
            ("label_payload_len", ctypes.c_uint64),
            ("parents", ctypes.c_void_p),
            ("parent_validity", ctypes.c_void_p),
            ("collapsed", ctypes.c_void_p),
            ("reserved", ctypes.c_uint64),
        ]
    ]


class _CoseDescriptor(ctypes.Structure):
    _fields_ = [
        ("in_x", ctypes.c_void_p),
        ("in_y", ctypes.c_void_p),
        ("pinned", ctypes.c_void_p),
        ("parents", ctypes.c_void_p),
        ("ideal_edge_length", ctypes.c_double),
        ("repulsion_strength", ctypes.c_double),
        ("gravity_strength", ctypes.c_double),
        ("cooling_factor", ctypes.c_double),
        ("overlap_padding", ctypes.c_double),
        ("component_spacing", ctypes.c_double),
        ("bounds", ctypes.c_void_p),
        ("has_bounds", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
    ]


class GraphProjectionNativeError(ValueError):
    """Stable error returned by the Rust-owned graph projection seam."""

    def __init__(self, status: int):
        self.status = int(status)
        super().__init__(f"native graph projection failed with status {self.status}")


class _TemporalColumnDescriptor(ctypes.Structure):
    _fields_ = [
        ("values", ctypes.c_void_p),
        ("validity", ctypes.c_void_p),
        ("len", ctypes.c_uint64),
        ("unit", ctypes.c_uint32),
        ("timezone", ctypes.c_void_p),
        ("timezone_len", ctypes.c_uint32),
        ("naive", ctypes.c_uint32),
        ("disambiguation", ctypes.c_uint32),
        ("dst_status", ctypes.c_void_p),
        ("offset_seconds", ctypes.c_void_p),
        ("fold_later_offset_seconds", ctypes.c_void_p),
        ("reserved", ctypes.c_uint32),
    ]


class _TemporalIntervalDescriptor(ctypes.Structure):
    _fields_ = [
        ("starts", ctypes.c_void_p),
        ("start_valid", ctypes.c_void_p),
        ("ends", ctypes.c_void_p),
        ("end_valid", ctypes.c_void_p),
        ("len", ctypes.c_uint64),
        ("reserved", ctypes.c_uint32),
    ]


class _TemporalControllerDescriptor(ctypes.Structure):
    _fields_ = [
        ("instance_id", ctypes.c_uint64),
        ("group_id", ctypes.c_uint64),
        ("domain_start", ctypes.c_int64),
        ("domain_end", ctypes.c_int64),
        ("cursor", ctypes.c_int64),
        ("window", ctypes.c_int64),
        ("step", ctypes.c_int64),
        ("direction", ctypes.c_int32),
        ("rate_milli", ctypes.c_uint32),
        ("loop_enabled", ctypes.c_uint32),
        ("reduced_motion", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
    ]


class _TemporalGraphDescriptor(ctypes.Structure):
    _fields_ = [
        ("projection_handle", ctypes.c_uint64),
        ("node_valid_from", ctypes.c_uint64),
        ("node_valid_to", ctypes.c_uint64),
        ("node_event_at", ctypes.c_uint64),
        ("edge_valid_from", ctypes.c_uint64),
        ("edge_valid_to", ctypes.c_uint64),
        ("edge_event_at", ctypes.c_uint64),
        ("reserved", ctypes.c_uint64),
    ]


class _TemporalGraphSnapshotMeta(ctypes.Structure):
    _fields_ = [
        ("revision", ctypes.c_uint64),
        ("cursor_micros", ctypes.c_int64),
        ("range_start_micros", ctypes.c_int64),
        ("range_end_micros", ctypes.c_int64),
        ("node_count", ctypes.c_uint64),
        ("edge_count", ctypes.c_uint64),
        ("visible_node_count", ctypes.c_uint64),
        ("visible_edge_count", ctypes.c_uint64),
        ("selected_visible_node_count", ctypes.c_uint64),
        ("selected_visible_edge_count", ctypes.c_uint64),
        ("pinned_visible_node_count", ctypes.c_uint64),
        ("selected_node_count", ctypes.c_uint64),
        ("selected_edge_count", ctypes.c_uint64),
        ("pinned_node_count", ctypes.c_uint64),
        ("focused_visible_kind", ctypes.c_uint32),
        ("focused_kind", ctypes.c_uint32),
        ("focused_visible_id", ctypes.c_uint8 * 16),
        ("focused_id", ctypes.c_uint8 * 16),
    ]


class _TemporalGraphSnapshotBuffers(ctypes.Structure):
    _fields_ = [
        ("node_visibility", ctypes.c_void_p),
        ("node_capacity", ctypes.c_uint64),
        ("edge_visibility", ctypes.c_void_p),
        ("edge_capacity", ctypes.c_uint64),
        ("visible_node_ids", ctypes.c_void_p),
        ("visible_node_capacity", ctypes.c_uint64),
        ("visible_edge_ids", ctypes.c_void_p),
        ("visible_edge_capacity", ctypes.c_uint64),
        ("selected_visible_node_ids", ctypes.c_void_p),
        ("selected_visible_node_capacity", ctypes.c_uint64),
        ("selected_visible_edge_ids", ctypes.c_void_p),
        ("selected_visible_edge_capacity", ctypes.c_uint64),
        ("pinned_visible_node_ids", ctypes.c_void_p),
        ("pinned_visible_node_capacity", ctypes.c_uint64),
        ("selected_node_ids", ctypes.c_void_p),
        ("selected_node_capacity", ctypes.c_uint64),
        ("selected_edge_ids", ctypes.c_void_p),
        ("selected_edge_capacity", ctypes.c_uint64),
        ("pinned_node_ids", ctypes.c_void_p),
        ("pinned_node_capacity", ctypes.c_uint64),
    ]


class _DensityEmitMeta(ctypes.Structure):
    _fields_ = [
        ("grid_path", ctypes.c_int32),
        ("bin_window_x0", ctypes.c_double),
        ("bin_window_x1", ctypes.c_double),
        ("bin_window_y0", ctypes.c_double),
        ("bin_window_y1", ctypes.c_double),
        ("full_identity", ctypes.c_uint32),
        ("oversized", ctypes.c_uint32),
        ("pyramid_eligible", ctypes.c_uint32),
        ("pyramid_attempt", ctypes.c_uint32),
        ("pyramid_no_rescan", ctypes.c_uint32),
        ("pyramid_max_upsample", ctypes.c_uint32),
        ("pyramid_tile_upsample", ctypes.c_uint32),
        ("wasm_eligible", ctypes.c_uint32),
        ("needs_pyramid_sample", ctypes.c_uint32),
        ("overlay_omitted", ctypes.c_uint32),
        ("visible_is_n_points", ctypes.c_uint32),
        ("use_raw_range_bin2d", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
    ]


class TemporalNativeError(ValueError):
    """Stable error returned by the Rust-owned temporal column/index seam."""

    _MESSAGES: ClassVar[dict[int, str]] = {
        -1: "temporal arguments are incomplete or inconsistent",
        -2: "temporal input exceeds native capacity",
        -3: "temporal integer conversion overflowed",
        -4: "timezone is required",
        -5: "local time falls in a DST gap",
        -6: "local time is ambiguous at a DST fold",
        -7: "temporal interval is reversed",
        -8: "temporal handle is stale or closed",
        -9: "temporal output buffer is too small",
        -10: "temporal work was cancelled",
        -11: "temporal work exceeds the supplied budget",
        -12: "temporal precision unit is unsupported",
        -13: "temporal resource is disposed",
        -14: "temporal revision is stale",
        -15: "temporal coordination rejected a self-echo",
    }

    def __init__(self, status: int):
        self.status = int(status)
        message = self._MESSAGES.get(
            self.status, f"native temporal failed with status {self.status}"
        )
        super().__init__(message)


class GeoNativeError(ValueError):
    """Stable error returned by the Rust-owned geographic column seam (#47)."""

    _MESSAGES: ClassVar[dict[int, str]] = {
        -1: "geographic descriptor is incomplete or inconsistent",
        -2: "CRS is not in the certified EPSG:4326 / EPSG:3857 profile",
        -3: "geometry kind does not match the supplied offset planes",
        -4: "offset planes are malformed or disagree with vertex counts",
        -5: "nested geometry parts cannot be null",
        -6: "coordinate is non-finite",
        -7: "coordinate is outside the declared CRS bounds",
        -8: "polygon ring is too short or not closed",
        -9: "geometry exceeds feature, vertex, or byte limits",
        -10: "geographic column handle is stale or freed",
    }

    def __init__(self, status: int):
        self.status = int(status)
        message = self._MESSAGES.get(self.status, f"native geo failed with status {self.status}")
        super().__init__(message)


GEO_GEOMETRY_POINT = 1
GEO_GEOMETRY_LINESTRING = 2
GEO_GEOMETRY_POLYGON = 3
GEO_GEOMETRY_MULTIPOINT = 4
GEO_GEOMETRY_MULTILINESTRING = 5
GEO_GEOMETRY_MULTIPOLYGON = 6
GEO_CRS_EPSG_4326 = 4326
GEO_CRS_EPSG_3857 = 3857


TEMPORAL_PRECISION_SECOND = 0
TEMPORAL_PRECISION_MILLISECOND = 1
TEMPORAL_PRECISION_MICROSECOND = 2
TEMPORAL_PRECISION_NANOSECOND = 3
TEMPORAL_DISAMBIGUATION_REJECT = 0
TEMPORAL_DISAMBIGUATION_PREFER_EARLIER = 1
TEMPORAL_DISAMBIGUATION_PREFER_LATER = 2
TEMPORAL_DST_UNIQUE = 0
TEMPORAL_DST_GAP = 1
TEMPORAL_DST_FOLD = 2
TEMPORAL_DIRECTION_REVERSE = -1
TEMPORAL_DIRECTION_FORWARD = 1


# Rust reports invalid arguments (and, via the ffi_guard panic shield, any
# internal panic) by returning `usize::MAX` from size-returning entry points.
# `usize` is `c_size_t`, whose width is platform-dependent — 32 bits on
# armv7/win32/wasm32 — so the sentinel must be derived from ctypes. Comparing
# against 2**64-1 would never match on 32-bit targets and an error return
# would be sliced as data.
_USIZE_MAX = ctypes.c_size_t(-1).value
_FACTORIZE_CAPACITY_EXCEEDED = _USIZE_MAX - 1
# Canonical row ids ship as u32 (the index ceiling the kernels enforce).
_U32_MAX = 2**32 - 1


def _lib_filename() -> str:
    if sys.platform == "win32":
        return "xyg_core.dll"
    if sys.platform == "darwin":
        return "libxyg_core.dylib"
    return "libxyg_core.so"


def _find_library() -> Path:
    name = _lib_filename()
    candidates = []
    env = os.environ.get("XYG_NATIVE_LIB")
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve().parent
    candidates.append(here / "_native_lib" / name)
    # Dev checkout: cargo target dir at the repo root.
    repo_root = here.parent.parent
    candidates.append(repo_root / "target" / "release" / name)
    candidates.append(repo_root / "target" / "debug" / name)
    for c in candidates:
        if c.exists():
            return c
    raise ImportError(
        f"xyg native core not found (looked for {name} in "
        f"{[str(c) for c in candidates]}). No prebuilt wheel exists for this "
        "platform — see the xyg README for supported platforms, or build "
        "from source with `cargo build --release`."
    )


def _load() -> ctypes.CDLL:
    lib = ctypes.CDLL(str(_find_library()))

    # Version is the only declaration bound before compatibility is proven.
    got = bind_abi_version(lib)()
    if got != ABI_VERSION:
        raise ImportError(
            f"xyg native core ABI mismatch: python wrapper expects "
            f"{ABI_VERSION}, library reports {got}. Rebuild with "
            "`cargo build --release` or reinstall xyg so the wheel and "
            "package versions match."
        )

    bind_generated_abi(lib)
    return lib


_lib = _load()


def _as_f64(arr: npt.NDArray[np.float64], label: str = "data") -> npt.NDArray[np.float64]:
    out = np.ascontiguousarray(arr, dtype=np.float64)
    if out.ndim != 1:
        raise ValueError(f"{label} must be 1-D, got shape {out.shape}")
    return out


def _scalar_or_f64(value: npt.NDArray[np.float64] | float, label: str) -> npt.NDArray[np.float64]:
    """Broadcast a Python float or keep a 1-D f64 array.

    ``np.isscalar`` does not narrow ``ndarray | float`` for ty, so the scalar
    vs array split has to be an ``isinstance`` check.
    """
    if isinstance(value, np.ndarray):
        return _as_f64(cast(npt.NDArray[np.float64], value), label)
    return np.asarray([float(value)], dtype=np.float64)


def _as_row_ids(rows: npt.NDArray[np.uint32], label: str = "rows") -> npt.NDArray[np.uint32]:
    """Canonical row ids as contiguous u32, rejecting anything that would wrap.

    `ascontiguousarray(..., dtype=np.uint32)` is an unchecked C cast: an id of
    `2**32 + 3` becomes 3 and a negative id becomes a huge one. The kernels
    bounds-check the ids they are *given*, so a wrapped id is indistinguishable
    from a real one there — the call would answer with a row the caller never
    asked for instead of returning the error sentinel. Range-check before the
    cast so the out-of-range contract holds for the value the caller passed.

    Integer dtypes only, and deliberately so: a float id has no row, and
    deciding one by cast is both silent and platform-dependent. `3.9` would
    become row 3 and `nan` would become row 0 on arm64, where the NaN cast
    saturates, while the same `nan` traps as `INT64_MIN` on x86_64 — the guard
    itself would disagree across the wheels we ship.
    """
    out = np.ascontiguousarray(rows)
    if out.ndim != 1:
        raise ValueError(f"{label} must be 1-D, got shape {out.shape}")
    if out.dtype == np.uint32:
        return out
    if out.size == 0:
        # `np.asarray([])` is float64; selecting no rows is not a dtype error.
        return np.empty(0, dtype=np.uint32)
    if not np.issubdtype(out.dtype, np.integer):
        raise ValueError(f"{label} must be an integer array of row ids, got dtype {out.dtype}")
    widened = out.astype(np.int64, copy=False)
    if widened.min() < 0 or widened.max() > _U32_MAX:
        raise ValueError(f"{label} must be canonical row ids in [0, 2**32)")
    return np.ascontiguousarray(widened, dtype=np.uint32)


def _ptr_f64(arr: npt.NDArray[np.float64]) -> int:
    # Raw address int for a c_void_p parameter: ~2x cheaper per call than
    # `ctypes.data_as(...)`, which allocates a fresh pointer object. The
    # typed wrappers above are the type-safety layer (`_as_f64` etc.), so
    # the C boundary can take the untyped address.
    return arr.ctypes.data


def _ptr_u8(arr: npt.NDArray[np.uint8]) -> int:
    return arr.ctypes.data


def _ptr_u32(arr: npt.NDArray[np.uint32]) -> int:
    return arr.ctypes.data


class _PolarAbiInput(ctypes.Structure):
    """Packed extras pointer/len view so Scene encode stays at Koffi's 64-arg ceiling."""

    _fields_ = (("data", ctypes.c_void_p), ("len", ctypes.c_size_t))


def _fixed_records(values: np.ndarray) -> tuple[np.ndarray, int]:
    records = np.ascontiguousarray(values)
    if records.ndim != 1 or records.dtype.hasobject:
        raise ValueError("factorize_fixed values must be a non-object 1-D array")
    width = int(records.dtype.itemsize)
    if width <= 0:
        raise ValueError("factorize_fixed values must have positive-width records")
    return records, width


def factorize_fixed(
    values: np.ndarray,
) -> tuple[npt.NDArray[np.uint32], npt.NDArray[np.uint32]]:
    """First-seen codes and unique-row indices for fixed-width 1-D values.

    The native kernel compares the complete memory record; label conversion
    and lexical ordering remain with the channel policy layer.
    """
    records, width = _fixed_records(values)
    n = len(records)
    codes = np.empty(n, dtype=np.uint32)
    unique_indices = np.empty(n, dtype=np.uint32)
    if n == 0:
        return codes, unique_indices
    written = _lib.xyg_factorize_fixed(
        records.ctypes.data,
        n,
        width,
        codes.ctypes.data,
        unique_indices.ctypes.data,
    )
    if written == _USIZE_MAX or written > n:
        raise ValueError("native factorize_fixed rejected the record array")
    return codes, unique_indices[:written].copy()


def factorize_fixed_u8(
    values: np.ndarray, max_unique: int = 256
) -> Optional[tuple[npt.NDArray[np.uint8], npt.NDArray[np.uint32]]]:
    """Compact fixed-record factorization, or ``None`` above `max_unique`."""
    max_unique = _bounded_positive_int(max_unique, "max_unique", max_value=256)
    records, width = _fixed_records(values)
    n = len(records)
    codes = np.empty(n, dtype=np.uint8)
    unique_indices = np.empty(min(n, max_unique), dtype=np.uint32)
    if n == 0:
        return codes, unique_indices
    written = _lib.xyg_factorize_fixed_u8(
        records.ctypes.data,
        n,
        width,
        codes.ctypes.data,
        unique_indices.ctypes.data,
        len(unique_indices),
    )
    if written == _FACTORIZE_CAPACITY_EXCEEDED:
        return None
    if written == _USIZE_MAX or written > len(unique_indices):
        raise ValueError("native factorize_fixed_u8 rejected the record array")
    return codes, unique_indices[:written].copy()


def factorize_fixed_u8_counts(
    values: np.ndarray, max_unique: int = 256
) -> Optional[
    tuple[
        npt.NDArray[np.uint8],
        npt.NDArray[np.uint32],
        npt.NDArray[np.uint64],
    ]
]:
    """Compact factorization plus exact counts in first-seen code order."""
    max_unique = _bounded_positive_int(max_unique, "max_unique", max_value=256)
    records, width = _fixed_records(values)
    n = len(records)
    codes = np.empty(n, dtype=np.uint8)
    capacity = min(n, max_unique)
    unique_indices = np.empty(capacity, dtype=np.uint32)
    counts = np.empty(capacity, dtype=np.uint64)
    if n == 0:
        return codes, unique_indices, counts
    written = _lib.xyg_factorize_fixed_u8_counts(
        records.ctypes.data,
        n,
        width,
        codes.ctypes.data,
        unique_indices.ctypes.data,
        counts.ctypes.data,
        capacity,
    )
    if written == _FACTORIZE_CAPACITY_EXCEEDED:
        return None
    if written == _USIZE_MAX or written > capacity:
        raise ValueError("native factorize_fixed_u8_counts rejected the record array")
    return codes, unique_indices[:written].copy(), counts[:written].copy()


def factorize_unicode1_u8_counts(
    values: np.ndarray, max_unique: int = 256
) -> Optional[
    tuple[
        npt.NDArray[np.uint8],
        npt.NDArray[np.uint32],
        npt.NDArray[np.uint64],
    ]
]:
    """Direct-table factorization for one-codepoint NumPy Unicode arrays."""
    max_unique = _bounded_positive_int(max_unique, "max_unique", max_value=256)
    records = np.ascontiguousarray(values)
    if records.ndim != 1 or records.dtype.kind != "U" or records.dtype.itemsize != 4:
        raise ValueError("values must be a one-dimensional Unicode U1 array")
    n = len(records)
    codes = np.empty(n, dtype=np.uint8)
    capacity = min(n, max_unique)
    unique_indices = np.empty(capacity, dtype=np.uint32)
    counts = np.empty(capacity, dtype=np.uint64)
    if n == 0:
        return codes, unique_indices, counts
    native_order = "<" if sys.byteorder == "little" else ">"
    swap_endian = records.dtype.byteorder not in ("=", "|", native_order)
    written = _lib.xyg_factorize_unicode1_u8_counts(
        records.ctypes.data,
        n,
        int(swap_endian),
        codes.ctypes.data,
        unique_indices.ctypes.data,
        counts.ctypes.data,
        capacity,
    )
    if written == _FACTORIZE_CAPACITY_EXCEEDED:
        return None
    if written == _USIZE_MAX or written > capacity:
        raise ValueError("native factorize_unicode1_u8_counts rejected the array")
    return codes, unique_indices[:written].copy(), counts[:written].copy()


def transition_keys_fixed(
    values: np.ndarray, label: str = "animation key"
) -> Optional[npt.NDArray[np.uint32]]:
    """Encode homogeneous fixed-width transition keys in one native row scan.

    The returned ``(N, 2)`` array is Fortran-contiguous: its two ``u32``
    columns are the caller-allocated lo/hi planes written by Rust, so an
    unreordered result ships each plane without another full-size copy.
    Reordering the rows (the line-like geometry sort, or a finite-row
    selection) hands back C-order and restores the usual per-column copy at
    ship time.

    ``None`` asks the policy layer to use its scalar oracle for a value this
    kernel declines (a non-finite float, an invalid Unicode scalar),
    preserving its precise user-facing error. An invalid *argument* is a bug
    here rather than a data property, and raises instead of degrading
    silently into the reference path.
    """
    records = np.asarray(values)
    if records.ndim != 1 or records.dtype.hasobject:
        raise ValueError("transition key values must be a non-object 1-D array")

    kind_name = records.dtype.kind
    width = int(records.dtype.itemsize)
    if kind_name == "U" and width > 0 and width % 4 == 0:
        kind = 0
    elif kind_name == "S" and width > 0:
        kind = 1
    elif kind_name == "b" and width == 1:
        kind = 2
    elif kind_name == "i" and width in (1, 2, 4, 8):
        kind = 3
    elif kind_name == "u" and width in (1, 2, 4, 8):
        kind = 4
    elif kind_name == "f" and width in (2, 4, 8):
        # Python canonicalizes NumPy float16/32 scalars through ``.item()``;
        # widening to f64 is exact and gives the native kernel the same value.
        if width != 8:
            records = records.astype(np.float64)
            width = 8
        kind = 5
    else:
        raise ValueError(
            "transition key values must use Unicode, bytes, bool, integer, or float dtype"
        )

    records = np.ascontiguousarray(records)
    n = len(records)
    result = np.empty((n, 2), dtype=np.uint32, order="F")
    if n == 0:
        return result

    native_order = "<" if sys.byteorder == "little" else ">"
    swap_endian = records.dtype.byteorder not in ("=", "|", native_order)
    error_first = ctypes.c_size_t(_USIZE_MAX)
    error_index = ctypes.c_size_t(_USIZE_MAX)
    status = int(
        _lib.xyg_transition_keys_fixed(
            records.ctypes.data,
            n,
            width,
            kind,
            int(swap_endian),
            result[:, 0].ctypes.data,
            result[:, 1].ctypes.data,
            ctypes.byref(error_first),
            ctypes.byref(error_index),
        )
    )
    if status == 0:
        return result
    if status == 1:
        return None
    if status == 2:
        if error_first.value >= n or error_index.value >= n:
            raise RuntimeError("native transition-key encoder returned invalid row indices")
        raise ValueError(
            f"{label} contains duplicate value at rows {error_first.value} and {error_index.value}"
        )
    if status == 3:
        raise ValueError(f"{label} produced an identity digest collision")
    if status == 4:
        raise RuntimeError(
            "native transition-key encoder rejected the "
            f"{records.dtype.str!r} layout it was handed (kind {kind}, width {width})"
        )
    raise RuntimeError(f"native transition-key encoder returned unknown status {status}")


def remap_u8(values: npt.NDArray[np.uint8], mapping: npt.NDArray[np.uint8]) -> None:
    """Apply a compact categorical codebook permutation in place."""
    values = np.asarray(values)
    mapping = np.ascontiguousarray(mapping, dtype=np.uint8)
    if values.dtype != np.uint8 or values.ndim != 1 or not values.flags.c_contiguous:
        raise ValueError("remap_u8 values must be a contiguous uint8 1-D array")
    if mapping.ndim != 1:
        raise ValueError("remap_u8 mapping must be a 1-D array")
    if len(values) == 0:
        return
    if len(mapping) == 0:
        raise ValueError("remap_u8 mapping must be non-empty")
    ok = _lib.xyg_remap_u8(
        values.ctypes.data,
        len(values),
        mapping.ctypes.data,
        len(mapping),
    )
    if not ok:
        raise ValueError("remap_u8 encountered a code outside the mapping")


def _positive_int(value: int, label: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label} must be a positive integer")
    try:
        out = operator.index(value)
    except TypeError as e:
        raise ValueError(f"{label} must be a positive integer") from e
    if out <= 0:
        raise ValueError(f"{label} must be > 0")
    return int(out)


def _bounded_positive_int(value: int, label: str, max_value: int = MAX_SCREEN_DIM) -> int:
    out = _positive_int(value, label)
    if out > max_value:
        raise ValueError(f"{label} must be <= {max_value}")
    return out


def _bounded_nonnegative_int(value: int, label: str, max_value: int) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label} must be a non-negative integer")
    try:
        out = operator.index(value)
    except TypeError as e:
        raise ValueError(f"{label} must be a non-negative integer") from e
    if out < 0 or out > max_value:
        raise ValueError(f"{label} must be between 0 and {max_value}")
    return int(out)


def _finite_float(value: float, label: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label} must be a finite real number")
    out = float(value)
    if not np.isfinite(out):
        raise ValueError(f"{label} must be finite")
    return out


def _finite_increasing(lo: float, hi: float, label: str) -> tuple[float, float]:
    lo_f = _finite_float(lo, label)
    hi_f = _finite_float(hi, label)
    if not hi_f > lo_f:
        raise ValueError(f"{label} must be finite and increasing")
    return lo_f, hi_f


def _finite_ordered(lo: float, hi: float, label: str) -> tuple[float, float]:
    lo_f = _finite_float(lo, label)
    hi_f = _finite_float(hi, label)
    if hi_f < lo_f:
        raise ValueError(f"{label} must be finite and ordered low-to-high")
    return lo_f, hi_f


def _pyramid_handle(value: int) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("pyramid handle must be an integer handle")
    try:
        out = operator.index(value)
    except TypeError as e:
        raise ValueError("pyramid handle must be an integer handle") from e
    if out < 0:
        raise ValueError("pyramid handle must be non-negative")
    return int(out)


def _pyramid_base_dim(value: int) -> int:
    # Pyramid dims are decoupled from MAX_SCREEN_DIM: a large trace's finest
    # level is far finer than any screen (65536² u32 ≈ 16 GB is the sanity cap).
    out = _bounded_positive_int(value, "base_dim", max_value=1 << 16)
    if out < 2 or out & (out - 1):
        raise ValueError("base_dim must be a power-of-two integer >= 2")
    return out


def zone_maps(
    data: npt.NDArray[np.float64], chunk_size: int = 65_536
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.uint64],
    npt.NDArray[np.uint64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Per-chunk (min, max, count, null_count, sum, sum_sq, positive_min,
    positive_max) — §22."""
    chunk_size = _positive_int(chunk_size, "chunk_size")
    data = _as_f64(data, "data")
    n = len(data)
    n_chunks = max(1, -(-n // chunk_size)) if n else 0
    if n == 0:
        empty_f = np.empty(0, dtype=np.float64)
        empty_u = np.empty(0, dtype=np.uint64)
        return (
            empty_f,
            empty_f,
            empty_u,
            empty_u,
            empty_f.copy(),
            empty_f.copy(),
            empty_f.copy(),
            empty_f.copy(),
        )
    # Two block allocations (6 f64 rows + 2 u64 rows) instead of eight
    # scattered ones: zone maps run on every ingest, and the allocator +
    # `.ctypes` round-trips were a measurable slice of small-chart builds.
    # Row views stay C-contiguous, and both dtypes are 8 bytes wide.
    f64_rows = np.empty((6, n_chunks), dtype=np.float64)
    u64_rows = np.empty((2, n_chunks), dtype=np.uint64)
    f64_ptr = f64_rows.ctypes.data
    u64_ptr = u64_rows.ctypes.data
    row_bytes = n_chunks * 8
    written = _lib.xyg_zone_maps(
        _ptr_f64(data),
        n,
        chunk_size,
        f64_ptr,  # mins
        f64_ptr + row_bytes,  # maxs
        u64_ptr,  # counts
        u64_ptr + row_bytes,  # null counts
        f64_ptr + 2 * row_bytes,  # sums
        f64_ptr + 3 * row_bytes,  # sum_sqs
        f64_ptr + 4 * row_bytes,  # positive_mins
        f64_ptr + 5 * row_bytes,  # positive_maxs
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid zone_maps arguments")
    if written != n_chunks:
        raise RuntimeError(f"xyg native zone_maps wrote {written} chunks, expected {n_chunks}")
    mins, maxs, sums, sum_sqs, positive_mins, positive_maxs = f64_rows
    counts, nulls = u64_rows
    return mins, maxs, counts, nulls, sums, sum_sqs, positive_mins, positive_maxs


_ZONE_MAP_DTYPE = np.dtype(
    [
        ("min", np.float64),
        ("max", np.float64),
        ("positive_min", np.float64),
        ("positive_max", np.float64),
        ("count", np.uint64),
        ("null_count", np.uint64),
        ("sum", np.float64),
        ("sum_sq", np.float64),
    ],
    align=True,
)
if _ZONE_MAP_DTYPE.itemsize != 64:  # pragma: no cover - platform ABI invariant
    raise ImportError("xyg native ZoneMap layout is not 64 bytes on this platform")


def zone_maps_pair(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    chunk_size: int = 65_536,
) -> tuple[tuple[np.ndarray, ...], tuple[np.ndarray, ...]]:
    """Bit-identical zone maps for two equal-length columns in one call."""
    chunk_size = _positive_int(chunk_size, "chunk_size")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    n_chunks = max(1, -(-len(x) // chunk_size)) if len(x) else 0
    x_records = np.empty(n_chunks, dtype=_ZONE_MAP_DTYPE)
    y_records = np.empty(n_chunks, dtype=_ZONE_MAP_DTYPE)
    if len(x):
        written = _lib.xyg_zone_maps_pair(
            x.ctypes.data,
            y.ctypes.data,
            len(x),
            chunk_size,
            x_records.ctypes.data,
            y_records.ctypes.data,
        )
        if written == _USIZE_MAX:
            raise ValueError("invalid zone_maps_pair arguments")
        if written != n_chunks:
            raise RuntimeError(
                f"xyg native zone_maps_pair wrote {written} chunks, expected {n_chunks}"
            )

    def unpack(records: np.ndarray) -> tuple[np.ndarray, ...]:
        return (
            records["min"].copy(),
            records["max"].copy(),
            records["count"].copy(),
            records["null_count"].copy(),
            records["sum"].copy(),
            records["sum_sq"].copy(),
            records["positive_min"].copy(),
            records["positive_max"].copy(),
        )

    return unpack(x_records), unpack(y_records)


def encode_f32(
    data: npt.NDArray[np.float64], offset: float, scale: float = 1.0
) -> npt.NDArray[np.float32]:
    """Relative-f32 encode `(v - offset) * scale` — §4/§16."""
    data = _as_f64(data, "data")
    offset = _finite_float(offset, "offset")
    scale = _finite_float(scale, "scale")
    if len(data) == 0:  # empty NumPy arrays may carry a null pointer
        return np.empty(0, dtype=np.float32)
    out = np.empty(len(data), dtype=np.float32)
    ok = _lib.xyg_encode_f32(_ptr_f64(data), len(data), offset, scale, out.ctypes.data)
    if ok != 1:
        raise RuntimeError("xyg native encode_f32 failed (output undefined)")
    return out


def geometry_offset(pin_zero: bool, lo: float, hi: float) -> float:
    """Precision center for offset-encoded geometry (ABI 208, §4/§16)."""
    out = ctypes.c_double()
    ok = _lib.xyg_geometry_offset(
        int(bool(pin_zero)),
        float(lo),
        float(hi),
        ctypes.byref(out),
    )
    if ok != 1:
        raise RuntimeError("xyg native geometry_offset failed (output undefined)")
    return float(out.value)


def scale_pins_offset(scale: str) -> bool:
    """Whether an axis scale name pins geometry offset to 0 (ABI 216, §16)."""
    encoded = str(scale).encode("utf-8")
    code = int(_lib.xyg_scale_pins_offset(encoded if encoded else 0, len(encoded)))
    if code < 0:
        raise ValueError("invalid scale-pins-offset request")
    return code == 1


def scene_dash_admit(
    text: str | None = None,
    lengths: npt.ArrayLike | None = None,
    *,
    use_lengths: bool = False,
) -> list[float] | None | bool:
    """Scene dash admit via ``xyg_scene_dash_admit`` (ABI 218).

    Returns ``None`` for solid/omitted, ``False`` when unusable, or a 2–8
    length pattern. Empty native pointers are ``0``.
    """
    encoded = b"" if text is None else str(text).encode("utf-8")
    if use_lengths:
        packed = _as_f64(
            np.asarray([] if lengths is None else lengths, dtype=np.float64).reshape(-1),
            "lengths",
        )
    else:
        packed = np.empty(0, dtype=np.float64)
    out = np.empty(8, dtype=np.float64)
    out_n = ctypes.c_size_t(0)
    code = int(
        _lib.xyg_scene_dash_admit(
            encoded if encoded else 0,
            len(encoded),
            _ptr_f64(packed) if len(packed) else 0,
            len(packed),
            int(bool(use_lengths)),
            _ptr_f64(out),
            8,
            ctypes.byref(out_n),
        )
    )
    if code == -2:
        raise ValueError("invalid scene-dash-admit request")
    if code < 0:
        return False
    if code == 0:
        return None
    count = int(out_n.value)
    return [float(value) for value in out[:count]]


def scene_linecap_admit(text: str | None = None) -> int | None | bool:
    """Scene linecap admit via ``xyg_scene_linecap_admit`` (ABI 219).

    Returns ``None`` for round/omitted, ``False`` when unusable, ``0`` for
    butt, or ``2`` for square. Empty native pointers are ``0``.
    """
    encoded = b"" if text is None else str(text).encode("utf-8")
    code = int(_lib.xyg_scene_linecap_admit(encoded if encoded else 0, len(encoded)))
    if code == -2:
        raise ValueError("invalid scene-linecap-admit request")
    if code < 0:
        return False
    if code == 255:
        return None
    return int(code)


def density_overlay_opacity(authored: float = 0.8) -> float:
    """Density overlay sample opacity via ``xyg_density_overlay_opacity`` (ABI 220).

    Finite values are capped at ``0.55``. Non-finite authored opacity becomes
    ``0.55``.
    """
    out = ctypes.c_double()
    ok = _lib.xyg_density_overlay_opacity(float(authored), ctypes.byref(out))
    if ok != 1:
        raise ValueError("invalid density-overlay-opacity request")
    return float(out.value)


def scene_marker_path_admit(
    values: npt.ArrayLike,
    lengths: npt.ArrayLike,
) -> bool:
    """Scene marker-path admit via ``xyg_scene_marker_path_admit`` (ABI 221).

    ``values`` is concatenated x/y pairs; ``lengths`` is the per-contour value
    count. Empty native pointers are ``0``.
    """
    packed = _as_f64(
        np.asarray(values, dtype=np.float64).reshape(-1),
        "values",
    )
    lens = np.ascontiguousarray(
        np.asarray(lengths, dtype=np.uint32).reshape(-1),
        dtype=np.uint32,
    )
    code = int(
        _lib.xyg_scene_marker_path_admit(
            _ptr_f64(packed) if len(packed) else 0,
            len(packed),
            _ptr_u32(lens) if len(lens) else 0,
            len(lens),
        )
    )
    if code == -2:
        raise ValueError("invalid scene-marker-path-admit request")
    return code == 1


def scene_annotation_style_admit(
    kind: str,
    wrapped: bool = False,
    labelled: bool = False,
    key: str = "",
) -> bool:
    """Scene annotation style-key admit via ``xyg_scene_annotation_style_admit`` (ABI 222).

    Empty native pointers are ``0``. Hosts still skip markup/typography/rotation
    and raise error text.
    """
    kind_b = str(kind).encode("utf-8")
    key_b = str(key).encode("utf-8")
    code = int(
        _lib.xyg_scene_annotation_style_admit(
            kind_b if kind_b else 0,
            len(kind_b),
            1 if wrapped else 0,
            1 if labelled else 0,
            key_b if key_b else 0,
            len(key_b),
        )
    )
    if code == -2:
        raise ValueError("invalid scene-annotation-style-admit request")
    return code == 1


_SCENE_RIBBON_COLOR2_NAMES = ("absent", "solid", "gradient", "ends", "fail")


def scene_ribbon_color2_classify(
    has_color2: bool,
    kind_is_ribbon: bool,
    source_css: str | None,
    target_css: str | None,
    source_paint: str,
    has_fill: bool = False,
    has_end_pair: bool = False,
) -> str:
    """Scene ribbon ``color2`` classify via ``xyg_scene_ribbon_color2_classify`` (ABI 223).

    Empty native pointers are ``0``. Hosts still coerce channels and pack end
    RGBA8.
    """
    source_b = b"" if source_css is None else str(source_css).encode("utf-8")
    target_b = b"" if target_css is None else str(target_css).encode("utf-8")
    paint_b = str(source_paint).encode("utf-8")
    code = int(
        _lib.xyg_scene_ribbon_color2_classify(
            1 if has_color2 else 0,
            1 if kind_is_ribbon else 0,
            0 if source_css is None else 1,
            source_b if source_b else 0,
            len(source_b),
            0 if target_css is None else 1,
            target_b if target_b else 0,
            len(target_b),
            paint_b if paint_b else 0,
            len(paint_b),
            1 if has_fill else 0,
            1 if has_end_pair else 0,
        )
    )
    if code == -2:
        raise ValueError("invalid scene-ribbon-color2-classify request")
    if 0 <= code < len(_SCENE_RIBBON_COLOR2_NAMES):
        return _SCENE_RIBBON_COLOR2_NAMES[code]
    return "fail"


def scene_tick_label_strategy(text: str | None = None) -> int:
    """Scene tick-label strategy admit via ``xyg_scene_tick_label_strategy`` (ABI 224).

    Returns ``0`` auto through ``6`` off. Unknown names, including empty text,
    map to ``0``. Empty native pointers are ``0``. Hosts still pick
    ``tick_label_strategy`` vs ``collision`` vs camelCase keys.
    """
    encoded = b"" if text is None else str(text).encode("utf-8")
    code = int(_lib.xyg_scene_tick_label_strategy(encoded if encoded else 0, len(encoded)))
    if code == -2:
        raise ValueError("invalid scene-tick-label-strategy request")
    return int(code)


def scene_tick_anchor(text: str | None = None) -> int | None:
    """Scene tick-label anchor admit via ``xyg_scene_tick_anchor`` (ABI 225).

    Returns ``0`` start, ``1`` center/middle, ``2`` end, or ``None`` when
    unknown. Empty native pointers are ``0``. Hosts still pick
    ``tick_label_anchor`` vs camelCase keys.
    """
    encoded = b"" if text is None else str(text).encode("utf-8")
    code = int(_lib.xyg_scene_tick_anchor(encoded if encoded else 0, len(encoded)))
    if code == -2:
        raise ValueError("invalid scene-tick-anchor request")
    if code < 0:
        return None
    return int(code)


def scene_fill_gradient_admit(
    space: str,
    direction: str,
    t: npt.ArrayLike,
    css: Sequence[str],
    mark_color: str,
) -> list[tuple[int, int, int, int]] | None:
    """Scene fill-gradient admit via ``xyg_scene_fill_gradient_admit`` (ABI 226).

    Returns per-stop RGBA8 or ``None`` when unusable. Empty native pointers are
    ``0``. Hosts still coerce fill mappings; CSS parse is ABI 227.
    """
    space_b = str(space).encode("utf-8")
    dir_b = str(direction).encode("utf-8")
    mark_b = str(mark_color).encode("utf-8")
    packed_t = _as_f64(np.asarray(t, dtype=np.float64).reshape(-1), "t")
    encoded = [str(item).encode("utf-8") for item in css]
    lens = np.asarray([len(item) for item in encoded], dtype=np.uint32)
    css_blob = b"".join(encoded)
    css_arr = (
        np.frombuffer(css_blob, dtype=np.uint8).copy() if css_blob else np.empty(0, dtype=np.uint8)
    )
    n = len(packed_t)
    out = np.empty(n * 4, dtype=np.uint8)
    code = int(
        _lib.xyg_scene_fill_gradient_admit(
            space_b if space_b else 0,
            len(space_b),
            dir_b if dir_b else 0,
            len(dir_b),
            _ptr_f64(packed_t) if n else 0,
            n,
            _ptr_u8(css_arr) if len(css_arr) else 0,
            len(css_arr),
            _ptr_u32(lens) if len(lens) else 0,
            len(lens),
            mark_b if mark_b else 0,
            len(mark_b),
            _ptr_u8(out) if len(out) else 0,
            len(out),
        )
    )
    if code == -2:
        raise ValueError("invalid scene-fill-gradient-admit request")
    if code != 1:
        return None
    return [
        (int(out[i * 4]), int(out[i * 4 + 1]), int(out[i * 4 + 2]), int(out[i * 4 + 3]))
        for i in range(n)
    ]


_SCENE_PARSE_LINEAR_GRADIENT_DIRS = ("down", "up", "right", "left")


def scene_parse_linear_gradient(css: str, space: str = "mark") -> tuple[int, dict[str, Any] | None]:
    """Scene ``linear-gradient(`` CSS parse via ``xyg_scene_parse_linear_gradient`` (ABI 227).

    Returns ``(1, spec)`` or ``(code, None)``. Empty native pointers are ``0``.
    Hosts still coerce fill mappings and raise authoring error text.
    """
    css_b = str(css).encode("utf-8")
    space_b = str(space).encode("utf-8")
    out_dir = ctypes.c_uint8(0)
    out_t = np.empty(8, dtype=np.float64)
    out_css = np.empty(65536, dtype=np.uint8)
    out_lens = np.empty(8, dtype=np.uint32)
    out_n = ctypes.c_size_t(0)
    code = int(
        _lib.xyg_scene_parse_linear_gradient(
            css_b if css_b else 0,
            len(css_b),
            space_b if space_b else 0,
            len(space_b),
            ctypes.byref(out_dir),
            _ptr_f64(out_t),
            len(out_t),
            _ptr_u8(out_css),
            len(out_css),
            _ptr_u32(out_lens),
            len(out_lens),
            ctypes.byref(out_n),
        )
    )
    if code == -2:
        raise ValueError("invalid scene-parse-linear-gradient request")
    if code != 1:
        return int(code), None
    n = int(out_n.value)
    dir_code = int(out_dir.value)
    if not 0 <= dir_code < len(_SCENE_PARSE_LINEAR_GRADIENT_DIRS) or not 2 <= n <= 8:
        return 0, None
    stops: list[list[Any]] = []
    at = 0
    for i in range(n):
        length = int(out_lens[i])
        color = out_css[at : at + length].tobytes().decode("utf-8")
        at += length
        stops.append([float(out_t[i]), color])
    return 1, {
        "space": str(space),
        "dir": _SCENE_PARSE_LINEAR_GRADIENT_DIRS[dir_code],
        "stops": stops,
    }


def f32_safe_scale(offset: float, lo: float, hi: float) -> float:
    """f32-safe encode scale for offset-encoded geometry (ABI 208, §19)."""
    out = ctypes.c_double()
    ok = _lib.xyg_f32_safe_scale(
        float(offset),
        float(lo),
        float(hi),
        ctypes.byref(out),
    )
    if ok != 1:
        raise RuntimeError("xyg native f32_safe_scale failed (output undefined)")
    return float(out.value)


def stacked_bounds(
    values: npt.NDArray[np.float64], baseline: str = "zero"
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Native stacked-series lower/upper bounds for area composition."""
    modes = {"zero": 0, "sym": 1, "wiggle": 2, "weighted_wiggle": 3}
    if baseline not in modes:
        raise ValueError(f"baseline must be one of {tuple(modes)}, got {baseline!r}")
    values = np.ascontiguousarray(values, dtype=np.float64)
    if values.ndim != 2 or min(values.shape) == 0:
        raise ValueError(f"values must be a non-empty 2-D array, got shape {values.shape}")
    lower = np.empty_like(values)
    upper = np.empty_like(values)
    ok = _lib.xyg_stacked_bounds(
        values.ctypes.data,
        values.shape[0],
        values.shape[1],
        modes[baseline],
        lower.ctypes.data,
        upper.ctypes.data,
    )
    if ok != 1:
        raise RuntimeError("xyg native stacked_bounds failed (output undefined)")
    return lower, upper


_BAR_MODE = {"grouped": 0, "stacked": 1, "normalized": 2}
_BAR_ORIENT = {"vertical": 0, "horizontal": 1}


def bar_stack(
    pos: npt.NDArray[np.float64],
    values: npt.NDArray[np.float64],
    width: npt.NDArray[np.float64] | float,
    base: npt.NDArray[np.float64] | float,
    mode: str = "grouped",
    orientation: str = "vertical",
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Grouped / stacked / normalized bar rect corners via ``xyg_bar_stack``.

    ``values`` is row-major ``(n_series, n_items)``. Returns ``(x0, x1, y0, y1)``
    each shaped ``(n_series, n_items)`` in plot axes (orientation applied).
    """
    if mode not in _BAR_MODE:
        raise ValueError(f"mode must be one of {tuple(_BAR_MODE)}, got {mode!r}")
    if orientation not in _BAR_ORIENT:
        raise ValueError(f"orientation must be one of {tuple(_BAR_ORIENT)}, got {orientation!r}")
    pos = _as_f64(pos, "pos")
    values = np.ascontiguousarray(values, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError(f"values must be a 2-D array, got shape {values.shape}")
    n_series, n_items = values.shape
    if len(pos) != n_items:
        raise ValueError(f"pos length {len(pos)} must match values columns {n_items}")
    if n_series == 0 or n_items == 0:
        empty = np.empty((n_series, n_items), dtype=np.float64)
        return empty, empty.copy(), empty.copy(), empty.copy()
    width_arr = _scalar_or_f64(width, "width")
    base_arr = _scalar_or_f64(base, "base")
    out_x0 = np.empty(n_series * n_items, dtype=np.float64)
    out_x1 = np.empty_like(out_x0)
    out_y0 = np.empty_like(out_x0)
    out_y1 = np.empty_like(out_x0)
    ok = _lib.xyg_bar_stack(
        _ptr_f64(pos),
        n_items,
        values.ctypes.data,
        n_series,
        _ptr_f64(width_arr),
        len(width_arr),
        _ptr_f64(base_arr),
        len(base_arr),
        _BAR_MODE[mode],
        _BAR_ORIENT[orientation],
        out_x0.ctypes.data,
        out_x1.ctypes.data,
        out_y0.ctypes.data,
        out_y1.ctypes.data,
    )
    if ok != 1:
        if mode == "normalized" and np.any(values[np.isfinite(values)] < 0):
            raise ValueError(
                "mode='normalized' requires non-negative values; "
                "normalizing mixed-sign stacks is ambiguous"
            )
        raise ValueError("invalid bar_stack arguments")
    shape = (n_series, n_items)
    return (
        out_x0.reshape(shape),
        out_x1.reshape(shape),
        out_y0.reshape(shape),
        out_y1.reshape(shape),
    )


def histogram2d(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    x_edges: npt.NDArray[np.float64],
    y_edges: npt.NDArray[np.float64],
    weights: Optional[npt.NDArray[np.float64]] = None,
) -> npt.NDArray[np.float64]:
    """Native weighted 2-D histogram for arbitrary monotonic bin edges."""
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    x_edges = _as_f64(x_edges, "x_edges")
    y_edges = _as_f64(y_edges, "y_edges")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    if len(x_edges) < 2 or len(y_edges) < 2:
        raise ValueError("x_edges and y_edges must each contain at least two values")
    if weights is not None:
        weights = _as_f64(weights, "weights")
        if len(weights) != len(x):
            raise ValueError("weights must have the same length as x and y")
        weights_ptr = weights.ctypes.data
    else:
        weights_ptr = 0
    out = np.empty((len(x_edges) - 1, len(y_edges) - 1), dtype=np.float64)
    ok = _lib.xyg_histogram2d(
        x.ctypes.data if len(x) else 0,
        y.ctypes.data if len(y) else 0,
        weights_ptr,
        len(x),
        x_edges.ctypes.data,
        len(x_edges),
        y_edges.ctypes.data,
        len(y_edges),
        out.ctypes.data,
    )
    if ok != 1:
        raise ValueError("invalid histogram2d arguments")
    return out


def quad_mesh_triangles(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    values: npt.NDArray[np.float64],
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Expand a rectilinear or curvilinear quad grid into finite triangles."""
    values = np.ascontiguousarray(values, dtype=np.float64)
    if values.ndim != 2 or min(values.shape, default=0) == 0:
        raise ValueError(f"values must be a non-empty 2-D array, got shape {values.shape}")
    rows, cols = values.shape
    x_values = np.ascontiguousarray(x, dtype=np.float64)
    y_values = np.ascontiguousarray(y, dtype=np.float64)
    if x_values.ndim == y_values.ndim == 1:
        if x_values.shape == (cols + 1,) and y_values.shape == (rows + 1,):
            layout = 0
        elif x_values.shape == (cols,) and y_values.shape == (rows,):
            layout = 2
        else:
            raise ValueError(
                "rectilinear coordinates must be cell centers or edges matching values.shape"
            )
    elif x_values.ndim == y_values.ndim == 2:
        if x_values.shape == y_values.shape == (rows + 1, cols + 1):
            layout = 1
        elif x_values.shape == y_values.shape == (rows, cols):
            layout = 3
        else:
            raise ValueError(
                "curvilinear coordinate grids must both match the value centers or cell edges"
            )
    else:
        raise ValueError("x and y must both be 1-D edge vectors or matching 2-D vertex grids")
    x_flat = x_values.reshape(-1)
    y_flat = y_values.reshape(-1)
    capacity = rows * cols * 2
    outputs = [np.empty(capacity, dtype=np.float64) for _ in range(7)]
    written = _lib.xyg_quad_mesh_triangles(
        x_flat.ctypes.data,
        len(x_flat),
        y_flat.ctypes.data,
        len(y_flat),
        values.ctypes.data,
        rows,
        cols,
        layout,
        *(output.ctypes.data for output in outputs),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid quad_mesh_triangles arguments")
    return (
        outputs[0][:written].copy(),
        outputs[1][:written].copy(),
        outputs[2][:written].copy(),
        outputs[3][:written].copy(),
        outputs[4][:written].copy(),
        outputs[5][:written].copy(),
        outputs[6][:written].copy(),
    )


def sector_triangles(
    values: npt.NDArray[np.float64],
    *,
    explode: Optional[npt.NDArray[np.float64]] = None,
    center: tuple[float, float] = (0.0, 0.0),
    radius: float = 1.0,
    inner_radius: float = 0.0,
    start_degrees: float = 0.0,
    counterclockwise: bool = True,
    normalize: bool = True,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Tessellate weighted circular or annular sectors in the native core."""
    weights = _as_f64(values, "values")
    if len(weights) == 0:
        raise ValueError("values must not be empty")
    offsets = None if explode is None else _as_f64(explode, "explode")
    if offsets is not None and len(offsets) != len(weights):
        raise ValueError("explode must have the same length as values")
    center_x = _finite_float(center[0], "center[0]")
    center_y = _finite_float(center[1], "center[1]")
    radius = _finite_float(radius, "radius")
    inner_radius = _finite_float(inner_radius, "inner_radius")
    start_degrees = _finite_float(start_degrees, "start_degrees")
    common = (
        weights.ctypes.data,
        len(weights),
        offsets.ctypes.data if offsets is not None else 0,
        center_x,
        center_y,
        radius,
        inner_radius,
        start_degrees,
        int(bool(counterclockwise)),
        int(bool(normalize)),
    )
    query = _lib.xyg_sector_triangles(*common, 0, 0, 0, 0, 0, 0, 0, 0)
    if query == _USIZE_MAX:
        raise ValueError("invalid sector geometry")
    outputs = [np.empty(query, dtype=np.float64) for _ in range(7)]
    written = _lib.xyg_sector_triangles(
        *common,
        *(output.ctypes.data for output in outputs),
        query,
    )
    if written != query:
        raise RuntimeError("native sector_triangles returned an inconsistent triangle count")
    return tuple(outputs)  # type: ignore[return-value]


def rfft(
    data: npt.NDArray[np.float64], *, nfft: int = 256, sample_rate: float = 2.0
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Windowed real FFT as frequency, real, and imaginary columns."""
    values = _as_f64(data, "data")
    nfft = _bounded_positive_int(nfft, "nfft", max_value=65_536)
    sample_rate = _finite_float(sample_rate, "sample_rate")
    outputs = [np.empty(nfft // 2 + 1, dtype=np.float64) for _ in range(3)]
    ok = _lib.xyg_rfft(
        values.ctypes.data if len(values) else 0,
        len(values),
        nfft,
        sample_rate,
        *(output.ctypes.data for output in outputs),
    )
    if ok != 1:
        raise ValueError("invalid rfft arguments")
    return outputs[0], outputs[1], outputs[2]


def welch_spectra(
    x: npt.NDArray[np.float64],
    y: Optional[npt.NDArray[np.float64]] = None,
    *,
    nfft: int = 256,
    noverlap: int = 0,
    sample_rate: float = 2.0,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Native non-detrended Welch auto and optional complex cross spectra."""
    x_values = _as_f64(x, "x")
    y_values = None if y is None else _as_f64(y, "y")
    if y_values is not None and len(y_values) != len(x_values):
        raise ValueError("x and y must have equal length")
    nfft = _bounded_positive_int(nfft, "nfft", max_value=65_536)
    noverlap = operator.index(noverlap)
    if noverlap < 0 or noverlap >= nfft:
        raise ValueError("noverlap must be non-negative and less than nfft")
    sample_rate = _finite_float(sample_rate, "sample_rate")
    outputs = [np.empty(nfft // 2 + 1, dtype=np.float64) for _ in range(5)]
    ok = _lib.xyg_welch_spectra(
        x_values.ctypes.data if len(x_values) else 0,
        y_values.ctypes.data if y_values is not None else 0,
        len(x_values),
        nfft,
        noverlap,
        sample_rate,
        *(output.ctypes.data for output in outputs),
    )
    if ok != 1:
        raise ValueError("invalid Welch spectrum arguments")
    return outputs[0], outputs[1], outputs[2], outputs[3], outputs[4]


def spectrogram(
    data: npt.NDArray[np.float64],
    *,
    nfft: int = 256,
    noverlap: int = 128,
    sample_rate: float = 2.0,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Native non-detrended time-major Welch spectrogram."""
    values = _as_f64(data, "data")
    nfft = _bounded_positive_int(nfft, "nfft", max_value=65_536)
    noverlap = operator.index(noverlap)
    if noverlap < 0 or noverlap >= nfft:
        raise ValueError("noverlap must be non-negative and less than nfft")
    sample_rate = _finite_float(sample_rate, "sample_rate")
    segments = 1 if len(values) <= nfft else 1 + (len(values) - nfft) // (nfft - noverlap)
    frequency = np.empty(nfft // 2 + 1, dtype=np.float64)
    time = np.empty(segments, dtype=np.float64)
    power = np.empty((segments, len(frequency)), dtype=np.float64)
    ok = _lib.xyg_spectrogram(
        values.ctypes.data if len(values) else 0,
        len(values),
        nfft,
        noverlap,
        sample_rate,
        frequency.ctypes.data,
        time.ctypes.data,
        power.ctypes.data,
    )
    if ok != 1:
        raise ValueError("invalid spectrogram arguments")
    return power, frequency, time


def correlation(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    *,
    max_lags: Optional[int] = None,
    normalize: bool = True,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Native direct lag correlation."""
    x_values = _as_f64(x, "x")
    y_values = _as_f64(y, "y")
    if len(x_values) != len(y_values) or len(x_values) == 0:
        raise ValueError("x and y must have equal non-zero length")
    lag_count = len(x_values) - 1 if max_lags is None else operator.index(max_lags)
    if lag_count < 0 or lag_count >= len(x_values):
        raise ValueError("max_lags must be between 0 and len(x)-1")
    lag = np.empty(2 * lag_count + 1, dtype=np.float64)
    result = np.empty_like(lag)
    ok = _lib.xyg_correlation(
        x_values.ctypes.data,
        y_values.ctypes.data,
        len(x_values),
        lag_count,
        int(bool(normalize)),
        lag.ctypes.data,
        result.ctypes.data,
    )
    if ok != 1:
        raise ValueError("invalid correlation arguments")
    return lag, result


def weighted_ecdf(
    values: npt.NDArray[np.float64], weights: npt.NDArray[np.float64]
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Native weighted sort, duplicate aggregation, and cumulative mass."""
    value_array = _as_f64(values, "values")
    weight_array = _as_f64(weights, "weights")
    if len(value_array) != len(weight_array) or len(value_array) == 0:
        raise ValueError("values and weights must have equal non-zero length")
    output_values = np.empty(len(value_array), dtype=np.float64)
    cumulative = np.empty(len(value_array), dtype=np.float64)
    written = _lib.xyg_weighted_ecdf(
        value_array.ctypes.data,
        weight_array.ctypes.data,
        len(value_array),
        output_values.ctypes.data,
        cumulative.ctypes.data,
    )
    if written == _USIZE_MAX:
        raise ValueError("weighted ECDF requires finite values and nonnegative positive mass")
    return output_values[:written].copy(), cumulative[:written].copy()


def binned_ecdf(
    values: npt.NDArray[np.float64],
    n_bins: int,
    *,
    range: tuple[float, float] | None = None,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Rust-owned finite filtering, uniform binning, and compact ECDF steps."""
    value_array = _as_f64(values, "values")
    if len(value_array) == 0:
        raise ValueError("ecdf values must contain at least one finite value")
    n_bins = _bounded_positive_int(n_bins, "ecdf bins", max_value=10_000)
    if range is None:
        lo = hi = 0.0
        use_range = 0
    else:
        try:
            range_lo, range_hi = range
        except (TypeError, ValueError) as e:
            raise ValueError("ecdf range must contain two finite increasing values") from e
        lo, hi = _finite_increasing(range_lo, range_hi, "ecdf range")
        use_range = 1
    capacity = n_bins + 1
    output_x = np.empty(capacity, dtype=np.float64)
    cumulative = np.empty(capacity, dtype=np.float64)
    written = _lib.xyg_binned_ecdf(
        _ptr_f64(value_array),
        len(value_array),
        n_bins,
        lo,
        hi,
        use_range,
        _ptr_f64(output_x),
        _ptr_f64(cumulative),
        capacity,
    )
    if written == _USIZE_MAX:
        raise ValueError("ecdf values must contain a finite representable distribution")
    return output_x[:written].copy(), cumulative[:written].copy()


def _triangle_inputs(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    triangles: npt.NDArray[np.int64],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.int64]]:
    x_values = _as_f64(x, "x")
    y_values = _as_f64(y, "y")
    if len(x_values) != len(y_values):
        raise ValueError("x and y must have equal length")
    topology = np.ascontiguousarray(triangles, dtype=np.int64)
    if topology.ndim != 2 or topology.shape[1:] != (3,):
        raise ValueError(f"triangles must have shape (n, 3), got {topology.shape}")
    if len(topology) == 0:
        raise ValueError("triangles must contain at least one face")
    return x_values, y_values, topology


def indexed_triangles(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    triangles: npt.NDArray[np.int64],
    values: Optional[npt.NDArray[np.float64]] = None,
    *,
    values_at: str = "auto",
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Expand indexed topology into finite renderer-ready triangles."""
    x_values, y_values, topology = _triangle_inputs(x, y, triangles)
    if values_at not in {"auto", "face", "vertex"}:
        raise ValueError("values_at must be 'auto', 'face', or 'vertex'")
    if values is None:
        scalar = np.empty(0, dtype=np.float64)
        mode = 0
    else:
        scalar = _as_f64(values, "values")
        if values_at == "face" or (values_at == "auto" and len(scalar) == len(topology)):
            mode = 1
            expected = len(topology)
        else:
            mode = 2
            expected = len(x_values)
        if len(scalar) != expected:
            raise ValueError(f"{values_at} values must have length {expected}, got {len(scalar)}")
    outputs = [np.empty(len(topology), dtype=np.float64) for _ in range(7)]
    written = _lib.xyg_indexed_triangles(
        x_values.ctypes.data,
        y_values.ctypes.data,
        len(x_values),
        topology.ctypes.data,
        len(topology),
        scalar.ctypes.data if len(scalar) else 0,
        len(scalar),
        mode,
        *(output.ctypes.data for output in outputs),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid indexed triangle geometry")
    return (
        outputs[0][:written].copy(),
        outputs[1][:written].copy(),
        outputs[2][:written].copy(),
        outputs[3][:written].copy(),
        outputs[4][:written].copy(),
        outputs[5][:written].copy(),
        outputs[6][:written].copy(),
    )


def triangle_edges(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    triangles: npt.NDArray[np.int64],
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Return unique finite edges from indexed triangle topology."""
    x_values, y_values, topology = _triangle_inputs(x, y, triangles)
    capacity = len(topology) * 3
    outputs = [np.empty(capacity, dtype=np.float64) for _ in range(4)]
    written = _lib.xyg_triangle_edges(
        x_values.ctypes.data,
        y_values.ctypes.data,
        len(x_values),
        topology.ctypes.data,
        len(topology),
        *(output.ctypes.data for output in outputs),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid triangle edge geometry")
    copied = [output[:written].copy() for output in outputs]
    return copied[0], copied[1], copied[2], copied[3]


def delaunay_triangles(
    x: npt.NDArray[np.float64], y: npt.NDArray[np.float64]
) -> npt.NDArray[np.int64]:
    """Construct dependency-free native Delaunay topology for 2-D points."""
    x_values = _as_f64(x, "x")
    y_values = _as_f64(y, "y")
    if len(x_values) != len(y_values) or len(x_values) < 3:
        raise ValueError("x and y must have equal length of at least three")
    if len(x_values) > 10_000:
        raise ValueError(
            "native quadratic Delaunay triangulation is limited to 10,000 points; "
            "provide explicit topology for larger inputs"
        )
    # A planar triangulation has at most 2n-5 faces for n>=3.
    capacity = max(1, 2 * len(x_values))
    output = np.empty((capacity, 3), dtype=np.int64)
    written = _lib.xyg_delaunay_triangles(
        x_values.ctypes.data,
        y_values.ctypes.data,
        len(x_values),
        output.ctypes.data,
        capacity,
    )
    if written == _USIZE_MAX:
        raise ValueError("points must include at least three finite, non-collinear locations")
    return output[:written].copy()


def polygon_triangles(
    x: npt.NDArray[np.float64], y: npt.NDArray[np.float64]
) -> npt.NDArray[np.int64]:
    """Triangulate one finite simple polygon with native ear clipping."""
    x_values = _as_f64(x, "x")
    y_values = _as_f64(y, "y")
    if len(x_values) != len(y_values) or len(x_values) < 3:
        raise ValueError("polygon x and y must have equal length of at least three")
    if len(x_values) > 10_000:
        raise ValueError("quadratic polygon triangulation is limited to 10,000 vertices")
    closed = x_values[0] == x_values[-1] and y_values[0] == y_values[-1]
    capacity = len(x_values) - (3 if closed else 2)
    output = np.empty((capacity, 3), dtype=np.int64)
    written = _lib.xyg_polygon_triangles(
        x_values.ctypes.data,
        y_values.ctypes.data,
        len(x_values),
        output.ctypes.data,
        capacity,
    )
    if written == _USIZE_MAX:
        raise ValueError("polygon must be finite, simple, and non-degenerate")
    return output[:written].copy()


def marching_triangles(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    z: npt.NDArray[np.float64],
    triangles: npt.NDArray[np.int64],
    levels: npt.NDArray[np.float64],
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Extract isoline segments from an indexed triangular scalar field."""
    x_values, y_values, topology = _triangle_inputs(x, y, triangles)
    z_values = _as_f64(z, "z")
    level_values = _as_f64(levels, "levels")
    if len(z_values) != len(x_values):
        raise ValueError("z must have the same length as x and y")
    if not np.isfinite(level_values).all():
        raise ValueError("levels must be finite")
    work = len(topology) * len(level_values)
    if work > MAX_CONTOUR_WORK:
        raise ValueError(
            f"marching_triangles faces x levels exceeds the bounded work budget ({MAX_CONTOUR_WORK:,})"
        )
    common = (
        x_values.ctypes.data,
        y_values.ctypes.data,
        z_values.ctypes.data,
        len(x_values),
        topology.ctypes.data,
        len(topology),
        level_values.ctypes.data if len(level_values) else 0,
        len(level_values),
    )
    query = _lib.xyg_marching_triangles(*common, 0, 0, 0, 0, 0, 0)
    if query == _USIZE_MAX:
        raise ValueError("invalid marching triangle geometry")
    outputs = [np.empty(query, dtype=np.float64) for _ in range(5)]
    if query == 0:
        return outputs[0], outputs[1], outputs[2], outputs[3], outputs[4]
    written = _lib.xyg_marching_triangles(
        *common,
        *(output.ctypes.data for output in outputs),
        query,
    )
    if written != query:
        raise RuntimeError("native marching_triangles returned an inconsistent segment count")
    return outputs[0], outputs[1], outputs[2], outputs[3], outputs[4]


def vector_segments(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    u: npt.NDArray[np.float64],
    v: npt.NDArray[np.float64],
    *,
    scale: float = 1.0,
    pivot: str = "tail",
    head_ratio: float = 0.22,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Native vector shafts and arrowheads as four compact segment columns."""
    pivots = {"tail": 0, "mid": 1, "middle": 1, "tip": 2}
    if pivot not in pivots:
        raise ValueError(f"pivot must be one of {tuple(pivots)}, got {pivot!r}")
    scale = _finite_float(scale, "scale")
    head_ratio = _finite_float(head_ratio, "head_ratio")
    if scale <= 0.0 or not 0.0 <= head_ratio <= 1.0:
        raise ValueError("scale must be positive and head_ratio must be between 0 and 1")
    arrays = [_as_f64(values, name) for values, name in ((x, "x"), (y, "y"), (u, "u"), (v, "v"))]
    if len({len(values) for values in arrays}) != 1:
        raise ValueError("x, y, u, and v must have equal length")
    capacity = len(arrays[0]) * 3
    outputs = [np.empty(capacity, dtype=np.float64) for _ in range(4)]
    if capacity == 0:
        return outputs[0], outputs[1], outputs[2], outputs[3]
    written = _lib.xyg_vector_segments(
        *(values.ctypes.data for values in arrays),
        len(arrays[0]),
        scale,
        pivots[pivot],
        head_ratio,
        *(values.ctypes.data for values in outputs),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid vector_segments arguments")
    copied = [values[:written].copy() for values in outputs]
    return copied[0], copied[1], copied[2], copied[3]


def streamlines(
    x_coords: npt.NDArray[np.float64],
    y_coords: npt.NDArray[np.float64],
    u: npt.NDArray[np.float64],
    v: npt.NDArray[np.float64],
    *,
    density: float = 1.0,
    max_steps: int = 2048,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Native bounded streamline integration over a regular vector grid."""
    x_coords = _as_f64(x_coords, "x_coords")
    y_coords = _as_f64(y_coords, "y_coords")
    u = np.ascontiguousarray(u, dtype=np.float64)
    v = np.ascontiguousarray(v, dtype=np.float64)
    expected = (len(y_coords), len(x_coords))
    if u.shape != expected or v.shape != expected:
        raise ValueError(f"u and v must both have shape {expected}")
    density = _finite_float(density, "density")
    max_steps = _bounded_positive_int(max_steps, "max_steps", max_value=100_000)
    query = _lib.xyg_streamlines(
        x_coords.ctypes.data,
        len(x_coords),
        y_coords.ctypes.data,
        len(y_coords),
        u.ctypes.data,
        v.ctypes.data,
        density,
        max_steps,
        0,
        0,
        0,
        0,
        0,
    )
    if query == _USIZE_MAX:
        raise ValueError("invalid streamlines arguments")
    outputs = [np.empty(query, dtype=np.float64) for _ in range(4)]
    if query == 0:
        return outputs[0], outputs[1], outputs[2], outputs[3]
    written = _lib.xyg_streamlines(
        x_coords.ctypes.data,
        len(x_coords),
        y_coords.ctypes.data,
        len(y_coords),
        u.ctypes.data,
        v.ctypes.data,
        density,
        max_steps,
        *(values.ctypes.data for values in outputs),
        query,
    )
    if written != query:
        raise RuntimeError("native streamlines returned an inconsistent segment count")
    return outputs[0], outputs[1], outputs[2], outputs[3]


def m4_indices(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    x0: float,
    x1: float,
    n_buckets: int,
) -> npt.NDArray[np.uint32]:
    """M4 decimation indices over the visible window — §5 Tier 1."""
    n_buckets = _bounded_positive_int(n_buckets, "n_buckets")
    x0, x1 = _finite_increasing(x0, x1, "x range")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    if len(x) == 0:
        return np.empty(0, dtype=np.uint32)
    out = np.empty(n_buckets * 4, dtype=np.uint32)
    written = _lib.xyg_m4_indices(
        _ptr_f64(x),
        _ptr_f64(y),
        len(x),
        x0,
        x1,
        n_buckets,
        out.ctypes.data,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid m4 arguments")
    return out[:written].copy()


def m4_points(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    x0: float,
    x1: float,
    n_buckets: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """M4-decimate an x/y pair without materializing gather indices in Python."""
    n_buckets = _bounded_positive_int(n_buckets, "n_buckets")
    x0, x1 = _finite_increasing(x0, x1, "x range")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    if len(x) == 0:
        empty = np.empty(0, dtype=np.float64)
        return empty, empty.copy()
    out_x = np.empty(n_buckets * 4, dtype=np.float64)
    out_y = np.empty(n_buckets * 4, dtype=np.float64)
    written = _lib.xyg_m4_points(
        _ptr_f64(x),
        _ptr_f64(y),
        len(x),
        x0,
        x1,
        n_buckets,
        _ptr_f64(out_x),
        _ptr_f64(out_y),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid m4 arguments")
    return out_x[:written], out_y[:written]


def svg_poly_path(x: npt.ArrayLike, y: npt.ArrayLike) -> str:
    """Serialize parallel screen coordinates as SVG path data in Rust."""
    xa = np.ascontiguousarray(x, dtype=np.float64).reshape(-1)
    ya = np.ascontiguousarray(y, dtype=np.float64).reshape(-1)
    if len(xa) != len(ya) or len(xa) == 0:
        raise ValueError("x and y must be non-empty and have equal length")
    # Normal chart coordinates fit comfortably. The ABI returns the exact
    # requirement without writing when an adversarial fixed-point value needs
    # more room, so the uncommon retry remains allocation-safe.
    capacity = max(64, len(xa) * 32)
    while True:
        out = ctypes.create_string_buffer(capacity)
        written = _lib.xyg_svg_poly_path(_ptr_f64(xa), _ptr_f64(ya), len(xa), out, capacity)
        if written == _USIZE_MAX:
            raise ValueError("invalid SVG polyline coordinates")
        if written <= capacity:
            return out.raw[:written].decode("ascii")
        capacity = written


def scene_version() -> int:
    """Return the canonical Rust scene-schema version."""
    return int(_lib.xyg_scene_version())


def scene_support_reason(features: int, *, request_version: int = 1) -> str:
    """Return Rust's stable diagnostic for authored Scene feature bits."""
    if (
        isinstance(request_version, bool)
        or not isinstance(request_version, int)
        or not 0 <= request_version <= 0xFFFF_FFFF
    ):
        raise ValueError("scene support request_version must be a u32 integer")
    if (
        isinstance(features, bool)
        or not isinstance(features, int)
        or not 0 <= features <= 0xFFFF_FFFF_FFFF_FFFF
    ):
        raise ValueError("scene support features must be a u64 bit mask")
    required = int(_lib.xyg_scene_support_reason(request_version, features, None, 0))
    if required == _USIZE_MAX:
        raise ValueError("invalid Scene support request version or feature mask")
    if required == 0:
        return ""
    output = ctypes.create_string_buffer(required)
    written = int(_lib.xyg_scene_support_reason(request_version, features, output, required))
    if written != required:
        raise RuntimeError("native Scene support predicate returned an inconsistent length")
    return output.raw.decode("utf-8")


def scene_public_export_reason(payload: bytes) -> str:
    """Return Rust's public-export diagnostic for a packed XYEP envelope."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("scene public export envelope must be bytes")
    array = (
        np.frombuffer(bytes(payload), dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    )
    array = np.ascontiguousarray(array)
    pointer = _ptr_u8(array) if len(array) else 0
    required = int(_lib.xyg_scene_public_export_reason(pointer, len(array), None, 0))
    if required == _USIZE_MAX:
        raise ValueError("invalid scene public export support envelope")
    if required == 0:
        return ""
    output = ctypes.create_string_buffer(required)
    written = int(_lib.xyg_scene_public_export_reason(pointer, len(array), output, required))
    if written != required:
        raise RuntimeError("native Scene public export predicate returned an inconsistent length")
    return output.raw.decode("utf-8")


def scene_pack_public_export(facts: bytes) -> bytes:
    """Pack XYEF v1 public-export facts into the XYEP v1 envelope (M2 #271)."""
    payload = facts if isinstance(facts, (bytes, bytearray, memoryview)) else bytes(facts)
    out = np.zeros(max(256, len(payload) + 64), dtype=np.uint8)
    source = np.frombuffer(payload, dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    code = int(
        _lib.xyg_scene_pack_public_export(
            _ptr_u8(source) if source.size else 0,
            int(source.size),
            _ptr_u8(out),
            len(out),
        )
    )
    if code == -2:
        raise ValueError("invalid scene public export facts version")
    if code < 0:
        raise ValueError("invalid scene public export packing")
    return bytes(out[:code])


def scene_pack_figure_chrome(facts: bytes) -> bytes:
    """Pack XYCF v1 chrome facts into the XYCC v1 encode-ready bundle (M2 #271)."""
    payload = facts if isinstance(facts, (bytes, bytearray, memoryview)) else bytes(facts)
    out = np.zeros(max(65536, len(payload) + 4096), dtype=np.uint8)
    source = np.frombuffer(payload, dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    code = int(
        _lib.xyg_scene_pack_figure_chrome(
            _ptr_u8(source) if source.size else 0,
            int(source.size),
            _ptr_u8(out),
            len(out),
        )
    )
    if code == -2:
        raise ValueError("invalid scene chrome facts version")
    if code == -5:
        raise ValueError("invalid canonical scene plot layout")
    if code == -7:
        raise ValueError(
            "Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content"
        )
    if code == -8:
        raise ValueError("Scene v12 primary legends are static; toggle and highlight must be false")
    if code == -9:
        raise ValueError("Scene v12 does not support legend location")
    if code == -10:
        raise ValueError("legend font sizes must be finite and in [1, 1000]")
    if code == -11:
        raise ValueError(
            "Scene v12 legends support only background, color, font_size, and title_font_size"
        )
    if code == -12:
        raise ValueError("Scene v19 colorbars require literal bounded RGBA stops")
    if code == -13:
        raise ValueError("Scene v19 colorbars require a two-value domain and 2-16 literal stops")
    if code == -14:
        raise ValueError("Scene v19 colorbars support only right or bottom placement")
    if code == -15:
        raise ValueError("scene axis tick lists are limited to 200 values")
    if code < 0:
        raise ValueError("invalid scene chrome packing")
    return bytes(out[:code])


def scene_pack_figure_chrome_from_sidecars(facts: bytes, xysd: bytes) -> bytes:
    """Pack XYCF v1 plus XYSD v1 into the XYCC v1 encode-ready bundle (M2 #271)."""
    payload = facts if isinstance(facts, (bytes, bytearray, memoryview)) else bytes(facts)
    sidecar_payload = xysd if isinstance(xysd, (bytes, bytearray, memoryview)) else bytes(xysd)
    capacity = max(65536, len(payload) + len(sidecar_payload) + 4096)
    source = np.frombuffer(payload, dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    source_xysd = (
        np.frombuffer(sidecar_payload, dtype=np.uint8)
        if sidecar_payload
        else np.empty(0, dtype=np.uint8)
    )
    for _ in range(4):
        out = np.zeros(capacity, dtype=np.uint8)
        code = int(
            _lib.xyg_scene_pack_figure_chrome_from_sidecars(
                _ptr_u8(source) if source.size else 0,
                int(source.size),
                _ptr_u8(source_xysd) if source_xysd.size else 0,
                int(source_xysd.size),
                _ptr_u8(out),
                len(out),
            )
        )
        if code == -4:
            capacity *= 2
            continue
        if code == -2:
            raise ValueError("invalid scene chrome facts version")
        if code == -5:
            raise ValueError("invalid canonical scene plot layout")
        if code == -7:
            raise ValueError(
                "Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content"
            )
        if code == -8:
            raise ValueError(
                "Scene v12 primary legends are static; toggle and highlight must be false"
            )
        if code == -9:
            raise ValueError("Scene v12 does not support legend location")
        if code == -10:
            raise ValueError("legend font sizes must be finite and in [1, 1000]")
        if code == -11:
            raise ValueError(
                "Scene v12 legends support only background, color, font_size, and title_font_size"
            )
        if code == -12:
            raise ValueError("Scene v19 colorbars require literal bounded RGBA stops")
        if code == -13:
            raise ValueError(
                "Scene v19 colorbars require a two-value domain and 2-16 literal stops"
            )
        if code == -14:
            raise ValueError("Scene v19 colorbars support only right or bottom placement")
        if code == -15:
            raise ValueError("scene axis tick lists are limited to 200 values")
        if code < 0:
            raise ValueError("invalid scene chrome packing")
        return bytes(out[:code])
    raise ValueError("invalid scene chrome packing")


class SceneTraceCompileError(ValueError):
    """Native XYTC compile failure carrying the ABI error code and trace index."""

    def __init__(self, code: int, index: int) -> None:
        self.code = int(code)
        self.index = int(index)
        messages = {
            -2: "invalid scene trace compile facts version",
            -5: "trace opacity must be finite and in [0, 1]",
            -12: "trace opacity channels must be finite and in [0, 1]",
        }
        super().__init__(messages.get(self.code, "invalid scene trace compile packing"))


def scene_pack_trace_compile(facts: bytes) -> bytes:
    """Pack XYTC v1 trace-compile facts into the XYTO v1 bundle (M2 #271)."""
    payload = facts if isinstance(facts, (bytes, bytearray, memoryview)) else bytes(facts)
    out = np.zeros(max(65536, len(payload) + 4096), dtype=np.uint8)
    source = np.frombuffer(payload, dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    code = int(
        _lib.xyg_scene_pack_trace_compile(
            _ptr_u8(source) if source.size else 0,
            int(source.size),
            _ptr_u8(out),
            len(out),
        )
    )
    if code < 0:
        index = int(np.frombuffer(bytes(out[:4]), dtype="<u4")[0]) if len(out) >= 4 else 0
        raise SceneTraceCompileError(code, index)
    return bytes(out[:code])


class SceneTraceAttachError(ValueError):
    """Native XYTA attach failure carrying the ABI error code and trace index."""

    def __init__(self, code: int, index: int) -> None:
        self.code = int(code)
        self.index = int(index)
        messages = {
            -2: "invalid scene trace attach facts version",
            -7: "heatmap Scene v12 compilation requires a scalar grid",
            -13: "Scene density columns must have equal length",
            -14: "Scene density mean-color source is invalid",
        }
        super().__init__(messages.get(self.code, "invalid scene trace attach packing"))


def scene_pack_trace_attach(compiled: bytes, attach: bytes) -> bytes:
    """Pack XYTO compile output plus XYTA v1 attach facts into XYTT (M2 #271)."""
    compiled_payload = (
        compiled if isinstance(compiled, (bytes, bytearray, memoryview)) else bytes(compiled)
    )
    attach_payload = attach if isinstance(attach, (bytes, bytearray, memoryview)) else bytes(attach)
    density_plane = 32 + 512 * 384 * 5
    capacity = max(
        65536,
        len(compiled_payload) + len(attach_payload) + density_plane + 4096,
    )
    source_compiled = (
        np.frombuffer(compiled_payload, dtype=np.uint8)
        if compiled_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_attach = (
        np.frombuffer(attach_payload, dtype=np.uint8)
        if attach_payload
        else np.empty(0, dtype=np.uint8)
    )
    for _ in range(4):
        out = np.zeros(capacity, dtype=np.uint8)
        code = int(
            _lib.xyg_scene_pack_trace_attach(
                _ptr_u8(source_compiled) if source_compiled.size else 0,
                int(source_compiled.size),
                _ptr_u8(source_attach) if source_attach.size else 0,
                int(source_attach.size),
                _ptr_u8(out),
                len(out),
            )
        )
        if code == -4:
            capacity *= 2
            continue
        if code < 0:
            index = int(np.frombuffer(bytes(out[:4]), dtype="<u4")[0]) if len(out) >= 4 else 0
            raise SceneTraceAttachError(code, index)
        return bytes(out[:code])
    raise SceneTraceAttachError(-4, 0)


class SceneTraceRowsError(ValueError):
    """Native XYCL row-pack failure carrying the ABI error code and trace index."""

    def __init__(self, code: int, index: int) -> None:
        self.code = int(code)
        self.index = int(index)
        messages = {
            -2: "invalid scene trace column facts version",
            -5: "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates",
            -6: "Scene v12 does not support product kind",
            -7: "invalid scene trace column packing",
        }
        super().__init__(messages.get(self.code, "invalid scene trace column packing"))


def scene_pack_trace_row_bytes(attached: bytes, columns: bytes) -> bytes:
    """Pack XYTT attach output plus XYCL v1 columns into 56-byte Scene rows."""
    attached_payload = (
        attached if isinstance(attached, (bytes, bytearray, memoryview)) else bytes(attached)
    )
    columns_payload = (
        columns if isinstance(columns, (bytes, bytearray, memoryview)) else bytes(columns)
    )
    capacity = max(65536, (len(columns_payload) // 8) * 2 * 56 + 4096)
    source_attached = (
        np.frombuffer(attached_payload, dtype=np.uint8)
        if attached_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_columns = (
        np.frombuffer(columns_payload, dtype=np.uint8)
        if columns_payload
        else np.empty(0, dtype=np.uint8)
    )
    for _ in range(4):
        out = np.zeros(capacity, dtype=np.uint8)
        code = int(
            _lib.xyg_scene_pack_trace_rows(
                _ptr_u8(source_attached) if source_attached.size else 0,
                int(source_attached.size),
                _ptr_u8(source_columns) if source_columns.size else 0,
                int(source_columns.size),
                _ptr_u8(out),
                len(out),
            )
        )
        if code == -4:
            capacity *= 2
            continue
        if code < 0:
            index = int(np.frombuffer(bytes(out[:4]), dtype="<u4")[0]) if len(out) >= 4 else 0
            raise SceneTraceRowsError(code, index)
        return bytes(out[: code * 56])
    raise SceneTraceRowsError(-4, 0)


def scene_pack_trace_rows(
    attached: bytes,
    columns: bytes,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Pack XYTT attach output plus XYCL v1 columns into Scene rows (M2 #271)."""
    payload = scene_pack_trace_row_bytes(attached, columns)
    n_rows = len(payload) // 56
    array = np.frombuffer(payload, dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    return _decode_packed_scene_rows(array, n_rows)


class SceneTraceSidecarsError(ValueError):
    """Native XYSD sidecar-pack failure carrying the ABI error code and trace index."""

    def __init__(self, code: int, index: int) -> None:
        self.code = int(code)
        self.index = int(index)
        messages = {
            -2: "invalid scene sidecar facts version",
            -5: "invalid scene sidecar packing",
            -6: "invalid scene sidecar packing",
        }
        super().__init__(messages.get(self.code, "invalid scene sidecar packing"))


def scene_pack_trace_sidecars(attached: bytes, names: bytes) -> bytes:
    """Pack XYTT attach output plus XYNM v1 names into XYSD sidecars (M2 #271)."""
    attached_payload = (
        attached if isinstance(attached, (bytes, bytearray, memoryview)) else bytes(attached)
    )
    names_payload = names if isinstance(names, (bytes, bytearray, memoryview)) else bytes(names)
    capacity = max(65536, len(attached_payload) + len(names_payload) + 4096)
    source_attached = (
        np.frombuffer(attached_payload, dtype=np.uint8)
        if attached_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_names = (
        np.frombuffer(names_payload, dtype=np.uint8)
        if names_payload
        else np.empty(0, dtype=np.uint8)
    )
    for _ in range(4):
        out = np.zeros(capacity, dtype=np.uint8)
        code = int(
            _lib.xyg_scene_pack_trace_sidecars(
                _ptr_u8(source_attached) if source_attached.size else 0,
                int(source_attached.size),
                _ptr_u8(source_names) if source_names.size else 0,
                int(source_names.size),
                _ptr_u8(out),
                len(out),
            )
        )
        if code == -4:
            capacity *= 2
            continue
        if code < 0:
            index = int(np.frombuffer(bytes(out[:4]), dtype="<u4")[0]) if len(out) >= 4 else 0
            raise SceneTraceSidecarsError(code, index)
        return bytes(out[:code])
    raise SceneTraceSidecarsError(-4, 0)


class SceneStyleSidecarsError(ValueError):
    """Native XYSS style-sidecar pack failure carrying the ABI error code and index."""

    def __init__(self, code: int, index: int) -> None:
        self.code = int(code)
        self.index = int(index)
        messages = {
            -2: "invalid scene style sidecar facts version",
        }
        super().__init__(messages.get(self.code, "invalid scene style sidecar packing"))


def scene_pack_style_sidecars(sidecars: bytes, annotations: bytes) -> bytes:
    """Pack XYSD plus optional XYAO into XYSS v1 (M2 #271)."""
    sidecar_payload = (
        sidecars if isinstance(sidecars, (bytes, bytearray, memoryview)) else bytes(sidecars)
    )
    annotation_payload = (
        annotations
        if isinstance(annotations, (bytes, bytearray, memoryview))
        else bytes(annotations)
    )
    capacity = max(65536, len(sidecar_payload) + len(annotation_payload) + 4096)
    source_sidecars = (
        np.frombuffer(sidecar_payload, dtype=np.uint8)
        if sidecar_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_annotations = (
        np.frombuffer(annotation_payload, dtype=np.uint8)
        if annotation_payload
        else np.empty(0, dtype=np.uint8)
    )
    for _ in range(4):
        out = np.zeros(capacity, dtype=np.uint8)
        code = int(
            _lib.xyg_scene_pack_style_sidecars(
                _ptr_u8(source_sidecars) if source_sidecars.size else 0,
                int(source_sidecars.size),
                _ptr_u8(source_annotations) if source_annotations.size else 0,
                int(source_annotations.size),
                _ptr_u8(out),
                len(out),
            )
        )
        if code == -4:
            capacity *= 2
            continue
        if code < 0:
            index = int(np.frombuffer(bytes(out[:4]), dtype="<u4")[0]) if len(out) >= 4 else 0
            raise SceneStyleSidecarsError(code, index)
        return bytes(out[:code])
    raise SceneStyleSidecarsError(-4, 0)


class SceneAnnotationSpliceError(ValueError):
    """Native XYAS annotation-splice failure carrying the ABI error code and index."""

    def __init__(self, code: int, index: int) -> None:
        self.code = int(code)
        self.index = int(index)
        messages = {
            -2: "invalid scene annotation splice version",
        }
        super().__init__(messages.get(self.code, "invalid scene annotation splice packing"))


def scene_splice_annotations(rows: bytes, sidecars: bytes, annotations: bytes) -> bytes:
    """Pack product rows plus XYSD plus optional XYAO into XYAS v1 (M2 #271)."""
    row_payload = rows if isinstance(rows, (bytes, bytearray, memoryview)) else bytes(rows)
    sidecar_payload = (
        sidecars if isinstance(sidecars, (bytes, bytearray, memoryview)) else bytes(sidecars)
    )
    annotation_payload = (
        annotations
        if isinstance(annotations, (bytes, bytearray, memoryview))
        else bytes(annotations)
    )
    capacity = max(65536, len(row_payload) + len(sidecar_payload) + len(annotation_payload) + 4096)
    source_rows = (
        np.frombuffer(row_payload, dtype=np.uint8) if row_payload else np.empty(0, dtype=np.uint8)
    )
    source_sidecars = (
        np.frombuffer(sidecar_payload, dtype=np.uint8)
        if sidecar_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_annotations = (
        np.frombuffer(annotation_payload, dtype=np.uint8)
        if annotation_payload
        else np.empty(0, dtype=np.uint8)
    )
    for _ in range(4):
        out = np.zeros(capacity, dtype=np.uint8)
        code = int(
            _lib.xyg_scene_splice_annotations(
                _ptr_u8(source_rows) if source_rows.size else 0,
                int(source_rows.size),
                _ptr_u8(source_sidecars) if source_sidecars.size else 0,
                int(source_sidecars.size),
                _ptr_u8(source_annotations) if source_annotations.size else 0,
                int(source_annotations.size),
                _ptr_u8(out),
                len(out),
            )
        )
        if code == -4:
            capacity *= 2
            continue
        if code < 0:
            index = int(np.frombuffer(bytes(out[:4]), dtype="<u4")[0]) if len(out) >= 4 else 0
            raise SceneAnnotationSpliceError(code, index)
        return bytes(out[:code])
    raise SceneAnnotationSpliceError(-4, 0)


class SceneEncodeAssembledError(ValueError):
    """Native assembled-encode failure carrying the ABI error code and index."""

    def __init__(self, code: int, index: int) -> None:
        self.code = int(code)
        self.index = int(index)
        messages = {
            -2: "invalid scene encode assembled version",
        }
        super().__init__(messages.get(self.code, "invalid canonical scene batch"))


def scene_encode_assembled(
    xyas: bytes,
    chrome: bytes,
    extras: bytes,
    *,
    viewport: tuple[float, float],
    x_axis: tuple[int, int, float, float, float, bool],
    y_axis: tuple[int, int, float, float, float, bool],
) -> bytes:
    """Encode packed XYAS plus XYCC plus extras into a Scene v31 batch (M2 #271)."""
    xyas_payload = xyas if isinstance(xyas, (bytes, bytearray, memoryview)) else bytes(xyas)
    chrome_payload = chrome if isinstance(chrome, (bytes, bytearray, memoryview)) else bytes(chrome)
    extras_payload = extras if isinstance(extras, (bytes, bytearray, memoryview)) else bytes(extras)
    if len(viewport) != 2:
        raise ValueError("viewport must contain two values")

    def axis_args(
        axis: tuple[int, int, float, float, float, bool], name: str
    ) -> tuple[int, int, float, float, float, int]:
        if len(axis) != 6:
            raise ValueError(f"{name} must contain six values")
        axis_id, kind, lo, hi, constant, mask = axis
        if isinstance(axis_id, (bool, np.bool_)) or not isinstance(axis_id, (int, np.integer)):
            raise ValueError(f"{name} id must be an unsigned 64-bit integer")
        converted = int(axis_id)
        if converted < 0:
            raise ValueError(f"{name} id must be an unsigned 64-bit integer")
        return (
            converted,
            int(kind),
            float(lo),
            float(hi),
            float(constant),
            1 if mask else 0,
        )

    x_args = axis_args(x_axis, "scene x_axis")
    y_args = axis_args(y_axis, "scene y_axis")
    capacity = max(65536, len(xyas_payload) + len(chrome_payload) + len(extras_payload) + 4096)
    source_xyas = (
        np.frombuffer(xyas_payload, dtype=np.uint8) if xyas_payload else np.empty(0, dtype=np.uint8)
    )
    source_chrome = (
        np.frombuffer(chrome_payload, dtype=np.uint8)
        if chrome_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_extras = (
        np.frombuffer(extras_payload, dtype=np.uint8)
        if extras_payload
        else np.empty(0, dtype=np.uint8)
    )
    for _ in range(4):
        out = np.zeros(capacity, dtype=np.uint8)
        code = int(
            _lib.xyg_scene_encode_assembled(
                _ptr_u8(source_xyas) if source_xyas.size else 0,
                int(source_xyas.size),
                _ptr_u8(source_chrome) if source_chrome.size else 0,
                int(source_chrome.size),
                _ptr_u8(source_extras) if source_extras.size else 0,
                int(source_extras.size),
                float(viewport[0]),
                float(viewport[1]),
                *x_args,
                *y_args,
                _ptr_u8(out),
                len(out),
            )
        )
        if code == -4:
            capacity *= 2
            continue
        if code < 0:
            index = int(np.frombuffer(bytes(out[:4]), dtype="<u4")[0]) if len(out) >= 4 else 0
            raise SceneEncodeAssembledError(code, index)
        return bytes(out[:code])
    raise SceneEncodeAssembledError(-4, 0)


def scene_encode_assembled_from_sidecars(
    *,
    xyas: bytes,
    chrome_facts: bytes,
    sidecars: bytes | None = None,
    polar: bytes | None = None,
    extras_facts: bytes | None = None,
) -> bytes:
    """Encode XYAS from XYCF plus XYSD plus polar plus XYSS (M2 #271)."""
    xyas_payload = xyas if isinstance(xyas, (bytes, bytearray, memoryview)) else bytes(xyas)
    chrome_payload = (
        chrome_facts
        if isinstance(chrome_facts, (bytes, bytearray, memoryview))
        else bytes(chrome_facts)
    )
    sidecar_payload = (
        b""
        if sidecars is None
        else (sidecars if isinstance(sidecars, (bytes, bytearray, memoryview)) else bytes(sidecars))
    )
    polar_payload = (
        b""
        if polar is None
        else (polar if isinstance(polar, (bytes, bytearray, memoryview)) else bytes(polar))
    )
    extras_payload = (
        b""
        if extras_facts is None
        else (
            extras_facts
            if isinstance(extras_facts, (bytes, bytearray, memoryview))
            else bytes(extras_facts)
        )
    )
    capacity = max(
        65536,
        len(xyas_payload)
        + len(chrome_payload)
        + len(sidecar_payload)
        + len(polar_payload)
        + len(extras_payload)
        + 4096,
    )
    source_xyas = (
        np.frombuffer(xyas_payload, dtype=np.uint8) if xyas_payload else np.empty(0, dtype=np.uint8)
    )
    source_chrome = (
        np.frombuffer(chrome_payload, dtype=np.uint8)
        if chrome_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_xysd = (
        np.frombuffer(sidecar_payload, dtype=np.uint8)
        if sidecar_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_polar = (
        np.frombuffer(polar_payload, dtype=np.uint8)
        if polar_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_extras = (
        np.frombuffer(extras_payload, dtype=np.uint8)
        if extras_payload
        else np.empty(0, dtype=np.uint8)
    )
    for _ in range(4):
        out = np.zeros(capacity, dtype=np.uint8)
        code = int(
            _lib.xyg_scene_encode_assembled_from_sidecars(
                _ptr_u8(source_xyas) if source_xyas.size else 0,
                int(source_xyas.size),
                _ptr_u8(source_chrome) if source_chrome.size else 0,
                int(source_chrome.size),
                _ptr_u8(source_xysd) if source_xysd.size else 0,
                int(source_xysd.size),
                _ptr_u8(source_polar) if source_polar.size else 0,
                int(source_polar.size),
                _ptr_u8(source_extras) if source_extras.size else 0,
                int(source_extras.size),
                _ptr_u8(out),
                len(out),
            )
        )
        if code == -4:
            capacity *= 2
            continue
        if code == -2:
            raise ValueError("invalid scene chrome facts version")
        if code == -5:
            raise ValueError("invalid canonical scene plot layout")
        if code == -7:
            raise ValueError(
                "Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content"
            )
        if code == -8:
            raise ValueError(
                "Scene v12 primary legends are static; toggle and highlight must be false"
            )
        if code == -9:
            raise ValueError("Scene v12 does not support legend location")
        if code == -10:
            raise ValueError("legend font sizes must be finite and in [1, 1000]")
        if code == -11:
            raise ValueError(
                "Scene v12 legends support only background, color, font_size, and title_font_size"
            )
        if code == -12:
            raise ValueError("Scene v19 colorbars require literal bounded RGBA stops")
        if code == -13:
            raise ValueError(
                "Scene v19 colorbars require a two-value domain and 2-16 literal stops"
            )
        if code == -14:
            raise ValueError("Scene v19 colorbars support only right or bottom placement")
        if code == -15:
            raise ValueError("scene axis tick lists are limited to 200 values")
        if code == -16:
            index = int(np.frombuffer(bytes(out[:4]), dtype="<u4")[0]) if len(out) >= 4 else 0
            raise SceneEncodeAssembledError(code, index)
        if code == -20:
            raise ValueError("Scene extras polar or paint envelope is invalid")
        if code == -21:
            raise ValueError("Scene style sidecar facts are invalid")
        if code in {-17, -18, -19}:
            raise ValueError("invalid scene extras packing")
        if code < 0:
            raise ValueError("invalid scene chrome packing")
        return bytes(out[:code])
    raise SceneEncodeAssembledError(-4, 0)


class SceneAnnotationFactsError(ValueError):
    """Native XYAF annotation-fact failure from product encode."""


class SceneFigureSupportError(ValueError):
    """Figure-compile support rejection from product encode (ABI 165)."""


_PRODUCT_STAGE_COMPILE = 100
_PRODUCT_STAGE_ATTACH = 200
_PRODUCT_STAGE_SIDECARS = 300
_PRODUCT_STAGE_ROWS = 400
_PRODUCT_STAGE_ANNOTATION = 500
_PRODUCT_STAGE_STYLE = 600
_PRODUCT_STAGE_SPLICE = 700


def _product_stage(code: int) -> tuple[int, int] | None:
    if int(code) >= 0:
        return None
    magnitude = abs(int(code))
    if magnitude < 100:
        return None
    return magnitude // 100, -(magnitude % 100)


def scene_encode_product(
    *,
    compile_facts: bytes,
    attach_facts: bytes,
    names: bytes,
    columns: bytes,
    annotation_facts: bytes | None = None,
    style_ref_base: int,
    x_domain: tuple[float, float],
    y_domain: tuple[float, float],
    chrome_facts: bytes,
    polar: bytes | None = None,
    figure_support: bytes | None = None,
) -> bytes:
    """Encode a product Scene from packed authored blobs (M2 #271)."""
    compile_payload = (
        compile_facts
        if isinstance(compile_facts, (bytes, bytearray, memoryview))
        else bytes(compile_facts)
    )
    attach_payload = (
        attach_facts
        if isinstance(attach_facts, (bytes, bytearray, memoryview))
        else bytes(attach_facts)
    )
    names_payload = names if isinstance(names, (bytes, bytearray, memoryview)) else bytes(names)
    columns_payload = (
        columns if isinstance(columns, (bytes, bytearray, memoryview)) else bytes(columns)
    )
    annotation_payload = (
        b""
        if annotation_facts is None
        else (
            annotation_facts
            if isinstance(annotation_facts, (bytes, bytearray, memoryview))
            else bytes(annotation_facts)
        )
    )
    chrome_payload = (
        chrome_facts
        if isinstance(chrome_facts, (bytes, bytearray, memoryview))
        else bytes(chrome_facts)
    )
    polar_payload = (
        b""
        if polar is None
        else (polar if isinstance(polar, (bytes, bytearray, memoryview)) else bytes(polar))
    )
    support_payload = (
        b""
        if figure_support is None
        else (
            figure_support
            if isinstance(figure_support, (bytes, bytearray, memoryview))
            else bytes(figure_support)
        )
    )
    x0, x1 = (float(value) for value in x_domain)
    y0, y1 = (float(value) for value in y_domain)
    capacity = max(
        65536,
        len(compile_payload)
        + len(attach_payload)
        + len(names_payload)
        + len(columns_payload)
        + len(annotation_payload)
        + len(chrome_payload)
        + len(polar_payload)
        + len(support_payload)
        + 32
        + 512 * 384 * 5
        + 4096,
    )
    source_compile = (
        np.frombuffer(compile_payload, dtype=np.uint8)
        if compile_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_attach = (
        np.frombuffer(attach_payload, dtype=np.uint8)
        if attach_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_names = (
        np.frombuffer(names_payload, dtype=np.uint8)
        if names_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_columns = (
        np.frombuffer(columns_payload, dtype=np.uint8)
        if columns_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_annotations = (
        np.frombuffer(annotation_payload, dtype=np.uint8)
        if annotation_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_chrome = (
        np.frombuffer(chrome_payload, dtype=np.uint8)
        if chrome_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_polar = (
        np.frombuffer(polar_payload, dtype=np.uint8)
        if polar_payload
        else np.empty(0, dtype=np.uint8)
    )
    source_support = (
        np.frombuffer(support_payload, dtype=np.uint8)
        if support_payload
        else np.empty(0, dtype=np.uint8)
    )
    for _ in range(4):
        out = np.zeros(capacity, dtype=np.uint8)
        code = int(
            _lib.xyg_scene_encode_product(
                _ptr_u8(source_compile) if source_compile.size else 0,
                int(source_compile.size),
                _ptr_u8(source_attach) if source_attach.size else 0,
                int(source_attach.size),
                _ptr_u8(source_names) if source_names.size else 0,
                int(source_names.size),
                _ptr_u8(source_columns) if source_columns.size else 0,
                int(source_columns.size),
                _ptr_u8(source_annotations) if source_annotations.size else 0,
                int(source_annotations.size),
                int(style_ref_base),
                x0,
                x1,
                y0,
                y1,
                _ptr_u8(source_chrome) if source_chrome.size else 0,
                int(source_chrome.size),
                _ptr_u8(source_polar) if source_polar.size else 0,
                int(source_polar.size),
                _ptr_u8(source_support) if source_support.size else 0,
                int(source_support.size),
                _ptr_u8(out),
                len(out),
            )
        )
        if code == -4:
            capacity *= 2
            continue
        if code == -801:
            n = int(np.frombuffer(bytes(out[:4]), dtype="<u4")[0]) if len(out) >= 4 else 0
            reason = bytes(out[4 : 4 + n]).decode("utf-8")
            raise SceneFigureSupportError(reason)
        if code == -802:
            raise ValueError("invalid scene figure support envelope")
        index = int(np.frombuffer(bytes(out[:4]), dtype="<u4")[0]) if len(out) >= 4 else 0
        staged = _product_stage(code)
        if staged is not None:
            stage, original = staged
            if stage == _PRODUCT_STAGE_COMPILE // 100:
                raise SceneTraceCompileError(original, index)
            if stage == _PRODUCT_STAGE_ATTACH // 100:
                raise SceneTraceAttachError(original, index)
            if stage == _PRODUCT_STAGE_SIDECARS // 100:
                raise SceneTraceSidecarsError(original, index)
            if stage == _PRODUCT_STAGE_ROWS // 100:
                raise SceneTraceRowsError(original, index)
            if stage == _PRODUCT_STAGE_ANNOTATION // 100:
                messages = {
                    -5: "Scene annotation geometry must be finite",
                    -6: "Scene annotations require nonempty NUL-free text",
                    -7: "Scene v23 label border requires label_background",
                    -3: "Scene annotations are limited to 128 entries",
                }
                raise SceneAnnotationFactsError(
                    messages.get(original, "invalid scene annotation packing")
                )
            if stage == _PRODUCT_STAGE_STYLE // 100:
                raise SceneStyleSidecarsError(original, index)
            if stage == _PRODUCT_STAGE_SPLICE // 100:
                raise SceneAnnotationSpliceError(original, index)
            raise SceneEncodeAssembledError(code, index)
        if code == -2:
            raise ValueError("invalid scene chrome facts version")
        if code == -5:
            raise ValueError("invalid canonical scene plot layout")
        if code == -7:
            raise ValueError(
                "Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content"
            )
        if code == -8:
            raise ValueError(
                "Scene v12 primary legends are static; toggle and highlight must be false"
            )
        if code == -9:
            raise ValueError("Scene v12 does not support legend location")
        if code == -10:
            raise ValueError("legend font sizes must be finite and in [1, 1000]")
        if code == -11:
            raise ValueError(
                "Scene v12 legends support only background, color, font_size, and title_font_size"
            )
        if code == -12:
            raise ValueError("Scene v19 colorbars require literal bounded RGBA stops")
        if code == -13:
            raise ValueError(
                "Scene v19 colorbars require a two-value domain and 2-16 literal stops"
            )
        if code == -14:
            raise ValueError("Scene v19 colorbars support only right or bottom placement")
        if code == -15:
            raise ValueError("scene axis tick lists are limited to 200 values")
        if code == -16:
            raise SceneEncodeAssembledError(code, index)
        if code == -20:
            raise ValueError("Scene extras polar or paint envelope is invalid")
        if code == -21:
            raise ValueError("Scene style sidecar facts are invalid")
        if code in {-17, -18, -19}:
            raise ValueError("invalid scene extras packing")
        if code < 0:
            raise ValueError("invalid scene chrome packing")
        return bytes(out[:code])
    raise SceneEncodeAssembledError(-4, 0)


def scene_figure_support_reason(payload: bytes) -> str:
    """Return Rust's figure-compile diagnostic for a packed XYFS envelope.

    Hosts pack observations, axis ids/keys, and v2 per-trace allowlist flags;
    Rust owns the diagnostic wording and check order.
    """
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("scene figure support envelope must be bytes")
    array = (
        np.frombuffer(bytes(payload), dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    )
    array = np.ascontiguousarray(array)
    pointer = _ptr_u8(array) if len(array) else 0
    required = int(_lib.xyg_scene_figure_support_reason(pointer, len(array), None, 0))
    if required == _USIZE_MAX:
        raise ValueError("invalid scene figure support envelope")
    if required == 0:
        return ""
    output = ctypes.create_string_buffer(required)
    written = int(_lib.xyg_scene_figure_support_reason(pointer, len(array), output, required))
    if written != required:
        raise RuntimeError("native Scene figure support predicate returned an inconsistent length")
    return output.raw.decode("utf-8")


def figure_autorange(payload: bytes) -> tuple[float, float]:
    """Return Rust's product axis range for a packed XYAR envelope."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("figure autorange envelope must be bytes")
    array = (
        np.frombuffer(bytes(payload), dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    )
    array = np.ascontiguousarray(array)
    pointer = _ptr_u8(array) if len(array) else 0
    out_lo = ctypes.c_double()
    out_hi = ctypes.c_double()
    code = int(
        _lib.xyg_figure_autorange(pointer, len(array), ctypes.byref(out_lo), ctypes.byref(out_hi))
    )
    if code == 0:
        return (float(out_lo.value), float(out_hi.value))
    if code == -4:
        raise ValueError("log axis requires at least one positive value")
    raise ValueError("invalid figure autorange envelope")


def auto_domain(bounds: tuple[float, float] | None) -> tuple[float, float]:
    """Expand a possibly-degenerate scalar domain in Rust."""
    out_lo = ctypes.c_double()
    out_hi = ctypes.c_double()
    if bounds is None:
        code = int(_lib.xyg_auto_domain(0, 0.0, 0.0, ctypes.byref(out_lo), ctypes.byref(out_hi)))
    else:
        lo, hi = bounds
        code = int(
            _lib.xyg_auto_domain(
                1, float(lo), float(hi), ctypes.byref(out_lo), ctypes.byref(out_hi)
            )
        )
    if code != 0:
        raise ValueError("native auto_domain rejected the bounds")
    return (float(out_lo.value), float(out_hi.value))


def css_color_rgba(css: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    """Resolve a CSS color to RGBA8 the way Scene and native raster paint do."""
    encoded = str(css).encode("utf-8")
    out = (ctypes.c_uint8 * 4)()
    pointer = encoded if encoded else None
    code = int(_lib.xyg_css_color_rgba(pointer, len(encoded), ctypes.c_float(opacity), out))
    if code != 0:
        raise ValueError("native css_color_rgba rejected the color")
    return (int(out[0]), int(out[1]), int(out[2]), int(out[3]))


def css_is_functional(css: str) -> bool:
    """Unambiguous `#` / `rgb()` / `hsl()` paint syntax (ABI 213)."""
    encoded = str(css).encode("utf-8")
    code = int(_lib.xyg_css_is_functional(encoded if encoded else 0, len(encoded)))
    if code < 0:
        raise ValueError("invalid css-is-functional request")
    return code == 1


def scene_resolve_mark_styles(
    payload: bytes,
) -> list[tuple[tuple[int, int, int, int], tuple[int, int, int, int], float]]:
    """Resolve packed XYMS mark styles to fill/stroke RGBA8 and stroke width."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("mark style envelope must be bytes")
    array = (
        np.frombuffer(bytes(payload), dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    )
    array = np.ascontiguousarray(array)
    if len(array) < 16:
        raise ValueError("invalid mark style envelope")
    n_marks = int(np.frombuffer(bytes(array[8:12]), dtype="<u4")[0])
    out = np.zeros(n_marks * 16, dtype=np.uint8)
    pointer = _ptr_u8(array) if len(array) else 0
    out_ptr = _ptr_u8(out) if len(out) else 0
    code = int(_lib.xyg_scene_resolve_mark_styles(pointer, len(array), out_ptr, len(out)))
    if code < 0:
        raise ValueError("invalid mark style envelope")
    if code != n_marks:
        raise RuntimeError("native mark style resolver returned an inconsistent count")
    resolved: list[tuple[tuple[int, int, int, int], tuple[int, int, int, int], float]] = []
    view = memoryview(out)
    for index in range(n_marks):
        base = index * 16
        fill = (int(view[base]), int(view[base + 1]), int(view[base + 2]), int(view[base + 3]))
        stroke = (
            int(view[base + 4]),
            int(view[base + 5]),
            int(view[base + 6]),
            int(view[base + 7]),
        )
        width = float(np.frombuffer(bytes(view[base + 8 : base + 16]), dtype="<f8")[0])
        resolved.append((fill, stroke, width))
    return resolved


def scene_resolve_chrome_style(payload: bytes) -> bytes:
    """Resolve packed XYCH chrome onto the 200-byte Scene style input."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("chrome style envelope must be bytes")
    array = (
        np.frombuffer(bytes(payload), dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    )
    array = np.ascontiguousarray(array)
    out = np.zeros(200, dtype=np.uint8)
    pointer = _ptr_u8(array) if len(array) else 0
    out_ptr = _ptr_u8(out)
    code = int(_lib.xyg_scene_resolve_chrome_style(pointer, len(array), out_ptr, len(out)))
    if code < 0:
        raise ValueError("invalid chrome style envelope")
    if code != 200:
        raise RuntimeError("native chrome style resolver returned an inconsistent length")
    return bytes(out)


def scene_pack_trace(
    pack_kind: int,
    columns: list[npt.NDArray[np.float64] | None],
    *,
    flags: int = 0,
    step_mode: int = 0,
    symbol: int = 0,
    style_ref: int = 0,
    trace_id: int = 0,
    diameter: float = 0.0,
    extra0: float = 0.0,
    extra1: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Pack one trace's columns into Scene rows (kind/id/coords/expansion)."""
    keep_alive: list[np.ndarray] = []
    lengths: list[int] = []
    pointers: list[int] = []
    padded = list(columns) + [None] * 6
    for column in padded[:6]:
        if column is None:
            keep_alive.append(np.empty(0, dtype=np.float64))
            lengths.append(0)
            pointers.append(0)
            continue
        arr = np.ascontiguousarray(np.asarray(column, dtype=np.float64).reshape(-1))
        keep_alive.append(arr)
        lengths.append(int(arr.size))
        pointers.append(_ptr_f64(arr) if arr.size else 0)
    n0 = lengths[0]
    if pack_kind in {4, 5}:
        n_rows = n0 * 2
    elif pack_kind in {7, 9}:
        n_rows = 2
    else:
        n_rows = n0
    out = np.zeros(max(n_rows, 1) * 56, dtype=np.uint8)
    code = int(
        _lib.xyg_scene_pack_trace(
            int(pack_kind),
            int(flags),
            int(step_mode),
            int(symbol),
            int(style_ref),
            int(trace_id),
            float(diameter),
            float(extra0),
            float(extra1),
            pointers[0],
            lengths[0],
            pointers[1],
            lengths[1],
            pointers[2],
            lengths[2],
            pointers[3],
            lengths[3],
            pointers[4],
            lengths[4],
            pointers[5],
            lengths[5],
            _ptr_u8(out),
            len(out),
        )
    )
    if len(keep_alive) != 6:
        raise RuntimeError("scene pack columns must be six native buffers")
    if code == -5:
        raise ValueError(
            "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
        )
    if code < 0:
        raise ValueError("invalid scene trace packing")
    return _decode_packed_scene_rows(out, code)


def scene_resolve_pack_kind(kind: str, flags: int = 0) -> int:
    """Map an authored product kind plus flags to a compact pack kind."""
    encoded = str(kind).encode("utf-8")
    code = int(
        _lib.xyg_scene_resolve_pack_kind(
            encoded if encoded else 0,
            len(encoded),
            int(flags),
        )
    )
    if code == -6:
        raise ValueError(f"Scene v12 does not support product kind {kind!r}")
    if code < 0:
        raise ValueError("invalid scene product kind")
    return code


def scene_pack_product(
    kind: str,
    columns: list[npt.NDArray[np.float64] | None],
    *,
    flags: int = 0,
    step_mode: int = 0,
    symbol: int = 0,
    style_ref: int = 0,
    trace_id: int = 0,
    diameter: float = 0.0,
    extra0: float = 0.0,
    extra1: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Pack one product-kind trace from the canonical x/y/x0/y0/x1/y1/base envelope."""
    keep_alive: list[np.ndarray] = []
    lengths: list[int] = []
    pointers: list[int] = []
    padded = list(columns) + [None] * 7
    for column in padded[:7]:
        if column is None:
            keep_alive.append(np.empty(0, dtype=np.float64))
            lengths.append(0)
            pointers.append(0)
            continue
        arr = np.ascontiguousarray(np.asarray(column, dtype=np.float64).reshape(-1))
        keep_alive.append(arr)
        lengths.append(int(arr.size))
        pointers.append(_ptr_f64(arr) if arr.size else 0)
    n_rows = max(max(lengths), 1) * 2
    out = np.zeros(max(n_rows, 2) * 56, dtype=np.uint8)
    encoded = str(kind).encode("utf-8")
    code = int(
        _lib.xyg_scene_pack_product(
            encoded if encoded else 0,
            len(encoded),
            int(flags),
            int(step_mode),
            int(symbol),
            int(style_ref),
            int(trace_id),
            float(diameter),
            float(extra0),
            float(extra1),
            pointers[0],
            lengths[0],
            pointers[1],
            lengths[1],
            pointers[2],
            lengths[2],
            pointers[3],
            lengths[3],
            pointers[4],
            lengths[4],
            pointers[5],
            lengths[5],
            pointers[6],
            lengths[6],
            _ptr_u8(out),
            len(out),
        )
    )
    if len(keep_alive) != 7:
        raise RuntimeError("scene product columns must be seven native buffers")
    if code == -5:
        raise ValueError(
            "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
        )
    if code == -6:
        raise ValueError(f"Scene v12 does not support product kind {kind!r}")
    if code < 0:
        raise ValueError("invalid scene trace packing")
    return _decode_packed_scene_rows(out, code)


def scene_pack_product_facts(
    facts: bytes,
    columns: list[npt.NDArray[np.float64] | None],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Pack one product-kind trace from XYPK v1 facts plus canonical columns."""
    keep_alive: list[np.ndarray] = []
    lengths: list[int] = []
    pointers: list[int] = []
    padded = list(columns) + [None] * 7
    for column in padded[:7]:
        if column is None:
            keep_alive.append(np.empty(0, dtype=np.float64))
            lengths.append(0)
            pointers.append(0)
            continue
        arr = np.ascontiguousarray(np.asarray(column, dtype=np.float64).reshape(-1))
        keep_alive.append(arr)
        lengths.append(int(arr.size))
        pointers.append(_ptr_f64(arr) if arr.size else 0)
    n_rows = max(max(lengths), 1) * 2
    out = np.zeros(max(n_rows, 2) * 56, dtype=np.uint8)
    payload = bytes(facts)
    code = int(
        _lib.xyg_scene_pack_product_facts(
            payload if payload else 0,
            len(payload),
            pointers[0],
            lengths[0],
            pointers[1],
            lengths[1],
            pointers[2],
            lengths[2],
            pointers[3],
            lengths[3],
            pointers[4],
            lengths[4],
            pointers[5],
            lengths[5],
            pointers[6],
            lengths[6],
            _ptr_u8(out),
            len(out),
        )
    )
    if len(keep_alive) != 7:
        raise RuntimeError("scene product columns must be seven native buffers")
    if code == -5:
        raise ValueError(
            "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
        )
    if code == -6:
        raise ValueError("Scene v12 does not support product kind")
    if code < 0:
        raise ValueError("invalid scene trace packing")
    return _decode_packed_scene_rows(out, code)


def scene_pack_annotation_marks(
    rows: bytes,
    *,
    x_domain: tuple[float, float],
    y_domain: tuple[float, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Expand packed rule/band/marker scalars into Scene rows.

    Rust owns stable-id tags, domain spanning, and finite rejection (M2 #271).
    """
    payload = rows if isinstance(rows, (bytes, bytearray, memoryview)) else bytes(rows)
    n_in = len(payload) // 40
    out = np.zeros(max(n_in * 2, 1) * 56, dtype=np.uint8)
    source = np.frombuffer(payload, dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    x0, x1 = (float(v) for v in x_domain)
    y0, y1 = (float(v) for v in y_domain)
    code = int(
        _lib.xyg_scene_pack_annotation_marks(
            _ptr_u8(source) if source.size else 0,
            int(source.size),
            x0,
            x1,
            y0,
            y1,
            _ptr_u8(out),
            len(out),
        )
    )
    if code == -5:
        raise ValueError("Scene v12 annotation geometry must be finite")
    if code < 0:
        raise ValueError("invalid scene annotation packing")
    return _decode_packed_scene_rows(out, code)


def _decode_packed_scene_rows(
    out: np.ndarray, code: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    empty_u8 = np.empty(0, dtype=np.uint8)
    empty_u64 = np.empty(0, dtype=np.uint64)
    empty_u32 = np.empty(0, dtype=np.uint32)
    empty_f64 = np.empty(0, dtype=np.float64)
    if code == 0:
        return (
            empty_u8,
            empty_u64,
            empty_u32,
            empty_f64,
            empty_u8,
            empty_u8,
            empty_f64.reshape(4, 0),
        )
    raw = np.frombuffer(out[: code * 56].tobytes(), dtype=np.uint8).reshape(code, 56)
    kinds = np.ascontiguousarray(raw[:, 0])
    symbols = np.ascontiguousarray(raw[:, 1])
    expansion = np.ascontiguousarray(raw[:, 2])
    style_refs = np.ascontiguousarray(np.frombuffer(raw[:, 4:8].tobytes(), dtype="<u4"))
    stable_ids = np.ascontiguousarray(np.frombuffer(raw[:, 8:16].tobytes(), dtype="<u8"))
    nums = np.frombuffer(raw[:, 16:56].tobytes(), dtype="<f8").reshape(-1, 5)
    diameters = np.ascontiguousarray(nums[:, 0])
    coords = np.ascontiguousarray(nums[:, 1:5].T)
    return kinds, stable_ids, style_refs, diameters, symbols, expansion, coords


def scene_pack_annotation_facts(
    facts: bytes,
    *,
    style_ref_base: int,
    x_domain: tuple[float, float],
    y_domain: tuple[float, float],
) -> bytes:
    """Pack XYAF v1 annotation facts into an XYAO envelope (M2 #271)."""
    payload = facts if isinstance(facts, (bytes, bytearray, memoryview)) else bytes(facts)
    extra = 32 + 512 * 56
    out = np.zeros(MAX_SCENE_ANNOTATION_INPUT_BYTES + extra, dtype=np.uint8)
    source = np.frombuffer(payload, dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    x0, x1 = (float(value) for value in x_domain)
    y0, y1 = (float(value) for value in y_domain)
    code = int(
        _lib.xyg_scene_pack_annotation_facts(
            _ptr_u8(source) if source.size else 0,
            int(source.size),
            int(style_ref_base),
            x0,
            x1,
            y0,
            y1,
            _ptr_u8(out),
            len(out),
        )
    )
    if code == -5:
        raise ValueError("Scene annotation geometry must be finite")
    if code == -6:
        raise ValueError("Scene annotations require nonempty NUL-free text")
    if code == -7:
        raise ValueError("Scene v23 label border requires label_background")
    if code == -3:
        raise ValueError("Scene annotations are limited to 128 entries")
    if code < 0:
        raise ValueError("invalid scene annotation packing")
    return bytes(out[:code])


def scene_pack_heatmap_facts(facts: bytes) -> bytes:
    """Pack XYHF v1 heatmap/density facts into one XYHP plane (M2 #271)."""
    payload = facts if isinstance(facts, (bytes, bytearray, memoryview)) else bytes(facts)
    out = np.zeros(max(256, len(payload) + 64), dtype=np.uint8)
    source = np.frombuffer(payload, dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)
    code = int(
        _lib.xyg_scene_pack_heatmap_facts(
            _ptr_u8(source) if source.size else 0,
            int(source.size),
            _ptr_u8(out),
            len(out),
        )
    )
    if code == -5:
        raise ValueError("Scene heatmap or density plane shape is invalid")
    if code == -6:
        raise ValueError("Scene heatmap colormap requires RGB stops")
    if code < 0:
        raise ValueError("invalid scene heatmap packing")
    return bytes(out[:code])


def scene_pack_scene_extras(polar: bytes, paint: bytes, facts: bytes) -> bytes:
    """Pack XYPL/XYHP plus XYSS sidecar facts into extras (M2 #271)."""
    polar_payload = polar if isinstance(polar, (bytes, bytearray, memoryview)) else bytes(polar)
    paint_payload = paint if isinstance(paint, (bytes, bytearray, memoryview)) else bytes(paint)
    facts_payload = facts if isinstance(facts, (bytes, bytearray, memoryview)) else bytes(facts)
    if not polar_payload and not paint_payload and not facts_payload:
        return b""
    out = np.zeros(
        max(256, len(polar_payload) + len(paint_payload) + len(facts_payload) + 64),
        dtype=np.uint8,
    )
    polar_arr = (
        np.frombuffer(polar_payload, dtype=np.uint8)
        if polar_payload
        else np.empty(0, dtype=np.uint8)
    )
    paint_arr = (
        np.frombuffer(paint_payload, dtype=np.uint8)
        if paint_payload
        else np.empty(0, dtype=np.uint8)
    )
    facts_arr = (
        np.frombuffer(facts_payload, dtype=np.uint8)
        if facts_payload
        else np.empty(0, dtype=np.uint8)
    )
    code = int(
        _lib.xyg_scene_pack_scene_extras(
            _ptr_u8(polar_arr) if polar_arr.size else 0,
            int(polar_arr.size),
            _ptr_u8(paint_arr) if paint_arr.size else 0,
            int(paint_arr.size),
            _ptr_u8(facts_arr) if facts_arr.size else 0,
            int(facts_arr.size),
            _ptr_u8(out),
            len(out),
        )
    )
    if code == -5:
        raise ValueError("Scene extras polar or paint envelope is invalid")
    if code == -6:
        raise ValueError("Scene style sidecar facts are invalid")
    if code < 0:
        raise ValueError("invalid scene extras packing")
    return bytes(out[:code])


def scene_pack_scene_extras_from_sidecars(polar: bytes, xysd: bytes, facts: bytes) -> bytes:
    """Pack XYPL plus XYSD planes plus XYSS sidecar facts into extras (M2 #271)."""
    polar_payload = polar if isinstance(polar, (bytes, bytearray, memoryview)) else bytes(polar)
    sidecar_payload = xysd if isinstance(xysd, (bytes, bytearray, memoryview)) else bytes(xysd)
    facts_payload = facts if isinstance(facts, (bytes, bytearray, memoryview)) else bytes(facts)
    if not polar_payload and not sidecar_payload and not facts_payload:
        return b""
    capacity = max(256, len(polar_payload) + len(sidecar_payload) + len(facts_payload) + 64)
    polar_arr = (
        np.frombuffer(polar_payload, dtype=np.uint8)
        if polar_payload
        else np.empty(0, dtype=np.uint8)
    )
    xysd_arr = (
        np.frombuffer(sidecar_payload, dtype=np.uint8)
        if sidecar_payload
        else np.empty(0, dtype=np.uint8)
    )
    facts_arr = (
        np.frombuffer(facts_payload, dtype=np.uint8)
        if facts_payload
        else np.empty(0, dtype=np.uint8)
    )
    for _ in range(4):
        out = np.zeros(capacity, dtype=np.uint8)
        code = int(
            _lib.xyg_scene_pack_scene_extras_from_sidecars(
                _ptr_u8(polar_arr) if polar_arr.size else 0,
                int(polar_arr.size),
                _ptr_u8(xysd_arr) if xysd_arr.size else 0,
                int(xysd_arr.size),
                _ptr_u8(facts_arr) if facts_arr.size else 0,
                int(facts_arr.size),
                _ptr_u8(out),
                len(out),
            )
        )
        if code == -4:
            capacity *= 2
            continue
        if code == -5:
            raise ValueError("Scene extras polar or paint envelope is invalid")
        if code == -6:
            raise ValueError("Scene style sidecar facts are invalid")
        if code < 0:
            raise ValueError("invalid scene extras packing")
        return bytes(out[:code])
    raise ValueError("invalid scene extras packing")


def scene_pack_density_grid(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    *,
    idx: "npt.NDArray[np.uint8] | None" = None,
    rgba: "npt.NDArray[np.uint8] | None" = None,
    lut: "npt.NDArray[np.uint8] | None" = None,
) -> tuple[np.ndarray, float, np.ndarray | None, int, int] | None:
    """Pack Scene density log-u8 (and optional mean RGBA) as XYDE (M2 #271)."""
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    idx_ptr = rgba_ptr = lut_ptr = 0
    lut_len = 0
    keepalive: tuple = ()
    if idx is not None or rgba is not None:
        idx_ptr, rgba_ptr, lut_ptr, lut_len, keepalive = _color_source_args(len(x), idx, rgba, lut)
        idx_ptr = int(idx_ptr or 0)
        rgba_ptr = int(rgba_ptr or 0)
        lut_ptr = int(lut_ptr or 0)
    out = np.zeros(32 + 512 * 384 * 5, dtype=np.uint8)
    code = int(
        _lib.xyg_scene_pack_density_grid(
            _ptr_f64(x) if len(x) else 0,
            _ptr_f64(y) if len(y) else 0,
            len(x),
            float(x0),
            float(x1),
            float(y0),
            float(y1),
            idx_ptr,
            rgba_ptr,
            lut_ptr,
            int(lut_len),
            _ptr_u8(out),
            len(out),
        )
    )
    _ = keepalive
    if code == -5:
        raise ValueError("Scene density columns must have equal length")
    if code == -6:
        raise ValueError("Scene density mean-color source is invalid")
    if code < 0:
        raise ValueError("invalid scene density packing")
    if code == 0:
        return None
    blob = bytes(out[:code])
    if blob[:4] != b"XYDE" or len(blob) < 32:
        raise ValueError("invalid scene density packing")
    cols = int.from_bytes(blob[8:12], "little")
    rows = int.from_bytes(blob[12:16], "little")
    flags = int.from_bytes(blob[16:20], "little")
    gmax = struct.unpack_from("<d", blob, 24)[0]
    cells = rows * cols
    encoded = np.frombuffer(blob, dtype=np.uint8, offset=32, count=cells).copy()
    mean: np.ndarray | None = None
    if flags & 1:
        mean = np.frombuffer(blob, dtype=np.uint8, offset=32 + cells, count=cells * 4).copy()
    return encoded, float(gmax), mean, int(rows), int(cols)


def scene_pack_legend(
    *,
    loc: int,
    flags: int,
    font_size: float,
    title_font_size: float,
    text_rgba: bytes,
    frame_fill_rgba: bytes,
    title: bytes,
    entry_meta: bytes,
    label_lens: list[int],
    labels: bytes,
) -> bytes:
    """Frame a primary Scene legend as XYLG bytes."""
    title_arr = np.frombuffer(title, dtype=np.uint8) if title else np.empty(0, dtype=np.uint8)
    meta_arr = (
        np.frombuffer(entry_meta, dtype=np.uint8) if entry_meta else np.empty(0, dtype=np.uint8)
    )
    label_arr = np.frombuffer(labels, dtype=np.uint8) if labels else np.empty(0, dtype=np.uint8)
    lens_arr = np.ascontiguousarray(np.asarray(label_lens, dtype="<u4"))
    color_arr = np.frombuffer(bytes(text_rgba), dtype=np.uint8)
    fill_arr = np.frombuffer(bytes(frame_fill_rgba), dtype=np.uint8)
    if len(color_arr) != 4 or len(fill_arr) != 4:
        raise ValueError("legend paints must be RGBA8")
    n_entries = int(len(label_lens))
    out = np.zeros(MAX_SCENE_LEGEND_INPUT_BYTES, dtype=np.uint8)
    code = int(
        _lib.xyg_scene_pack_legend(
            int(loc),
            int(flags),
            float(font_size),
            float(title_font_size),
            _ptr_u8(color_arr),
            _ptr_u8(fill_arr),
            _ptr_u8(title_arr) if len(title_arr) else 0,
            len(title_arr),
            n_entries,
            _ptr_u8(meta_arr) if len(meta_arr) else 0,
            len(meta_arr),
            lens_arr.ctypes.data if n_entries else 0,
            _ptr_u8(label_arr) if len(label_arr) else 0,
            len(label_arr),
            _ptr_u8(out),
            len(out),
        )
    )
    if code == -5:
        raise ValueError("legend font sizes must be finite and in [1, 1000]")
    if code == -6:
        raise ValueError("Scene v12 does not support legend location")
    if code == -3:
        raise ValueError("Scene v12 legend text is limited to 16,384 UTF-8 bytes")
    if code < 0:
        raise ValueError("invalid scene legend packing")
    return bytes(out[:code])


def scene_pack_colorbar(
    *,
    flags: int,
    lo: float,
    hi: float,
    text_rgba: bytes,
    title: bytes,
    stop_values: npt.NDArray[np.float64] | list[float],
    stop_rgba: bytes,
    ticks: npt.NDArray[np.float64] | list[float],
) -> bytes:
    """Frame a primary Scene colorbar as XYCB v2 bytes."""
    title_arr = np.frombuffer(title, dtype=np.uint8) if title else np.empty(0, dtype=np.uint8)
    color_arr = np.frombuffer(bytes(text_rgba), dtype=np.uint8)
    values = np.ascontiguousarray(np.asarray(stop_values, dtype=np.float64).reshape(-1))
    rgba_arr = np.frombuffer(bytes(stop_rgba), dtype=np.uint8)
    tick_arr = np.ascontiguousarray(np.asarray(ticks, dtype=np.float64).reshape(-1))
    if len(color_arr) != 4:
        raise ValueError("colorbar text_rgba must be RGBA8")
    out = np.zeros(MAX_SCENE_COLORBAR_INPUT_BYTES, dtype=np.uint8)
    code = int(
        _lib.xyg_scene_pack_colorbar(
            int(flags),
            float(lo),
            float(hi),
            _ptr_u8(color_arr),
            _ptr_u8(title_arr) if len(title_arr) else 0,
            len(title_arr),
            int(values.size),
            _ptr_f64(values) if values.size else 0,
            _ptr_u8(rgba_arr) if len(rgba_arr) else 0,
            len(rgba_arr),
            int(tick_arr.size),
            _ptr_f64(tick_arr) if tick_arr.size else 0,
            _ptr_u8(out),
            len(out),
        )
    )
    if code == -5:
        raise ValueError(
            "Scene v19 colorbar values must be finite and RGBA literals exactly four bytes"
        )
    if code == -6:
        raise ValueError(
            "Scene v19 colorbar stops must be strictly increasing and match the domain endpoints"
        )
    if code == -7:
        raise ValueError("Scene v19 colorbar ticks are limited to 32 finite ordered values")
    if code == -3:
        raise ValueError("Scene v19 colorbar ticks are limited to 32 finite ordered values")
    if code < 0:
        raise ValueError("invalid scene colorbar packing")
    return bytes(out[:code])


def scene_pack_annotations(
    *,
    text_meta: bytes,
    text_lens: list[int],
    texts: bytes,
    attached_meta: bytes,
    attached_lens: list[int],
    attached_texts: bytes,
    arrow_meta: bytes,
    callout_meta: bytes,
    callout_lens: list[int],
    callout_texts: bytes,
    wrapped_meta: bytes,
    wrapped_lens: list[int],
    wrapped_texts: bytes,
) -> bytes:
    """Frame primary Scene annotations as XYAD bytes."""

    def as_u8(payload: bytes) -> npt.NDArray[np.uint8]:
        return np.frombuffer(payload, dtype=np.uint8) if payload else np.empty(0, dtype=np.uint8)

    def as_u32(values: list[int]) -> npt.NDArray[np.uint32]:
        return np.ascontiguousarray(np.asarray(values, dtype="<u4"))

    text_meta_arr = as_u8(text_meta)
    texts_arr = as_u8(texts)
    text_lens_arr = as_u32(text_lens)
    attached_meta_arr = as_u8(attached_meta)
    attached_texts_arr = as_u8(attached_texts)
    attached_lens_arr = as_u32(attached_lens)
    arrow_meta_arr = as_u8(arrow_meta)
    callout_meta_arr = as_u8(callout_meta)
    callout_texts_arr = as_u8(callout_texts)
    callout_lens_arr = as_u32(callout_lens)
    wrapped_meta_arr = as_u8(wrapped_meta)
    wrapped_texts_arr = as_u8(wrapped_texts)
    wrapped_lens_arr = as_u32(wrapped_lens)
    out = np.zeros(MAX_SCENE_ANNOTATION_INPUT_BYTES, dtype=np.uint8)
    code = int(
        _lib.xyg_scene_pack_annotations(
            len(text_lens),
            _ptr_u8(text_meta_arr) if len(text_meta_arr) else 0,
            len(text_meta_arr),
            text_lens_arr.ctypes.data if len(text_lens) else 0,
            _ptr_u8(texts_arr) if len(texts_arr) else 0,
            len(texts_arr),
            len(attached_lens),
            _ptr_u8(attached_meta_arr) if len(attached_meta_arr) else 0,
            len(attached_meta_arr),
            attached_lens_arr.ctypes.data if len(attached_lens) else 0,
            _ptr_u8(attached_texts_arr) if len(attached_texts_arr) else 0,
            len(attached_texts_arr),
            len(arrow_meta) // 60,
            _ptr_u8(arrow_meta_arr) if len(arrow_meta_arr) else 0,
            len(arrow_meta_arr),
            len(callout_lens),
            _ptr_u8(callout_meta_arr) if len(callout_meta_arr) else 0,
            len(callout_meta_arr),
            callout_lens_arr.ctypes.data if len(callout_lens) else 0,
            _ptr_u8(callout_texts_arr) if len(callout_texts_arr) else 0,
            len(callout_texts_arr),
            len(wrapped_lens),
            _ptr_u8(wrapped_meta_arr) if len(wrapped_meta_arr) else 0,
            len(wrapped_meta_arr),
            wrapped_lens_arr.ctypes.data if len(wrapped_lens) else 0,
            _ptr_u8(wrapped_texts_arr) if len(wrapped_texts_arr) else 0,
            len(wrapped_texts_arr),
            _ptr_u8(out),
            len(out),
        )
    )
    if code == -5:
        raise ValueError("Scene annotation geometry must be finite")
    if code == -6:
        raise ValueError("Scene annotations require nonempty NUL-free text")
    if code == -7:
        raise ValueError("Scene v23 label border requires label_background")
    if code == -3:
        raise ValueError("Scene annotations are limited to 128 entries")
    if code < 0:
        raise ValueError("invalid scene annotation packing")
    return bytes(out[:code])


def rect_zero_baseline_flags(base: npt.NDArray[np.float64], value: npt.NDArray[np.float64]) -> int:
    """Pack rectangle zero-baseline predicates for an XYAR trace row."""
    base_arr = np.ascontiguousarray(np.asarray(base, dtype=np.float64))
    value_arr = np.ascontiguousarray(np.asarray(value, dtype=np.float64))
    if len(base_arr) != len(value_arr):
        return 0xFF
    n = len(base_arr)
    return int(
        _lib.xyg_rect_zero_baseline_flags(
            _ptr_f64(base_arr) if n else 0,
            _ptr_f64(value_arr) if n else 0,
            n,
        )
    )


def scene_axis_ticks(
    kind: int,
    lo: float,
    hi: float,
    target: int,
    aux: float = 0.0,
) -> tuple[list[float], list[float], float]:
    """Build bounded canonical axis ticks in Rust.

    ``kind`` is ``0`` linear, ``1`` log, ``2`` category (``aux`` = category
    count), ``3`` angular degrees, ``4`` angular radians, or ``5`` time
    (UTC milliseconds since epoch; calendar steps for long spans), or ``6``
    symmetric log (``aux`` = positive linear-region constant).
    """
    # Calendar time ladders can emit up to ~1000 first-of-month ticks.
    capacity = 1000 if kind == 5 else 200
    ticks = np.empty(capacity, dtype=np.float64)
    labeled = np.empty(capacity, dtype=np.float64)
    labeled_len = ctypes.c_size_t()
    step = ctypes.c_double()
    written = _lib.xyg_scene_axis_ticks(
        kind,
        lo,
        hi,
        target,
        float(aux),
        _ptr_f64(ticks),
        _ptr_f64(labeled),
        ctypes.byref(labeled_len),
        ctypes.byref(step),
        capacity,
    )
    if written == _USIZE_MAX or written > capacity or labeled_len.value > written:
        raise ValueError("invalid canonical axis tick request")
    return ticks[:written].tolist(), labeled[: labeled_len.value].tolist(), step.value


_TICK_LAYOUT_KIND = {
    "auto": 0,
    "hide": 1,
    "rotate": 2,
    "stagger": 3,
    "preserve": 4,
    "none": 5,
    "off": 6,
}
_TICK_LAYOUT_SIDE = {"bottom": 0, "top": 1, "left": 2, "right": 3}
_TICK_LAYOUT_ANCHOR = {"start": 0, "center": 1, "end": 2}


def _tick_layout_enum(value: str | int, mapping: dict[str, int], name: str) -> int:
    if isinstance(value, str):
        key = value.strip().lower().replace("-", "_")
        if key not in mapping:
            raise ValueError(f"{name} must be one of {sorted(mapping)}")
        return mapping[key]
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral):
        raise ValueError(f"{name} must be a string or integer code")
    return int(value)


def scene_tick_label_layout(
    positions: npt.ArrayLike,
    labels: Sequence[str],
    *,
    kind: str | int = "auto",
    side: str | int = "bottom",
    anchor: str | int = "center",
    is_x: bool = True,
    category: bool = False,
    font_size: float = 11.0,
    min_gap: float = 8.0,
    explicit_angle: float | None = None,
) -> list[dict[str, Any]]:
    """Tick-label collision layout via ``xyg_scene_tick_label_layout`` (ABI 123).

    Hosts format label strings and map tick values to pixels. Rust owns auto /
    hide / rotate / stagger thinning. ``explicit_angle`` is ``None`` or NaN when
    unset.
    """
    pos = _as_f64(np.asarray(positions, dtype=np.float64).reshape(-1), "positions")
    texts = [str(label) for label in labels]
    if len(pos) != len(texts):
        raise ValueError("positions and labels must have the same length")
    encoded = [text.encode("utf-8") for text in texts]
    lens = np.asarray([len(item) for item in encoded], dtype=np.uint32)
    packed = (
        np.frombuffer(b"".join(encoded), dtype=np.uint8).copy()
        if encoded
        else np.empty(0, dtype=np.uint8)
    )
    n = len(pos)
    out_index = np.empty(n, dtype=np.uint32)
    out_angle = np.empty(n, dtype=np.float64)
    out_row = np.empty(n, dtype=np.uint32)
    angle = float("nan") if explicit_angle is None else float(explicit_angle)
    flags = (1 if is_x else 0) | (2 if category else 0)
    written = _lib.xyg_scene_tick_label_layout(
        _ptr_f64(pos) if n else 0,
        n,
        lens.ctypes.data if n else 0,
        _ptr_u8(packed) if len(packed) else 0,
        len(packed),
        _tick_layout_enum(kind, _TICK_LAYOUT_KIND, "kind"),
        _tick_layout_enum(side, _TICK_LAYOUT_SIDE, "side"),
        _tick_layout_enum(anchor, _TICK_LAYOUT_ANCHOR, "anchor"),
        flags,
        float(font_size),
        float(min_gap),
        angle,
        out_index.ctypes.data if n else 0,
        _ptr_f64(out_angle) if n else 0,
        out_row.ctypes.data if n else 0,
        n,
    )
    if written == _USIZE_MAX or written > n:
        raise ValueError("invalid tick-label layout request")
    return [
        {
            "index": int(out_index[i]),
            "angle": float(out_angle[i]),
            "row": int(out_row[i]),
        }
        for i in range(written)
    ]


def _tick_window_theta_unit(theta_unit: object) -> int:
    if theta_unit is None:
        return 0
    return 1 if theta_unit == "degrees" else 2


def tick_window(
    range_lo: float,
    range_hi: float,
    *,
    theta_unit: str | None = None,
    kind: str = "linear",
    n_categories: int = 0,
    sector_lo: float = float("nan"),
    sector_hi: float = float("nan"),
) -> tuple[float, float]:
    """Authored tick-window resolve via ``xyg_tick_window`` (ABI 128)."""
    out_lo = ctypes.c_double()
    out_hi = ctypes.c_double()
    written = _lib.xyg_tick_window(
        float(range_lo),
        float(range_hi),
        _tick_window_theta_unit(theta_unit),
        1 if kind == "category" else 0,
        int(n_categories),
        float(sector_lo),
        float(sector_hi),
        ctypes.byref(out_lo),
        ctypes.byref(out_hi),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid tick-window request")
    return float(out_lo.value), float(out_hi.value)


def tick_window_filter(
    values: npt.ArrayLike,
    lo: float,
    hi: float,
    *,
    theta_unit: str | None = None,
    kind: str = "linear",
    require_finite: bool = False,
) -> list[float]:
    """Authored tick-window filter via ``xyg_tick_window_filter`` (ABI 128)."""
    arr = _as_f64(np.asarray(values, dtype=np.float64).reshape(-1), "values")
    n = len(arr)
    out = np.empty(n, dtype=np.float64)
    written = _lib.xyg_tick_window_filter(
        _ptr_f64(arr) if n else 0,
        n,
        float(lo),
        float(hi),
        _tick_window_theta_unit(theta_unit),
        1 if kind == "category" else 0,
        1 if require_finite else 0,
        _ptr_f64(out) if n else 0,
        n,
    )
    if written == _USIZE_MAX or written > n:
        raise ValueError("invalid tick-window filter request")
    return out[:written].tolist()


def _tick_format_kind(axis_kind: str | None) -> int:
    if axis_kind == "category":
        return 2
    if axis_kind == "time":
        return 1
    return 0


def tick_format(
    value: float,
    step: float,
    *,
    kind: str | None = "linear",
    scale: str | None = None,
    theta_unit: str | None = None,
    format: str | None = None,
    categories: Sequence[str] | None = None,
) -> str:
    """Cartesian compatibility tick-label formatting via ``xyg_tick_format`` (ABI 130)."""
    cats = [str(item) for item in categories or ()]
    lens = (ctypes.c_uint32 * len(cats))(*[len(item.encode("utf-8")) for item in cats])
    packed = b"".join(item.encode("utf-8") for item in cats)
    format_bytes = format.encode("utf-8") if isinstance(format, str) else b""
    out = bytearray(256)
    written = _lib.xyg_tick_format(
        float(value),
        float(step),
        _tick_format_kind(kind),
        1 if scale == "log" else 0,
        _tick_window_theta_unit(theta_unit),
        format_bytes,
        len(format_bytes),
        len(cats),
        ctypes.cast(lens, ctypes.POINTER(ctypes.c_uint32)) if cats else 0,
        packed,
        len(packed),
        (ctypes.c_char * len(out)).from_buffer(out),
        len(out),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid tick-format request")
    if written > len(out):
        out = bytearray(written)
        written = _lib.xyg_tick_format(
            float(value),
            float(step),
            _tick_format_kind(kind),
            1 if scale == "log" else 0,
            _tick_window_theta_unit(theta_unit),
            format_bytes,
            len(format_bytes),
            len(cats),
            ctypes.cast(lens, ctypes.POINTER(ctypes.c_uint32)) if cats else 0,
            packed,
            len(packed),
            (ctypes.c_char * len(out)).from_buffer(out),
            len(out),
        )
        if written == _USIZE_MAX or written > len(out):
            raise ValueError("invalid tick-format request")
    return bytes(out[:written]).decode("utf-8")


def scene_legend_box_layout(
    *,
    plot: Mapping[str, float],
    names: Sequence[str],
    title: str | None = None,
    loc: str = "upper right",
    font_size: float = 11.0,
    handlelength: float | None = None,
    handletextpad: float | None = None,
    handleheight: float | None = None,
    ncols: int = 1,
    padding_em: float = 0.4,
    row_gap_em: float = 0.5,
    anchor: Sequence[float] | None = None,
    border_axes_pad: float = 0.0,
) -> dict[str, Any]:
    """Static legend box packing via ``xyg_legend_box_layout`` (ABI 124)."""
    texts = [str(name) for name in names]
    encoded = [text.encode("utf-8") for text in texts]
    lens = np.asarray([len(item) for item in encoded], dtype=np.uint32)
    packed = (
        np.frombuffer(b"".join(encoded), dtype=np.uint8).copy()
        if encoded
        else np.empty(0, dtype=np.uint8)
    )
    n = len(texts)
    title_b = np.frombuffer((title or "").encode("utf-8"), dtype=np.uint8).copy()
    loc_b = np.frombuffer((loc or "upper right").encode("utf-8"), dtype=np.uint8).copy()
    metrics = np.empty(17, dtype=np.float64)
    col_cap = max(n, 1)
    widths = np.empty(col_cap, dtype=np.float64)
    offsets = np.empty(col_cap, dtype=np.float64)
    name_lens = np.empty(col_cap, dtype=np.uint32)
    names_cap = len(packed) + 3 * n
    names_out = np.empty(max(names_cap, 1), dtype=np.uint8)
    title_cap = max(int(title_b.size) + 8, 1)
    title_out = np.empty(title_cap, dtype=np.uint8)
    title_len = ctypes.c_size_t()
    anchor_arr = None
    anchor_len = 0
    if anchor is not None:
        vals = [float(v) for v in anchor]
        if len(vals) not in (2, 4):
            raise ValueError("legend anchor must have length 2 or 4")
        anchor_arr = np.asarray(vals, dtype=np.float64)
        anchor_len = len(vals)
    written = _lib.xyg_legend_box_layout(
        float(plot["x"]),
        float(plot["y"]),
        float(plot["w"]),
        float(plot["h"]),
        lens.ctypes.data if n else 0,
        _ptr_u8(packed) if len(packed) else 0,
        len(packed),
        n,
        _ptr_u8(title_b) if title_b.size else 0,
        int(title_b.size),
        _ptr_u8(loc_b) if loc_b.size else 0,
        int(loc_b.size),
        float(font_size),
        float("nan") if handlelength is None else float(handlelength),
        float("nan") if handletextpad is None else float(handletextpad),
        float("nan") if handleheight is None else float(handleheight),
        max(1, int(ncols)),
        float(padding_em),
        float(row_gap_em),
        _ptr_f64(anchor_arr) if anchor_arr is not None else 0,
        anchor_len,
        float(border_axes_pad),
        _ptr_f64(metrics),
        _ptr_f64(widths),
        _ptr_f64(offsets),
        col_cap,
        name_lens.ctypes.data,
        _ptr_u8(names_out),
        len(names_out),
        _ptr_u8(title_out),
        len(title_out),
        ctypes.byref(title_len),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid legend box layout request")
    vis = int(written)
    ncols_out = int(metrics[9])
    at = 0
    out_names: list[str] = []
    for i in range(vis):
        length = int(name_lens[i])
        out_names.append(bytes(names_out[at : at + length]).decode("utf-8"))
        at += length
    title_s = bytes(title_out[: int(title_len.value)]).decode("utf-8")
    return {
        "pad": float(metrics[0]),
        "handle": float(metrics[1]),
        "gap": float(metrics[2]),
        "column_gap": float(metrics[3]),
        "row_gap": float(metrics[4]),
        "font_size": float(metrics[5]),
        "text_h": float(metrics[6]),
        "line_h": float(metrics[7]),
        "swatch_h": float(metrics[8]),
        "ncols": ncols_out,
        "title": title_s or None,
        "title_h": float(metrics[10]),
        "cell_w": float(metrics[11]),
        "column_widths": widths[:ncols_out].tolist(),
        "column_offsets": offsets[:ncols_out].tolist(),
        "box_w": float(metrics[12]),
        "box_h": float(metrics[13]),
        "x": float(metrics[14]),
        "y": float(metrics[15]),
        "visible_count": vis,
        "names": out_names,
    }


_ANCHOR_CODES = {"start": 0, "center": 1, "end": 2}


def _pack_utf8_strings(texts: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    encoded = [str(text).encode("utf-8") for text in texts]
    lens = np.asarray([len(item) for item in encoded], dtype=np.uint32)
    packed = (
        np.frombuffer(b"".join(encoded), dtype=np.uint8).copy()
        if encoded
        else np.empty(0, dtype=np.uint8)
    )
    return lens, packed


def _unpack_utf8_strings(lens: np.ndarray, packed: np.ndarray, count: int) -> list[str]:
    out: list[str] = []
    at = 0
    for i in range(count):
        length = int(lens[i])
        out.append(bytes(packed[at : at + length]).decode("utf-8"))
        at += length
    return out


def text_block_measure(
    text: object,
    font_size: float,
    line_height: float = 1.2,
    max_width: float | None = None,
) -> dict[str, Any]:
    """Newline-delimited chrome measure via ``xyg_text_block_measure`` (ABI 125)."""
    text_b = np.frombuffer(str(text).encode("utf-8"), dtype=np.uint8).copy()
    line_cap = max(int(text_b.size) + 8, 8)
    packed_cap = max(int(text_b.size) + 8, 8)
    metrics = np.empty(6, dtype=np.float64)
    written = _USIZE_MAX
    line_lens = np.empty(0, dtype=np.uint32)
    packed = np.empty(0, dtype=np.uint8)
    for _ in range(4):
        line_lens = np.empty(line_cap, dtype=np.uint32)
        packed = np.empty(packed_cap, dtype=np.uint8)
        written = _lib.xyg_text_block_measure(
            _ptr_u8(text_b) if text_b.size else 0,
            int(text_b.size),
            float(font_size),
            float(line_height),
            float("nan") if max_width is None else float(max_width),
            _ptr_f64(metrics),
            line_lens.ctypes.data,
            line_cap,
            _ptr_u8(packed),
            packed_cap,
        )
        if written != _USIZE_MAX:
            break
        line_cap *= 4
        packed_cap *= 4
    if written == _USIZE_MAX:
        raise ValueError("invalid text-block measure request")
    n = int(written)
    return {
        "lines": _unpack_utf8_strings(line_lens, packed, n),
        "width": float(metrics[0]),
        "height": float(metrics[1]),
        "line_step": float(metrics[2]),
        "ascent": float(metrics[3]),
        "descent": float(metrics[4]),
        "line_count": n,
    }


def text_block_rotated_extent(
    width: float,
    height: float,
    angle_degrees: float,
) -> tuple[float, float]:
    """Axis-aligned extent after rotation via ``xyg_text_block_rotated_extent``."""
    out_x = ctypes.c_double()
    out_y = ctypes.c_double()
    written = _lib.xyg_text_block_rotated_extent(
        float(width),
        float(height),
        float(angle_degrees),
        ctypes.byref(out_x),
        ctypes.byref(out_y),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid text-block rotation request")
    return float(out_x.value), float(out_y.value)


def y_tick_label_extent(
    labels: Sequence[str],
    font_size: float,
    angle: float,
) -> float:
    """Widest rotated x-extent of y tick labels (ABI 125)."""
    lens, packed = _pack_utf8_strings([str(label) for label in labels])
    n = len(labels)
    out = ctypes.c_double()
    written = _lib.xyg_y_tick_label_extent(
        lens.ctypes.data if n else 0,
        _ptr_u8(packed) if packed.size else 0,
        int(packed.size),
        n,
        float(font_size),
        float(angle),
        ctypes.byref(out),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid y tick-label extent request")
    return float(out.value)


def y_axis_left_room(
    tick_offset: float,
    tick_room: float,
    title: str | None,
    title_font_size: float,
    title_gap: float,
) -> float:
    """Left gutter for one y axis after the host resolved tick ink (ABI 125)."""
    title_b = np.frombuffer(str(title or "").encode("utf-8"), dtype=np.uint8).copy()
    out = ctypes.c_double()
    written = _lib.xyg_y_axis_left_room(
        float(tick_offset),
        float(tick_room),
        _ptr_u8(title_b) if title_b.size else 0,
        int(title_b.size),
        float(title_font_size),
        float(title_gap),
        ctypes.byref(out),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid y-axis left-room request")
    return float(out.value)


def x_axis_title_room(
    title: str | None,
    font_size: float,
    offset: float,
    top: bool,
) -> float:
    """Outside x-axis title room via ``xyg_x_axis_title_room`` (ABI 125)."""
    title_b = np.frombuffer(str(title or "").encode("utf-8"), dtype=np.uint8).copy()
    out = ctypes.c_double()
    written = _lib.xyg_x_axis_title_room(
        _ptr_u8(title_b) if title_b.size else 0,
        int(title_b.size),
        float(font_size),
        float(offset),
        1 if top else 0,
        ctypes.byref(out),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid x-axis title-room request")
    return float(out.value)


def x_tick_label_room(
    labels: Sequence[str],
    angles: Sequence[float],
    rows: Sequence[int],
    font_size: float,
    label_offset: float,
    title_room: float,
) -> float:
    """Measured x tick-label band after collision layout (ABI 125)."""
    texts = [str(label) for label in labels]
    n = len(texts)
    if n != len(angles) or n != len(rows):
        raise ValueError("x tick-label room arrays must have equal length")
    lens, packed = _pack_utf8_strings(texts)
    angle_arr = (
        np.asarray([float(angle) for angle in angles], dtype=np.float64)
        if n
        else np.empty(0, dtype=np.float64)
    )
    row_arr = (
        np.asarray([int(row) for row in rows], dtype=np.uint32)
        if n
        else np.empty(0, dtype=np.uint32)
    )
    out = ctypes.c_double()
    written = _lib.xyg_x_tick_label_room(
        lens.ctypes.data if n else 0,
        _ptr_u8(packed) if packed.size else 0,
        int(packed.size),
        n,
        _ptr_f64(angle_arr) if n else 0,
        row_arr.ctypes.data if n else 0,
        float(font_size),
        float(label_offset),
        float(title_room),
        ctypes.byref(out),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid x tick-label room request")
    return float(out.value)


def x_tick_label_edge_rooms(
    plot_w: float,
    positions: Sequence[float],
    labels: Sequence[str],
    angles: Sequence[float],
    anchors: Sequence[str],
    font_size: float,
) -> tuple[float, float]:
    """Canvas-edge overhang from laid-out x tick labels (ABI 125)."""
    texts = [str(label) for label in labels]
    n = len(texts)
    if n != len(positions) or n != len(angles) or n != len(anchors):
        raise ValueError("x tick-label edge-room arrays must have equal length")
    lens, packed = _pack_utf8_strings(texts)
    pos_arr = (
        np.asarray([float(pos) for pos in positions], dtype=np.float64)
        if n
        else np.empty(0, dtype=np.float64)
    )
    angle_arr = (
        np.asarray([float(angle) for angle in angles], dtype=np.float64)
        if n
        else np.empty(0, dtype=np.float64)
    )
    try:
        anchor_arr = (
            np.asarray([_ANCHOR_CODES[str(anchor)] for anchor in anchors], dtype=np.uint32)
            if n
            else np.empty(0, dtype=np.uint32)
        )
    except KeyError as exc:
        raise ValueError("anchor must be start, center, or end") from exc
    out_left = ctypes.c_double()
    out_right = ctypes.c_double()
    written = _lib.xyg_x_tick_label_edge_rooms(
        float(plot_w),
        _ptr_f64(pos_arr) if n else 0,
        n,
        lens.ctypes.data if n else 0,
        _ptr_u8(packed) if packed.size else 0,
        int(packed.size),
        _ptr_f64(angle_arr) if n else 0,
        anchor_arr.ctypes.data if n else 0,
        float(font_size),
        ctypes.byref(out_left),
        ctypes.byref(out_right),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid x tick-label edge-room request")
    return float(out_left.value), float(out_right.value)


_COLORBAR_KINDS = {
    "none": 0,
    "axes_horizontal": 1,
    "axes_vertical": 2,
    "figure_horizontal": 3,
    "figure_vertical": 4,
}
_POLAR_LEGEND_SIDES = {0: "", 1: "left", 2: "right", 3: "bottom"}


def compat_is_compact(width: float) -> bool:
    """Whether a canvas width uses compact static gutters (ABI 126)."""
    status = int(_lib.xyg_compat_is_compact(float(width)))
    if status == 1:
        return True
    if status == 0:
        return False
    raise ValueError("invalid compact-width request")


def compat_default_padding(compact: bool) -> tuple[float, float, float, float]:
    """Default static-export padding via ``xyg_compat_default_padding`` (ABI 126)."""
    out = np.empty(4, dtype=np.float64)
    written = _lib.xyg_compat_default_padding(1 if compact else 0, _ptr_f64(out))
    if written == _USIZE_MAX:
        raise ValueError("invalid default-padding request")
    return float(out[0]), float(out[1]), float(out[2]), float(out[3])


def compat_title_wrap_width(width: float, left: float, right: float) -> float:
    """Title wrap width via ``xyg_compat_title_wrap_width`` (ABI 126)."""
    out = ctypes.c_double()
    written = _lib.xyg_compat_title_wrap_width(
        float(width), float(left), float(right), ctypes.byref(out)
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid title-wrap-width request")
    return float(out.value)


def compat_title_room(
    compact: bool,
    block_height: float,
    pad: float,
    automatic_y: bool,
    y: float,
) -> float:
    """Title-band room via ``xyg_compat_title_room`` (ABI 126)."""
    out = ctypes.c_double()
    written = _lib.xyg_compat_title_room(
        1 if compact else 0,
        float(block_height),
        float(pad),
        1 if automatic_y else 0,
        float(y),
        ctypes.byref(out),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid title-room request")
    return float(out.value)


def compat_x_axis_side_room(compact: bool, top: bool, measured: float) -> tuple[float, float]:
    """Compact floor plus measured x-axis room (ABI 126)."""
    out_room = ctypes.c_double()
    out_measured = ctypes.c_double()
    written = _lib.xyg_compat_x_axis_side_room(
        1 if compact else 0,
        1 if top else 0,
        float(measured),
        ctypes.byref(out_room),
        ctypes.byref(out_measured),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid x-axis side-room request")
    return float(out_room.value), float(out_measured.value)


def compat_colorbar_extra(kind: str, has_label: bool, pad_zero: bool) -> tuple[float, float]:
    """Extra right/bottom claimed by a colorbar (ABI 126)."""
    try:
        code = _COLORBAR_KINDS[kind]
    except KeyError as exc:
        raise ValueError("unknown colorbar layout kind") from exc
    out_right = ctypes.c_double()
    out_bottom = ctypes.c_double()
    written = _lib.xyg_compat_colorbar_extra(
        code,
        1 if has_label else 0,
        1 if pad_zero else 0,
        ctypes.byref(out_right),
        ctypes.byref(out_bottom),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid colorbar-extra request")
    return float(out_right.value), float(out_bottom.value)


def compat_right_y_room(compact: bool) -> float:
    """Shared right-side y-axis gutter (ABI 126)."""
    out = ctypes.c_double()
    written = _lib.xyg_compat_right_y_room(1 if compact else 0, ctypes.byref(out))
    if written == _USIZE_MAX:
        raise ValueError("invalid right-y-room request")
    return float(out.value)


def polar_legend_room(width: float) -> float:
    """Polar legend side-gutter width (ABI 126)."""
    out = ctypes.c_double()
    written = _lib.xyg_polar_legend_room(float(width), ctypes.byref(out))
    if written == _USIZE_MAX:
        raise ValueError("invalid polar-legend-room request")
    return float(out.value)


def polar_legend_reserve(compact: bool, loc_has_left: bool, width: float) -> tuple[str, float]:
    """Compact vs loc polar legend reserve (ABI 126)."""
    side = ctypes.c_uint32()
    room = ctypes.c_double()
    written = _lib.xyg_polar_legend_reserve(
        1 if compact else 0,
        1 if loc_has_left else 0,
        float(width),
        ctypes.byref(side),
        ctypes.byref(room),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid polar-legend-reserve request")
    return _POLAR_LEGEND_SIDES[int(side.value)], float(room.value)


def polar_label_room(widest: float | None) -> float:
    """Uniform polar angular-label inset (ABI 126)."""
    out = ctypes.c_double()
    written = _lib.xyg_polar_label_room(
        float("nan") if widest is None else float(widest),
        ctypes.byref(out),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid polar-label-room request")
    return float(out.value)


POLAR_METRICS_LEN = 23


def _polar_theta_unit(unit: str | None) -> int:
    return 1 if unit == "degrees" else 0


def _polar_theta_direction(direction: str | None) -> int:
    return 1 if direction == "clockwise" else 0


def _polar_as_float(value: object, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float, np.integer, np.floating, str)):
        return float(value)
    return float(cast(Any, value))


def _polar_pair(value: object, default: tuple[float, float]) -> tuple[float, float]:
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        return _polar_as_float(value[0], default[0]), _polar_as_float(value[1], default[1])
    return default


def _polar_theta_zero(zero: object) -> float:
    if isinstance(zero, str):
        named = {"E": 0.0, "N": math.pi / 2.0, "W": math.pi, "S": -math.pi / 2.0}
        if zero in named:
            return named[zero]
        return float(zero)
    return _polar_as_float(zero, 0.0)


def _polar_r_scale(axis: Mapping[str, object]) -> tuple[int, float, bool]:
    scale = axis.get("scale")
    kind = axis.get("kind", "linear")
    if scale == "log" or kind == "log":
        code = 1
    elif scale == "symlog":
        code = 2
    else:
        code = 0
    constant = _polar_as_float(axis.get("constant", 1.0), 1.0)
    mask = axis.get("nonpositive", "clip") == "mask"
    return code, constant, mask


def polar_layout(
    theta_axis: Mapping[str, object],
    r_axis: Mapping[str, object],
    plot: Mapping[str, float],
) -> npt.NDArray[np.float64]:
    """Polar disc layout via ``xyg_polar_layout`` (ABI 131)."""
    unit = str(theta_axis.get("theta_unit", "radians"))
    turn = 360.0 if unit == "degrees" else 2.0 * math.pi
    sector_start, sector_end = _polar_pair(theta_axis.get("sector"), (0.0, turn))
    categories = theta_axis.get("categories")
    n_categories = len(categories) if isinstance(categories, (list, tuple)) else 0
    raw_range = r_axis.get("range")
    if not isinstance(raw_range, (tuple, list)) or len(raw_range) < 2:
        raise (
            KeyError("range")
            if raw_range is None
            else TypeError("polar r-axis range must be a pair")
        )
    r_lo, r_hi = _polar_as_float(raw_range[0], 0.0), _polar_as_float(raw_range[1], 1.0)
    origin = r_axis.get("r_origin")
    r_origin = float("nan") if origin is None else _polar_as_float(origin, float("nan"))
    hole = _polar_as_float(r_axis.get("hole"), 0.0)
    scale_kind, constant, mask_nonpositive = _polar_r_scale(r_axis)
    metrics = np.empty(POLAR_METRICS_LEN, dtype=np.float64)
    raw_direction = theta_axis.get("theta_direction")
    written = _lib.xyg_polar_layout(
        float(plot["x"]),
        float(plot["y"]),
        float(plot["w"]),
        float(plot["h"]),
        _polar_theta_unit(unit),
        _polar_theta_zero(theta_axis.get("theta_zero", "E")),
        _polar_theta_direction(raw_direction if isinstance(raw_direction, str) else None),
        sector_start,
        sector_end,
        n_categories,
        float(r_lo),
        float(r_hi),
        r_origin,
        hole,
        scale_kind,
        constant,
        1 if mask_nonpositive else 0,
        _ptr_f64(metrics),
        POLAR_METRICS_LEN,
    )
    if written != POLAR_METRICS_LEN:
        raise ValueError("invalid polar-layout request")
    return metrics


def polar_project(
    metrics: npt.ArrayLike,
    theta: npt.ArrayLike,
    r: npt.ArrayLike,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Project polar (theta, r) via ``xyg_polar_project`` (ABI 131)."""
    packed = _as_f64(np.asarray(metrics, dtype=np.float64).reshape(-1), "metrics")
    th = _as_f64(np.asarray(theta, dtype=np.float64).reshape(-1), "theta")
    rv = _as_f64(np.asarray(r, dtype=np.float64).reshape(-1), "r")
    if th.shape != rv.shape:
        raise ValueError("theta and r must have the same shape")
    n = len(th)
    out_x = np.empty(n, dtype=np.float64)
    out_y = np.empty(n, dtype=np.float64)
    written = _lib.xyg_polar_project(
        _ptr_f64(packed) if len(packed) else 0,
        len(packed),
        _ptr_f64(th) if n else 0,
        _ptr_f64(rv) if n else 0,
        n,
        _ptr_f64(out_x) if n else 0,
        _ptr_f64(out_y) if n else 0,
    )
    if written == _USIZE_MAX or written != n:
        raise ValueError("invalid polar-project request")
    if np.ndim(theta) == 0:
        return out_x.reshape(()), out_y.reshape(())
    return out_x.reshape(np.shape(theta)), out_y.reshape(np.shape(r))


def polar_wedge_points(
    metrics: npt.ArrayLike,
    theta0: float,
    theta1: float,
    r0: float,
    r1: float,
    wedge_gap: float = 0.0,
    corner_radius: float = 0.0,
    steps: int = 0,
    normalized: tuple[float, float] | list[float] | None = None,
) -> list[tuple[float, float]]:
    """Flatten a polar annular sector to screen pixels (ABI 209).

    ``steps == 0`` uses ``polar_bar_segments``. Finite ``normalized``
    fractions skip radial-range normalization. Empty native pointers are
    ``0``.
    """
    packed = _as_f64(np.asarray(metrics, dtype=np.float64).reshape(-1), "metrics")
    step_count = int(steps)
    if step_count < 0:
        raise ValueError("polar wedge steps must be non-negative")
    if normalized is None:
        norm_lo = float("nan")
        norm_hi = float("nan")
    else:
        norm_lo = float(normalized[0])
        norm_hi = float(normalized[1])
    probed = _lib.xyg_polar_wedge_points(
        _ptr_f64(packed) if len(packed) else 0,
        len(packed),
        float(theta0),
        float(theta1),
        float(r0),
        float(r1),
        float(wedge_gap),
        float(corner_radius),
        step_count,
        norm_lo,
        norm_hi,
        0,
        0,
        0,
    )
    if probed == _USIZE_MAX:
        raise ValueError("invalid polar-wedge request")
    n = int(probed)
    if n == 0:
        return []
    out_x = np.empty(n, dtype=np.float64)
    out_y = np.empty(n, dtype=np.float64)
    written = _lib.xyg_polar_wedge_points(
        _ptr_f64(packed) if len(packed) else 0,
        len(packed),
        float(theta0),
        float(theta1),
        float(r0),
        float(r1),
        float(wedge_gap),
        float(corner_radius),
        step_count,
        norm_lo,
        norm_hi,
        _ptr_f64(out_x),
        _ptr_f64(out_y),
        n,
    )
    if written == _USIZE_MAX or written != n:
        raise ValueError("invalid polar-wedge request")
    return [(float(x), float(y)) for x, y in zip(out_x, out_y, strict=True)]


def polar_heatmap_inverse_map(
    metrics: npt.ArrayLike,
    plot: Mapping[str, float],
    grid_w: int,
    grid_h: int,
    x_range: tuple[float, float] | list[float],
    y_range: tuple[float, float] | list[float],
    output_scale: float = 1.0,
) -> tuple[int, int, npt.NDArray[np.uint32], npt.NDArray[np.uint32], npt.NDArray[np.uint32]]:
    """Map visible polar-heatmap pixels onto source cells (ABI 207).

    Returns ``(out_w, out_h, rows, cols, source_indices)``. ``source_indices``
    are row-major with source row 0 at the radial-range bottom so hosts can
    color only those cells. Empty native pointers are ``0``.
    """
    packed = _as_f64(np.asarray(metrics, dtype=np.float64).reshape(-1), "metrics")
    grid_w = int(grid_w)
    grid_h = int(grid_h)
    if grid_w <= 0 or grid_h <= 0:
        raise ValueError("polar heatmap dimensions must be positive")
    scale = float(output_scale)
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("polar heatmap output_scale must be positive and finite")
    xr = (float(x_range[0]), float(x_range[1]))
    yr = (float(y_range[0]), float(y_range[1]))
    out_w = ctypes.c_uint32()
    out_h = ctypes.c_uint32()
    probed = _lib.xyg_polar_heatmap_inverse_map(
        _ptr_f64(packed) if len(packed) else 0,
        len(packed),
        float(plot["x"]),
        float(plot["y"]),
        float(plot["w"]),
        float(plot["h"]),
        grid_w,
        grid_h,
        xr[0],
        yr[0],
        xr[1],
        yr[1],
        scale,
        ctypes.byref(out_w),
        ctypes.byref(out_h),
        0,
        0,
        0,
        0,
    )
    if probed == _USIZE_MAX:
        raise ValueError("invalid polar-heatmap inverse-map request")
    width = int(out_w.value)
    height = int(out_h.value)
    capacity = width * height
    rows = np.empty(capacity, dtype=np.uint32)
    cols = np.empty(capacity, dtype=np.uint32)
    source = np.empty(capacity, dtype=np.uint32)
    written = _lib.xyg_polar_heatmap_inverse_map(
        _ptr_f64(packed) if len(packed) else 0,
        len(packed),
        float(plot["x"]),
        float(plot["y"]),
        float(plot["w"]),
        float(plot["h"]),
        grid_w,
        grid_h,
        xr[0],
        yr[0],
        xr[1],
        yr[1],
        scale,
        ctypes.byref(out_w),
        ctypes.byref(out_h),
        _ptr_u32(rows) if capacity else 0,
        _ptr_u32(cols) if capacity else 0,
        _ptr_u32(source) if capacity else 0,
        capacity,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid polar-heatmap inverse-map request")
    n = int(written)
    return width, height, rows[:n], cols[:n], source[:n]


def _polar_mask(
    fn: Callable[..., int],
    metrics: npt.ArrayLike,
    *arrays: npt.ArrayLike,
) -> npt.NDArray[np.bool_]:
    packed = _as_f64(np.asarray(metrics, dtype=np.float64).reshape(-1), "metrics")
    inputs = [
        _as_f64(np.asarray(value, dtype=np.float64).reshape(-1), "values") for value in arrays
    ]
    n = len(inputs[0])
    if any(len(arr) != n for arr in inputs[1:]):
        raise ValueError("polar mask inputs must have the same length")
    out = np.empty(n, dtype=np.uint8)
    args: list[object] = [_ptr_f64(packed) if len(packed) else 0, len(packed)]
    for arr in inputs:
        args.extend([_ptr_f64(arr) if n else 0])
    args.append(n)
    args.extend([out.ctypes.data if n else 0, n])
    written = fn(*args)
    if written == _USIZE_MAX or written != n:
        raise ValueError("invalid polar-mask request")
    return out.astype(np.bool_)


def polar_theta_visible_mask(metrics: npt.ArrayLike, theta: npt.ArrayLike) -> npt.NDArray[np.bool_]:
    """Angular-sector visibility via ``xyg_polar_theta_visible_mask`` (ABI 131)."""
    return _polar_mask(_lib.xyg_polar_theta_visible_mask, metrics, theta)


def polar_visible_mask(metrics: npt.ArrayLike, r: npt.ArrayLike) -> npt.NDArray[np.bool_]:
    """Radial-range visibility via ``xyg_polar_visible_mask`` (ABI 131)."""
    return _polar_mask(_lib.xyg_polar_visible_mask, metrics, r)


def polar_position_mask(
    metrics: npt.ArrayLike,
    theta: npt.ArrayLike,
    r: npt.ArrayLike,
) -> npt.NDArray[np.bool_]:
    """Combined polar visibility via ``xyg_polar_position_mask`` (ABI 131)."""
    packed = _as_f64(np.asarray(metrics, dtype=np.float64).reshape(-1), "metrics")
    th = _as_f64(np.asarray(theta, dtype=np.float64).reshape(-1), "theta")
    rv = _as_f64(np.asarray(r, dtype=np.float64).reshape(-1), "r")
    n = len(th)
    if len(rv) != n:
        raise ValueError("theta and r must have the same length")
    out = np.empty(n, dtype=np.uint8)
    written = _lib.xyg_polar_position_mask(
        _ptr_f64(packed) if len(packed) else 0,
        len(packed),
        _ptr_f64(th) if n else 0,
        _ptr_f64(rv) if n else 0,
        n,
        out.ctypes.data if n else 0,
        n,
    )
    if written == _USIZE_MAX or written != n:
        raise ValueError("invalid polar-position-mask request")
    return out.astype(np.bool_)


def recut_polar_plot(
    plot: Mapping[str, float],
    width: float,
    height: float,
    *,
    legend_side: str = "",
    legend_room: float = 0.0,
    polar_label_room: float = 0.0,
    authored_padding: bool = False,
    y_titled: bool = False,
    keeps_bottom: bool = False,
) -> dict[str, float]:
    """Re-cut a cartesian plot rect into a polar disc (ABI 126)."""
    side_codes = {"": 0, "left": 1, "right": 2, "bottom": 3}
    try:
        side = side_codes[legend_side]
    except KeyError as exc:
        raise ValueError("legend_side must be '', left, right, or bottom") from exc
    incoming = np.asarray(
        [
            float(plot["x"]),
            float(plot["y"]),
            float(plot["w"]),
            float(plot["h"]),
            float(plot.get("top_axis_room", 0.0)),
        ],
        dtype=np.float64,
    )
    out = np.empty(9, dtype=np.float64)
    written = _lib.xyg_recut_polar_plot(
        _ptr_f64(incoming),
        float(width),
        float(height),
        side,
        float(legend_room),
        float(polar_label_room),
        1 if authored_padding else 0,
        1 if y_titled else 0,
        1 if keeps_bottom else 0,
        _ptr_f64(out),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid polar-recut request")
    result = {
        "x": float(out[0]),
        "y": float(out[1]),
        "w": float(out[2]),
        "h": float(out[3]),
        "top_axis_room": float(out[4]),
    }
    if np.isfinite(out[5]):
        result["legend_box_x"] = float(out[5])
        result["legend_box_y"] = float(out[6])
        result["legend_box_w"] = float(out[7])
        result["legend_box_h"] = float(out[8])
    return result


def compat_combine_plot(
    width: float,
    height: float,
    *,
    authored_padding: Sequence[float] | None = None,
    title_room: float = 0.0,
    x_top_room: float = 0.0,
    x_bottom_room: float = 0.0,
    x_measured_bottom: float = 0.0,
    colorbar_kind: str = "none",
    colorbar_has_label: bool = False,
    colorbar_pad_zero: bool = False,
    has_right_y: bool = False,
    y_left_room: float | None = None,
    edge_left: float | None = None,
    edge_right: float | None = None,
    x_rooms_final: Sequence[float] | None = None,
    polar: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """Combine static-export padding/title/rooms/colorbar/polar recut (ABI 198)."""
    try:
        cb_code = _COLORBAR_KINDS[colorbar_kind]
    except KeyError as exc:
        raise ValueError("unknown colorbar layout kind") from exc
    pad_arr = None
    if authored_padding is not None:
        if len(authored_padding) != 4:
            raise ValueError("authored_padding must be top, right, bottom, left")
        pad_arr = np.asarray(authored_padding, dtype=np.float64)
    x_final_arr = None
    if x_rooms_final is not None:
        if len(x_rooms_final) != 3:
            raise ValueError("x_rooms_final must be top, bottom, measured_bottom")
        x_final_arr = np.asarray(x_rooms_final, dtype=np.float64)
    side_codes = {"": 0, "left": 1, "right": 2, "bottom": 3}
    polar_on = polar is not None
    legend_side = ""
    legend_room = 0.0
    polar_label_room = 0.0
    authored_padding_flag = False
    y_titled = False
    keeps_bottom = False
    if polar_on:
        legend_side = str(polar.get("legend_side") or "")
        try:
            side = side_codes[legend_side]
        except KeyError as exc:
            raise ValueError("legend_side must be '', left, right, or bottom") from exc
        legend_room = float(polar.get("legend_room") or 0.0)
        polar_label_room = float(polar.get("polar_label_room") or 0.0)
        authored_padding_flag = bool(polar.get("authored_padding"))
        y_titled = bool(polar.get("y_titled"))
        keeps_bottom = bool(polar.get("keeps_bottom"))
    else:
        side = 0
    out = np.empty(12, dtype=np.float64)
    written = _lib.xyg_compat_combine_plot(
        float(width),
        float(height),
        _ptr_f64(pad_arr) if pad_arr is not None else 0,
        float(title_room),
        float(x_top_room),
        float(x_bottom_room),
        float(x_measured_bottom),
        cb_code,
        1 if colorbar_has_label else 0,
        1 if colorbar_pad_zero else 0,
        1 if has_right_y else 0,
        float("nan") if y_left_room is None else float(y_left_room),
        float("nan") if edge_left is None else float(edge_left),
        float("nan") if edge_right is None else float(edge_right),
        _ptr_f64(x_final_arr) if x_final_arr is not None else 0,
        1 if polar_on else 0,
        side,
        legend_room,
        polar_label_room,
        1 if authored_padding_flag else 0,
        1 if y_titled else 0,
        1 if keeps_bottom else 0,
        _ptr_f64(out),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid static-export layout combination")
    result = {
        "x": float(out[0]),
        "y": float(out[1]),
        "w": float(out[2]),
        "h": float(out[3]),
        "title_room": float(out[4]),
        "title_wrap_width": float(out[5]),
        "top_axis_room": float(out[6]),
        "bottom_axis_room": float(out[7]),
    }
    if np.isfinite(out[8]):
        result["legend_box_x"] = float(out[8])
        result["legend_box_y"] = float(out[9])
        result["legend_box_w"] = float(out[10])
        result["legend_box_h"] = float(out[11])
    return result


def tight_layout_solve(
    canvas_w: float,
    canvas_h: float,
    nrows: int,
    ncols: int,
    compact: bool,
    panels: Sequence[Mapping[str, float]],
    extra: Sequence[float] = (0.0, 0.0, 0.0, 0.0),
    pad: float | None = None,
    w_pad: float | None = None,
    h_pad: float | None = None,
    point_px: float = 1.0,
    rect: Sequence[float] = (0.0, 0.0, 1.0, 1.0),
) -> tuple[float, float, float, float, float, float]:
    """Pyplot tight-layout grid solve via ``xyg_tight_layout_solve`` (ABI 127)."""
    if len(extra) != 4:
        raise ValueError("extra must be left, right, bottom, top")
    if len(rect) != 4:
        raise ValueError("rect must be left, bottom, right, top")
    packed = np.empty((len(panels), 8), dtype=np.float64)
    for index, panel in enumerate(panels):
        packed[index] = (
            float(panel["row0"]),
            float(panel["row1"]),
            float(panel["col0"]),
            float(panel["col1"]),
            float(panel["left"]),
            float(panel["top"]),
            float(panel["right"]),
            float(panel["bottom"]),
        )
    extra_arr = np.asarray(extra, dtype=np.float64)
    rect_arr = np.asarray(rect, dtype=np.float64)
    out = np.empty(6, dtype=np.float64)
    written = _lib.xyg_tight_layout_solve(
        float(canvas_w),
        float(canvas_h),
        int(nrows),
        int(ncols),
        1 if compact else 0,
        _ptr_f64(packed) if len(panels) else 0,
        len(panels),
        _ptr_f64(extra_arr),
        float("nan") if pad is None else float(pad),
        float("nan") if w_pad is None else float(w_pad),
        float("nan") if h_pad is None else float(h_pad),
        float(point_px),
        _ptr_f64(rect_arr),
        _ptr_f64(out),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid tight-layout request")
    return (
        float(out[0]),
        float(out[1]),
        float(out[2]),
        float(out[3]),
        float(out[4]),
        float(out[5]),
    )


def tight_layout_figure_extra(
    canvas_w: float,
    canvas_h: float,
    *,
    suptitle_height: float | None = None,
    suptitle_y: float = 0.98,
    xlabel_size: float | None = None,
    ylabel_size: float | None = None,
    legend_box_w: float | None = None,
) -> tuple[float, float, float, float]:
    """Figure-edge extras for ``xyg_tight_layout_solve`` (ABI 198).

    Returns ``(left, right, bottom, top)``. Hosts still measure suptitle height,
    figure-label sizes, and outside-legend box width.
    """
    extra = np.empty(4, dtype=np.float64)
    written = _lib.xyg_tight_layout_figure_extra(
        float(canvas_w),
        float(canvas_h),
        float("nan") if suptitle_height is None else float(suptitle_height),
        float(suptitle_y),
        float("nan") if xlabel_size is None else float(xlabel_size),
        float("nan") if ylabel_size is None else float(ylabel_size),
        float("nan") if legend_box_w is None else float(legend_box_w),
        _ptr_f64(extra),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid tight-layout figure-extra request")
    return float(extra[0]), float(extra[1]), float(extra[2]), float(extra[3])


def scene_scale_map(
    values: npt.ArrayLike,
    kind: int,
    operation: int,
    lo: float,
    hi: float,
    px0: float,
    px1: float,
    constant: float = 1.0,
    mask_nonpositive: bool = False,
) -> float | npt.NDArray[np.float64]:
    """Apply the bounded canonical scene scale while preserving input shape."""
    source = np.asarray(values, dtype=np.float64)
    if source.ndim == 0:
        scalar = ctypes.c_double(float(source))
        result = ctypes.c_double()
        status = _lib.xyg_scene_scale_map(
            ctypes.byref(scalar),
            1,
            kind,
            operation,
            lo,
            hi,
            px0,
            px1,
            constant,
            int(mask_nonpositive),
            ctypes.byref(result),
        )
        if status != 0:
            raise ValueError("invalid canonical scene scale")
        return result.value
    flat = np.ascontiguousarray(source).reshape(-1)
    out = np.empty(len(flat), dtype=np.float64)
    status = _lib.xyg_scene_scale_map(
        _ptr_f64(flat) if len(flat) else 0,
        len(flat),
        kind,
        operation,
        lo,
        hi,
        px0,
        px1,
        constant,
        int(mask_nonpositive),
        _ptr_f64(out) if len(flat) else 0,
    )
    if status != 0:
        raise ValueError("invalid canonical scene scale")
    return out.reshape(source.shape)


def scene_plot_layout(
    *,
    viewport: tuple[float, float],
    x_axis: tuple[int, float, float, float, bool],
    y_axis: tuple[int, float, float, float, bool],
    title: str = "",
    x_label: str = "",
    y_label: str = "",
    x_format: str | None = None,
    y_format: str | None = None,
    padding: tuple[float, float, float, float] | None = None,
    colorbar_side: str | None = None,
) -> tuple[float, float, float, float]:
    """Rust-owned Cartesian gutters for the Scene-eligible export subset.

    Returns ``(left, right, top, bottom)``. ``padding`` is optional authored
    ``(top, right, bottom, left)``; omit it for compact/regular defaults.
    """
    title_b = title.encode("utf-8")
    xlabel_b = x_label.encode("utf-8")
    ylabel_b = y_label.encode("utf-8")

    def axis_format_bytes(value: str | None, name: str) -> bytes:
        if value is None:
            return b""
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a string or None")
        encoded = value.encode("utf-8")
        if len(encoded) > 256 or b"\0" in encoded:
            raise ValueError(f"{name} must be NUL-free and at most 256 UTF-8 bytes")
        return encoded

    xformat_b = axis_format_bytes(x_format, "scene x axis format")
    yformat_b = axis_format_bytes(y_format, "scene y axis format")
    out = (ctypes.c_double * 4)()
    pad_buf = None
    pad_ptr = None
    if padding is not None:
        pad_buf = (ctypes.c_double * 4)(*padding)
        pad_ptr = ctypes.cast(pad_buf, ctypes.POINTER(ctypes.c_double))
    side = {None: 0, "right": 1, "bottom": 2}.get(colorbar_side)
    if side is None:
        raise ValueError("colorbar side must be right, bottom, or omitted")
    written = _lib.xyg_scene_plot_layout(
        float(viewport[0]),
        float(viewport[1]),
        pad_ptr,
        int(x_axis[0]),
        float(x_axis[1]),
        float(x_axis[2]),
        float(x_axis[3]),
        1 if x_axis[4] else 0,
        int(y_axis[0]),
        float(y_axis[1]),
        float(y_axis[2]),
        float(y_axis[3]),
        1 if y_axis[4] else 0,
        title_b if title_b else None,
        len(title_b),
        xlabel_b if xlabel_b else None,
        len(xlabel_b),
        ylabel_b if ylabel_b else None,
        len(ylabel_b),
        xformat_b if xformat_b else None,
        len(xformat_b),
        yformat_b if yformat_b else None,
        len(yformat_b),
        side,
        out,
    )
    if written != 4:
        raise ValueError("invalid canonical scene plot layout")
    return float(out[0]), float(out[1]), float(out[2]), float(out[3])


def scene_batch_encode(
    *,
    viewport: tuple[float, float],
    margins: tuple[float, float, float, float],
    x_axis: tuple[int, int, float, float, float, bool],
    y_axis: tuple[int, int, float, float, float, bool],
    kinds: npt.ArrayLike,
    stable_ids: npt.ArrayLike,
    style_refs: npt.ArrayLike,
    fill_rgba: npt.ArrayLike,
    stroke_rgba: npt.ArrayLike,
    stroke_width: npt.ArrayLike,
    diameter: npt.ArrayLike,
    symbols: npt.ArrayLike,
    x0: npt.ArrayLike,
    y0: npt.ArrayLike,
    x1: npt.ArrayLike,
    y1: npt.ArrayLike,
    expansion_modes: npt.ArrayLike | None = None,
    title: str = "",
    x_label: str = "",
    y_label: str = "",
    chrome_style: bytes | None = None,
    x_major_ticks: npt.ArrayLike | None = None,
    x_minor_ticks: npt.ArrayLike = (),
    y_major_ticks: npt.ArrayLike | None = None,
    y_minor_ticks: npt.ArrayLike = (),
    x_tick_labels: list[str] | tuple[str, ...] | None = None,
    y_tick_labels: list[str] | tuple[str, ...] | None = None,
    x_format: str | None = None,
    y_format: str | None = None,
    legend_input: bytes = b"",
    colorbar_input: bytes = b"",
    authored_text_annotations: bytes = b"",
    polar_input: bytes = b"",
) -> bytes:
    """Encode the bounded backend-neutral Scene v16 typed batch."""

    def scene_uint(
        value: npt.ArrayLike, dtype: npt.DTypeLike, maximum: int, name: str
    ) -> np.ndarray:
        raw = np.asarray(value)
        if raw.ndim != 1:
            raise ValueError(f"{name} must be 1-D, got shape {raw.shape}")
        if (
            raw.size
            and not np.issubdtype(raw.dtype, np.integer)
            and (
                raw.dtype != np.dtype(object)
                or any(
                    isinstance(item, (bool, np.bool_)) or not isinstance(item, (int, np.integer))
                    for item in raw
                )
            )
        ):
            raise ValueError(f"{name} must contain unsigned integers")
        if any(int(item) < 0 or int(item) > maximum for item in raw):
            raise ValueError(f"{name} values exceed their unsigned integer range")
        return np.ascontiguousarray(raw, dtype=dtype)

    def scene_u64_scalar(value: object, name: str) -> int:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise ValueError(f"{name} must be an unsigned 64-bit integer")
        converted = int(value)
        if converted < 0 or converted > np.iinfo(np.uint64).max:
            raise ValueError(f"{name} must be an unsigned 64-bit integer")
        return converted

    kind_array = scene_uint(kinds, np.uint8, np.iinfo(np.uint8).max, "scene kinds")
    ids = scene_uint(stable_ids, np.uint64, np.iinfo(np.uint64).max, "scene stable_ids")
    styles = scene_uint(style_refs, np.uint32, np.iinfo(np.uint32).max, "scene style_refs")
    fills = scene_uint(fill_rgba, np.uint8, np.iinfo(np.uint8).max, "scene fill_rgba")
    strokes = scene_uint(stroke_rgba, np.uint8, np.iinfo(np.uint8).max, "scene stroke_rgba")
    widths = _as_f64(np.asarray(stroke_width), "scene style stroke_width")
    diameters = _as_f64(np.asarray(diameter), "scene diameter")
    symbol_codes = scene_uint(symbols, np.uint8, np.iinfo(np.uint8).max, "scene symbols")
    expansion_mode_codes = scene_uint(
        np.zeros(len(kind_array), dtype=np.uint8) if expansion_modes is None else expansion_modes,
        np.uint8,
        12,
        "scene expansion_modes",
    )
    coordinates = [
        _as_f64(np.asarray(value), name)
        for value, name in ((x0, "scene x0"), (y0, "scene y0"), (x1, "scene x1"), (y1, "scene y1"))
    ]
    x_axis = (scene_u64_scalar(x_axis[0], "scene x_axis id"), *x_axis[1:])
    y_axis = (scene_u64_scalar(y_axis[0], "scene y_axis id"), *y_axis[1:])
    n = len(kind_array)
    if n > _MAX_SCENE_MARKS:
        raise ValueError(f"scene batches are limited to {_MAX_SCENE_MARKS:,} records")
    if len(widths) > _MAX_SCENE_STYLES:
        raise ValueError(f"scene style tables are limited to {_MAX_SCENE_STYLES:,} entries")
    if any(
        len(value) != n
        for value in [ids, styles, diameters, symbol_codes, expansion_mode_codes, *coordinates]
    ):
        raise ValueError("scene batch arrays must have equal length")
    if len(fills) != len(widths) * 4 or len(strokes) != len(widths) * 4:
        raise ValueError("scene style table must have one fill and stroke RGBA per style")
    title_b = title.encode("utf-8")
    xlabel_b = x_label.encode("utf-8")
    ylabel_b = y_label.encode("utf-8")
    if not isinstance(authored_text_annotations, bytes):
        raise TypeError("authored_text_annotations must be bytes")
    if any(len(value) > _MAX_SCENE_TEXT_BYTES for value in (title_b, xlabel_b, ylabel_b)):
        raise ValueError(
            f"scene title and axis labels are limited to {_MAX_SCENE_TEXT_BYTES:,} UTF-8 bytes each"
        )
    if chrome_style is None:
        chrome = bytearray(200)
        chrome[8:12] = bytes((32, 32, 32, 217))
        struct.pack_into("<d", chrome, 16, 12.0)
        for offset in (24, 112):
            chrome[offset + 1] = 1
            chrome[offset + 2] = 1
            chrome[offset + 8 : offset + 12] = bytes((32, 32, 32, 140))
            chrome[offset + 12 : offset + 16] = bytes((32, 32, 32, 36))
            chrome[offset + 16 : offset + 20] = bytes((32, 32, 32, 140))
            chrome[offset + 24 : offset + 28] = bytes((32, 32, 32, 140))
            chrome[offset + 28 : offset + 32] = bytes((32, 32, 32, 217))
            struct.pack_into("<7d", chrome, offset + 32, 1.0, 1.0, 1.0, 4.0, 1.0, 1.0, 0.0)
        chrome_style = bytes(chrome)
    chrome_array = np.frombuffer(chrome_style, dtype=np.uint8)
    if len(chrome_array) != 200:
        raise ValueError("scene chrome_style must be exactly 200 bytes")
    x_major = (
        None if x_major_ticks is None else _as_f64(np.asarray(x_major_ticks), "scene x major ticks")
    )
    x_minor = _as_f64(np.asarray(x_minor_ticks), "scene x minor ticks")
    y_major = (
        None if y_major_ticks is None else _as_f64(np.asarray(y_major_ticks), "scene y major ticks")
    )
    y_minor = _as_f64(np.asarray(y_minor_ticks), "scene y minor ticks")
    legend_array = np.frombuffer(legend_input, dtype=np.uint8)
    colorbar_array = np.frombuffer(colorbar_input, dtype=np.uint8)
    if not isinstance(polar_input, (bytes, bytearray)):
        raise TypeError("polar_input must be bytes")
    if polar_input:
        magic = bytes(polar_input[:4])
        if magic not in {b"XYPL", b"XYHP", b"XYEX", b"XYDS", b"XYLC", b"XYMP", b"XYGR"}:
            raise ValueError(
                "polar_input must be empty, XYPL, XYHP, XYEX, XYDS, XYLC, XYMP, or XYGR"
            )
        if magic == b"XYPL" and len(polar_input) != 92:
            raise ValueError("polar_input must be empty or a 92-byte XYPL v1 envelope")
    polar_array = np.frombuffer(bytes(polar_input), dtype=np.uint8)
    polar_view = (
        None if not len(polar_array) else _PolarAbiInput(_ptr_u8(polar_array), len(polar_array))
    )

    def tick_label_input(labels: list[str] | tuple[str, ...] | None, name: str) -> np.ndarray:
        if labels is None:
            return np.empty(0, dtype=np.uint8)
        if len(labels) > 200:
            raise ValueError(f"{name} is limited to 200 strings")
        encoded = [str(label).encode("utf-8") for label in labels]
        if (
            any(not label or b"\0" in label for label in encoded)
            or sum(map(len, encoded)) > _MAX_SCENE_TEXT_BYTES
        ):
            raise ValueError(f"{name} must contain nonempty bounded UTF-8 strings")
        out = bytearray(b"XYTL" + (1).to_bytes(4, "little") + len(encoded).to_bytes(4, "little"))
        for label in encoded:
            out.extend(len(label).to_bytes(4, "little"))
            out.extend(label)
        return np.frombuffer(bytes(out), dtype=np.uint8)

    x_tick_label_array = tick_label_input(x_tick_labels, "scene x tick labels")
    y_tick_label_array = tick_label_input(y_tick_labels, "scene y tick labels")

    def axis_format_input(value: str | None, name: str) -> bytes:
        if value is None:
            return b""
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a string or None")
        encoded = value.encode("utf-8")
        if len(encoded) > 256 or b"\0" in encoded:
            raise ValueError(f"{name} must be NUL-free and at most 256 UTF-8 bytes")
        return encoded

    x_format_b = axis_format_input(x_format, "scene x axis format")
    y_format_b = axis_format_input(y_format, "scene y axis format")
    authored_input = authored_text_annotations
    if x_format_b or y_format_b:
        authored_input = (
            b"XYAF"
            + (1).to_bytes(4, "little")
            + len(x_format_b).to_bytes(4, "little")
            + len(y_format_b).to_bytes(4, "little")
            + len(authored_text_annotations).to_bytes(4, "little")
            + x_format_b
            + y_format_b
            + authored_text_annotations
        )
    authored_text_array = np.frombuffer(authored_input, dtype=np.uint8)
    if len(legend_array) > MAX_SCENE_LEGEND_INPUT_BYTES:
        raise ValueError(f"scene legend input is limited to {MAX_SCENE_LEGEND_INPUT_BYTES:,} bytes")
    if len(colorbar_array) > MAX_SCENE_COLORBAR_INPUT_BYTES:
        raise ValueError(
            f"scene colorbar input is limited to {MAX_SCENE_COLORBAR_INPUT_BYTES:,} bytes"
        )
    tick_arrays = (x_major, x_minor, y_major, y_minor)
    if any(value is not None and len(value) > 200 for value in tick_arrays):
        raise ValueError("scene axis tick lists are limited to 200 values")
    capacity = (
        160
        + len(widths) * 16
        + n * 56
        + 240
        + len(title_b)
        + len(xlabel_b)
        + len(ylabel_b)
        + sum(0 if value is None else len(value) * 8 for value in tick_arrays)
        + len(legend_array)
        + len(colorbar_array)
        + len(x_tick_label_array)
        + len(y_tick_label_array)
        + len(authored_text_array)
    )
    while True:
        out = ctypes.create_string_buffer(capacity)
        written = _lib.xyg_scene_batch_encode(
            viewport[0],
            viewport[1],
            *margins,
            *x_axis,
            *y_axis,
            _ptr_u8(chrome_array),
            len(chrome_array),
            _ptr_f64(x_major) if x_major is not None and len(x_major) else 0,
            0 if x_major is None else len(x_major),
            1 if x_major is None else 0,
            _ptr_f64(x_minor) if len(x_minor) else 0,
            len(x_minor),
            _ptr_f64(y_major) if y_major is not None and len(y_major) else 0,
            0 if y_major is None else len(y_major),
            1 if y_major is None else 0,
            _ptr_f64(y_minor) if len(y_minor) else 0,
            len(y_minor),
            _ptr_u8(x_tick_label_array) if len(x_tick_label_array) else 0,
            len(x_tick_label_array),
            _ptr_u8(y_tick_label_array) if len(y_tick_label_array) else 0,
            len(y_tick_label_array),
            _ptr_u8(authored_text_array) if len(authored_text_array) else 0,
            len(authored_text_array),
            kind_array.ctypes.data if n else 0,
            ids.ctypes.data if n else 0,
            styles.ctypes.data if n else 0,
            _ptr_u8(fills) if len(widths) else 0,
            _ptr_u8(strokes) if len(widths) else 0,
            _ptr_f64(widths) if len(widths) else 0,
            len(widths),
            _ptr_f64(diameters) if n else 0,
            _ptr_u8(symbol_codes) if n else 0,
            _ptr_u8(expansion_mode_codes) if n else 0,
            *(_ptr_f64(value) if n else 0 for value in coordinates),
            n,
            ctypes.c_char_p(title_b) if title_b else None,
            len(title_b),
            ctypes.c_char_p(xlabel_b) if xlabel_b else None,
            len(xlabel_b),
            ctypes.c_char_p(ylabel_b) if ylabel_b else None,
            len(ylabel_b),
            _ptr_u8(legend_array) if len(legend_array) else 0,
            len(legend_array),
            _ptr_u8(colorbar_array) if len(colorbar_array) else 0,
            len(colorbar_array),
            ctypes.addressof(polar_view) if polar_view is not None else 0,
            out,
            capacity,
        )
        if written == _USIZE_MAX:
            raise ValueError("invalid canonical scene batch")
        if written <= capacity:
            return out.raw[:written]
        capacity = written


def _scene_bytes_output(encoded: bytes, function: Any, label: str, *extra: Any) -> bytes:
    source = np.frombuffer(encoded, dtype=np.uint8)
    if not len(source):
        raise ValueError("encoded scene must not be empty")
    capacity = max(256, len(source) * 3)
    while True:
        out = ctypes.create_string_buffer(capacity)
        written = function(_ptr_u8(source), len(source), *extra, out, capacity)
        if written == _USIZE_MAX:
            raise ValueError(f"invalid canonical scene for {label}")
        if written <= capacity:
            return out.raw[:written]
        capacity = written


def scene_svg(encoded: bytes) -> str:
    """Render one validated Scene v12 document as a complete SVG."""
    return _scene_bytes_output(encoded, _lib.xyg_scene_svg, "SVG").decode("utf-8")


def svg_to_pdf(svg: str) -> bytes:
    """Convert an xy-generated closed-subset SVG into a single-page vector PDF.

    Rust owns the converter (M2 #274). Unsupported elements, attributes, and
    path commands raise ``ValueError("unsupported SVG feature: ...")``.
    """
    if not isinstance(svg, str):
        raise TypeError("svg must be a str")
    encoded = svg.encode("utf-8")
    source = np.frombuffer(encoded, dtype=np.uint8)
    n = len(source)
    capacity = max(256, n * 2)
    while True:
        out = ctypes.create_string_buffer(capacity)
        written = _lib.xyg_svg_to_pdf(_ptr_u8(source) if n else 0, n, out, capacity)
        if written == _USIZE_MAX:
            message = out.value.decode("utf-8", "replace") or "unsupported SVG feature"
            raise ValueError(message)
        if written <= capacity:
            return out.raw[:written]
        capacity = written


def _encode_pixels(
    function: Any,
    pixels: np.ndarray,
    extra: tuple[Any, ...] = (),
    *,
    label: str,
) -> bytes:
    if not isinstance(pixels, np.ndarray):
        raise ValueError(f"{label} image must be a numpy array, got {type(pixels).__name__}")
    if pixels.dtype != np.uint8:
        raise ValueError(f"{label} image must be uint8, got {pixels.dtype}")
    if pixels.ndim != 3 or pixels.shape[2] not in (3, 4):
        raise ValueError(
            f"{label} image must be (h, w, 4) RGBA or (h, w, 3) RGB, got {pixels.shape}"
        )
    arr = np.ascontiguousarray(pixels)
    height, width, channels = (int(v) for v in arr.shape)
    n = int(arr.size)
    capacity = max(256, n)
    while True:
        out = ctypes.create_string_buffer(capacity)
        written = function(
            _ptr_u8(arr) if n else 0,
            n,
            width,
            height,
            channels,
            *extra,
            out,
            capacity,
        )
        if written == _USIZE_MAX:
            message = out.value.decode("utf-8", "replace") or f"invalid {label} input"
            raise ValueError(message)
        if written <= capacity:
            return out.raw[:written]
        capacity = written


def encode_jpeg(pixels: np.ndarray, *, quality: int = 90) -> bytes:
    """Encode RGB/RGBA8 pixels as a baseline sequential JFIF JPEG.

    Rust owns YCbCr 4:4:4, Annex K tables, the libjpeg quality curve, and
    Huffman packing (M2 #274). Alpha is ignored.
    """
    if isinstance(quality, bool) or not isinstance(quality, int):
        raise ValueError(f"quality must be an int in 1..100, got {quality!r}")
    return _encode_pixels(_lib.xyg_encode_jpeg, pixels, (int(quality),), label="JPEG")


def encode_webp(pixels: np.ndarray) -> bytes:
    """Encode RGB/RGBA8 pixels as a lossless VP8L WebP.

    Rust owns the simple-lossless subset, length-limited prefix codes, and
    distance-1 run packing (M2 #274). Alpha survives bit-exact.
    """
    return _encode_pixels(_lib.xyg_encode_webp, pixels, label="WebP")


def encode_png(pixels: np.ndarray, *, mode: int = 0, compression: int = 6) -> bytes:
    """Encode RGB/RGBA8 pixels as a PNG.

    Rust owns filter-0 scanlines, zlib IDAT, and indexed-vs-truecolor
    selection (M2 #274). `mode` 0 auto-selects an indexed palette when the
    image has ≤256 unique RGBA colors; `mode` 1 forces truecolor.
    `compression` is the zlib level in ``0..9``.
    """
    if isinstance(mode, bool) or not isinstance(mode, int) or mode not in (0, 1):
        raise ValueError(f"PNG mode must be 0 (auto) or 1 (truecolor), got {mode!r}")
    if isinstance(compression, bool) or not isinstance(compression, int):
        raise ValueError(f"PNG compression must be an int in 0..9, got {compression!r}")
    if not (0 <= compression <= 9):
        raise ValueError(f"PNG compression must be an int in 0..9, got {compression!r}")
    return _encode_pixels(
        _lib.xyg_encode_png,
        pixels,
        (int(mode), int(compression)),
        label="PNG",
    )


def scene_raster_commands(encoded: bytes, scale: float = 1.0) -> bytes:
    """Compile Scene v12 into the existing native raster display list."""
    factor = float(scale)
    if not math.isfinite(factor) or factor <= 0.0:
        raise ValueError("scene raster scale must be positive and finite")
    return _scene_bytes_output(encoded, _lib.xyg_scene_raster_commands, "raster commands", factor)


_SCENE_STATIC_FORMATS = {"svg": 0, "png": 1, "pdf": 2, "jpeg": 3, "webp": 4}


def scene_static_export(
    encoded: bytes,
    format: str,
    *,
    scale: float = 1.0,
    width: int = 1,
    height: int = 1,
    quality: int = 90,
) -> bytes:
    """Render one encoded Scene to a public static format (ABI 164)."""
    code = _SCENE_STATIC_FORMATS.get(format)
    if code is None:
        raise ValueError(
            f"Scene public static format must be svg, png, pdf, jpeg, or webp, got {format!r}"
        )
    if format in {"png", "jpeg", "webp"}:
        factor = float(scale)
        if not math.isfinite(factor) or factor <= 0.0:
            raise ValueError("scene raster scale must be positive and finite")
    else:
        factor = float(scale) if math.isfinite(float(scale)) else 1.0
    width_px = _positive_int(width, "scene static width")
    height_px = _positive_int(height, "scene static height")
    if isinstance(quality, bool) or not isinstance(quality, int):
        raise ValueError(f"quality must be an int in 1..100, got {quality!r}")
    return _scene_bytes_output(
        encoded,
        _lib.xyg_scene_static_export,
        "static export",
        int(code),
        factor,
        width_px,
        height_px,
        int(quality),
    )


def scene_browser_painter(encoded: bytes, max_bytes: int = 64 * 1024 * 1024) -> bytes:
    """Lower Scene v12 through Rust to the canonical painter-v9 stream."""
    limit = int(max_bytes)
    if limit <= 0:
        raise ValueError("scene painter byte limit must be positive")
    return _scene_bytes_output(encoded, _lib.xyg_scene_browser_painter, "browser painter", limit)


def scene_scatter_svg(
    x: npt.ArrayLike,
    y: npt.ArrayLike,
    diameter: npt.ArrayLike,
    fill_rgba: npt.ArrayLike,
    stroke_rgba: npt.ArrayLike,
    stroke_width: npt.ArrayLike,
    symbols: npt.ArrayLike,
    visible: Optional[npt.ArrayLike] = None,
    fill_css: Optional[str] = None,
    stroke_css: Optional[str] = None,
) -> str:
    """Build the versioned built-in scatter scene and serialize its SVG fragment."""
    xa = _as_f64(np.asarray(x), "scene x")
    ya = _as_f64(np.asarray(y), "scene y")
    diameters = _as_f64(np.asarray(diameter), "scene diameter")
    widths = _as_f64(np.asarray(stroke_width), "scene stroke_width")
    symbol_codes = np.ascontiguousarray(symbols, dtype=np.uint8).reshape(-1)
    fills = np.ascontiguousarray(fill_rgba, dtype=np.uint8).reshape(-1)
    strokes = np.ascontiguousarray(stroke_rgba, dtype=np.uint8).reshape(-1)
    n = len(xa)
    expected = {
        "y": len(ya),
        "diameter": len(diameters),
        "stroke_width": len(widths),
        "symbols": len(symbol_codes),
    }
    bad = [name for name, length in expected.items() if length != n]
    if bad or len(fills) != n * 4 or len(strokes) != n * 4:
        raise ValueError("scatter scene arrays must have one record per mark and RGBA rows")
    visibility: Optional[npt.NDArray[np.uint8]] = None
    if visible is not None:
        visibility = np.ascontiguousarray(visible, dtype=np.uint8).reshape(-1)
        if len(visibility) != n:
            raise ValueError("scene visibility must have one value per mark")
    fill_css_bytes = np.frombuffer(fill_css.encode("utf-8"), dtype=np.uint8) if fill_css else None
    stroke_css_bytes = (
        np.frombuffer(stroke_css.encode("utf-8"), dtype=np.uint8) if stroke_css else None
    )

    capacity = max(32, n * 160)
    while True:
        out = ctypes.create_string_buffer(capacity)
        written = _lib.xyg_scene_scatter_svg(
            _ptr_f64(xa) if n else 0,
            _ptr_f64(ya) if n else 0,
            _ptr_f64(diameters) if n else 0,
            _ptr_u8(fills) if n else 0,
            _ptr_u8(strokes) if n else 0,
            _ptr_f64(widths) if n else 0,
            _ptr_u8(symbol_codes) if n else 0,
            _ptr_u8(visibility) if visibility is not None and n else 0,
            _ptr_u8(fill_css_bytes) if fill_css_bytes is not None else 0,
            len(fill_css_bytes) if fill_css_bytes is not None else 0,
            _ptr_u8(stroke_css_bytes) if stroke_css_bytes is not None else 0,
            len(stroke_css_bytes) if stroke_css_bytes is not None else 0,
            n,
            out,
            capacity,
        )
        if written == _USIZE_MAX:
            raise ValueError("invalid canonical scatter scene")
        if written <= capacity:
            return out.raw[:written].decode("ascii")
        capacity = written


def marching_squares(
    z: npt.NDArray[np.float64],
    x_coords: npt.NDArray[np.float64],
    y_coords: npt.NDArray[np.float64],
    levels: npt.NDArray[np.float64],
    *,
    corner_mask: bool = False,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Extract regular-grid contour segments with native marching squares."""
    z = np.ascontiguousarray(z, dtype=np.float64)
    x_coords = _as_f64(x_coords, "x_coords")
    y_coords = _as_f64(y_coords, "y_coords")
    levels = _as_f64(levels, "levels")
    if z.ndim != 2 or min(z.shape) < 2:
        raise ValueError(f"z must be a 2-D array with at least 2 rows/columns, got {z.shape}")
    rows, cols = z.shape
    if len(x_coords) != cols or len(y_coords) != rows:
        raise ValueError("coordinate arrays must match the z grid dimensions")
    if (
        not np.isfinite(x_coords).all()
        or not np.isfinite(y_coords).all()
        or not np.isfinite(levels).all()
    ):
        raise ValueError("coordinates and levels must be finite")
    if not np.all(np.diff(x_coords) > 0) or not np.all(np.diff(y_coords) > 0):
        raise ValueError("coordinate arrays must be strictly increasing")
    if len(levels) == 0:
        empty = np.empty(0, dtype=np.float64)
        return empty, empty.copy(), empty.copy(), empty.copy(), empty.copy()
    work = (rows - 1) * (cols - 1) * len(levels)
    if work > MAX_CONTOUR_WORK:
        raise ValueError(
            f"marching_squares grid x levels exceeds the bounded work budget ({MAX_CONTOUR_WORK:,})"
        )
    # Most smooth fields emit O(perimeter × levels) segments, far below the
    # two-per-cell theoretical maximum. Start with that exact-output capacity
    # and exploit the kernel's required-count return to retry only adversarial
    # checkerboards. This removes the unconditional full count-only scan.
    maximum = 2 * work
    capacity = min(maximum, max(64, 2 * (rows + cols) * len(levels)))

    def allocate(
        size: int,
    ) -> tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ]:
        return (
            np.empty(size, dtype=np.float64),
            np.empty(size, dtype=np.float64),
            np.empty(size, dtype=np.float64),
            np.empty(size, dtype=np.float64),
            np.empty(size, dtype=np.float64),
        )

    def extract(outputs: tuple[npt.NDArray[np.float64], ...]) -> int:
        return int(
            _lib.xyg_marching_squares(
                _ptr_f64(z),
                rows,
                cols,
                _ptr_f64(x_coords),
                _ptr_f64(y_coords),
                _ptr_f64(levels),
                len(levels),
                int(bool(corner_mask)),
                *(_ptr_f64(output) for output in outputs),
                len(outputs[0]),
            )
        )

    outputs = allocate(capacity)
    written = extract(outputs)
    if written == _USIZE_MAX or written > maximum:
        raise ValueError("invalid marching_squares arguments")
    if written > capacity:
        outputs = allocate(written)
        repeated = extract(outputs)
        if repeated != written:
            raise RuntimeError("native marching_squares returned an inconsistent segment count")
    return (
        outputs[0][:written],
        outputs[1][:written],
        outputs[2][:written],
        outputs[3][:written],
        outputs[4][:written],
    )


def bin_2d(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    w: int,
    h: int,
) -> npt.NDArray[np.float32]:
    """2D density grid (h, w) f32, row 0 = bottom — §5 Tier 2."""
    w = _bounded_positive_int(w, "w")
    h = _bounded_positive_int(h, "h")
    x0, x1 = _finite_increasing(x0, x1, "x range")
    y0, y1 = _finite_increasing(y0, y1, "y range")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    out = np.zeros((h, w), dtype=np.float32)
    if len(x):
        ok = _lib.xyg_bin_2d(
            _ptr_f64(x),
            _ptr_f64(y),
            len(x),
            x0,
            x1,
            y0,
            y1,
            w,
            h,
            out.ctypes.data,
        )
        if not ok:
            raise ValueError("invalid bin_2d arguments")
    return out


def bin_2d_f32(
    x: npt.NDArray[np.float32],
    y: npt.NDArray[np.float32],
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    w: int,
    h: int,
) -> npt.NDArray[np.float32]:
    """2D density grid from f32 inputs — the out-of-core spatial-index path.

    Same result as :func:`bin_2d` over the same points cast to f64, but bins the
    memmap'd f32 columns directly (no f64 widening copy, which otherwise
    dominates a windowed gather). Row 0 = bottom (§5 Tier 2)."""
    w = _bounded_positive_int(w, "w")
    h = _bounded_positive_int(h, "h")
    x0, x1 = _finite_increasing(x0, x1, "x range")
    y0, y1 = _finite_increasing(y0, y1, "y range")
    x = np.ascontiguousarray(x, dtype=np.float32)
    y = np.ascontiguousarray(y, dtype=np.float32)
    if x.ndim != 1 or y.ndim != 1:
        raise ValueError("x and y must be 1-D")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    out = np.zeros((h, w), dtype=np.float32)
    if len(x):
        ok = _lib.xyg_bin_2d_f32(
            x.ctypes.data,
            y.ctypes.data,
            len(x),
            x0,
            x1,
            y0,
            y1,
            w,
            h,
            out.ctypes.data,
        )
        if not ok:
            raise ValueError("invalid bin_2d_f32 arguments")
    return out


def _color_source_args(
    n: int,
    idx: "npt.NDArray[np.uint8] | None",
    rgba: "npt.NDArray[np.uint8] | None",
    lut: "npt.NDArray[np.uint8] | None",
) -> tuple:
    """Validate and marshal a mean-color source: exactly one of `idx`
    (per-point LUT index + `lut` of 1..=256 RGBA8 rows) or `rgba` (per-point
    straight-alpha RGBA8). Returns the four C arguments plus the arrays kept
    alive through the call."""
    if (idx is None) == (rgba is None):
        raise ValueError("exactly one of idx or rgba must be provided")
    if idx is not None:
        idx = np.ascontiguousarray(idx, dtype=np.uint8)
        if idx.shape != (n,):
            raise ValueError(f"idx must be 1-D length {n}, got shape {idx.shape}")
        if lut is None:
            raise ValueError("idx colors need a lut")
        lut = np.ascontiguousarray(lut, dtype=np.uint8)
        if lut.ndim != 2 or lut.shape[1] != 4 or not 1 <= lut.shape[0] <= 256:
            raise ValueError(f"lut must be (1..=256, 4) u8, got shape {lut.shape}")
        return idx.ctypes.data, None, lut.ctypes.data, lut.shape[0], (idx, lut)
    rgba = np.ascontiguousarray(rgba, dtype=np.uint8)
    if rgba.shape not in {(n, 4), (n * 4,)}:
        raise ValueError(f"rgba must be ({n}, 4) u8, got shape {rgba.shape}")
    return None, rgba.ctypes.data, None, 0, (rgba,)


def bin_2d_mean_color(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    w: int,
    h: int,
    *,
    idx: "npt.NDArray[np.uint8] | None" = None,
    rgba: "npt.NDArray[np.uint8] | None" = None,
    lut: "npt.NDArray[np.uint8] | None" = None,
) -> npt.NDArray[np.uint8]:
    """Mean-color companion grid to `bin_2d` (§5 Tier 2, LOD doc §2): (h, w, 4)
    straight-alpha RGBA8, row 0 = bottom. Each occupied cell carries the
    alpha-weighted mean of its points' resolved colors (averaged in linear
    light) and the plain mean of their straight alpha; cell membership is
    bit-identical to `bin_2d`."""
    w = _bounded_positive_int(w, "w")
    h = _bounded_positive_int(h, "h")
    x0, x1 = _finite_increasing(x0, x1, "x range")
    y0, y1 = _finite_increasing(y0, y1, "y range")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    idx_ptr, rgba_ptr, lut_ptr, lut_len, _keepalive = _color_source_args(len(x), idx, rgba, lut)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    if len(x):
        ok = _lib.xyg_bin_2d_mean_color(
            _ptr_f64(x),
            _ptr_f64(y),
            len(x),
            idx_ptr,
            rgba_ptr,
            lut_ptr,
            lut_len,
            x0,
            x1,
            y0,
            y1,
            w,
            h,
            out.ctypes.data,
        )
        if not ok:
            raise ValueError("invalid bin_2d_mean_color arguments")
    return out


def bin_2d_indices(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    w: int,
    h: int,
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.uint32]]:
    """Fused density scan: `(bin_2d grid, range_indices rows)` in one pass.

    Each output is bitwise identical to its standalone kernel (asserted by the
    parity test); fusing halves the column traffic on the Tier-2 density path,
    which reads the full x/y columns twice otherwise.
    """
    w = _bounded_positive_int(w, "w")
    h = _bounded_positive_int(h, "h")
    x0, x1 = _finite_increasing(x0, x1, "x range")
    y0, y1 = _finite_increasing(y0, y1, "y range")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    grid = np.zeros((h, w), dtype=np.float32)
    idx = np.empty(len(x), dtype=np.uint32)
    if len(x) == 0:
        return grid, idx
    written = _lib.xyg_bin_2d_indices(
        _ptr_f64(x),
        _ptr_f64(y),
        len(x),
        x0,
        x1,
        y0,
        y1,
        w,
        h,
        grid.ctypes.data,
        idx.ctypes.data,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid bin_2d_indices arguments")
    # First paint autoranges to the data extent, so every finite row is
    # usually in range: avoid duplicating the full selection when no slack
    # needs trimming.
    return grid, idx if written == len(idx) else idx[:written].copy()


def bin_2d_sample_range(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    w: int,
    h: int,
    seed: int,
    threshold: int,
    capacity_hint: int,
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.uint32]]:
    """Return the exact density grid and implicit-row sample in one scan."""
    w = _bounded_positive_int(w, "w")
    h = _bounded_positive_int(h, "h")
    x0, x1 = _finite_increasing(x0, x1, "x range")
    y0, y1 = _finite_increasing(y0, y1, "y range")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    seed = _bounded_nonnegative_int(seed, "seed", max_value=np.iinfo(np.uint64).max)
    threshold = _bounded_nonnegative_int(threshold, "threshold", max_value=np.iinfo(np.uint64).max)
    capacity = _bounded_nonnegative_int(capacity_hint, "capacity_hint", max_value=len(x))
    grid = np.zeros((h, w), dtype=np.float32)
    rows = np.empty(capacity, dtype=np.uint32)

    def extract(output: npt.NDArray[np.uint32]) -> int:
        return int(
            _lib.xyg_bin_2d_sample_range(
                _ptr_f64(x),
                _ptr_f64(y),
                len(x),
                x0,
                x1,
                y0,
                y1,
                w,
                h,
                ctypes.c_uint64(int(seed)),
                ctypes.c_uint64(int(threshold)),
                grid.ctypes.data,
                output.ctypes.data if len(output) else None,
                len(output),
            )
        )

    written = extract(rows)
    if written == _USIZE_MAX:
        raise ValueError("invalid bin_2d_sample_range arguments")
    if written > capacity:
        rows = np.empty(written, dtype=np.uint32)
        repeated = extract(rows)
        if repeated != written:
            raise RuntimeError("native bin_2d_sample_range returned an inconsistent count")
    return grid, rows[:written]


def bin_2d_stratified_sample_range_u8_counted(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    groups: npt.NDArray[np.uint8],
    counts: npt.NDArray[np.uint64],
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    w: int,
    h: int,
    seed: int,
    fraction: float,
    min_count: int,
    capacity_hint: int,
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.uint32]]:
    """Return the exact density grid and counted u8 stratified sample."""
    w = _bounded_positive_int(w, "w")
    h = _bounded_positive_int(h, "h")
    x0, x1 = _finite_increasing(x0, x1, "x range")
    y0, y1 = _finite_increasing(y0, y1, "y range")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    groups = np.asarray(groups)
    if groups.ndim != 1 or groups.dtype != np.uint8 or len(groups) != len(x):
        raise ValueError("groups must be a one-dimensional uint8 array matching x and y")
    groups = np.ascontiguousarray(groups)
    counts = np.asarray(counts)
    if counts.ndim != 1 or counts.dtype != np.uint64 or not 1 <= len(counts) <= 256:
        raise ValueError("counts must be a one-dimensional uint64 array of length 1..256")
    counts = np.ascontiguousarray(counts)
    seed = _bounded_nonnegative_int(seed, "seed", max_value=np.iinfo(np.uint64).max)
    fraction = _finite_float(fraction, "fraction")
    if fraction <= 0.0:
        raise ValueError("fraction must be > 0")
    min_count = _bounded_nonnegative_int(min_count, "min_count", max_value=np.iinfo(np.uint64).max)
    capacity = _bounded_nonnegative_int(capacity_hint, "capacity_hint", max_value=len(x))
    grid = np.zeros((h, w), dtype=np.float32)
    rows = np.empty(capacity, dtype=np.uint32)

    def extract(output: npt.NDArray[np.uint32]) -> int:
        return int(
            _lib.xyg_bin_2d_stratified_sample_range_u8_counted(
                _ptr_f64(x),
                _ptr_f64(y),
                groups.ctypes.data if len(groups) else None,
                len(x),
                counts.ctypes.data,
                len(counts),
                x0,
                x1,
                y0,
                y1,
                w,
                h,
                ctypes.c_uint64(seed),
                ctypes.c_double(fraction),
                ctypes.c_uint64(min_count),
                grid.ctypes.data,
                output.ctypes.data if len(output) else None,
                len(output),
            )
        )

    written = extract(rows)
    if written == _USIZE_MAX:
        raise ValueError("invalid bin_2d_stratified_sample_range_u8_counted arguments or codes")
    if written > capacity:
        rows = np.empty(written, dtype=np.uint32)
        repeated = extract(rows)
        if repeated != written:
            raise RuntimeError("native categorical bin/sample returned an inconsistent count")
    return grid, rows[:written]


def is_sorted(data: npt.NDArray[np.float64]) -> bool:
    """Non-decreasing check with NaN-poisoning (any NaN fails its pairs) —
    identical to ``np.all(np.diff(data) >= 0)`` without the two temporaries."""
    data = _as_f64(data, "data")
    if len(data) < 2:
        return True
    return bool(_lib.xyg_is_sorted(_ptr_f64(data), len(data)))


def argsort_stable(data: npt.NDArray[np.float64]) -> npt.NDArray[np.uint32]:
    """Stable argsort (NaNs last) matching ``np.argsort(..., kind="stable")``."""
    data = _as_f64(data, "data")
    n = len(data)
    if n == 0:
        return np.empty(0, dtype=np.uint32)
    out = np.empty(n, dtype=np.uint32)
    written = _lib.xyg_argsort_stable(_ptr_f64(data), n, out.ctypes.data, n)
    if written != n:
        raise ValueError("invalid argsort_stable arguments")
    return out


def min_max(data: npt.NDArray[np.float64]) -> Optional[tuple[float, float]]:
    """NaN-skipping min/max; None for empty/all-NaN input."""
    data = _as_f64(data, "data")
    if len(data) == 0:
        return None
    lo = ctypes.c_double()
    hi = ctypes.c_double()
    ok = _lib.xyg_min_max(_ptr_f64(data), len(data), ctypes.byref(lo), ctypes.byref(hi))
    return (lo.value, hi.value) if ok else None


def continuous_domain(data: npt.NDArray[np.float64]) -> tuple[float, float]:
    """Continuous color/size domain via ``xyg_continuous_domain`` (ABI 213)."""
    data = _as_f64(data, "data")
    n = len(data)
    lo = ctypes.c_double()
    hi = ctypes.c_double()
    code = int(
        _lib.xyg_continuous_domain(
            _ptr_f64(data) if n else 0,
            n,
            ctypes.byref(lo),
            ctypes.byref(hi),
        )
    )
    if code != 0:
        raise ValueError("invalid continuous-domain request")
    return (float(lo.value), float(hi.value))


def direct_rgba_admit(
    values: npt.NDArray[np.float64],
    components: int,
) -> npt.NDArray[np.float64]:
    """Admit per-point RGB/RGBA in ``[0, 1]`` as contiguous Nx4 (ABI 213)."""
    values = _as_f64(values, "direct rgba")
    components = int(components)
    if components not in (3, 4):
        raise ValueError("direct RGB/RGBA colors must be 3 or 4 components")
    if values.size % components != 0:
        raise ValueError("direct RGB/RGBA colors must be a multiple of the component count")
    n = int(values.size // components)
    probed = _lib.xyg_direct_rgba_admit(
        _ptr_f64(values) if n else 0,
        n,
        components,
        0,
        0,
    )
    if probed == _USIZE_MAX:
        raise ValueError("direct RGB/RGBA colors must contain finite values between 0 and 1")
    count = int(probed)
    if count == 0:
        return np.empty(0, dtype=np.float64)
    out = np.empty(count, dtype=np.float64)
    written = _lib.xyg_direct_rgba_admit(
        _ptr_f64(values) if n else 0,
        n,
        components,
        _ptr_f64(out),
        count,
    )
    if written == _USIZE_MAX or written != count:
        raise ValueError("direct RGB/RGBA colors must contain finite values between 0 and 1")
    return out


def histogram_uniform(
    data: npt.NDArray[np.float64],
    lo: float,
    hi: float,
    n_bins: int,
    *,
    density: bool = False,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Uniform fixed-bin histogram — one Rust pass, no finite temp copy."""
    n_bins = _bounded_positive_int(n_bins, "n_bins")
    lo, hi = _finite_increasing(lo, hi, "histogram range")
    data = _as_f64(data, "data")
    counts = np.empty(n_bins, dtype=np.float64)
    written = _lib.xyg_histogram_uniform(
        _ptr_f64(data),
        len(data),
        lo,
        hi,
        n_bins,
        int(density),
        _ptr_f64(counts),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid histogram arguments")
    edges = np.linspace(lo, hi, n_bins + 1, dtype=np.float64)
    return counts, edges


def histogram_bins(
    data: npt.NDArray[np.float64],
    edges: npt.NDArray[np.float64],
    *,
    density: bool = False,
    cumulative: bool = False,
) -> npt.NDArray[np.float64]:
    """Authored-edge histogram counts with Rust-owned density/cumulative modes."""
    data = _as_f64(data, "data")
    edges = _as_f64(edges, "edges")
    if edges.ndim != 1 or not 2 <= len(edges) <= 10_001:
        raise ValueError("histogram edges must contain 2 through 10,001 values")
    counts = np.empty(len(edges) - 1, dtype=np.float64)
    written = _lib.xyg_histogram_bins(
        _ptr_f64(data),
        len(data),
        _ptr_f64(edges),
        len(edges),
        int(bool(density)),
        int(bool(cumulative)),
        _ptr_f64(counts),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid histogram_bins arguments")
    return counts


def normalize_f32(
    data: npt.NDArray[np.float64],
    domain: tuple[float, float],
    *,
    nonfinite: str = "zero",
) -> npt.NDArray[np.float32]:
    """Normalize to f32 [0,1]. nonfinite='zero' or 'nan'."""
    if nonfinite not in {"zero", "nan"}:
        raise ValueError("nonfinite must be 'zero' or 'nan'")
    data = _as_f64(data, "data")
    try:
        lo_raw, hi_raw = domain
    except (TypeError, ValueError) as e:
        raise ValueError("domain must contain exactly two finite increasing values") from e
    lo, hi = _finite_increasing(lo_raw, hi_raw, "domain")
    out = np.empty(len(data), dtype=np.float32)
    nan_mode = 1 if nonfinite == "nan" else 0
    if len(data):
        ok = _lib.xyg_normalize_f32(_ptr_f64(data), len(data), lo, hi, nan_mode, out.ctypes.data)
        if ok != 1:
            raise RuntimeError("xyg native normalize_f32 failed (output undefined)")
    return out


def valid_indices_f64(
    columns: tuple[npt.NDArray[np.float64], ...],
    *,
    positive_columns: tuple[int, ...] = (),
) -> Optional[npt.NDArray[np.uint32]]:
    """Rows finite across every column, or ``None`` when every row is valid.

    ``positive_columns`` additionally requires ``> 0`` for those zero-based
    column positions. The all-valid path is one allocation-free Rust scan;
    only a filtered result allocates row IDs.
    """
    if not 1 <= len(columns) <= 64:
        raise ValueError("columns must contain between 1 and 64 arrays")
    arrays = tuple(_as_f64(column, f"columns[{index}]") for index, column in enumerate(columns))
    size = len(arrays[0])
    if any(len(array) != size for array in arrays[1:]):
        raise ValueError("validity columns must have equal length")
    positive_mask = 0
    for column in positive_columns:
        column = _bounded_nonnegative_int(column, "positive column", max_value=len(arrays) - 1)
        positive_mask |= 1 << column
    pointer_array_type = ctypes.c_void_p * len(arrays)
    pointers = pointer_array_type(*(array.ctypes.data if size else None for array in arrays))

    def invoke(output: npt.NDArray[np.uint32] | None) -> int:
        return int(
            _lib.xyg_valid_indices_f64(
                pointers,
                len(arrays),
                size,
                ctypes.c_uint64(positive_mask),
                output.ctypes.data if output is not None and len(output) else None,
                len(output) if output is not None else 0,
            )
        )

    written = invoke(None)
    if written == _USIZE_MAX or written > size:
        raise ValueError("invalid valid_indices_f64 arguments")
    if written == size:
        return None
    # A source-sized scratch lets Rust workers fill disjoint row-aligned
    # segments and compact in parallel. Shrink before returning so callers do
    # not retain N-row storage for a small filtered result.
    output = np.empty(size, dtype=np.uint32)
    repeated = invoke(output)
    if repeated != written:
        raise RuntimeError("native valid_indices_f64 returned an inconsistent count")
    return output[:written].copy()


def range_indices(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    lo_x: float,
    hi_x: float,
    lo_y: float,
    hi_y: float,
) -> npt.NDArray[np.uint32]:
    """Canonical row indices in an inclusive rectangular window."""
    lo_x, hi_x = _finite_ordered(lo_x, hi_x, "x range")
    lo_y, hi_y = _finite_ordered(lo_y, hi_y, "y range")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    out = np.empty(len(x), dtype=np.uint32)
    if len(x) == 0:
        return out
    written = _lib.xyg_range_indices(
        _ptr_f64(x),
        _ptr_f64(y),
        len(x),
        lo_x,
        hi_x,
        lo_y,
        hi_y,
        out.ctypes.data,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid range_indices arguments")
    return out if written == len(out) else out[:written].copy()


def range_indices_rows(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    rows: npt.NDArray[np.uint32],
    lo_x: float,
    hi_x: float,
    lo_y: float,
    hi_y: float,
) -> npt.NDArray[np.uint32]:
    """Those of `rows` whose canonical point is in the inclusive window.

    The row-restricted form of `range_indices`, shaped like `polygon_select`.
    A caller that already knows its candidate rows (zone-map pruning, a drill
    window) reads them in place instead of gathering `x[rows]`/`y[rows]` into
    two fresh f64 columns first.
    """
    lo_x, hi_x = _finite_ordered(lo_x, hi_x, "x range")
    lo_y, hi_y = _finite_ordered(lo_y, hi_y, "y range")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    rows = _as_row_ids(rows)
    out = np.empty(len(rows), dtype=np.uint32)
    if len(rows) == 0:
        return out
    written = _lib.xyg_range_indices_rows(
        _ptr_f64(x),
        _ptr_f64(y),
        len(x),
        rows.ctypes.data,
        len(rows),
        lo_x,
        hi_x,
        lo_y,
        hi_y,
        out.ctypes.data,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid range_indices_rows arguments")
    return out if written == len(out) else out[:written].copy()


def polygon_select(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    rows: npt.NDArray[np.uint32],
    poly_x: npt.NDArray[np.float64],
    poly_y: npt.NDArray[np.float64],
) -> npt.NDArray[np.uint32]:
    """Those of `rows` whose canonical point is inside the lasso polygon.

    Even-odd ray casting, order preserved. Non-finite coordinates are never
    inside, matching `range_indices`."""
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    poly_x = _as_f64(poly_x, "polygon x")
    poly_y = _as_f64(poly_y, "polygon y")
    if len(poly_x) != len(poly_y):
        raise ValueError("polygon x and y must have equal length")
    rows = _as_row_ids(rows)
    out = np.empty(len(rows), dtype=np.uint32)
    if len(rows) == 0:
        return out
    written = _lib.xyg_polygon_select(
        _ptr_f64(x),
        _ptr_f64(y),
        len(x),
        rows.ctypes.data,
        len(rows),
        _ptr_f64(poly_x),
        _ptr_f64(poly_y),
        len(poly_x),
        out.ctypes.data,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid polygon_select arguments")
    return out if written == len(out) else out[:written].copy()


def sample_mask(
    ids: npt.NDArray[np.uint64],
    seed: int,
    threshold: int,
) -> npt.NDArray[np.bool_]:
    """Deterministic sampling mask: `splitmix64(ids + seed) <= threshold`.

    Bit-identical to `lod.hash_row_ids(ids, seed=seed) <= threshold` (the
    NumPy reference, asserted by the parity test), fused into one native pass
    with no full-width u64 temporaries. uint32 ids dispatch to an entry point
    that widens each id in-register instead of copying the full selection.
    """
    ids = np.asarray(ids)
    if ids.dtype == np.uint32:
        ids = np.ascontiguousarray(ids)
        fn = _lib.xyg_sample_mask_u32
    else:
        ids = np.ascontiguousarray(ids, dtype=np.uint64)
        fn = _lib.xyg_sample_mask
    if ids.ndim != 1:
        raise ValueError("ids must be a one-dimensional uint64 array")
    out = np.empty(len(ids), dtype=np.uint8)
    if len(ids):
        ok = fn(
            ids.ctypes.data,
            len(ids),
            ctypes.c_uint64(int(seed)),
            ctypes.c_uint64(int(threshold)),
            out.ctypes.data,
        )
        if ok != 1:
            raise RuntimeError("xyg native sample_mask failed (output undefined)")
    return out.view(np.bool_)


def sample_range_indices(
    size: int,
    seed: int,
    threshold: int,
    capacity_hint: int,
) -> npt.NDArray[np.uint32]:
    """Sample implicit ids ``0..size`` without an input array or mask."""
    size = _bounded_nonnegative_int(size, "size", max_value=np.iinfo(np.uint32).max)
    capacity = _bounded_nonnegative_int(capacity_hint, "capacity_hint", max_value=size)
    out = np.empty(capacity, dtype=np.uint32)
    written = _lib.xyg_sample_range_indices(
        size,
        ctypes.c_uint64(int(seed)),
        ctypes.c_uint64(int(threshold)),
        out.ctypes.data if capacity else None,
        capacity,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid sample_range_indices arguments")
    if written > capacity:
        out = np.empty(written, dtype=np.uint32)
        repeated = _lib.xyg_sample_range_indices(
            size,
            ctypes.c_uint64(int(seed)),
            ctypes.c_uint64(int(threshold)),
            out.ctypes.data,
            written,
        )
        if repeated != written:
            raise RuntimeError("native sample_range_indices returned an inconsistent count")
    return out[:written]


def stratified_sample_range_u8(
    groups: npt.NDArray[np.uint8],
    n_groups: int,
    seed: int,
    fraction: float,
    min_count: int,
    capacity_hint: int,
    counts: npt.NDArray[np.uint64] | None = None,
) -> npt.NDArray[np.uint32]:
    """Stratified sample of implicit ids ``0..len(groups)``.

    This is equivalent to materializing the ids and a stratified keep mask,
    but its temporary memory scales with the returned sample.
    """
    groups = np.asarray(groups)
    if groups.ndim != 1 or groups.dtype != np.uint8:
        raise ValueError("groups must be a one-dimensional uint8 array")
    groups = np.ascontiguousarray(groups)
    n_groups = _bounded_positive_int(n_groups, "n_groups", 256)
    fraction = _finite_float(fraction, "fraction")
    if fraction <= 0.0:
        raise ValueError("fraction must be > 0")
    min_count = _bounded_nonnegative_int(min_count, "min_count", np.iinfo(np.uint64).max)
    capacity = _bounded_nonnegative_int(capacity_hint, "capacity_hint", len(groups))
    if counts is not None:
        counts = np.asarray(counts)
        if counts.ndim != 1 or counts.dtype != np.uint64 or len(counts) != n_groups:
            raise ValueError("counts must be a uint64 array with one value per group")
        counts = np.ascontiguousarray(counts)

    def invoke(out_pointer: int | None, out_capacity: int) -> int:
        if counts is None:
            return int(
                _lib.xyg_stratified_sample_range_u8(
                    groups.ctypes.data if len(groups) else None,
                    len(groups),
                    n_groups,
                    ctypes.c_uint64(int(seed)),
                    ctypes.c_double(fraction),
                    ctypes.c_uint64(min_count),
                    out_pointer,
                    out_capacity,
                )
            )
        return int(
            _lib.xyg_stratified_sample_range_u8_counted(
                groups.ctypes.data if len(groups) else None,
                len(groups),
                counts.ctypes.data,
                n_groups,
                ctypes.c_uint64(int(seed)),
                ctypes.c_double(fraction),
                ctypes.c_uint64(min_count),
                out_pointer,
                out_capacity,
            )
        )

    out = np.empty(capacity, dtype=np.uint32)
    written = invoke(out.ctypes.data if capacity else None, capacity)
    if written == _USIZE_MAX:
        detail = "counts or group code" if counts is not None else "arguments or group code"
        raise ValueError(f"invalid stratified_sample_range_u8 {detail}")
    if written > capacity:
        out = np.empty(written, dtype=np.uint32)
        repeated = invoke(out.ctypes.data, written)
        if repeated != written:
            raise RuntimeError("native stratified_sample_range_u8 returned an inconsistent count")
    return out[:written]


def stratified_sample_mask(
    ids: npt.NDArray[np.uint64],
    groups: npt.NDArray[np.uint32],
    n_groups: int,
    seed: int,
    fraction: float,
    min_count: int,
) -> npt.NDArray[np.bool_]:
    """Category-stratified deterministic sampling mask (§5/§17).

    Per-category keep fractions scale as `min(1, fraction * sqrt(n / count))`
    with a `min_count` lowest-hash floor per category. Bit-identical to the
    per-category NumPy reference in `xyg.lod` (asserted by the parity
    test), fused into one native pass instead of O(n · n_groups) rescans.
    uint32 ids dispatch to the in-register widening entry point.
    """
    ids = np.asarray(ids)
    if ids.dtype == np.uint32:
        ids = np.ascontiguousarray(ids)
        fn = _lib.xyg_stratified_sample_mask_u32
    else:
        ids = np.ascontiguousarray(ids, dtype=np.uint64)
        fn = _lib.xyg_stratified_sample_mask
    groups = np.ascontiguousarray(groups, dtype=np.uint32)
    if ids.ndim != 1 or groups.ndim != 1:
        raise ValueError("ids and groups must be one-dimensional arrays")
    if len(ids) != len(groups):
        raise ValueError("ids and groups must have equal length")
    n_groups = _positive_int(n_groups, "n_groups")
    fraction = _finite_float(fraction, "fraction")
    if fraction <= 0.0:
        raise ValueError("fraction must be > 0")
    if isinstance(min_count, (bool, np.bool_)):
        raise ValueError("min_count must be a non-negative integer")
    min_count = operator.index(min_count)
    if min_count < 0:
        raise ValueError("min_count must be a non-negative integer")
    out = np.empty(len(ids), dtype=np.uint8)
    if len(ids):
        ok = fn(
            ids.ctypes.data,
            groups.ctypes.data,
            len(ids),
            n_groups,
            ctypes.c_uint64(int(seed)),
            ctypes.c_double(fraction),
            ctypes.c_uint64(min_count),
            out.ctypes.data,
        )
        if ok != 1:
            raise ValueError(
                "invalid stratified_sample_mask arguments (group codes must be < n_groups)"
            )
    return out.view(np.bool_)


def _stream_handle(value: int) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("stream handle must be an integer handle")
    try:
        out = operator.index(value)
    except TypeError as e:
        raise ValueError("stream handle must be an integer handle") from e
    if out < 0:
        raise ValueError("stream handle must be non-negative")
    return int(out)


def stream_new(data: "npt.NDArray[np.float64] | None" = None) -> int:
    """Create a Rust-owned canonical f64 stream. Empty when `data` is omitted."""
    arr = np.empty(0, dtype=np.float64) if data is None else _as_f64(data, "data")
    handle = int(_lib.xyg_stream_new(_ptr_f64(arr) if len(arr) else None, len(arr)))
    if handle == 0:
        raise ValueError("xyg_stream_new failed")
    return handle


def stream_append(handle: int, data: "npt.NDArray[np.float64]") -> None:
    handle = _stream_handle(handle)
    arr = _as_f64(data, "data")
    ok = _lib.xyg_stream_append(
        ctypes.c_uint64(handle),
        _ptr_f64(arr) if len(arr) else None,
        len(arr),
    )
    if ok != 1:
        raise ValueError("stale or busy stream handle")


def stream_seal(handle: int) -> None:
    handle = _stream_handle(handle)
    if _lib.xyg_stream_seal(ctypes.c_uint64(handle)) != 1:
        raise ValueError("stale or busy stream handle")


def stream_free(handle: int) -> bool:
    handle = _stream_handle(handle)
    return _lib.xyg_stream_free(ctypes.c_uint64(handle)) == 1


def stream_len(handle: int) -> int:
    handle = _stream_handle(handle)
    n = int(_lib.xyg_stream_len(ctypes.c_uint64(handle)))
    if n == _USIZE_MAX:
        raise ValueError("stale stream handle")
    return n


def stream_capacity(handle: int) -> int:
    handle = _stream_handle(handle)
    n = int(_lib.xyg_stream_capacity(ctypes.c_uint64(handle)))
    if n == _USIZE_MAX:
        raise ValueError("stale stream handle")
    return n


def stream_view(handle: int) -> npt.NDArray[np.float64]:
    """Zero-copy NumPy view of the Rust-owned buffer. Invalid after realloc."""
    handle = _stream_handle(handle)
    ptr = ctypes.c_void_p()
    n = ctypes.c_size_t()
    ok = _lib.xyg_stream_data(ctypes.c_uint64(handle), ctypes.byref(ptr), ctypes.byref(n))
    if ok != 1:
        raise ValueError("stale stream handle")
    if n.value == 0:
        return np.empty(0, dtype=np.float64)
    addr = ptr.value
    if addr is None:
        raise ValueError("stale stream handle")
    buf = (ctypes.c_double * n.value).from_address(addr)
    arr = np.frombuffer(buf, dtype=np.float64)
    with contextlib.suppress(ValueError):
        arr.flags.writeable = True
    return arr


def stream_copy(handle: int) -> npt.NDArray[np.float64]:
    handle = _stream_handle(handle)
    n = stream_len(handle)
    out = np.empty(n, dtype=np.float64)
    ok = _lib.xyg_stream_copy(
        ctypes.c_uint64(handle),
        _ptr_f64(out) if n else None,
        n,
    )
    if ok != 1:
        raise ValueError("stale stream handle")
    return out


def stream_zone_maps(
    handle: int,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.uint64],
    npt.NDArray[np.uint64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    """Sealed zone maps, same 8-tuple as `zone_maps`."""
    handle = _stream_handle(handle)
    n = stream_len(handle)
    n_chunks = 0 if n == 0 else -(-n // 65_536)
    if n_chunks == 0:
        empty_f = np.empty(0, dtype=np.float64)
        empty_u = np.empty(0, dtype=np.uint64)
        return (
            empty_f,
            empty_f,
            empty_u,
            empty_u,
            empty_f.copy(),
            empty_f.copy(),
            empty_f.copy(),
            empty_f.copy(),
        )
    f64_rows = np.empty((6, n_chunks), dtype=np.float64)
    u64_rows = np.empty((2, n_chunks), dtype=np.uint64)
    f64_ptr = f64_rows.ctypes.data
    u64_ptr = u64_rows.ctypes.data
    row_bytes = n_chunks * 8
    written = _lib.xyg_stream_zone_maps(
        ctypes.c_uint64(handle),
        f64_ptr,
        f64_ptr + row_bytes,
        u64_ptr,
        u64_ptr + row_bytes,
        f64_ptr + 2 * row_bytes,
        f64_ptr + 3 * row_bytes,
        f64_ptr + 4 * row_bytes,
        f64_ptr + 5 * row_bytes,
    )
    if written == _USIZE_MAX:
        raise ValueError("stale stream handle or stream is not sealed")
    if written != n_chunks:
        raise RuntimeError(f"xyg_stream_zone_maps wrote {written} chunks, expected {n_chunks}")
    mins, maxs, sums, sum_sqs, positive_mins, positive_maxs = f64_rows
    counts, nulls = u64_rows
    return mins, maxs, counts, nulls, sums, sum_sqs, positive_mins, positive_maxs


def pyramid_build_from_stream(
    x_handle: int,
    y_handle: int,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    base_dim: int,
) -> int:
    """Build a count pyramid from two stream handles (no host-passed arrays)."""
    x_handle = _stream_handle(x_handle)
    y_handle = _stream_handle(y_handle)
    base_dim = _pyramid_base_dim(base_dim)
    x0, x1 = _finite_increasing(x0, x1, "x range")
    y0, y1 = _finite_increasing(y0, y1, "y range")
    return int(
        _lib.xyg_pyramid_build_from_stream(
            ctypes.c_uint64(x_handle),
            ctypes.c_uint64(y_handle),
            x0,
            x1,
            y0,
            y1,
            base_dim,
        )
    )


def pyramid_append_from_stream(handle: int, x_handle: int, y_handle: int, tail_len: int) -> bool:
    """Increment a pyramid from the tail of two streams. False → invalidate."""
    handle = _pyramid_handle(handle)
    x_handle = _stream_handle(x_handle)
    y_handle = _stream_handle(y_handle)
    if isinstance(tail_len, (bool, np.bool_)):
        raise ValueError("tail_len must be a non-negative integer")
    try:
        n = operator.index(tail_len)
    except TypeError as e:
        raise ValueError("tail_len must be a non-negative integer") from e
    if n < 0:
        raise ValueError("tail_len must be a non-negative integer")
    return (
        _lib.xyg_pyramid_append_from_stream(
            ctypes.c_uint64(handle),
            ctypes.c_uint64(x_handle),
            ctypes.c_uint64(y_handle),
            n,
        )
        == 1
    )


def pyramid_build(
    x: "npt.NDArray[np.float64]",
    y: "npt.NDArray[np.float64]",
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    base_dim: int,
) -> int:
    """Build a count pyramid (§5 Tier 3). Returns a handle, 0 on failure."""
    base_dim = _pyramid_base_dim(base_dim)
    x0, x1 = _finite_increasing(x0, x1, "x range")
    y0, y1 = _finite_increasing(y0, y1, "y range")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    if len(x) == 0:
        return 0
    return int(
        _lib.xyg_pyramid_build(
            x.ctypes.data,
            y.ctypes.data,
            len(x),
            x0,
            x1,
            y0,
            y1,
            base_dim,
        )
    )


def pyramid_build_color(
    x: "npt.NDArray[np.float64]",
    y: "npt.NDArray[np.float64]",
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    base_dim: int,
    *,
    idx: "npt.NDArray[np.uint8] | None" = None,
    rgba: "npt.NDArray[np.uint8] | None" = None,
    lut: "npt.NDArray[np.uint8] | None" = None,
) -> int:
    """Build a pyramid with mean-color planes (LOD doc §2/§4.1) so zoomed-out
    density views of a channel-bearing trace keep the mean point color without
    an O(N) rescan. Returns a handle, 0 on failure. Color source as in
    `bin_2d_mean_color`. Colored pyramids refuse `pyramid_append` — callers
    invalidate and lazily rebuild instead."""
    base_dim = _pyramid_base_dim(base_dim)
    x0, x1 = _finite_increasing(x0, x1, "x range")
    y0, y1 = _finite_increasing(y0, y1, "y range")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    if len(x) == 0:
        return 0
    idx_ptr, rgba_ptr, lut_ptr, lut_len, _keepalive = _color_source_args(len(x), idx, rgba, lut)
    return int(
        _lib.xyg_pyramid_build_color(
            x.ctypes.data,
            y.ctypes.data,
            len(x),
            idx_ptr,
            rgba_ptr,
            lut_ptr,
            lut_len,
            x0,
            x1,
            y0,
            y1,
            base_dim,
        )
    )


def pyramid_append(
    handle: int,
    x: "npt.NDArray[np.float64]",
    y: "npt.NDArray[np.float64]",
) -> bool:
    """Increment an existing count pyramid from a canonical append batch.

    Returns ``False`` when the handle is stale/busy or a finite point expands
    the pyramid domain; callers then invalidate it and lazily rebuild. A false
    result never partially updates the native cache.
    """
    handle = _pyramid_handle(handle)
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    return (
        _lib.xyg_pyramid_append(
            ctypes.c_uint64(handle),
            _ptr_f64(x) if len(x) else None,
            _ptr_f64(y) if len(y) else None,
            len(x),
        )
        == 1
    )


def pyramid_count(handle: int, lo_x: float, hi_x: float, lo_y: float, hi_y: float) -> float | None:
    handle = _pyramid_handle(handle)
    lo_x, hi_x = _finite_increasing(lo_x, hi_x, "x range")
    lo_y, hi_y = _finite_increasing(lo_y, hi_y, "y range")
    out = ctypes.c_double(0.0)
    ok = _lib.xyg_pyramid_count(
        ctypes.c_uint64(handle),
        lo_x,
        hi_x,
        lo_y,
        hi_y,
        ctypes.byref(out),
    )
    return float(out.value) if ok == 1 else None


def pyramid_compose(
    handle: int,
    lo_x: float,
    hi_x: float,
    lo_y: float,
    hi_y: float,
    w: int,
    h: int,
    max_upsample: int = 2,
) -> tuple[npt.NDArray[np.float32], int] | None:
    """(grid f32 [h*w], level) from the pyramid, or None when the window
    outresolves it beyond ``max_upsample`` (caller falls back to an exact
    re-bin, §28). Callers over huge/out-of-core columns pass a large
    ``max_upsample`` so the finest level is served upsampled instead of
    triggering an O(N) rescan."""
    handle = _pyramid_handle(handle)
    lo_x, hi_x = _finite_increasing(lo_x, hi_x, "x range")
    lo_y, hi_y = _finite_increasing(lo_y, hi_y, "y range")
    w = _bounded_positive_int(w, "w")
    h = _bounded_positive_int(h, "h")
    max_upsample = _positive_int(max_upsample, "max_upsample")
    out = np.zeros(w * h, dtype=np.float32)
    level = _lib.xyg_pyramid_compose(
        ctypes.c_uint64(handle),
        lo_x,
        hi_x,
        lo_y,
        hi_y,
        w,
        h,
        max_upsample,
        out.ctypes.data,
    )
    if level < 0:
        return None
    return out, int(level)


def pyramid_compose_color(
    handle: int,
    lo_x: float,
    hi_x: float,
    lo_y: float,
    hi_y: float,
    w: int,
    h: int,
    max_upsample: int = 2,
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.uint8], int] | None:
    """(counts f32 [h*w], mean-color rgba8 [h, w, 4], level) from a colored
    pyramid, or None when the window outresolves it beyond ``max_upsample``
    or the pyramid carries no color planes (caller falls back to an exact
    re-bin, §28). Counts are bit-identical to `pyramid_compose` with the
    same ``max_upsample``."""
    handle = _pyramid_handle(handle)
    lo_x, hi_x = _finite_increasing(lo_x, hi_x, "x range")
    lo_y, hi_y = _finite_increasing(lo_y, hi_y, "y range")
    w = _bounded_positive_int(w, "w")
    h = _bounded_positive_int(h, "h")
    max_upsample = _positive_int(max_upsample, "max_upsample")
    out = np.zeros(w * h, dtype=np.float32)
    out_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    level = _lib.xyg_pyramid_compose_color(
        ctypes.c_uint64(handle),
        lo_x,
        hi_x,
        lo_y,
        hi_y,
        w,
        h,
        max_upsample,
        out.ctypes.data,
        out_rgba.ctypes.data,
    )
    if level < 0:
        return None
    return out, out_rgba, int(level)


def pyramid_free(handle: int) -> bool:
    return _lib.xyg_pyramid_free(ctypes.c_uint64(_pyramid_handle(handle))) == 1


def pyramid_spill(handle: int) -> int:
    """Snapshot a live pyramid into a disk tile store (Phase-4 WP1 ABI).

    Returns a nonzero store handle (release with :func:`tile_store_free`), or
    0 on a stale pyramid / I/O failure. The pyramid stays live until the host
    frees it — reclaim RAM after a successful spill.
    """
    return int(_lib.xyg_pyramid_spill(ctypes.c_uint64(_pyramid_handle(handle))))


def tile_store_compose(
    store: int,
    lo_x: float,
    hi_x: float,
    lo_y: float,
    hi_y: float,
    w: int,
    h: int,
    max_upsample: int = 2,
) -> tuple[npt.NDArray[np.float32], int] | None:
    """Tile-store twin of :func:`pyramid_compose` (bit-identical counts)."""
    store = _pyramid_handle(store)
    lo_x, hi_x = _finite_increasing(lo_x, hi_x, "x range")
    lo_y, hi_y = _finite_increasing(lo_y, hi_y, "y range")
    w = _bounded_positive_int(w, "w")
    h = _bounded_positive_int(h, "h")
    max_upsample = _positive_int(max_upsample, "max_upsample")
    out = np.zeros(w * h, dtype=np.float32)
    level = _lib.xyg_tile_store_compose(
        ctypes.c_uint64(store),
        lo_x,
        hi_x,
        lo_y,
        hi_y,
        w,
        h,
        max_upsample,
        out.ctypes.data,
    )
    if level < 0:
        return None
    return out, int(level)


def tile_store_compose_color(
    store: int,
    lo_x: float,
    hi_x: float,
    lo_y: float,
    hi_y: float,
    w: int,
    h: int,
    max_upsample: int = 2,
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.uint8], int] | None:
    """Tile-store twin of :func:`pyramid_compose_color`."""
    store = _pyramid_handle(store)
    lo_x, hi_x = _finite_increasing(lo_x, hi_x, "x range")
    lo_y, hi_y = _finite_increasing(lo_y, hi_y, "y range")
    w = _bounded_positive_int(w, "w")
    h = _bounded_positive_int(h, "h")
    max_upsample = _positive_int(max_upsample, "max_upsample")
    out = np.zeros(w * h, dtype=np.float32)
    out_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    level = _lib.xyg_tile_store_compose_color(
        ctypes.c_uint64(store),
        lo_x,
        hi_x,
        lo_y,
        hi_y,
        w,
        h,
        max_upsample,
        out.ctypes.data,
        out_rgba.ctypes.data,
    )
    if level < 0:
        return None
    return out, out_rgba, int(level)


def tile_store_append(
    store: int,
    x: "npt.NDArray[np.float64]",
    y: "npt.NDArray[np.float64]",
) -> bool:
    """Increment a count-only tile store from an append batch (D4)."""
    store = _pyramid_handle(store)
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    return (
        _lib.xyg_tile_store_append(
            ctypes.c_uint64(store),
            x.ctypes.data if len(x) else None,
            y.ctypes.data if len(y) else None,
            len(x),
        )
        == 1
    )


def tile_store_stats(store: int) -> tuple[int, int, int, int, int, bool] | None:
    """§28 residency: ``(hit, miss, resident_bytes, spilled_bytes, budget, over)``."""
    store = _pyramid_handle(store)
    out = (ctypes.c_uint64 * 6)()
    if _lib.xyg_tile_store_stats(ctypes.c_uint64(store), out) != 1:
        return None
    return (
        int(out[0]),
        int(out[1]),
        int(out[2]),
        int(out[3]),
        int(out[4]),
        bool(out[5]),
    )


def tile_store_free(store: int) -> bool:
    return _lib.xyg_tile_store_free(ctypes.c_uint64(_pyramid_handle(store))) == 1


def tile_budget_set(bytes_: int) -> bool:
    """Mirror ``PYRAMID_RESIDENT_BYTES`` into the process-wide tile LRU budget."""
    if isinstance(bytes_, (bool, np.bool_)):
        raise ValueError("budget bytes must be an integer")
    try:
        n = operator.index(bytes_)
    except TypeError as e:
        raise ValueError("budget bytes must be an integer") from e
    if n < 0:
        raise ValueError("budget bytes must be non-negative")
    return _lib.xyg_tile_budget_set(ctypes.c_uint64(n)) == 1


# Graph layout ids — keep in lockstep with src/graph.rs LAYOUT_*.
GRAPH_LAYOUT_PRESET = 0
GRAPH_LAYOUT_GRID = 1
GRAPH_LAYOUT_CIRCLE = 2
GRAPH_LAYOUT_FORCE = 3
GRAPH_LAYOUT_BREADTHFIRST = 4
GRAPH_LAYOUT_AUTO = 5
GRAPH_LAYOUT_RADIAL = 6
GRAPH_LAYOUT_CONCENTRIC = 7
GRAPH_LAYOUT_HIERARCHICAL = 8
GRAPH_LAYOUT_BARNES_HUT = 9
GRAPH_LAYOUT_SPRING = 10
GRAPH_LAYOUT_FORCEATLAS2 = 11
GRAPH_LAYOUT_KAMADA_KAWAI = 12
GRAPH_LAYOUT_YIFANHU = 13
GRAPH_LAYOUT_LINLOG = 14
GRAPH_LAYOUT_STRESS = 15
GRAPH_LAYOUT_COSE = 16

_GRAPH_LAYOUT_NAMES = {
    "preset": GRAPH_LAYOUT_PRESET,
    "grid": GRAPH_LAYOUT_GRID,
    "circle": GRAPH_LAYOUT_CIRCLE,
    "force": GRAPH_LAYOUT_FORCE,
    "fr": GRAPH_LAYOUT_FORCE,
    "fruchterman_reingold": GRAPH_LAYOUT_FORCE,
    "breadthfirst": GRAPH_LAYOUT_BREADTHFIRST,
    "dagre": GRAPH_LAYOUT_HIERARCHICAL,
    "hierarchical": GRAPH_LAYOUT_HIERARCHICAL,
    "auto": GRAPH_LAYOUT_AUTO,
    "radial": GRAPH_LAYOUT_RADIAL,
    "concentric": GRAPH_LAYOUT_CONCENTRIC,
    "barnes_hut": GRAPH_LAYOUT_BARNES_HUT,
    "spring": GRAPH_LAYOUT_SPRING,
    "forceatlas2": GRAPH_LAYOUT_FORCEATLAS2,
    "fa2": GRAPH_LAYOUT_FORCEATLAS2,
    "kamada_kawai": GRAPH_LAYOUT_KAMADA_KAWAI,
    "kk": GRAPH_LAYOUT_KAMADA_KAWAI,
    "yifanhu": GRAPH_LAYOUT_YIFANHU,
    "linlog": GRAPH_LAYOUT_LINLOG,
    "stress": GRAPH_LAYOUT_STRESS,
    "cose": GRAPH_LAYOUT_COSE,
}

# Progressive force families (share xyg_graph_force_create/tick).
_GRAPH_PROGRESSIVE_FORCE = frozenset(
    {
        GRAPH_LAYOUT_FORCE,
        GRAPH_LAYOUT_BARNES_HUT,
        GRAPH_LAYOUT_SPRING,
        GRAPH_LAYOUT_FORCEATLAS2,
        GRAPH_LAYOUT_YIFANHU,
        GRAPH_LAYOUT_LINLOG,
        GRAPH_LAYOUT_KAMADA_KAWAI,
        GRAPH_LAYOUT_STRESS,
        GRAPH_LAYOUT_COSE,
    }
)


def graph_layout_id(name: str) -> int:
    key = str(name).strip().lower()
    if key not in _GRAPH_LAYOUT_NAMES:
        raise ValueError(
            f"unknown graph layout {name!r}; expected one of {sorted(_GRAPH_LAYOUT_NAMES)}"
        )
    return _GRAPH_LAYOUT_NAMES[key]


def _as_u64(
    data: npt.NDArray[np.uint64] | npt.NDArray[np.integer], name: str
) -> npt.NDArray[np.uint64]:
    arr = np.asarray(data)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D")
    return np.ascontiguousarray(arr, dtype=np.uint64)


def graph_layout(
    layout: str | int,
    n_nodes: int,
    sources: npt.NDArray[np.uint64],
    targets: npt.NDArray[np.uint64],
    *,
    x: npt.NDArray[np.float64] | None = None,
    y: npt.NDArray[np.float64] | None = None,
    roots: npt.NDArray[np.uint64] | None = None,
    seed: int = 0,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Run a one-shot graph layout; returns (x, y) f64 positions."""
    layout_id = graph_layout_id(layout) if isinstance(layout, str) else int(layout)
    n_nodes = int(n_nodes)
    if n_nodes < 0:
        raise ValueError("n_nodes must be non-negative")
    sources = _as_u64(sources, "sources")
    targets = _as_u64(targets, "targets")
    if len(sources) != len(targets):
        raise ValueError("sources and targets must have equal length")
    out_x = np.empty(n_nodes, dtype=np.float64)
    out_y = np.empty(n_nodes, dtype=np.float64)
    in_x_ptr = ctypes.c_void_p()
    in_y_ptr = ctypes.c_void_p()
    if x is not None or y is not None:
        if x is None or y is None:
            raise ValueError("preset layout requires both x and y")
        x_arr = _as_f64(x, "x")
        y_arr = _as_f64(y, "y")
        if len(x_arr) != n_nodes or len(y_arr) != n_nodes:
            raise ValueError("x/y must have length n_nodes")
        in_x_ptr = _ptr_f64(x_arr)
        in_y_ptr = _ptr_f64(y_arr)
    roots_arr = np.empty(0, dtype=np.uint64) if roots is None else _as_u64(roots, "roots")
    src_ptr = sources.ctypes.data if len(sources) else None
    tgt_ptr = targets.ctypes.data if len(targets) else None
    roots_ptr = roots_arr.ctypes.data if len(roots_arr) else None
    ok = _lib.xyg_graph_layout(
        ctypes.c_uint32(layout_id),
        ctypes.c_uint64(n_nodes),
        ctypes.c_uint64(len(sources)),
        src_ptr,
        tgt_ptr,
        in_x_ptr,
        in_y_ptr,
        roots_ptr,
        ctypes.c_uint64(len(roots_arr)),
        ctypes.c_uint64(int(seed) & ((1 << 64) - 1)),
        out_x.ctypes.data,
        out_y.ctypes.data,
    )
    if ok != 0:
        raise ValueError("native graph_layout failed (invalid arguments or layout)")
    return out_x, out_y


def _projection_uuid_buffer(values: Any, name: str) -> npt.NDArray[np.uint8]:
    array = np.ascontiguousarray(values, dtype=np.uint8)
    if array.ndim != 2 or array.shape[1:] != (16,):
        raise ValueError(f"{name} must have shape (n, 16) and dtype uint8")
    return array


def graph_projection_create(
    node_ids: Any,
    edge_ids: Any,
    source_ids: Any,
    target_ids: Any,
    *,
    parent_ids: Any | None = None,
    parent_validity: Any | None = None,
    directed: bool = True,
) -> int:
    """Create a Rust-owned canonical graph identity/topology projection."""
    nodes = _projection_uuid_buffer(node_ids, "node_ids")
    edges = _projection_uuid_buffer(edge_ids, "edge_ids")
    sources = _projection_uuid_buffer(source_ids, "source_ids")
    targets = _projection_uuid_buffer(target_ids, "target_ids")
    if len(edges) != len(sources) or len(edges) != len(targets):
        raise ValueError("edge_ids, source_ids, and target_ids must have equal lengths")
    parents: npt.NDArray[np.uint8] | None = None
    validity: npt.NDArray[np.uint8] | None = None
    if parent_ids is not None or parent_validity is not None:
        if parent_ids is None or parent_validity is None:
            raise ValueError("parent_ids and parent_validity must be provided together")
        parents = _projection_uuid_buffer(parent_ids, "parent_ids")
        validity = np.ascontiguousarray(parent_validity, dtype=np.uint8)
        if len(parents) != len(nodes) or validity.ndim != 1 or len(validity) != len(nodes):
            raise ValueError("parent buffers must match node count")
    descriptor = _GraphProjectionDescriptor(
        nodes.ctypes.data if len(nodes) else None,
        len(nodes),
        edges.ctypes.data if len(edges) else None,
        len(edges),
        sources.ctypes.data if len(sources) else None,
        targets.ctypes.data if len(targets) else None,
        parents.ctypes.data if parents is not None and len(parents) else None,
        validity.ctypes.data if validity is not None and len(validity) else None,
        int(bool(directed)),
        0,
    )
    handle = ctypes.c_uint64()
    status = _lib.xyg_graph_projection_create(ctypes.byref(descriptor), ctypes.byref(handle))
    if status != 0:
        raise GraphProjectionNativeError(status)
    return int(handle.value)


def graph_projection_counts(handle: int) -> tuple[int, int, bool]:
    nodes, edges, directed = ctypes.c_uint64(), ctypes.c_uint64(), ctypes.c_uint32()
    status = _lib.xyg_graph_projection_counts(
        ctypes.c_uint64(handle), ctypes.byref(nodes), ctypes.byref(edges), ctypes.byref(directed)
    )
    if status != 0:
        raise GraphProjectionNativeError(status)
    return int(nodes.value), int(edges.value), bool(directed.value)


def graph_projection_copy(
    handle: int,
) -> tuple[
    npt.NDArray[np.uint8],
    npt.NDArray[np.uint8],
    npt.NDArray[np.uint64],
    npt.NDArray[np.uint64],
    npt.NDArray[np.uint64],
    npt.NDArray[np.uint8],
    bool,
]:
    n_nodes, n_edges, directed = graph_projection_counts(handle)
    node_ids = np.empty((n_nodes, 16), dtype=np.uint8)
    edge_ids = np.empty((n_edges, 16), dtype=np.uint8)
    sources = np.empty(n_edges, dtype=np.uint64)
    targets = np.empty(n_edges, dtype=np.uint64)
    parents = np.empty(n_nodes, dtype=np.uint64)
    validity = np.empty(n_nodes, dtype=np.uint8)
    calls = (
        _lib.xyg_graph_projection_copy_node_ids(
            handle, node_ids.ctypes.data if n_nodes else None, n_nodes
        ),
        _lib.xyg_graph_projection_copy_edge_ids(
            handle, edge_ids.ctypes.data if n_edges else None, n_edges
        ),
        _lib.xyg_graph_projection_copy_endpoints(
            handle,
            sources.ctypes.data if n_edges else None,
            targets.ctypes.data if n_edges else None,
            n_edges,
        ),
        _lib.xyg_graph_projection_copy_parents(
            handle,
            parents.ctypes.data if n_nodes else None,
            validity.ctypes.data if n_nodes else None,
            n_nodes,
        ),
    )
    for status in calls:
        if status != 0:
            raise GraphProjectionNativeError(status)
    return node_ids, edge_ids, sources, targets, parents, validity, directed


def graph_projection_destroy(handle: int) -> None:
    status = _lib.xyg_graph_projection_destroy(ctypes.c_uint64(handle))
    if status != 0:
        raise GraphProjectionNativeError(status)


def temporal_column_create(
    values: Any,
    validity: Any,
    *,
    timezone: str,
    unit: int = TEMPORAL_PRECISION_MICROSECOND,
    naive: bool = False,
    disambiguation: int = TEMPORAL_DISAMBIGUATION_REJECT,
    dst_status: Any | None = None,
    offset_seconds: Any | None = None,
    fold_later_offset_seconds: Any | None = None,
) -> int:
    """Create a Rust-owned canonical temporal column (UTC microseconds)."""
    if not isinstance(timezone, str) or not timezone:
        raise ValueError("timezone is required")
    tz = timezone.encode("utf-8")
    vals = np.ascontiguousarray(values, dtype=np.int64)
    valid = np.ascontiguousarray(validity, dtype=np.uint8)
    if vals.ndim != 1 or valid.ndim != 1 or len(vals) != len(valid):
        raise ValueError("values and validity must be equal-length 1-D arrays")
    dst: npt.NDArray[np.uint8] | None = None
    offsets: npt.NDArray[np.int32] | None = None
    fold_later: npt.NDArray[np.int32] | None = None
    if naive:
        if dst_status is None or offset_seconds is None or fold_later_offset_seconds is None:
            raise ValueError("naive ingest requires dst_status and offset planes")
        dst = np.ascontiguousarray(dst_status, dtype=np.uint8)
        offsets = np.ascontiguousarray(offset_seconds, dtype=np.int32)
        fold_later = np.ascontiguousarray(fold_later_offset_seconds, dtype=np.int32)
        if len(dst) != len(vals) or len(offsets) != len(vals) or len(fold_later) != len(vals):
            raise ValueError("naive DST planes must match values length")
    tz_buf = ctypes.create_string_buffer(tz)
    descriptor = _TemporalColumnDescriptor(
        vals.ctypes.data if len(vals) else None,
        valid.ctypes.data if len(valid) else None,
        len(vals),
        int(unit),
        ctypes.addressof(tz_buf),
        len(tz),
        int(bool(naive)),
        int(disambiguation),
        dst.ctypes.data if dst is not None and len(dst) else None,
        offsets.ctypes.data if offsets is not None and len(offsets) else None,
        fold_later.ctypes.data if fold_later is not None and len(fold_later) else None,
        0,
    )
    handle = ctypes.c_uint64()
    status = _lib.xyg_temporal_column_create(ctypes.byref(descriptor), ctypes.byref(handle))
    if status != 0:
        raise TemporalNativeError(status)
    return int(handle.value)


def temporal_column_read(
    handle: int,
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.uint8], str, int]:
    """Copy UTC micros, validity, timezone, and source precision from Rust."""
    length = ctypes.c_uint64()
    precision = ctypes.c_uint32()
    tz_len = ctypes.c_uint32()
    status = _lib.xyg_temporal_column_meta(
        ctypes.c_uint64(handle),
        ctypes.byref(length),
        ctypes.byref(precision),
        ctypes.byref(tz_len),
    )
    if status != 0:
        raise TemporalNativeError(status)
    n = int(length.value)
    values = np.empty(n, dtype=np.int64)
    validity = np.empty(n, dtype=np.uint8)
    status = _lib.xyg_temporal_column_copy(
        ctypes.c_uint64(handle),
        values.ctypes.data if n else None,
        validity.ctypes.data if n else None,
        n,
    )
    if status != 0:
        raise TemporalNativeError(status)
    tz_buf = (ctypes.c_uint8 * int(tz_len.value))()
    status = _lib.xyg_temporal_column_timezone(
        ctypes.c_uint64(handle),
        ctypes.cast(tz_buf, ctypes.c_void_p) if tz_len.value else None,
        tz_len.value,
    )
    if status != 0:
        raise TemporalNativeError(status)
    timezone = bytes(tz_buf).decode("utf-8")
    return values, validity, timezone, int(precision.value)


def temporal_column_destroy(handle: int) -> None:
    status = _lib.xyg_temporal_column_destroy(ctypes.c_uint64(handle))
    if status != 0:
        raise TemporalNativeError(status)


def geo_column_new(
    *,
    geometry: int,
    crs: int,
    xy: Any,
    validity: Any,
    feature_ids: Any | None = None,
    offsets0: Any | None = None,
    offsets1: Any | None = None,
    offsets2: Any | None = None,
) -> int:
    """Create a Rust-owned geographic column from a typed host descriptor (#47)."""
    coords = np.ascontiguousarray(xy, dtype=np.float64)
    valid = np.ascontiguousarray(validity, dtype=np.uint8)
    if coords.ndim != 1 or coords.size % 2 != 0:
        raise ValueError("xy must be a 1-D interleaved [x0,y0,…] f64 array")
    if valid.ndim != 1:
        raise ValueError("validity must be a 1-D u8 array")
    ids: npt.NDArray[np.uint64] | None = None
    if feature_ids is not None:
        ids = np.ascontiguousarray(feature_ids, dtype=np.uint64)
        if ids.ndim != 1 or len(ids) != len(valid):
            raise ValueError("feature_ids must match validity length")

    def _offsets(values: Any | None) -> npt.NDArray[np.uint32]:
        if values is None:
            return np.empty(0, dtype=np.uint32)
        arr = np.ascontiguousarray(values, dtype=np.uint32)
        if arr.ndim != 1:
            raise ValueError("offset planes must be 1-D u32 arrays")
        return arr

    o0, o1, o2 = _offsets(offsets0), _offsets(offsets1), _offsets(offsets2)
    err = ctypes.c_int32(0)
    handle = int(
        _lib.xyg_geo_column_new(
            ctypes.c_uint32(geometry),
            ctypes.c_uint32(crs),
            _ptr_f64(coords) if len(coords) else None,
            len(coords),
            valid.ctypes.data if len(valid) else None,
            len(valid),
            ids.ctypes.data if ids is not None and len(ids) else None,
            o0.ctypes.data if len(o0) else None,
            len(o0),
            o1.ctypes.data if len(o1) else None,
            len(o1),
            o2.ctypes.data if len(o2) else None,
            len(o2),
            ctypes.byref(err),
        )
    )
    if handle == 0:
        raise GeoNativeError(int(err.value) or -1)
    return handle


def geo_column_meta(handle: int) -> tuple[int, int, int, int]:
    """Return `(len, vertex_count, geometry, crs)` for a geographic column."""
    h = ctypes.c_uint64(handle)
    length = int(_lib.xyg_geo_column_len(h))
    if length == _USIZE_MAX:
        raise GeoNativeError(-10)
    vertices = int(_lib.xyg_geo_column_vertex_count(h))
    if vertices == _USIZE_MAX:
        raise GeoNativeError(-10)
    geometry = int(_lib.xyg_geo_column_geometry(h))
    crs = int(_lib.xyg_geo_column_crs(h))
    if geometry == 0 or crs == 0:
        raise GeoNativeError(-10)
    return length, vertices, geometry, crs


def geo_column_free(handle: int) -> bool:
    """Free a geographic column handle. Returns False when already stale."""
    return _lib.xyg_geo_column_free(ctypes.c_uint64(handle)) == 1


def temporal_interval_index_create(
    starts: Any,
    start_valid: Any,
    ends: Any,
    end_valid: Any,
) -> int:
    """Build a Rust-owned half-open interval index."""
    start_vals = np.ascontiguousarray(starts, dtype=np.int64)
    start_bits = np.ascontiguousarray(start_valid, dtype=np.uint8)
    end_vals = np.ascontiguousarray(ends, dtype=np.int64)
    end_bits = np.ascontiguousarray(end_valid, dtype=np.uint8)
    n = len(start_vals)
    if not (
        start_bits.shape == (n,)
        and end_vals.shape == (n,)
        and end_bits.shape == (n,)
        and start_vals.ndim == 1
    ):
        raise ValueError("interval endpoint arrays must be equal-length 1-D")
    descriptor = _TemporalIntervalDescriptor(
        start_vals.ctypes.data if n else None,
        start_bits.ctypes.data if n else None,
        end_vals.ctypes.data if n else None,
        end_bits.ctypes.data if n else None,
        n,
        0,
    )
    handle = ctypes.c_uint64()
    status = _lib.xyg_temporal_interval_index_create(ctypes.byref(descriptor), ctypes.byref(handle))
    if status != 0:
        raise TemporalNativeError(status)
    return int(handle.value)


def temporal_interval_visibility_at(
    handle: int,
    instant_micros: int,
    *,
    budget: int | None = None,
    cancel_flag: int = 0,
) -> npt.NDArray[np.uint8]:
    """Return a 0/1 visibility plane for half-open interval membership."""
    length = ctypes.c_uint64()
    status = _lib.xyg_temporal_interval_index_len(ctypes.c_uint64(handle), ctypes.byref(length))
    if status != 0:
        raise TemporalNativeError(status)
    n = int(length.value)
    if budget is None:
        budget = n
    if budget < n:
        raise ValueError("budget must be at least index length")
    out = np.zeros(n, dtype=np.uint8)
    cancel = ctypes.c_uint32(int(cancel_flag))
    status = _lib.xyg_temporal_interval_visibility_at(
        ctypes.c_uint64(handle),
        ctypes.c_int64(instant_micros),
        out.ctypes.data if n else None,
        n,
        int(budget),
        ctypes.byref(cancel),
    )
    if status != 0:
        raise TemporalNativeError(status)
    return out


def temporal_interval_index_destroy(handle: int) -> None:
    status = _lib.xyg_temporal_interval_index_destroy(ctypes.c_uint64(handle))
    if status != 0:
        raise TemporalNativeError(status)


def temporal_events_in_range(
    event_micros: Any,
    event_valid: Any,
    *,
    range_start: int | None = None,
    range_end: int | None = None,
    budget: int | None = None,
    cancel_flag: int = 0,
) -> npt.NDArray[np.uint8]:
    """Filter event instants into a half-open `[start, end)` window."""
    events = np.ascontiguousarray(event_micros, dtype=np.int64)
    valid = np.ascontiguousarray(event_valid, dtype=np.uint8)
    if events.ndim != 1 or valid.ndim != 1 or len(events) != len(valid):
        raise ValueError("event_micros and event_valid must be equal-length 1-D")
    n = len(events)
    if budget is None:
        budget = n
    if budget < n:
        raise ValueError("budget must be at least event length")
    out = np.zeros(n, dtype=np.uint8)
    cancel = ctypes.c_uint32(int(cancel_flag))
    status = _lib.xyg_temporal_events_in_range(
        events.ctypes.data if n else None,
        valid.ctypes.data if n else None,
        n,
        ctypes.c_int64(0 if range_start is None else range_start),
        0 if range_start is None else 1,
        ctypes.c_int64(0 if range_end is None else range_end),
        0 if range_end is None else 1,
        out.ctypes.data if n else None,
        n,
        int(budget),
        ctypes.byref(cancel),
    )
    if status != 0:
        raise TemporalNativeError(status)
    return out


def _temporal_scalar(value: object, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    converted = int(value)
    if converted < minimum or converted > maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return converted


def _temporal_u64(value: object, name: str) -> int:
    return _temporal_scalar(value, name, 0, (1 << 64) - 1)


def _temporal_i64(value: object, name: str) -> int:
    return _temporal_scalar(value, name, -(1 << 63), (1 << 63) - 1)


def _temporal_u32(value: object, name: str) -> int:
    return _temporal_scalar(value, name, 0, (1 << 32) - 1)


def _temporal_i32(value: object, name: str) -> int:
    return _temporal_scalar(value, name, -(1 << 31), (1 << 31) - 1)


def _temporal_bool(value: object, name: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a boolean")
    return bool(value)


def temporal_controller_create(
    *,
    instance_id: int,
    domain_start: int,
    domain_end: int,
    cursor: int | None = None,
    window: int = 0,
    step: int = 1,
    direction: int = TEMPORAL_DIRECTION_FORWARD,
    rate_milli: int = 1000,
    loop_enabled: bool = False,
    reduced_motion: bool = False,
    group_id: int = 0,
) -> int:
    """Create a Rust-owned TemporalController (UTC microseconds)."""
    if cursor is None:
        cursor = domain_start
    descriptor = _TemporalControllerDescriptor(
        _temporal_u64(instance_id, "instance_id"),
        _temporal_u64(group_id, "group_id"),
        _temporal_i64(domain_start, "domain_start"),
        _temporal_i64(domain_end, "domain_end"),
        _temporal_i64(cursor, "cursor"),
        _temporal_i64(window, "window"),
        _temporal_i64(step, "step"),
        _temporal_i32(direction, "direction"),
        _temporal_u32(rate_milli, "rate_milli"),
        int(_temporal_bool(loop_enabled, "loop_enabled")),
        int(_temporal_bool(reduced_motion, "reduced_motion")),
        0,
    )
    handle = ctypes.c_uint64()
    status = _lib.xyg_temporal_controller_create(ctypes.byref(descriptor), ctypes.byref(handle))
    if status != 0:
        raise TemporalNativeError(status)
    return int(handle.value)


def _temporal_selection(values: Any, name: str = "selection") -> tuple[ctypes.Array, int]:
    if isinstance(values, (str, bytes, bytearray)):
        raise ValueError(f"{name} must be an iterable of u64 stable IDs")
    try:
        iterator = iter(values)
    except TypeError as exc:
        raise ValueError(f"{name} must be an iterable of u64 stable IDs") from exc
    limit = _temporal_selection_limit()
    normalized = []
    for index, value in enumerate(iterator):
        if index >= limit:
            raise ValueError(f"{name} may contain at most {limit} IDs")
        normalized.append(_temporal_u64(value, f"{name}[{index}]"))
    array = (ctypes.c_uint64 * len(normalized))(*normalized)
    return array, len(normalized)


def _temporal_selection_limit() -> int:
    return int(_lib.xyg_temporal_selection_limit())


def temporal_controller_state(handle: int) -> dict[str, int | bool | list[int]]:
    """Read the full controller state snapshot."""
    fields = {
        "instance_id": ctypes.c_uint64(),
        "group_id": ctypes.c_uint64(),
        "domain_start": ctypes.c_int64(),
        "domain_end": ctypes.c_int64(),
        "range_start": ctypes.c_int64(),
        "range_end": ctypes.c_int64(),
        "cursor": ctypes.c_int64(),
        "window": ctypes.c_int64(),
        "step": ctypes.c_int64(),
        "direction": ctypes.c_int32(),
        "rate_milli": ctypes.c_uint32(),
        "loop_enabled": ctypes.c_uint32(),
        "playing": ctypes.c_uint32(),
        "reduced_motion": ctypes.c_uint32(),
        "revision": ctypes.c_uint64(),
        "disposed": ctypes.c_uint32(),
    }
    selection_capacity = _temporal_selection_limit()
    selection = (ctypes.c_uint64 * selection_capacity)()
    selection_count = ctypes.c_uint64()
    status = _lib.xyg_temporal_controller_state(
        ctypes.c_uint64(_temporal_u64(handle, "handle")),
        *(ctypes.byref(value) for value in fields.values()),
        selection,
        ctypes.c_uint64(selection_capacity),
        ctypes.byref(selection_count),
    )
    if status != 0:
        raise TemporalNativeError(status)
    return {
        "instance_id": int(fields["instance_id"].value),
        "group_id": int(fields["group_id"].value),
        "domain_start": int(fields["domain_start"].value),
        "domain_end": int(fields["domain_end"].value),
        "range_start": int(fields["range_start"].value),
        "range_end": int(fields["range_end"].value),
        "cursor": int(fields["cursor"].value),
        "window": int(fields["window"].value),
        "step": int(fields["step"].value),
        "direction": int(fields["direction"].value),
        "rate_milli": int(fields["rate_milli"].value),
        "loop_enabled": bool(fields["loop_enabled"].value),
        "playing": bool(fields["playing"].value),
        "reduced_motion": bool(fields["reduced_motion"].value),
        "revision": int(fields["revision"].value),
        "disposed": bool(fields["disposed"].value),
        "selection": [int(selection[index]) for index in range(selection_count.value)],
    }


def _temporal_controller_status(status: int) -> None:
    if status != 0:
        raise TemporalNativeError(status)


def temporal_controller_set_range(handle: int, start: int, end: int) -> None:
    _temporal_controller_status(
        _lib.xyg_temporal_controller_set_range(
            ctypes.c_uint64(_temporal_u64(handle, "handle")),
            ctypes.c_int64(_temporal_i64(start, "start")),
            ctypes.c_int64(_temporal_i64(end, "end")),
        )
    )


def temporal_controller_set_cursor(handle: int, cursor: int) -> None:
    _temporal_controller_status(
        _lib.xyg_temporal_controller_set_cursor(
            ctypes.c_uint64(_temporal_u64(handle, "handle")),
            ctypes.c_int64(_temporal_i64(cursor, "cursor")),
        )
    )


def temporal_controller_set_selection(handle: int, ids: object) -> None:
    selection, count = _temporal_selection(ids)
    _temporal_controller_status(
        _lib.xyg_temporal_controller_set_selection(
            ctypes.c_uint64(_temporal_u64(handle, "handle")),
            selection,
            ctypes.c_uint64(count),
        )
    )


def temporal_controller_step(handle: int) -> None:
    _temporal_controller_status(
        _lib.xyg_temporal_controller_step(ctypes.c_uint64(_temporal_u64(handle, "handle")))
    )


def temporal_controller_play(handle: int) -> None:
    _temporal_controller_status(
        _lib.xyg_temporal_controller_play(ctypes.c_uint64(_temporal_u64(handle, "handle")))
    )


def temporal_controller_pause(handle: int) -> None:
    _temporal_controller_status(
        _lib.xyg_temporal_controller_pause(ctypes.c_uint64(_temporal_u64(handle, "handle")))
    )


def temporal_controller_set_rate_milli(handle: int, rate_milli: int) -> None:
    _temporal_controller_status(
        _lib.xyg_temporal_controller_set_rate_milli(
            ctypes.c_uint64(_temporal_u64(handle, "handle")),
            ctypes.c_uint32(_temporal_u32(rate_milli, "rate_milli")),
        )
    )


def temporal_controller_set_direction(handle: int, direction: int) -> None:
    _temporal_controller_status(
        _lib.xyg_temporal_controller_set_direction(
            ctypes.c_uint64(_temporal_u64(handle, "handle")),
            ctypes.c_int32(_temporal_i32(direction, "direction")),
        )
    )


def temporal_controller_set_loop(handle: int, enabled: bool) -> None:
    _temporal_controller_status(
        _lib.xyg_temporal_controller_set_loop(
            ctypes.c_uint64(_temporal_u64(handle, "handle")),
            int(_temporal_bool(enabled, "enabled")),
        )
    )


def temporal_controller_set_reduced_motion(handle: int, enabled: bool) -> None:
    _temporal_controller_status(
        _lib.xyg_temporal_controller_set_reduced_motion(
            ctypes.c_uint64(_temporal_u64(handle, "handle")),
            int(_temporal_bool(enabled, "enabled")),
        )
    )


def temporal_controller_tick(handle: int, dt_micros: int) -> bool:
    advanced = ctypes.c_uint32()
    status = _lib.xyg_temporal_controller_tick(
        ctypes.c_uint64(_temporal_u64(handle, "handle")),
        ctypes.c_int64(_temporal_i64(dt_micros, "dt_micros")),
        ctypes.byref(advanced),
    )
    _temporal_controller_status(status)
    return bool(advanced.value)


def temporal_controller_poll_event(handle: int) -> dict[str, int | list[int]] | None:
    has_event = ctypes.c_uint32()
    group_id = ctypes.c_uint64()
    source = ctypes.c_uint64()
    revision = ctypes.c_uint64()
    range_start = ctypes.c_int64()
    range_end = ctypes.c_int64()
    cursor = ctypes.c_int64()
    window = ctypes.c_int64()
    selection_capacity = _temporal_selection_limit()
    selection = (ctypes.c_uint64 * selection_capacity)()
    selection_count = ctypes.c_uint64()
    status = _lib.xyg_temporal_controller_poll_event(
        ctypes.c_uint64(_temporal_u64(handle, "handle")),
        ctypes.byref(has_event),
        ctypes.byref(group_id),
        ctypes.byref(source),
        ctypes.byref(revision),
        ctypes.byref(range_start),
        ctypes.byref(range_end),
        ctypes.byref(cursor),
        ctypes.byref(window),
        selection,
        ctypes.c_uint64(selection_capacity),
        ctypes.byref(selection_count),
    )
    _temporal_controller_status(status)
    if not has_event.value:
        return None
    return {
        "group_id": int(group_id.value),
        "source_instance": int(source.value),
        "revision": int(revision.value),
        "range_start": int(range_start.value),
        "range_end": int(range_end.value),
        "cursor": int(cursor.value),
        "window": int(window.value),
        "selection": [int(selection[index]) for index in range(selection_count.value)],
    }


def temporal_controller_apply_event(handle: int, event: dict[str, object]) -> bool:
    applied = ctypes.c_uint32()
    selection, selection_count = _temporal_selection(event["selection"], "event.selection")
    status = _lib.xyg_temporal_controller_apply_event(
        ctypes.c_uint64(_temporal_u64(handle, "handle")),
        ctypes.c_uint64(_temporal_u64(event["group_id"], "group_id")),
        ctypes.c_uint64(_temporal_u64(event["source_instance"], "source_instance")),
        ctypes.c_uint64(_temporal_u64(event["revision"], "revision")),
        ctypes.c_int64(_temporal_i64(event["range_start"], "range_start")),
        ctypes.c_int64(_temporal_i64(event["range_end"], "range_end")),
        ctypes.c_int64(_temporal_i64(event["cursor"], "cursor")),
        ctypes.c_int64(_temporal_i64(event["window"], "window")),
        selection,
        ctypes.c_uint64(selection_count),
        ctypes.byref(applied),
    )
    _temporal_controller_status(status)
    return bool(applied.value)


def temporal_coordinate_deliver(event: dict[str, object]) -> int:
    applied = ctypes.c_uint32()
    selection, selection_count = _temporal_selection(event["selection"], "event.selection")
    status = _lib.xyg_temporal_coordinate_deliver(
        ctypes.c_uint64(_temporal_u64(event["group_id"], "group_id")),
        ctypes.c_uint64(_temporal_u64(event["source_instance"], "source_instance")),
        ctypes.c_uint64(_temporal_u64(event["revision"], "revision")),
        ctypes.c_int64(_temporal_i64(event["range_start"], "range_start")),
        ctypes.c_int64(_temporal_i64(event["range_end"], "range_end")),
        ctypes.c_int64(_temporal_i64(event["cursor"], "cursor")),
        ctypes.c_int64(_temporal_i64(event["window"], "window")),
        selection,
        ctypes.c_uint64(selection_count),
        ctypes.byref(applied),
    )
    _temporal_controller_status(status)
    return int(applied.value)


def temporal_controller_dispose(handle: int) -> None:
    _temporal_controller_status(
        _lib.xyg_temporal_controller_dispose(ctypes.c_uint64(_temporal_u64(handle, "handle")))
    )


def temporal_controller_destroy(handle: int) -> None:
    _temporal_controller_status(
        _lib.xyg_temporal_controller_destroy(ctypes.c_uint64(_temporal_u64(handle, "handle")))
    )


def temporal_graph_create(
    projection_handle: int,
    *,
    node_valid_from: int = 0,
    node_valid_to: int = 0,
    node_event_at: int = 0,
    edge_valid_from: int = 0,
    edge_valid_to: int = 0,
    edge_event_at: int = 0,
) -> int:
    """Bind canonical graph/time handles into one Rust-owned graph filter."""
    descriptor = _TemporalGraphDescriptor(
        _temporal_u64(projection_handle, "projection_handle"),
        _temporal_u64(node_valid_from, "node_valid_from"),
        _temporal_u64(node_valid_to, "node_valid_to"),
        _temporal_u64(node_event_at, "node_event_at"),
        _temporal_u64(edge_valid_from, "edge_valid_from"),
        _temporal_u64(edge_valid_to, "edge_valid_to"),
        _temporal_u64(edge_event_at, "edge_event_at"),
        0,
    )
    handle = ctypes.c_uint64()
    status = _lib.xyg_temporal_graph_create(ctypes.byref(descriptor), ctypes.byref(handle))
    _temporal_controller_status(status)
    return int(handle.value)


def _temporal_graph_uuid_buffer(values: Any, name: str) -> npt.NDArray[np.uint8]:
    array = np.ascontiguousarray(values, dtype=np.uint8)
    if array.size == 0:
        return np.empty((0, 16), dtype=np.uint8)
    return _projection_uuid_buffer(array, name)


def temporal_graph_set_selection(handle: int, node_ids: Any, edge_ids: Any) -> None:
    nodes = _temporal_graph_uuid_buffer(node_ids, "node_ids")
    edges = _temporal_graph_uuid_buffer(edge_ids, "edge_ids")
    status = _lib.xyg_temporal_graph_set_selection(
        _temporal_u64(handle, "handle"),
        nodes.ctypes.data if len(nodes) else None,
        len(nodes),
        edges.ctypes.data if len(edges) else None,
        len(edges),
    )
    _temporal_controller_status(status)


def temporal_graph_set_focus(handle: int, kind: int, entity_id: Any | None = None) -> None:
    if isinstance(kind, bool) or kind not in (0, 1, 2):
        raise ValueError("kind must be 0 (clear), 1 (node), or 2 (edge)")
    if kind == 0:
        if entity_id is not None:
            raise ValueError("entity_id must be omitted when clearing focus")
        pointer = None
    else:
        if isinstance(entity_id, (bytes, bytearray, memoryview)):
            raw = bytes(entity_id)
            if len(raw) != 16:
                raise ValueError("entity_id must contain exactly 16 bytes")
            entity = np.frombuffer(raw, dtype=np.uint8).reshape((1, 16))
        else:
            entity = _projection_uuid_buffer(entity_id, "entity_id")
            if len(entity) != 1:
                raise ValueError("entity_id must contain exactly one UUID")
        pointer = entity.ctypes.data
    status = _lib.xyg_temporal_graph_set_focus(_temporal_u64(handle, "handle"), kind, pointer)
    _temporal_controller_status(status)


def temporal_graph_set_pinned(handle: int, node_ids: Any) -> None:
    nodes = _temporal_graph_uuid_buffer(node_ids, "node_ids")
    status = _lib.xyg_temporal_graph_set_pinned(
        _temporal_u64(handle, "handle"),
        nodes.ctypes.data if len(nodes) else None,
        len(nodes),
    )
    _temporal_controller_status(status)


def temporal_graph_required_budget(handle: int) -> int:
    budget = ctypes.c_uint64()
    status = _lib.xyg_temporal_graph_required_budget(
        _temporal_u64(handle, "handle"), ctypes.byref(budget)
    )
    _temporal_controller_status(status)
    return int(budget.value)


def temporal_graph_frame(
    handle: int,
    *,
    revision: int,
    cursor_micros: int,
    range_start_micros: int,
    range_end_micros: int,
    budget: int | None = None,
) -> None:
    if budget is None:
        budget = temporal_graph_required_budget(handle)
    status = _lib.xyg_temporal_graph_frame(
        _temporal_u64(handle, "handle"),
        _temporal_u64(revision, "revision"),
        _temporal_i64(cursor_micros, "cursor_micros"),
        _temporal_i64(range_start_micros, "range_start_micros"),
        _temporal_i64(range_end_micros, "range_end_micros"),
        _temporal_u64(budget, "budget"),
    )
    _temporal_controller_status(status)


def temporal_graph_cancel(handle: int) -> None:
    _temporal_controller_status(_lib.xyg_temporal_graph_cancel(_temporal_u64(handle, "handle")))


def _temporal_graph_uuid_output(count: int) -> npt.NDArray[np.uint8]:
    return np.empty((count, 16), dtype=np.uint8)


def temporal_graph_snapshot(handle: int) -> dict[str, object]:
    """Copy the last complete frame plus exact frozen export provenance."""
    meta = _TemporalGraphSnapshotMeta()
    status = _lib.xyg_temporal_graph_snapshot_meta(
        _temporal_u64(handle, "handle"), ctypes.byref(meta)
    )
    _temporal_controller_status(status)
    node_visibility = np.empty(meta.node_count, dtype=np.uint8)
    edge_visibility = np.empty(meta.edge_count, dtype=np.uint8)
    names = (
        ("visible_node_ids", meta.visible_node_count),
        ("visible_edge_ids", meta.visible_edge_count),
        ("selected_visible_node_ids", meta.selected_visible_node_count),
        ("selected_visible_edge_ids", meta.selected_visible_edge_count),
        ("pinned_visible_node_ids", meta.pinned_visible_node_count),
        ("selected_node_ids", meta.selected_node_count),
        ("selected_edge_ids", meta.selected_edge_count),
        ("pinned_node_ids", meta.pinned_node_count),
    )
    ids = {name: _temporal_graph_uuid_output(int(count)) for name, count in names}

    def ptr(array: npt.NDArray[np.uint8]) -> int | None:
        return array.ctypes.data if len(array) else None

    buffers = _TemporalGraphSnapshotBuffers(
        ptr(node_visibility),
        len(node_visibility),
        ptr(edge_visibility),
        len(edge_visibility),
        ptr(ids["visible_node_ids"]),
        len(ids["visible_node_ids"]),
        ptr(ids["visible_edge_ids"]),
        len(ids["visible_edge_ids"]),
        ptr(ids["selected_visible_node_ids"]),
        len(ids["selected_visible_node_ids"]),
        ptr(ids["selected_visible_edge_ids"]),
        len(ids["selected_visible_edge_ids"]),
        ptr(ids["pinned_visible_node_ids"]),
        len(ids["pinned_visible_node_ids"]),
        ptr(ids["selected_node_ids"]),
        len(ids["selected_node_ids"]),
        ptr(ids["selected_edge_ids"]),
        len(ids["selected_edge_ids"]),
        ptr(ids["pinned_node_ids"]),
        len(ids["pinned_node_ids"]),
    )
    status = _lib.xyg_temporal_graph_snapshot_copy(
        _temporal_u64(handle, "handle"),
        meta.revision,
        ctypes.byref(buffers),
    )
    _temporal_controller_status(status)

    def focus(kind: int, value: ctypes.Array[ctypes.c_uint8]) -> dict[str, object] | None:
        if kind == 0:
            return None
        return {"kind": "node" if kind == 1 else "edge", "id": bytes(value)}

    return {
        "revision": int(meta.revision),
        "cursor_micros": int(meta.cursor_micros),
        "range_start_micros": int(meta.range_start_micros),
        "range_end_micros": int(meta.range_end_micros),
        "node_visibility": node_visibility,
        "edge_visibility": edge_visibility,
        **ids,
        "focused_visible": focus(meta.focused_visible_kind, meta.focused_visible_id),
        "focused": focus(meta.focused_kind, meta.focused_id),
    }


def temporal_graph_destroy(handle: int) -> None:
    _temporal_controller_status(_lib.xyg_temporal_graph_destroy(_temporal_u64(handle, "handle")))


def graph_force_create(
    n_nodes: int,
    sources: npt.NDArray[np.uint64],
    targets: npt.NDArray[np.uint64],
    *,
    x: npt.NDArray[np.float64] | None = None,
    y: npt.NDArray[np.float64] | None = None,
    seed: int = 0,
    algorithm: int | str = GRAPH_LAYOUT_FORCE,
    cose: Mapping[str, Any] | None = None,
    pinned: npt.ArrayLike | None = None,
    parents: npt.ArrayLike | None = None,
) -> int:
    n_nodes = int(n_nodes)
    if n_nodes < 0:
        raise ValueError("n_nodes must be non-negative")
    sources = _as_u64(sources, "sources")
    targets = _as_u64(targets, "targets")
    if len(sources) != len(targets):
        raise ValueError("sources and targets must have equal length")
    algo = graph_layout_id(algorithm) if isinstance(algorithm, str) else int(algorithm)
    handle = ctypes.c_uint64(0)
    x_array = None if x is None else _as_f64(x, "x")
    y_array = None if y is None else _as_f64(y, "y")
    if (x_array is None) != (y_array is None):
        raise ValueError("force create requires both x and y or neither")
    if x_array is not None:
        assert y_array is not None
        if len(x_array) != n_nodes or len(y_array) != n_nodes:
            raise ValueError("x and y must have length n_nodes")
    in_x = None if x_array is None else _ptr_f64(x_array)
    in_y = None if y_array is None else _ptr_f64(y_array)
    configured_cose = cose is not None or pinned is not None or parents is not None
    if configured_cose:
        if algo != GRAPH_LAYOUT_COSE:
            raise ValueError("CoSE options, pins, and parents require algorithm='cose'")
        raw = dict(cose or {})
        allowed = {
            "ideal_edge_length",
            "repulsion_strength",
            "gravity_strength",
            "cooling_factor",
            "overlap_padding",
            "component_spacing",
            "bounds",
        }
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise ValueError(f"unknown CoSE option(s): {', '.join(unknown)}")
        pin_array = None
        if pinned is not None:
            raw_pins = np.asarray(pinned).reshape(-1)
            if not (
                np.issubdtype(raw_pins.dtype, np.bool_) or np.issubdtype(raw_pins.dtype, np.integer)
            ) or np.any((raw_pins != 0) & (raw_pins != 1)):
                raise ValueError("pinned must contain only booleans or 0/1 integers")
            pin_array = np.ascontiguousarray(raw_pins, dtype=np.uint8)
        parent_array = (
            None if parents is None else np.ascontiguousarray(parents, dtype=np.uint64).reshape(-1)
        )
        if pin_array is not None and len(pin_array) != int(n_nodes):
            raise ValueError("pinned must have length n_nodes")
        if parent_array is not None and len(parent_array) != int(n_nodes):
            raise ValueError("parents must have length n_nodes")
        if pin_array is not None and np.any(pin_array) and x is None:
            raise ValueError("pinned nodes require explicit x and y initial positions")
        bounds_value = raw.get("bounds")
        bounds = (
            None
            if bounds_value is None
            else np.ascontiguousarray(bounds_value, dtype=np.float64).reshape(-1)
        )
        if bounds is not None and len(bounds) != 4:
            raise ValueError("CoSE bounds must be (x0, y0, x1, y1)")
        descriptor = _CoseDescriptor(
            in_x,
            in_y,
            None if pin_array is None else pin_array.ctypes.data,
            None if parent_array is None else parent_array.ctypes.data,
            float(raw.get("ideal_edge_length", 1.0)),
            float(raw.get("repulsion_strength", 1.25)),
            float(raw.get("gravity_strength", 0.08)),
            float(raw.get("cooling_factor", 0.985)),
            float(raw.get("overlap_padding", 0.35)),
            float(raw.get("component_spacing", 2.5)),
            None if bounds is None else bounds.ctypes.data,
            0 if bounds is None else 1,
            0,
        )
        ok = _lib.xyg_graph_force_create_cose(
            ctypes.byref(descriptor),
            ctypes.c_uint64(int(n_nodes)),
            ctypes.c_uint64(len(sources)),
            sources.ctypes.data if len(sources) else None,
            targets.ctypes.data if len(targets) else None,
            ctypes.c_uint64(int(seed) & ((1 << 64) - 1)),
            ctypes.byref(handle),
        )
    else:
        ok = _lib.xyg_graph_force_create(
            ctypes.c_uint64(int(n_nodes)),
            ctypes.c_uint64(len(sources)),
            sources.ctypes.data if len(sources) else None,
            targets.ctypes.data if len(targets) else None,
            in_x,
            in_y,
            ctypes.c_uint64(int(seed) & ((1 << 64) - 1)),
            ctypes.c_uint32(algo),
            ctypes.byref(handle),
        )
    if ok != 0:
        raise ValueError("native graph_force_create failed")
    return int(handle.value)


def graph_is_progressive_force(layout: str | int) -> bool:
    layout_id = graph_layout_id(layout) if isinstance(layout, str) else int(layout)
    return layout_id in _GRAPH_PROGRESSIVE_FORCE


def graph_force_tick(
    handle: int, n_nodes: int, steps: int = 1
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], float]:
    out_x = np.empty(int(n_nodes), dtype=np.float64)
    out_y = np.empty(int(n_nodes), dtype=np.float64)
    alpha = ctypes.c_double()
    ok = _lib.xyg_graph_force_tick(
        ctypes.c_uint64(handle),
        ctypes.c_uint64(int(n_nodes)),
        ctypes.c_uint32(max(0, int(steps))),
        out_x.ctypes.data,
        out_y.ctypes.data,
        ctypes.byref(alpha),
    )
    if ok != 0:
        raise ValueError("native graph_force_tick failed")
    return out_x, out_y, float(alpha.value)


def graph_force_destroy(handle: int) -> bool:
    return _lib.xyg_graph_force_destroy(ctypes.c_uint64(handle)) == 1


def graph_lod_decision(
    n_nodes: int, n_edges: int, *, node_budget: int = 200_000, edge_budget: int = 500_000
) -> tuple[int, int]:
    tier = ctypes.c_uint32()
    kept = ctypes.c_uint64()
    ok = _lib.xyg_graph_lod_decision(
        ctypes.c_uint64(int(n_nodes)),
        ctypes.c_uint64(int(n_edges)),
        ctypes.c_uint64(int(node_budget)),
        ctypes.c_uint64(int(edge_budget)),
        ctypes.byref(tier),
        ctypes.byref(kept),
    )
    if ok != 0:
        raise ValueError("native graph_lod_decision failed")
    return int(tier.value), int(kept.value)


def graph_sample_edges(n_edges: int, budget: int) -> npt.NDArray[np.uint64]:
    budget = max(0, int(budget))
    out = np.empty(budget, dtype=np.uint64)
    if budget == 0:
        return out
    kept = _lib.xyg_graph_sample_edges(
        ctypes.c_uint64(int(n_edges)),
        ctypes.c_uint64(budget),
        out.ctypes.data,
    )
    return out[: int(kept)]


def graph_cluster_aggregate(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    *,
    n_edges: int = 0,
    node_budget: int,
    edge_budget: int = 500_000,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.uint64],
    int,
    int,
]:
    """Cluster graph node positions for LOD; returns centroids, membership, tier, edges_kept."""
    x_arr = _as_f64(x, "x")
    y_arr = _as_f64(y, "y")
    if len(x_arr) != len(y_arr):
        raise ValueError("x and y must have equal length")
    n_nodes = len(x_arr)
    node_budget = int(node_budget)
    edge_budget = int(edge_budget)
    if node_budget < 0:
        raise ValueError("node_budget must be non-negative")
    if n_nodes > node_budget and node_budget == 0:
        raise ValueError("node_budget must be positive when clustering non-empty positions")
    out_cap = n_nodes if n_nodes <= node_budget else node_budget
    out_x = np.empty(out_cap, dtype=np.float64)
    out_y = np.empty(out_cap, dtype=np.float64)
    member_of = np.empty(n_nodes, dtype=np.uint64)
    out_count = ctypes.c_uint64(0)
    tier = ctypes.c_uint32(0)
    edges_kept = ctypes.c_uint64(0)
    ok = _lib.xyg_graph_cluster_aggregate(
        ctypes.c_uint64(n_nodes),
        ctypes.c_uint64(int(n_edges)),
        x_arr.ctypes.data if n_nodes else None,
        y_arr.ctypes.data if n_nodes else None,
        ctypes.c_uint64(node_budget),
        ctypes.c_uint64(edge_budget),
        out_x.ctypes.data if out_cap else None,
        out_y.ctypes.data if out_cap else None,
        ctypes.byref(out_count),
        member_of.ctypes.data if n_nodes else None,
        ctypes.byref(tier),
        ctypes.byref(edges_kept),
    )
    if ok != 0:
        raise ValueError("native graph_cluster_aggregate failed")
    return (
        out_x[: int(out_count.value)],
        out_y[: int(out_count.value)],
        member_of,
        int(tier.value),
        int(edges_kept.value),
    )


def graph_build_render(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    sources: npt.NDArray[np.uint64],
    targets: npt.NDArray[np.uint64],
    *,
    node_budget: int = 200_000,
    edge_budget: int = 500_000,
    viewport: tuple[float, float, float, float] | None = None,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.uint64],
    npt.NDArray[np.uint64],
    npt.NDArray[np.uint64],
    int,
    int,
]:
    """Build a perceptually bounded render graph; returns nodes, member_of, edges, tier, edges_kept."""
    x_arr = _as_f64(x, "x")
    y_arr = _as_f64(y, "y")
    if len(x_arr) != len(y_arr):
        raise ValueError("x and y must have equal length")
    sources = _as_u64(sources, "sources")
    targets = _as_u64(targets, "targets")
    if len(sources) != len(targets):
        raise ValueError("sources and targets must have equal length")
    n_nodes = len(x_arr)
    node_budget = max(1, int(node_budget))
    edge_budget = max(1, int(edge_budget))
    out_node_cap = min(n_nodes, node_budget) if n_nodes else 0
    out_x = np.empty(out_node_cap, dtype=np.float64)
    out_y = np.empty(out_node_cap, dtype=np.float64)
    member_of = np.empty(n_nodes, dtype=np.uint64)
    edge_s = np.empty(edge_budget, dtype=np.uint64)
    edge_t = np.empty(edge_budget, dtype=np.uint64)
    out_n_nodes = ctypes.c_uint64(0)
    out_n_edges = ctypes.c_uint64(0)
    tier = ctypes.c_uint32(0)
    edges_kept = ctypes.c_uint64(0)
    if viewport is None:
        vp_en, x0, y0, x1, y1 = 0, 0.0, 0.0, 0.0, 0.0
    else:
        vp_en = 1
        x0, y0, x1, y1 = (float(v) for v in viewport)
    ok = _lib.xyg_graph_build_render(
        ctypes.c_uint64(n_nodes),
        ctypes.c_uint64(len(sources)),
        x_arr.ctypes.data if n_nodes else None,
        y_arr.ctypes.data if n_nodes else None,
        sources.ctypes.data if len(sources) else None,
        targets.ctypes.data if len(targets) else None,
        ctypes.c_uint64(node_budget),
        ctypes.c_uint64(edge_budget),
        ctypes.c_int32(vp_en),
        ctypes.c_double(x0),
        ctypes.c_double(y0),
        ctypes.c_double(x1),
        ctypes.c_double(y1),
        out_x.ctypes.data if out_node_cap else None,
        out_y.ctypes.data if out_node_cap else None,
        member_of.ctypes.data if n_nodes else None,
        edge_s.ctypes.data if edge_budget else None,
        edge_t.ctypes.data if edge_budget else None,
        ctypes.byref(out_n_nodes),
        ctypes.byref(out_n_edges),
        ctypes.byref(tier),
        ctypes.byref(edges_kept),
    )
    if ok != 0:
        raise ValueError("native graph_build_render failed")
    n_out = int(out_n_nodes.value)
    e_out = int(out_n_edges.value)
    return (
        out_x[:n_out],
        out_y[:n_out],
        member_of,
        edge_s[:e_out],
        edge_t[:e_out],
        int(tier.value),
        int(edges_kept.value),
    )


EDGE_ROUTE_SEGMENTS_PER_EDGE = 5


def graph_edge_route_segments(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    sources: npt.NDArray[np.uint64],
    targets: npt.NDArray[np.uint64],
    *,
    directed: bool = True,
    separation: float = 0.08,
    loop_radius: float = 0.35,
    arrow_size: float = 0.12,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.uint64],
]:
    """Route render-graph edges into paint segments (parallels, loops, arrows)."""
    x_arr = _as_f64(x, "x")
    y_arr = _as_f64(y, "y")
    if len(x_arr) != len(y_arr):
        raise ValueError("x and y must have equal length")
    sources = _as_u64(sources, "sources")
    targets = _as_u64(targets, "targets")
    if len(sources) != len(targets):
        raise ValueError("sources and targets must have equal length")
    n_nodes = len(x_arr)
    n_edges = len(sources)
    cap = n_edges * EDGE_ROUTE_SEGMENTS_PER_EDGE
    out_x0 = np.empty(cap, dtype=np.float64)
    out_y0 = np.empty(cap, dtype=np.float64)
    out_x1 = np.empty(cap, dtype=np.float64)
    out_y1 = np.empty(cap, dtype=np.float64)
    out_edge_index = np.empty(cap, dtype=np.uint64)
    out_n = ctypes.c_uint64(0)
    ok = _lib.xyg_graph_edge_route_segments(
        ctypes.c_uint64(n_nodes),
        ctypes.c_uint64(n_edges),
        x_arr.ctypes.data if n_nodes else None,
        y_arr.ctypes.data if n_nodes else None,
        sources.ctypes.data if n_edges else None,
        targets.ctypes.data if n_edges else None,
        ctypes.c_int32(1 if directed else 0),
        ctypes.c_double(float(separation)),
        ctypes.c_double(float(loop_radius)),
        ctypes.c_double(float(arrow_size)),
        out_x0.ctypes.data if cap else None,
        out_y0.ctypes.data if cap else None,
        out_x1.ctypes.data if cap else None,
        out_y1.ctypes.data if cap else None,
        out_edge_index.ctypes.data if cap else None,
        ctypes.byref(out_n),
    )
    if ok != 0:
        raise ValueError("native graph_edge_route_segments failed")
    n_seg = int(out_n.value)
    return (
        out_x0[:n_seg],
        out_y0[:n_seg],
        out_x1[:n_seg],
        out_y1[:n_seg],
        out_edge_index[:n_seg],
    )


def graph_visual_states(flags: npt.NDArray[np.uint32]) -> npt.NDArray[np.uint8]:
    """Resolve interaction flags with the shared Rust precedence contract."""
    raw = np.asarray(flags)
    if raw.ndim != 1 or raw.dtype.kind not in "iu" or raw.dtype.kind == "b":
        raise ValueError("flags must be a 1-D exact integer array")
    if any(int(value) < 0 or int(value) > 0xFFFF_FFFF for value in raw):
        raise ValueError("flags must contain uint32 values")
    flags_arr = np.ascontiguousarray(raw, dtype=np.uint32)
    out = np.empty(len(flags_arr), dtype=np.uint8)
    status = _lib.xyg_graph_visual_state_resolve(
        ctypes.c_uint64(len(flags_arr)),
        flags_arr.ctypes.data if len(flags_arr) else None,
        out.ctypes.data if len(out) else None,
    )
    if status != 0:
        raise ValueError("native graph_visual_states failed")
    return out


def graph_semantic_styles(
    classes: Any,
    epistemic: Any,
    statuses: Any,
    metric: Any,
    flags: Any,
    *,
    edge: bool = False,
    theme: str = "light",
) -> dict[str, Any]:
    """Resolve the v1 GraphForge semantic style contract in Rust."""
    if not isinstance(edge, (bool, np.bool_)):
        raise TypeError("edge must be a bool")
    theme_id = {"light": 0, "dark": 1}.get(theme)
    if theme_id is None:
        raise ValueError("theme must be 'light' or 'dark'")
    inputs = [np.asarray(value) for value in (classes, epistemic, statuses)]
    if any(value.ndim != 1 or value.dtype.kind not in "iu" for value in inputs):
        raise ValueError("semantic codes must be 1-D integer arrays")
    if any(any(int(code) < 0 or int(code) > 7 for code in value) for value in inputs):
        raise ValueError("semantic codes must be in the closed range 0..7")
    codes = [np.ascontiguousarray(value, dtype=np.uint8) for value in inputs]
    metric_arr = np.ascontiguousarray(metric, dtype=np.float64)
    flag_raw = np.asarray(flags)
    if flag_raw.ndim != 1 or flag_raw.dtype.kind not in "iu" or flag_raw.dtype.kind == "b":
        raise ValueError("flags must be a 1-D exact integer array")
    if any(int(value) < 0 or int(value) > 0xFFFF_FFFF for value in flag_raw):
        raise ValueError("flags must contain uint32 values")
    flags_arr = np.ascontiguousarray(flag_raw, dtype=np.uint32)
    n = len(codes[0])
    if metric_arr.ndim != 1 or any(
        len(value) != n for value in [*codes[1:], metric_arr, flags_arr]
    ):
        raise ValueError("semantic style fields must have equal 1-D lengths")
    rgba = [np.empty((n, 4), dtype=np.uint8) for _ in range(3)]
    floats = [np.empty(n, dtype=np.float32) for _ in range(3)]
    bytes_out = [np.empty(n, dtype=np.uint8) for _ in range(4)]
    lo = ctypes.c_double()
    hi = ctypes.c_double()

    def ptr(value: np.ndarray) -> int | None:
        return value.ctypes.data if n else None

    status = _lib.xyg_graph_semantic_style_resolve(
        ctypes.c_uint32(1),
        ctypes.c_uint32(theme_id),
        ctypes.c_uint64(n),
        *(ptr(value) for value in codes),
        ptr(metric_arr),
        ptr(flags_arr),
        ctypes.c_int32(bool(edge)),
        *(ptr(value) for value in rgba),
        *(ptr(value) for value in floats),
        *(ptr(value) for value in bytes_out),
        ctypes.byref(lo),
        ctypes.byref(hi),
    )
    if status != 0:
        raise ValueError("native graph_semantic_styles failed")
    return {
        "version": 1,
        "fill_rgba": rgba[0],
        "stroke_rgba": rgba[1],
        "halo_rgba": rgba[2],
        "size": floats[0],
        "width": floats[1],
        "opacity": floats[2],
        "shape": bytes_out[0],
        "dash": bytes_out[1],
        "arrow": bytes_out[2],
        "state": bytes_out[3],
        "metric_domain": (lo.value, hi.value),
    }


def graph_semantic_legend(
    classes: Any, epistemic: Any, statuses: Any, *, theme: str = "light"
) -> dict[str, Any]:
    """Return bounded deterministic v1 GraphForge legend descriptors."""
    theme_id = {"light": 0, "dark": 1}.get(theme)
    if theme_id is None:
        raise ValueError("theme must be 'light' or 'dark'")
    values = [np.asarray(value) for value in (classes, epistemic, statuses)]
    if any(value.ndim != 1 or value.dtype.kind not in "iu" for value in values):
        raise ValueError("semantic codes must be 1-D integer arrays")
    if any(any(int(code) < 0 or int(code) > 7 for code in value) for value in values):
        raise ValueError("semantic codes must be in the closed range 0..7")
    codes = [np.ascontiguousarray(value, dtype=np.uint8) for value in values]
    n = len(codes[0])
    if any(len(value) != n for value in codes[1:]):
        raise ValueError("semantic legend fields must have equal lengths")
    count = ctypes.c_uint64()

    def ptr(value: np.ndarray) -> int | None:
        return value.ctypes.data if len(value) else None

    status = _lib.xyg_graph_semantic_legend(
        1,
        theme_id,
        n,
        *(ptr(value) for value in codes),
        0,
        None,
        None,
        None,
        None,
        ctypes.byref(count),
    )
    if status != 0 or count.value > 24:
        raise ValueError("native graph_semantic_legend query failed")
    cap = int(count.value)
    field = np.empty(cap, dtype=np.uint8)
    value = np.empty(cap, dtype=np.uint8)
    rgba = np.empty((cap, 4), dtype=np.uint8)
    shape = np.empty(cap, dtype=np.uint8)
    status = _lib.xyg_graph_semantic_legend(
        1,
        theme_id,
        n,
        *(ptr(item) for item in codes),
        cap,
        ptr(field),
        ptr(value),
        ptr(rgba),
        ptr(shape),
        ctypes.byref(count),
    )
    if status != 0 or count.value != cap:
        raise ValueError("native graph_semantic_legend copy failed")
    return {
        "version": 1,
        "theme": theme,
        "field": field,
        "value": value,
        "rgba": rgba,
        "shape": shape,
    }


def graph_label_accept(
    priorities: npt.NDArray[np.float64], budget: int, *, min_priority: float | None = None
) -> npt.NDArray[np.bool_]:
    """Return the deterministic Rust-owned label mask for the viewport budget."""
    # Priorities deliberately use their own converter: non-finite values are
    # valid missing candidates that Rust rejects from the accepted mask.
    priority_arr = np.ascontiguousarray(priorities, dtype=np.float64)
    if priority_arr.ndim != 1:
        raise ValueError(f"priorities must be 1-D, got shape {priority_arr.shape}")
    if isinstance(budget, (bool, np.bool_)):
        raise TypeError("budget must be an exact uint64 integer")
    try:
        budget_value = operator.index(budget)
    except TypeError as exc:
        raise TypeError("budget must be an exact uint64 integer") from exc
    if budget_value < 0 or budget_value > 0xFFFF_FFFF_FFFF_FFFF:
        raise ValueError("budget must fit uint64")
    out = np.empty(len(priority_arr), dtype=np.uint8)
    count = ctypes.c_uint64()
    status = _lib.xyg_graph_label_accept(
        ctypes.c_uint64(len(priority_arr)),
        priority_arr.ctypes.data if len(priority_arr) else None,
        ctypes.c_uint64(budget_value),
        ctypes.c_double(math.nan if min_priority is None else float(min_priority)),
        out.ctypes.data if len(out) else None,
        ctypes.byref(count),
    )
    if status != 0:
        raise ValueError("native graph_label_accept failed")
    return out.astype(np.bool_)


def graph_compound_bounds(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    parents: npt.NDArray[np.uint64],
    parent_validity: npt.NDArray[np.uint8],
) -> tuple[npt.NDArray[np.uint64], npt.NDArray[np.bool_], npt.NDArray[np.float64]]:
    """Return parent membership, compound mask, and ``[xmin,xmax,ymin,ymax]`` bounds."""
    x_arr = _as_f64(x, "x")
    y_arr = _as_f64(y, "y")
    raw_parents = np.asarray(parents)
    if raw_parents.ndim != 1 or raw_parents.dtype.kind not in "iu" or raw_parents.dtype.kind == "b":
        raise ValueError("parents must be a 1-D exact integer array")
    if any(int(value) < 0 or int(value) > 0xFFFF_FFFF_FFFF_FFFF for value in raw_parents):
        raise ValueError("parents must contain uint64 identities")
    parent_arr = np.ascontiguousarray(raw_parents, dtype=np.uint64)
    raw_validity = np.asarray(parent_validity)
    if raw_validity.ndim != 1 or raw_validity.dtype.kind not in "iub":
        raise ValueError("parent_validity must be a 1-D boolean or integer array")
    if any(int(value) not in (0, 1) for value in raw_validity):
        raise ValueError("parent_validity must contain only 0 or 1")
    validity_arr = np.ascontiguousarray(raw_validity, dtype=np.uint8)
    n = len(x_arr)
    if (
        y_arr.ndim != 1
        or validity_arr.ndim != 1
        or len(y_arr) != n
        or len(parent_arr) != n
        or len(validity_arr) != n
    ):
        raise ValueError("compound inputs must be 1-D arrays of equal length")
    parent_of = np.empty(n, dtype=np.uint64)
    compounds = np.empty(n, dtype=np.uint8)
    xmin = np.empty(n, dtype=np.float64)
    xmax = np.empty(n, dtype=np.float64)
    ymin = np.empty(n, dtype=np.float64)
    ymax = np.empty(n, dtype=np.float64)
    status = _lib.xyg_graph_compound_bounds(
        ctypes.c_uint64(n),
        x_arr.ctypes.data if n else None,
        y_arr.ctypes.data if n else None,
        parent_arr.ctypes.data if n else None,
        validity_arr.ctypes.data if n else None,
        parent_of.ctypes.data if n else None,
        compounds.ctypes.data if n else None,
        xmin.ctypes.data if n else None,
        xmax.ctypes.data if n else None,
        ymin.ctypes.data if n else None,
        ymax.ctypes.data if n else None,
    )
    if status != 0:
        raise ValueError("native graph_compound_bounds failed")
    return parent_of, compounds.astype(np.bool_), np.column_stack((xmin, xmax, ymin, ymax))


def graph_compound_transition(
    node_ids: npt.ArrayLike,
    parents: npt.ArrayLike,
    parent_validity: npt.ArrayLike,
    collapsed: npt.ArrayLike,
    target_id: int,
    action: int,
    lod_tier: int = 0,
) -> tuple[npt.NDArray[np.bool_], bool]:
    """Apply one Rust-owned compound disclosure transition by stable identity."""

    def exact_unsigned(
        values: npt.ArrayLike,
        name: str,
        dtype: npt.DTypeLike,
        maximum: int,
        *,
        allow_bool: bool = False,
    ):
        raw = np.asarray(values)
        if raw.ndim != 1 or raw.dtype.kind not in ("iub" if allow_bool else "iu"):
            raise ValueError(f"{name} must be a 1-D exact integer array")
        if any(int(value) < 0 or int(value) > maximum for value in raw):
            raise ValueError(f"{name} contains an out-of-range value")
        return np.ascontiguousarray(raw, dtype=dtype)

    ids = exact_unsigned(node_ids, "node_ids", np.uint64, 0xFFFF_FFFF_FFFF_FFFF)
    parent_arr = exact_unsigned(parents, "parents", np.uint64, 0xFFFF_FFFF_FFFF_FFFF)
    validity = exact_unsigned(parent_validity, "parent_validity", np.uint8, 1, allow_bool=True)
    state = exact_unsigned(collapsed, "collapsed", np.uint8, 1, allow_bool=True)
    if not (len(parent_arr) == len(validity) == len(state) == len(ids)):
        raise ValueError("compound transition planes must have equal length")
    if (
        isinstance(target_id, (bool, np.bool_))
        or not 0 <= operator.index(target_id) <= 0xFFFF_FFFF_FFFF_FFFF
    ):
        raise ValueError("target_id must be an exact uint64 integer")
    if isinstance(action, (bool, np.bool_)) or isinstance(lod_tier, (bool, np.bool_)):
        raise TypeError("action and lod_tier must be exact integers")
    action_value = operator.index(action)
    lod_value = operator.index(lod_tier)
    if not 0 <= action_value <= 0xFFFF_FFFF or not 0 <= lod_value <= 0xFFFF_FFFF:
        raise ValueError("action and lod_tier must fit uint32")
    out = np.empty(len(ids), dtype=np.uint8)
    changed = ctypes.c_uint8()
    status = _lib.xyg_graph_compound_transition(
        ctypes.c_uint64(len(ids)),
        ids.ctypes.data if len(ids) else None,
        parent_arr.ctypes.data if len(ids) else None,
        validity.ctypes.data if len(ids) else None,
        state.ctypes.data if len(ids) else None,
        ctypes.c_uint64(operator.index(target_id)),
        ctypes.c_uint32(action_value),
        ctypes.c_uint32(lod_value),
        out.ctypes.data if len(ids) else None,
        ctypes.byref(changed),
    )
    if status != 0:
        raise ValueError("native graph_compound_transition failed")
    return out.astype(np.bool_), bool(changed.value)


def graph_compound_scene(
    *,
    width,
    height,
    theme,
    title,
    x,
    y,
    node_classes,
    node_epistemic,
    node_statuses,
    node_metric,
    node_flags,
    node_labels,
    sources,
    targets,
    edge_classes,
    edge_epistemic,
    edge_statuses,
    edge_metric,
    edge_flags,
    edge_labels,
    parents,
    parent_validity,
    collapsed,
) -> bytes:
    """Compile Rust-owned compound/collapse policy to one canonical Scene."""
    xa, ya = _as_f64(np.asarray(x), "x"), _as_f64(np.asarray(y), "y")
    arrays = {
        "node_classes": np.ascontiguousarray(node_classes, dtype=np.uint8),
        "node_epistemic": np.ascontiguousarray(node_epistemic, dtype=np.uint8),
        "node_statuses": np.ascontiguousarray(node_statuses, dtype=np.uint8),
        "node_metric": _as_f64(np.asarray(node_metric), "node_metric"),
        "node_flags": np.ascontiguousarray(node_flags, dtype=np.uint32),
        "sources": np.ascontiguousarray(sources, dtype=np.uint64),
        "targets": np.ascontiguousarray(targets, dtype=np.uint64),
        "edge_classes": np.ascontiguousarray(edge_classes, dtype=np.uint8),
        "edge_epistemic": np.ascontiguousarray(edge_epistemic, dtype=np.uint8),
        "edge_statuses": np.ascontiguousarray(edge_statuses, dtype=np.uint8),
        "edge_metric": _as_f64(np.asarray(edge_metric), "edge_metric"),
        "edge_flags": np.ascontiguousarray(edge_flags, dtype=np.uint32),
        "parents": np.ascontiguousarray(parents, dtype=np.uint64),
        "parent_validity": np.ascontiguousarray(parent_validity, dtype=np.uint8),
        "collapsed": np.ascontiguousarray(collapsed, dtype=np.uint8),
    }
    n, e = len(xa), len(arrays["sources"])
    if (
        len(ya) != n
        or any(
            len(arrays[name]) != n
            for name in (
                "node_classes",
                "node_epistemic",
                "node_statuses",
                "node_metric",
                "node_flags",
                "parents",
                "parent_validity",
                "collapsed",
            )
        )
        or len(node_labels) != n
    ):
        raise ValueError("node and compound planes must have exactly node_count values")
    if (
        any(
            len(arrays[name]) != e
            for name in (
                "targets",
                "edge_classes",
                "edge_epistemic",
                "edge_statuses",
                "edge_metric",
                "edge_flags",
            )
        )
        or len(edge_labels) != e
    ):
        raise ValueError("edge planes must have exactly edge_count values")
    if not isinstance(title, str) or any(
        not isinstance(value, str) for value in (*node_labels, *edge_labels)
    ):
        raise TypeError("title and graph labels must be strings")
    encoded_labels = [value.encode() for value in (*node_labels, *edge_labels)]
    payload = b"".join(encoded_labels)
    node_lengths = np.asarray([len(value) for value in encoded_labels[:n]], dtype=np.uint32)
    edge_lengths = np.asarray([len(value) for value in encoded_labels[n:]], dtype=np.uint32)
    title_bytes = title.encode()
    title_buffer, payload_buffer = (
        ctypes.create_string_buffer(title_bytes),
        ctypes.create_string_buffer(payload),
    )
    descriptor = _GraphCompoundSceneDescriptor(
        2,
        int(theme),
        float(width),
        float(height),
        n,
        e,
        ctypes.addressof(title_buffer),
        len(title_bytes),
        xa.ctypes.data,
        ya.ctypes.data,
        *[
            arrays[name].ctypes.data
            for name in (
                "node_classes",
                "node_epistemic",
                "node_statuses",
                "node_metric",
                "node_flags",
            )
        ],
        node_lengths.ctypes.data,
        *[
            arrays[name].ctypes.data
            for name in (
                "sources",
                "targets",
                "edge_classes",
                "edge_epistemic",
                "edge_statuses",
                "edge_metric",
                "edge_flags",
            )
        ],
        edge_lengths.ctypes.data if e else None,
        ctypes.addressof(payload_buffer) if payload else None,
        len(payload),
        arrays["parents"].ctypes.data,
        arrays["parent_validity"].ctypes.data,
        arrays["collapsed"].ctypes.data,
        0,
    )
    needed = int(_lib.xyg_graph_compound_scene(ctypes.byref(descriptor), None, 0))
    if needed == ctypes.c_size_t(-1).value:
        raise ValueError("invalid compound graph Scene input")
    output = (ctypes.c_uint8 * needed)()
    if int(_lib.xyg_graph_compound_scene(ctypes.byref(descriptor), output, needed)) != needed:
        raise ValueError("compound graph Scene changed between bounded copies")
    return bytes(output)


def graph_cluster_positions(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    budget: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.uint64]]:
    """Compat wrapper around :func:`graph_cluster_aggregate` (centroids + membership only)."""
    cx, cy, member_of, _tier, _kept = graph_cluster_aggregate(
        x, y, n_edges=0, node_budget=budget, edge_budget=max(int(budget), 1)
    )
    return cx, cy, member_of


def graph_build_csr(
    n_nodes: int,
    sources: npt.NDArray[np.uint64],
    targets: npt.NDArray[np.uint64],
    *,
    directed: bool = True,
) -> tuple[npt.NDArray[np.uint64], npt.NDArray[np.uint64]]:
    """Build CSR offsets (len n+1) and neighbors (u64) for neighborhood highlight."""
    sources = _as_u64(sources, "sources")
    targets = _as_u64(targets, "targets")
    n_nodes = int(n_nodes)
    if n_nodes < 0:
        raise ValueError("n_nodes must be non-negative")
    # Undirected doubles edges; directed uses |E|. Cap with 2*|E|.
    cap = max(len(sources) * 2, 1)
    offsets = np.empty(n_nodes + 1, dtype=np.uint64)
    neighbors = np.empty(cap, dtype=np.uint64)
    out_len = ctypes.c_uint64(0)
    ok = _lib.xyg_graph_build_csr(
        ctypes.c_uint64(n_nodes),
        ctypes.c_uint64(len(sources)),
        sources.ctypes.data if len(sources) else None,
        targets.ctypes.data if len(targets) else None,
        ctypes.c_int32(1 if directed else 0),
        offsets.ctypes.data,
        neighbors.ctypes.data,
        ctypes.c_uint64(cap),
        ctypes.byref(out_len),
    )
    if ok != 0:
        raise ValueError("native graph_build_csr failed")
    return offsets, neighbors[: int(out_len.value)]


# Sankey align ids — must match `sankey::ALIGN_*` in src/sankey.rs.
SANKEY_ALIGN_JUSTIFY = 0
SANKEY_ALIGN_LEFT = 1
SANKEY_ALIGN_RIGHT = 2
SANKEY_ALIGN_CENTER = 3

_SANKEY_ALIGN_NAMES = {
    "justify": SANKEY_ALIGN_JUSTIFY,
    "left": SANKEY_ALIGN_LEFT,
    "right": SANKEY_ALIGN_RIGHT,
    "center": SANKEY_ALIGN_CENTER,
}


def sankey_align_id(name: str) -> int:
    key = str(name).strip().lower()
    if key not in _SANKEY_ALIGN_NAMES:
        raise ValueError(f"sankey align must be one of {sorted(_SANKEY_ALIGN_NAMES)}; got {name!r}")
    return _SANKEY_ALIGN_NAMES[key]


class SankeyLayoutError(ValueError):
    """Native sankey layout refusal with structured detail for host messages."""

    __slots__ = ("code", "err_nodes")

    def __init__(self, code: int, err_nodes: npt.NDArray[np.uint64], message: str) -> None:
        super().__init__(message)
        self.code = int(code)
        self.err_nodes = err_nodes


def sankey_layout(
    sources: npt.NDArray[np.uint64],
    targets: npt.NDArray[np.uint64],
    values: npt.NDArray[np.float64],
    *,
    n_nodes: int,
    node_width: float = 0.02,
    node_padding: float = 0.02,
    align: str | int = "justify",
    iterations: int = 6,
) -> dict[str, Any]:
    """Run the native Sankey layout; returns dict of f64/u32 arrays + `layers`.

    Raises `SankeyLayoutError` with `.code` `-2` (cycle) or `-3` (padding) and
    `.err_nodes` carrying the detail indices the host maps to names/text.
    Other failures raise `ValueError`.
    """
    n_nodes = int(n_nodes)
    if n_nodes <= 0:
        raise ValueError("n_nodes must be positive")
    sources = _as_u64(sources, "sources")
    targets = _as_u64(targets, "targets")
    values = _as_f64(values, "values")
    if not (len(sources) == len(targets) == len(values)):
        raise ValueError("sources, targets, and values must have equal length")
    if len(sources) == 0:
        raise ValueError("sankey needs at least one link")
    align_id = sankey_align_id(align) if isinstance(align, str) else int(align)
    out_x0 = np.empty(n_nodes, dtype=np.float64)
    out_y0 = np.empty(n_nodes, dtype=np.float64)
    out_x1 = np.empty(n_nodes, dtype=np.float64)
    out_y1 = np.empty(n_nodes, dtype=np.float64)
    out_layer = np.empty(n_nodes, dtype=np.uint32)
    out_value = np.empty(n_nodes, dtype=np.float64)
    n_links = len(sources)
    out_sy0 = np.empty(n_links, dtype=np.float64)
    out_sy1 = np.empty(n_links, dtype=np.float64)
    out_ty0 = np.empty(n_links, dtype=np.float64)
    out_ty1 = np.empty(n_links, dtype=np.float64)
    out_layers = ctypes.c_uint32(0)
    out_err_nodes = np.empty(n_nodes, dtype=np.uint64)
    out_err_n = ctypes.c_uint64(0)
    code = _lib.xyg_sankey_layout(
        ctypes.c_uint64(n_nodes),
        ctypes.c_uint64(n_links),
        sources.ctypes.data,
        targets.ctypes.data,
        values.ctypes.data,
        ctypes.c_double(float(node_width)),
        ctypes.c_double(float(node_padding)),
        ctypes.c_uint32(align_id),
        ctypes.c_uint32(max(0, int(iterations))),
        out_x0.ctypes.data,
        out_y0.ctypes.data,
        out_x1.ctypes.data,
        out_y1.ctypes.data,
        out_layer.ctypes.data,
        out_value.ctypes.data,
        out_sy0.ctypes.data,
        out_sy1.ctypes.data,
        out_ty0.ctypes.data,
        out_ty1.ctypes.data,
        ctypes.byref(out_layers),
        out_err_nodes.ctypes.data,
        ctypes.byref(out_err_n),
    )
    err = out_err_nodes[: int(out_err_n.value)].copy()
    if code == -2:
        raise SankeyLayoutError(-2, err, "sankey links form a cycle")
    if code == -3:
        raise SankeyLayoutError(-3, err, "sankey node_padding leaves no room")
    if code != 0:
        raise ValueError("native sankey_layout failed (invalid arguments)")
    return {
        "x0": out_x0,
        "y0": out_y0,
        "x1": out_x1,
        "y1": out_y1,
        "layer": out_layer,
        "value": out_value,
        "source_y0": out_sy0,
        "source_y1": out_sy1,
        "target_y0": out_ty0,
        "target_y1": out_ty1,
        "layers": int(out_layers.value),
    }


def local_log_density(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    lo_x: float,
    hi_x: float,
    lo_y: float,
    hi_y: float,
    w: int,
    h: int,
) -> npt.NDArray[np.float32]:
    """Per-point log-normalized local density in [0,1]."""
    w = _bounded_positive_int(w, "w")
    h = _bounded_positive_int(h, "h")
    lo_x, hi_x = _finite_increasing(lo_x, hi_x, "x range")
    lo_y, hi_y = _finite_increasing(lo_y, hi_y, "y range")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    out = np.empty(len(x), dtype=np.float32)
    if len(x):
        ok = _lib.xyg_local_log_density(
            _ptr_f64(x),
            _ptr_f64(y),
            len(x),
            lo_x,
            hi_x,
            lo_y,
            hi_y,
            w,
            h,
            out.ctypes.data,
        )
        if not ok:
            raise ValueError("invalid local_log_density arguments")
    return out


def rasterize(cmds: bytes, w: int, h: int) -> npt.NDArray[np.uint8]:
    """Paint a display-list command buffer (`_raster.py`) into an ``(h, w, 4)``
    straight-alpha RGBA8 image via the native rasterizer. Raises on a malformed
    buffer (the Rust side returns 0 = output undefined)."""
    w = _positive_int(w, "raster width")
    h = _positive_int(h, "raster height")
    buf = np.frombuffer(cmds, dtype=np.uint8)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    cmd_ptr = _ptr_u8(buf) if buf.size else None
    ok = _lib.xyg_rasterize(cmd_ptr, buf.size, _ptr_u8(out), w, h)
    if not ok:
        raise ValueError("native rasterizer rejected the command buffer")
    return out


def rasterize_png(cmds: bytes, w: int, h: int) -> bytes:
    """Paint a display list and encode it as PNG wholly inside the Rust core."""
    w = _positive_int(w, "raster width")
    h = _positive_int(h, "raster height")
    buf = np.frombuffer(cmds, dtype=np.uint8)
    raw_len = operator.mul(operator.mul(w, h), 4)
    capacity = raw_len + raw_len // 8 + 65_536
    out = np.empty(capacity, dtype=np.uint8)
    cmd_ptr = _ptr_u8(buf) if buf.size else None
    written = _lib.xyg_rasterize_png(cmd_ptr, buf.size, _ptr_u8(out), out.size, w, h)
    if written == _USIZE_MAX or written > out.size:
        raise ValueError("native raster-to-PNG encoder rejected the command buffer")
    return out[:written].tobytes()


def rasterize_png_data(cmds: bytes, data: bytes, w: int, h: int) -> bytes:
    """Paint a display list with an external arena and encode PNG in Rust."""
    w = _positive_int(w, "raster width")
    h = _positive_int(h, "raster height")
    buf = np.frombuffer(cmds, dtype=np.uint8)
    arena = np.frombuffer(data, dtype=np.uint8)
    raw_len = operator.mul(operator.mul(w, h), 4)
    capacity = raw_len + raw_len // 8 + 65_536
    out = np.empty(capacity, dtype=np.uint8)
    written = _lib.xyg_rasterize_png_data(
        _ptr_u8(buf) if buf.size else None,
        buf.size,
        _ptr_u8(arena) if arena.size else None,
        arena.size,
        _ptr_u8(out),
        out.size,
        w,
        h,
    )
    if written == _USIZE_MAX or written > out.size:
        raise ValueError(
            "native raster-to-PNG encoder rejected the command buffer or external data"
        )
    return out[:written].tobytes()


def rasterize_data(cmds: bytes, data: bytes, w: int, h: int) -> npt.NDArray[np.uint8]:
    """Paint a display list that may reference a synchronous external arena."""
    w = _positive_int(w, "raster width")
    h = _positive_int(h, "raster height")
    buf = np.frombuffer(cmds, dtype=np.uint8)
    arena = np.frombuffer(data, dtype=np.uint8)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    ok = _lib.xyg_rasterize_data(
        _ptr_u8(buf) if buf.size else None,
        buf.size,
        _ptr_u8(arena) if arena.size else None,
        arena.size,
        _ptr_u8(out),
        w,
        h,
    )
    if not ok:
        raise ValueError("native rasterizer rejected the command buffer or external data")
    return out


def _byte_span_arrays(spans):  # noqa: ANN001, ANN202 - private ctypes adapter
    arenas: list[npt.NDArray[np.uint8]] = []
    for span in spans:
        if isinstance(span, np.ndarray):
            contiguous = np.ascontiguousarray(span)
            arena = contiguous.view(np.uint8).reshape(-1)
        else:
            arena = np.frombuffer(span, dtype=np.uint8)
        arenas.append(arena)
    pointer_type = ctypes.c_void_p * len(arenas)
    length_type = ctypes.c_size_t * len(arenas)
    pointers = pointer_type(*(arena.ctypes.data if arena.size else None for arena in arenas))
    lengths = length_type(*(arena.size for arena in arenas))
    return arenas, pointers, lengths


def rasterize_spans(cmds: Any, spans, w: int, h: int) -> npt.NDArray[np.uint8]:  # noqa: ANN001
    """Paint a display list borrowing multiple call-scoped byte arenas.

    `cmds` is any read-only-safe buffer (`bytes`, `bytearray`, `memoryview`):
    it is borrowed through `np.frombuffer`, never copied."""
    w = _positive_int(w, "raster width")
    h = _positive_int(h, "raster height")
    buf = np.frombuffer(cmds, dtype=np.uint8)
    arenas, pointers, lengths = _byte_span_arrays(spans)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    ok = _lib.xyg_rasterize_spans(
        _ptr_u8(buf) if buf.size else None,
        buf.size,
        pointers if arenas else None,
        lengths if arenas else None,
        len(arenas),
        _ptr_u8(out),
        w,
        h,
    )
    if not ok:
        raise ValueError("native rasterizer rejected the command buffer or borrowed spans")
    return out


def rasterize_png_spans(cmds: Any, spans, w: int, h: int) -> bytes:  # noqa: ANN001
    """Paint and encode a display list borrowing multiple byte arenas
    (`cmds` is borrowed, as in `rasterize_spans`)."""
    w = _positive_int(w, "raster width")
    h = _positive_int(h, "raster height")
    buf = np.frombuffer(cmds, dtype=np.uint8)
    arenas, pointers, lengths = _byte_span_arrays(spans)
    raw_len = operator.mul(operator.mul(w, h), 4)
    capacity = raw_len + raw_len // 8 + 65_536
    out = np.empty(capacity, dtype=np.uint8)
    written = _lib.xyg_rasterize_png_spans(
        _ptr_u8(buf) if buf.size else None,
        buf.size,
        pointers if arenas else None,
        lengths if arenas else None,
        len(arenas),
        _ptr_u8(out),
        out.size,
        w,
        h,
    )
    if written == _USIZE_MAX or written > out.size:
        raise ValueError("native raster-to-PNG encoder rejected the command buffer or spans")
    return out[:written].tobytes()


def colormap_rgba(
    raw: npt.ArrayLike,
    w: int,
    h: int,
    stops: npt.ArrayLike,
    alpha: int,
) -> npt.NDArray[np.uint8]:
    """Map normalized scalars ``t ∈ [0, 1]`` to a vertically flipped ``(h, w, 4)`` RGBA image."""
    w = _positive_int(w, "colormap width")
    h = _positive_int(h, "colormap height")
    values = np.ascontiguousarray(raw, dtype=np.float64).reshape(-1)
    stop_array = np.ascontiguousarray(stops, dtype=np.uint8)
    if values.size != w * h:
        raise ValueError("colormap scalar count must match width * height")
    if stop_array.ndim != 2 or stop_array.shape[1] != 3 or stop_array.shape[0] < 1:
        raise ValueError("colormap stops must be a non-empty (n, 3) array")
    alpha = operator.index(alpha)
    if not 0 <= alpha <= 255:
        raise ValueError("colormap alpha must be in [0, 255]")
    out = np.empty((h, w, 4), dtype=np.uint8)
    ok = _lib.xyg_colormap_rgba(
        _ptr_f64(values),
        w,
        h,
        _ptr_u8(stop_array),
        stop_array.shape[0],
        alpha,
        _ptr_u8(out),
    )
    if not ok:
        raise ValueError("native colormap rejected the inputs")
    return out


def colormap_rgba_canonical(
    raw: npt.ArrayLike,
    w: int,
    h: int,
    domain: tuple[float, float],
    stops: npt.ArrayLike,
    alpha: int,
) -> npt.NDArray[np.uint8]:
    """Map canonical f64 scalars through domain normalization to RGBA8."""
    w = _positive_int(w, "colormap width")
    h = _positive_int(h, "colormap height")
    values = np.ascontiguousarray(raw, dtype=np.float64).reshape(-1)
    stop_array = np.ascontiguousarray(stops, dtype=np.uint8)
    if values.size != w * h:
        raise ValueError("colormap scalar count must match width * height")
    if stop_array.ndim != 2 or stop_array.shape[1] != 3 or stop_array.shape[0] < 1:
        raise ValueError("colormap stops must be a non-empty (n, 3) array")
    d0 = _finite_float(domain[0], "colormap domain lo")
    d1 = _finite_float(domain[1], "colormap domain hi")
    alpha = operator.index(alpha)
    if not 0 <= alpha <= 255:
        raise ValueError("colormap alpha must be in [0, 255]")
    out = np.empty((h, w, 4), dtype=np.uint8)
    ok = _lib.xyg_colormap_rgba_canonical(
        _ptr_f64(values),
        w,
        h,
        d0,
        d1,
        _ptr_u8(stop_array),
        stop_array.shape[0],
        alpha,
        _ptr_u8(out),
    )
    if not ok:
        raise ValueError("native canonical colormap rejected the inputs")
    return out


def colormap_stops(name: str) -> npt.NDArray[np.uint8]:
    """Resolve a named colormap to ``(n, 3)`` uint8 RGB stops (ABI 135)."""
    encoded = str(name).encode("utf-8")
    out = np.empty((256, 3), dtype=np.uint8)
    count = int(
        _lib.xyg_colormap_stops(
            encoded if encoded else 0,
            len(encoded),
            _ptr_u8(out),
            out.size,
        )
    )
    if count <= 0:
        raise ValueError("native colormap stops rejected the inputs")
    return out[:count].copy()


def heatmap_rgba(
    raw: npt.ArrayLike,
    w: int,
    h: int,
    stops: npt.ArrayLike,
    alpha: int,
) -> npt.NDArray[np.uint8]:
    """Map heatmap scalars to a vertically flipped ``(h, w, 4)`` RGBA image."""
    w = _positive_int(w, "heatmap width")
    h = _positive_int(h, "heatmap height")
    values = np.ascontiguousarray(raw, dtype=np.float64).reshape(-1)
    stop_array = np.ascontiguousarray(stops, dtype=np.uint8)
    if values.size != w * h:
        raise ValueError("heatmap scalar count must match width * height")
    if stop_array.ndim != 2 or stop_array.shape[1] != 3 or stop_array.shape[0] < 1:
        raise ValueError("heatmap stops must be a non-empty (n, 3) array")
    alpha = operator.index(alpha)
    if not 0 <= alpha <= 255:
        raise ValueError("heatmap alpha must be in [0, 255]")
    out = np.empty((h, w, 4), dtype=np.uint8)
    ok = _lib.xyg_heatmap_rgba(
        _ptr_f64(values),
        w,
        h,
        _ptr_u8(stop_array),
        stop_array.shape[0],
        alpha,
        _ptr_u8(out),
    )
    if not ok:
        raise ValueError("native heatmap colormap rejected the inputs")
    return out


def density_rgba(
    encoded: npt.ArrayLike,
    w: int,
    h: int,
    maximum: float,
    stops: npt.ArrayLike,
    opacity: float,
) -> npt.NDArray[np.uint8]:
    """Map a log-u8 density grid to a vertically flipped RGBA8 image."""
    w = _positive_int(w, "density width")
    h = _positive_int(h, "density height")
    values = np.ascontiguousarray(encoded, dtype=np.uint8).reshape(-1)
    stop_array = np.ascontiguousarray(stops, dtype=np.uint8)
    maximum = _finite_float(maximum, "density maximum")
    opacity = _finite_float(opacity, "density opacity")
    if maximum < 0.0:
        raise ValueError("density maximum must be >= 0")
    if not 0.0 <= opacity <= 1.0:
        raise ValueError("density opacity must be in [0, 1]")
    if values.size != w * h:
        raise ValueError("density scalar count must match width * height")
    if stop_array.ndim != 2 or stop_array.shape[1] != 3 or stop_array.shape[0] < 1:
        raise ValueError("density stops must be a non-empty (n, 3) array")
    out = np.empty((h, w, 4), dtype=np.uint8)
    ok = _lib.xyg_density_rgba(
        _ptr_u8(values),
        w,
        h,
        maximum,
        _ptr_u8(stop_array),
        stop_array.shape[0],
        opacity,
        _ptr_u8(out),
    )
    if not ok:
        raise ValueError("native density colormap rejected the inputs")
    return out


def colormap_lut(t: npt.ArrayLike, stops: npt.ArrayLike) -> npt.NDArray[np.uint8]:
    """Map normalized scalars ``t ∈ [0, 1]`` to packed ``(n, 3)`` RGB (ABI 206)."""
    values = np.ascontiguousarray(t, dtype=np.float64).reshape(-1)
    stop_array = np.ascontiguousarray(stops, dtype=np.uint8)
    if stop_array.ndim != 2 or stop_array.shape[1] != 3 or stop_array.shape[0] < 1:
        raise ValueError("colormap stops must be a non-empty (n, 3) array")
    n = int(values.size)
    out = np.empty((n, 3), dtype=np.uint8)
    ok = _lib.xyg_colormap_lut(
        _ptr_f64(values) if n else 0,
        n,
        _ptr_u8(stop_array),
        stop_array.shape[0],
        _ptr_u8(out) if n else 0,
    )
    if not ok:
        raise ValueError("native colormap lut rejected the inputs")
    return out


def density_rgba_linear(
    counts: npt.ArrayLike,
    w: int,
    h: int,
    maximum: float,
    stops: npt.ArrayLike,
    opacity: float,
) -> npt.NDArray[np.uint8]:
    """Map an f64 count grid to a vertically flipped RGBA8 image (ABI 206)."""
    w = _positive_int(w, "density width")
    h = _positive_int(h, "density height")
    values = np.ascontiguousarray(counts, dtype=np.float64).reshape(-1)
    stop_array = np.ascontiguousarray(stops, dtype=np.uint8)
    maximum = _finite_float(maximum, "density maximum")
    opacity = _finite_float(opacity, "density opacity")
    if maximum < 0.0:
        raise ValueError("density maximum must be >= 0")
    if not 0.0 <= opacity <= 1.0:
        raise ValueError("density opacity must be in [0, 1]")
    if values.size != w * h:
        raise ValueError("density scalar count must match width * height")
    if stop_array.ndim != 2 or stop_array.shape[1] != 3 or stop_array.shape[0] < 1:
        raise ValueError("density stops must be a non-empty (n, 3) array")
    out = np.empty((h, w, 4), dtype=np.uint8)
    ok = _lib.xyg_density_rgba_linear(
        _ptr_f64(values),
        w,
        h,
        maximum,
        _ptr_u8(stop_array),
        stop_array.shape[0],
        opacity,
        _ptr_u8(out),
    )
    if not ok:
        raise ValueError("native linear density colormap rejected the inputs")
    return out


def paint_effective_rgba(
    intrinsic: npt.ArrayLike,
    artist_alpha: npt.ArrayLike,
    opacity: npt.ArrayLike,
    component_opacity: float,
) -> npt.NDArray[np.float64]:
    """Artist-alpha replace then xy opacity multiply (ABI 206)."""
    rgba = np.ascontiguousarray(intrinsic, dtype=np.float64)
    if rgba.ndim != 2 or rgba.shape[1] != 4:
        raise ValueError(f"intrinsic paint must have shape (N, 4), got {rgba.shape}")
    n = int(rgba.shape[0])
    artist = np.ascontiguousarray(artist_alpha, dtype=np.float64).reshape(-1)
    opac = np.ascontiguousarray(opacity, dtype=np.float64).reshape(-1)
    if artist.size != n or opac.size != n:
        raise ValueError("artist_alpha and opacity must match intrinsic row count")
    component_opacity = _finite_float(component_opacity, "component_opacity")
    out = np.empty((n, 4), dtype=np.float64)
    ok = _lib.xyg_paint_effective_rgba(
        _ptr_f64(rgba) if n else 0,
        n,
        _ptr_f64(artist) if n else 0,
        _ptr_f64(opac) if n else 0,
        component_opacity,
        _ptr_f64(out) if n else 0,
    )
    if not ok:
        raise ValueError("native paint_effective_rgba rejected the inputs")
    return out


def density_log_u8(grid: npt.NDArray[np.float32]) -> tuple[npt.NDArray[np.uint8], float]:
    """Log-encode a density grid for the client's one-byte R8 texture."""
    values = np.ascontiguousarray(grid, dtype=np.float32)
    if values.ndim not in (1, 2):
        raise ValueError("density grid must be one- or two-dimensional")
    out = np.empty(values.shape, dtype=np.uint8)
    maximum = ctypes.c_double()
    ok = _lib.xyg_density_log_u8(
        values.ctypes.data if values.size else None,
        values.size,
        out.ctypes.data if out.size else None,
        ctypes.byref(maximum),
    )
    if ok != 1:
        raise RuntimeError("xyg native density_log_u8 failed")
    return out, float(maximum.value)


def drill_decision(visible: int, budget: float, in_drill: bool, exit_factor: float = 1.15) -> bool:
    """Native hysteresis-guarded LOD drill decision (§5)."""
    if isinstance(visible, (bool, np.bool_)) or not isinstance(visible, numbers.Integral):
        raise ValueError("visible must be an integer >= 0")
    visible_i = int(visible)
    if visible_i < 0:
        raise ValueError("visible must be an integer >= 0")
    budget_f = _finite_float(budget, "budget")
    exit_f = _finite_float(exit_factor, "exit_factor")
    if budget_f <= 0.0 or exit_f <= 0.0:
        raise ValueError("budget and exit_factor must be > 0")
    if not isinstance(in_drill, (bool, np.bool_)):
        raise ValueError("in_drill must be True or False")
    out = ctypes.c_int32()
    ok = _lib.xyg_drill_decision(
        visible_i, budget_f, int(bool(in_drill)), exit_f, ctypes.byref(out)
    )
    if ok != 1:
        raise ValueError("invalid drill_decision arguments")
    return bool(out.value)


def lod_grid_shape(
    width: int, height: int, visible: int, target_per_cell: float = 16.0
) -> tuple[int, int]:
    """Native screen-bounded aggregation grid shape."""
    if isinstance(width, (bool, np.bool_)) or isinstance(height, (bool, np.bool_)):
        raise ValueError("screen dimensions must be integers")
    if isinstance(visible, (bool, np.bool_)) or not isinstance(visible, numbers.Integral):
        raise ValueError("visible must be an integer >= 0")
    visible_i = int(visible)
    if visible_i < 0:
        raise ValueError("visible must be an integer >= 0")
    target = _finite_float(target_per_cell, "target_per_cell")
    if target <= 0.0:
        raise ValueError("target_per_cell must be > 0")
    out_w = ctypes.c_int32()
    out_h = ctypes.c_int32()
    ok = _lib.xyg_lod_grid_shape(
        int(width), int(height), visible_i, target, ctypes.byref(out_w), ctypes.byref(out_h)
    )
    if ok != 1:
        raise ValueError("invalid lod_grid_shape arguments")
    return int(out_w.value), int(out_h.value)


def lod_plan(
    visible: int,
    budget: float,
    in_drill: bool,
    *,
    exit_factor: float = 1.15,
    width: int,
    height: int,
    target_per_cell: float = 16.0,
) -> tuple[bool, int, int, int]:
    """Native numeric LOD plan: ``(exact, mode, grid_w, grid_h)``.

    ``mode`` is ``0`` (direct) or ``1`` (aggregate); hosts map to wire strings.
    """
    if isinstance(visible, (bool, np.bool_)) or not isinstance(visible, numbers.Integral):
        raise ValueError("visible must be an integer >= 0")
    visible_i = int(visible)
    if visible_i < 0:
        raise ValueError("visible must be an integer >= 0")
    budget_f = _finite_float(budget, "budget")
    exit_f = _finite_float(exit_factor, "exit_factor")
    target = _finite_float(target_per_cell, "target_per_cell")
    if budget_f <= 0.0 or exit_f <= 0.0 or target <= 0.0:
        raise ValueError("budget, exit_factor, and target_per_cell must be > 0")
    if not isinstance(in_drill, (bool, np.bool_)):
        raise ValueError("in_drill must be True or False")
    out_exact = ctypes.c_int32()
    out_mode = ctypes.c_uint32()
    out_gw = ctypes.c_int32()
    out_gh = ctypes.c_int32()
    ok = _lib.xyg_lod_plan(
        visible_i,
        budget_f,
        int(bool(in_drill)),
        exit_f,
        int(width),
        int(height),
        target,
        ctypes.byref(out_exact),
        ctypes.byref(out_mode),
        ctypes.byref(out_gw),
        ctypes.byref(out_gh),
    )
    if ok != 1:
        raise ValueError("invalid lod_plan arguments")
    return bool(out_exact.value), int(out_mode.value), int(out_gw.value), int(out_gh.value)


def payload_tier(
    kind: int,
    n_points: int,
    *,
    polar: bool = False,
    force_density: int = -1,
    force_direct: bool = False,
    per_item: bool = False,
) -> int:
    """Compile-time payload tier via ``xyg_payload_tier`` (ABI 122).

    ``kind`` is 0=line/area, 1=scatter. ``force_density`` is -1 auto, 0 false,
    1 true. Returns 0=direct, 1=decimated, 2=density.
    """
    if isinstance(n_points, (bool, np.bool_)) or not isinstance(n_points, numbers.Integral):
        raise ValueError("n_points must be an integer >= 0")
    n = int(n_points)
    if n < 0:
        raise ValueError("n_points must be an integer >= 0")
    code = int(
        _lib.xyg_payload_tier(
            int(kind),
            n,
            int(bool(polar)),
            int(force_density),
            int(bool(force_direct)),
            int(bool(per_item)),
        )
    )
    if code < 0:
        raise ValueError("invalid payload_tier arguments")
    return code


def payload_visible_needed(
    *,
    x_log: bool,
    y_log: bool,
    prefiltered: bool,
    x_has_nulls: bool,
    y_has_nulls: bool,
    has_base: bool = False,
    base_has_nulls: bool = False,
) -> bool:
    """Whether the payload visible-row mask can drop rows (ABI 122)."""
    code = int(
        _lib.xyg_payload_visible_needed(
            int(bool(x_log)),
            int(bool(y_log)),
            int(bool(prefiltered)),
            int(bool(x_has_nulls)),
            int(bool(y_has_nulls)),
            int(bool(has_base)),
            int(bool(base_has_nulls)),
        )
    )
    if code < 0:
        raise ValueError("invalid payload_visible_needed arguments")
    return bool(code)


def payload_visible_mask(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    *,
    x_log: bool = False,
    y_log: bool = False,
    base: npt.NDArray[np.float64] | None = None,
) -> npt.NDArray[np.bool_]:
    """Finite + log-positive keep mask via ``xyg_payload_visible_mask``."""
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("payload_visible_mask x and y must have equal length")
    n = len(x)
    out = np.empty(n, dtype=np.uint8)
    has_base = base is not None
    base_arr = _as_f64(base, "base") if has_base else None
    if has_base and base_arr is not None and len(base_arr) != n:
        raise ValueError("payload_visible_mask base must match x/y length")
    written = _lib.xyg_payload_visible_mask(
        _ptr_f64(x),
        _ptr_f64(y),
        n,
        int(bool(x_log)),
        int(bool(y_log)),
        _ptr_f64(base_arr) if has_base and base_arr is not None else 0,
        int(has_base),
        out.ctypes.data if n else 0,
        n,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid payload_visible_mask arguments")
    return out.astype(bool, copy=False)


def payload_m4_indices(
    n_points: int,
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    x0: float,
    x1: float,
    n_buckets: int,
    *,
    polar: bool = False,
    bin_x: npt.NDArray[np.float64] | None = None,
    bin_x0: float = 0.0,
    bin_x1: float = 0.0,
) -> tuple[int, npt.NDArray[np.uint32]]:
    """Line M4 indices via ``xyg_payload_m4_indices`` (ABI 204).

    Returns ``(tier, indices)``. ``tier`` is 0=direct (empty indices) or
    1=decimated. Rust owns the threshold, polar skip, and closed-window ulp.
    """
    if isinstance(n_points, (bool, np.bool_)) or not isinstance(n_points, numbers.Integral):
        raise ValueError("n_points must be an integer >= 0")
    n_pts = int(n_points)
    if n_pts < 0:
        raise ValueError("n_points must be an integer >= 0")
    if isinstance(n_buckets, (bool, np.bool_)) or not isinstance(n_buckets, numbers.Integral):
        raise ValueError("n_buckets must be an integer >= 0")
    n_buckets_i = int(n_buckets)
    if n_buckets_i < 0:
        raise ValueError("n_buckets must be an integer >= 0")
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("payload_m4_indices x and y must have equal length")
    n = len(x)
    bin_arr = _as_f64(bin_x, "bin_x") if bin_x is not None else None
    if bin_arr is not None and len(bin_arr) != n:
        raise ValueError("payload_m4_indices bin_x must match x/y length")
    out_tier = ctypes.c_int32(-1)
    cap = n_buckets_i * 4 if n_buckets_i else 0
    out = np.empty(cap, dtype=np.uint32) if cap else np.empty(0, dtype=np.uint32)
    written = _lib.xyg_payload_m4_indices(
        n_pts,
        int(bool(polar)),
        _ptr_f64(x) if n else 0,
        _ptr_f64(y) if n else 0,
        n,
        float(x0),
        float(x1),
        n_buckets_i,
        _ptr_f64(bin_arr) if bin_arr is not None and n else 0,
        float(bin_x0),
        float(bin_x1),
        ctypes.byref(out_tier),
        out.ctypes.data if cap else 0,
        cap,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid payload_m4_indices arguments")
    return int(out_tier.value), out[:written].copy()


def payload_visible_indices(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    *,
    x_log: bool = False,
    y_log: bool = False,
    base: npt.NDArray[np.float64] | None = None,
    prefiltered: bool = False,
    x_has_nulls: bool = False,
    y_has_nulls: bool = False,
    has_base: bool = False,
    base_has_nulls: bool = False,
) -> tuple[bool, npt.NDArray[np.uint32]]:
    """Fused keep-all vs keep-indices via ``xyg_payload_visible_indices`` (ABI 205).

    Returns ``(keep_all, indices)``. ``keep_all`` means ship every row without
    an N-index allocation. Indices are positions in the passed ``x``/``y``.
    """
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("payload_visible_indices x and y must have equal length")
    n = len(x)
    has_base_flag = bool(has_base) or base is not None
    base_arr = _as_f64(base, "base") if base is not None else None
    if has_base_flag and base_arr is None:
        raise ValueError("payload_visible_indices base is required when has_base is set")
    if base_arr is not None and len(base_arr) != n:
        raise ValueError("payload_visible_indices base must match x/y length")
    if not payload_visible_needed(
        x_log=x_log,
        y_log=y_log,
        prefiltered=prefiltered,
        x_has_nulls=x_has_nulls,
        y_has_nulls=y_has_nulls,
        has_base=has_base_flag,
        base_has_nulls=base_has_nulls,
    ):
        return True, np.empty(0, dtype=np.uint32)
    out = np.empty(n, dtype=np.uint32) if n else np.empty(0, dtype=np.uint32)
    keep_all = ctypes.c_int32(-1)
    written = _lib.xyg_payload_visible_indices(
        _ptr_f64(x) if n else 0,
        _ptr_f64(y) if n else 0,
        n,
        int(bool(x_log)),
        int(bool(y_log)),
        _ptr_f64(base_arr) if base_arr is not None and n else 0,
        int(has_base_flag),
        int(bool(prefiltered)),
        int(bool(x_has_nulls)),
        int(bool(y_has_nulls)),
        int(bool(base_has_nulls)),
        ctypes.byref(keep_all),
        out.ctypes.data if n else 0,
        n,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid payload_visible_indices arguments")
    if int(keep_all.value) == 1:
        return True, np.empty(0, dtype=np.uint32)
    if written > n:
        out = np.empty(written, dtype=np.uint32)
        keep_all = ctypes.c_int32(-1)
        repeated = _lib.xyg_payload_visible_indices(
            _ptr_f64(x) if n else 0,
            _ptr_f64(y) if n else 0,
            n,
            int(bool(x_log)),
            int(bool(y_log)),
            _ptr_f64(base_arr) if base_arr is not None and n else 0,
            int(has_base_flag),
            int(bool(prefiltered)),
            int(bool(x_has_nulls)),
            int(bool(y_has_nulls)),
            int(bool(base_has_nulls)),
            ctypes.byref(keep_all),
            out.ctypes.data,
            written,
        )
        if repeated != written or int(keep_all.value) == 1:
            raise RuntimeError("native payload_visible_indices returned an inconsistent count")
    return False, out[:written].copy()


def payload_even_indices(n: int, count: int) -> tuple[bool, npt.NDArray[np.uint32]]:
    """Even keep indices via ``xyg_payload_even_indices`` (ABI 205).

    Matches NumPy ``linspace(0, n-1, count, dtype=np.int64)``. Returns
    ``(keep_all, indices)``; ``keep_all`` when ``n <= count``.
    """
    n_i = _bounded_nonnegative_int(n, "n", max_value=np.iinfo(np.uint32).max)
    count_i = _bounded_nonnegative_int(count, "count", max_value=np.iinfo(np.uint32).max)
    if count_i == 0:
        raise ValueError("count must be a positive integer")
    keep_all = ctypes.c_int32(-1)
    out = np.empty(count_i, dtype=np.uint32)
    written = _lib.xyg_payload_even_indices(
        n_i,
        count_i,
        ctypes.byref(keep_all),
        out.ctypes.data,
        count_i,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid payload_even_indices arguments")
    if int(keep_all.value) == 1:
        return True, np.empty(0, dtype=np.uint32)
    if written > count_i:
        raise RuntimeError("native payload_even_indices returned an inconsistent count")
    return False, out[:written].copy()


def payload_segment_budget(px_width: float) -> int:
    """Stem/errorbar emit count budget via ``xyg_payload_segment_budget`` (ABI 214).

    ``max(1024, floor(px_width) * 4)``.
    """
    if isinstance(px_width, (bool, np.bool_)) or not isinstance(
        px_width, (int, float, np.integer, np.floating, numbers.Real)
    ):
        raise ValueError("px_width must be a finite number")
    written = int(_lib.xyg_payload_segment_budget(float(px_width)))
    if written == _USIZE_MAX:
        raise ValueError("invalid payload_segment_budget arguments")
    return written


def payload_errorbar_indices(
    n_segments: int, n_points: int, budget: int
) -> tuple[bool, npt.NDArray[np.uint32]]:
    """Errorbar role-block keep indices via ``xyg_payload_errorbar_indices`` (ABI 215).

    Even-samples ``n_points`` at ``budget`` then expands
    ``chosen[i] + k * n_points`` across concatenated role groups. Returns
    ``(keep_all, indices)``; ``keep_all`` when every segment ships.
    """
    n_seg = _bounded_nonnegative_int(n_segments, "n_segments", max_value=np.iinfo(np.uint32).max)
    n_pts = _bounded_nonnegative_int(n_points, "n_points", max_value=np.iinfo(np.uint32).max)
    budget_i = _bounded_nonnegative_int(budget, "budget", max_value=np.iinfo(np.uint32).max)
    if n_pts == 0 or budget_i == 0:
        raise ValueError("n_points and budget must be positive integers")
    keep_all = ctypes.c_int32(-1)
    out = np.empty(n_seg, dtype=np.uint32)
    written = _lib.xyg_payload_errorbar_indices(
        n_seg,
        n_pts,
        budget_i,
        ctypes.byref(keep_all),
        out.ctypes.data if n_seg else 0,
        n_seg,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid payload_errorbar_indices arguments")
    if int(keep_all.value) == 1:
        return True, np.empty(0, dtype=np.uint32)
    if written > n_seg:
        raise RuntimeError("native payload_errorbar_indices returned an inconsistent count")
    return False, out[:written].copy()


def payload_sample_target_indices(
    n: int,
    target: int,
    seed: int = 0,
    level: int = 0,
    growth: float = 2.0,
) -> tuple[bool, npt.NDArray[np.uint32]]:
    """Density-overlay sample of implicit ids via ``xyg_payload_sample_target_indices``.

    Owns ``min(1, target/n)``, level/growth fraction, threshold, and range
    sampling (ABI 205). Returns ``(keep_all, indices)``.
    """
    n_i = _bounded_nonnegative_int(n, "n", max_value=np.iinfo(np.uint32).max)
    target_i = _bounded_nonnegative_int(target, "target", max_value=np.iinfo(np.uint32).max)
    if target_i == 0:
        raise ValueError("target must be a positive integer")
    level_i = _bounded_nonnegative_int(level, "level", max_value=np.iinfo(np.uint32).max)
    seed_i = _bounded_nonnegative_int(seed, "seed", max_value=np.iinfo(np.uint64).max)
    growth_f = _finite_float(growth, "growth")
    if growth_f < 1.0:
        raise ValueError("growth must be >= 1")
    keep_all = ctypes.c_int32(-1)
    cap = min(n_i, max(64, target_i * 2)) if n_i else 0
    out = np.empty(cap, dtype=np.uint32) if cap else np.empty(0, dtype=np.uint32)
    written = _lib.xyg_payload_sample_target_indices(
        n_i,
        target_i,
        ctypes.c_uint64(seed_i),
        ctypes.c_uint32(level_i),
        growth_f,
        ctypes.byref(keep_all),
        out.ctypes.data if cap else 0,
        cap,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid payload_sample_target_indices arguments")
    if int(keep_all.value) == 1:
        return True, np.empty(0, dtype=np.uint32)
    if written > cap:
        out = np.empty(written, dtype=np.uint32)
        keep_all = ctypes.c_int32(-1)
        repeated = _lib.xyg_payload_sample_target_indices(
            n_i,
            target_i,
            ctypes.c_uint64(seed_i),
            ctypes.c_uint32(level_i),
            growth_f,
            ctypes.byref(keep_all),
            out.ctypes.data,
            written,
        )
        if repeated != written or int(keep_all.value) == 1:
            raise RuntimeError(
                "native payload_sample_target_indices returned an inconsistent count"
            )
        cap = written
    return False, out[:written].copy()


DENSITY_GRID_PATH_OVERSIZED_BIN2D = 0
DENSITY_GRID_PATH_IDENTITY_GRID_ONLY = 1
DENSITY_GRID_PATH_IDENTITY_STRATIFIED_FUSED = 2
DENSITY_GRID_PATH_IDENTITY_STRATIFIED_SPLIT = 3
DENSITY_GRID_PATH_IDENTITY_SAMPLE_FUSED = 4
DENSITY_GRID_PATH_RANGE_INDICES = 5

DENSITY_COLOR_MODE_NONE = 0
DENSITY_COLOR_MODE_CONSTANT = 1
DENSITY_COLOR_MODE_OTHER = 2

DENSITY_OVERLAY_NONE = 0
DENSITY_OVERLAY_ROWS_EXCEED_U32 = 1
DENSITY_OVERLAY_STATIC_RASTER = 2


def density_bin_window(
    *,
    x_linear: bool,
    y_linear: bool,
    xr0: float,
    xr1: float,
    yr0: float,
    yr1: float,
    x_c0: float,
    x_c1: float,
    y_c0: float,
    y_c1: float,
) -> tuple[float, float, float, float]:
    """Bin window via ``xyg_density_bin_window`` (ABI 132)."""
    out = (ctypes.c_double * 4)()
    written = _lib.xyg_density_bin_window(
        int(bool(x_linear)),
        int(bool(y_linear)),
        float(xr0),
        float(xr1),
        float(yr0),
        float(yr1),
        float(x_c0),
        float(x_c1),
        float(y_c0),
        float(y_c1),
        out,
    )
    if written != 4:
        raise ValueError("invalid density_bin_window arguments")
    return float(out[0]), float(out[1]), float(out[2]), float(out[3])


def density_full_identity(
    *,
    categorical: bool,
    compact_categorical: bool,
    x_has_nulls: bool,
    y_has_nulls: bool,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    xr0: float,
    xr1: float,
    yr0: float,
    yr1: float,
) -> bool:
    """Identity visible-row predicate via ``xyg_density_full_identity`` (ABI 132)."""
    code = int(
        _lib.xyg_density_full_identity(
            int(bool(categorical)),
            int(bool(compact_categorical)),
            int(bool(x_has_nulls)),
            int(bool(y_has_nulls)),
            float(x_min),
            float(x_max),
            float(y_min),
            float(y_max),
            float(xr0),
            float(xr1),
            float(yr0),
            float(yr1),
        )
    )
    if code < 0:
        raise ValueError("invalid density_full_identity arguments")
    return bool(code)


def density_pyramid_preflight(
    *,
    x_linear: bool,
    y_linear: bool,
    n_points: int,
    has_pyramid_resource: bool,
    x_memmapped: bool,
    y_memmapped: bool,
    force_pyramid: bool = False,
    force_bin2d: bool = False,
) -> dict[str, int | bool]:
    """Pyramid preflight via ``xyg_density_pyramid_preflight`` (ABI 132)."""
    if isinstance(n_points, (bool, np.bool_)) or not isinstance(n_points, numbers.Integral):
        raise ValueError("n_points must be an integer >= 0")
    n = int(n_points)
    if n < 0:
        raise ValueError("n_points must be an integer >= 0")
    out = (ctypes.c_uint32 * 6)()
    written = _lib.xyg_density_pyramid_preflight(
        int(bool(x_linear)),
        int(bool(y_linear)),
        n,
        int(bool(has_pyramid_resource)),
        int(bool(x_memmapped)),
        int(bool(y_memmapped)),
        int(bool(force_pyramid)),
        int(bool(force_bin2d)),
        out,
    )
    if written != 6:
        raise ValueError("invalid density_pyramid_preflight arguments")
    return {
        "eligible": bool(out[0]),
        "attempt": bool(out[1]),
        "no_rescan": bool(out[2]),
        "max_upsample": int(out[3]),
        "tile_upsample": int(out[4]),
    }


def density_grid_path(
    *,
    oversized: bool,
    full_identity: bool,
    point_overlay: bool,
    compact_categorical: bool,
    stratified_counts: bool,
) -> int:
    """Exact grid-kernel path via ``xyg_density_grid_path`` (ABI 132)."""
    code = int(
        _lib.xyg_density_grid_path(
            int(bool(oversized)),
            int(bool(full_identity)),
            int(bool(point_overlay)),
            int(bool(compact_categorical)),
            int(bool(stratified_counts)),
        )
    )
    if code < 0:
        raise ValueError("invalid density_grid_path arguments")
    return code


def density_format_binning(
    *,
    exact: bool,
    level: int = 0,
    tiles: bool = False,
    upsampled: bool = False,
) -> str:
    """Format §28 density ``binning`` via ``xyg_density_format_binning`` (ABI 132)."""
    buf = np.empty(64, dtype=np.uint8)
    written = _lib.xyg_density_format_binning(
        int(bool(exact)),
        int(level),
        int(bool(tiles)),
        int(bool(upsampled)),
        buf.ctypes.data,
        len(buf),
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid density_format_binning arguments")
    return bytes(buf[:written]).decode("ascii")


def density_wasm_eligible(
    *,
    cartesian: bool,
    x_linear: bool,
    y_linear: bool,
    color_mode: int,
    x_has_nulls: bool,
    y_has_nulls: bool,
    n_points: int,
) -> bool:
    """WASM aggregate replay eligibility via ``xyg_density_wasm_eligible`` (ABI 132)."""
    if isinstance(n_points, (bool, np.bool_)) or not isinstance(n_points, numbers.Integral):
        raise ValueError("n_points must be an integer >= 0")
    n = int(n_points)
    if n < 0:
        raise ValueError("n_points must be an integer >= 0")
    code = int(
        _lib.xyg_density_wasm_eligible(
            int(bool(cartesian)),
            int(bool(x_linear)),
            int(bool(y_linear)),
            int(color_mode),
            int(bool(x_has_nulls)),
            int(bool(y_has_nulls)),
            n,
        )
    )
    if code < 0:
        raise ValueError("invalid density_wasm_eligible arguments")
    return bool(code)


def density_emit_plan(
    *,
    cartesian: bool,
    x_linear: bool,
    y_linear: bool,
    categorical: bool,
    compact_categorical: bool,
    stratified_counts: bool,
    x_has_nulls: bool,
    y_has_nulls: bool,
    point_overlay: bool,
    grid_from_pyramid: bool,
    x_memmapped: bool,
    y_memmapped: bool,
    has_pyramid_resource: bool,
    force_bin2d: bool = False,
    force_pyramid: bool = False,
    color_mode: int,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    xr0: float,
    xr1: float,
    yr0: float,
    yr1: float,
    x_c0: float,
    x_c1: float,
    y_c0: float,
    y_c1: float,
    n_points: int,
) -> dict[str, int | bool | float]:
    """First-paint density emit plan via ``xyg_density_emit_meta`` (ABI 132)."""
    if isinstance(n_points, (bool, np.bool_)) or not isinstance(n_points, numbers.Integral):
        raise ValueError("n_points must be an integer >= 0")
    n = int(n_points)
    if n < 0:
        raise ValueError("n_points must be an integer >= 0")
    out = _DensityEmitMeta()
    code = int(
        _lib.xyg_density_emit_meta(
            int(bool(cartesian)),
            int(bool(x_linear)),
            int(bool(y_linear)),
            int(bool(categorical)),
            int(bool(compact_categorical)),
            int(bool(stratified_counts)),
            int(bool(x_has_nulls)),
            int(bool(y_has_nulls)),
            int(bool(point_overlay)),
            int(bool(grid_from_pyramid)),
            int(bool(x_memmapped)),
            int(bool(y_memmapped)),
            int(bool(has_pyramid_resource)),
            int(bool(force_bin2d)),
            int(bool(force_pyramid)),
            int(color_mode),
            float(x_min),
            float(x_max),
            float(y_min),
            float(y_max),
            float(xr0),
            float(xr1),
            float(yr0),
            float(yr1),
            float(x_c0),
            float(x_c1),
            float(y_c0),
            float(y_c1),
            n,
            ctypes.byref(out),
        )
    )
    if code != 0:
        raise ValueError("invalid density_emit_plan arguments")
    return {
        "grid_path": int(out.grid_path),
        "bin_window_x0": float(out.bin_window_x0),
        "bin_window_x1": float(out.bin_window_x1),
        "bin_window_y0": float(out.bin_window_y0),
        "bin_window_y1": float(out.bin_window_y1),
        "full_identity": bool(out.full_identity),
        "oversized": bool(out.oversized),
        "pyramid_eligible": bool(out.pyramid_eligible),
        "pyramid_attempt": bool(out.pyramid_attempt),
        "pyramid_no_rescan": bool(out.pyramid_no_rescan),
        "pyramid_max_upsample": int(out.pyramid_max_upsample),
        "pyramid_tile_upsample": int(out.pyramid_tile_upsample),
        "wasm_eligible": bool(out.wasm_eligible),
        "needs_pyramid_sample": bool(out.needs_pyramid_sample),
        "overlay_omitted": int(out.overlay_omitted),
        "visible_is_n_points": bool(out.visible_is_n_points),
        "use_raw_range_bin2d": bool(out.use_raw_range_bin2d),
    }


def quantiles(
    data: npt.NDArray[np.float64], probs: npt.NDArray[np.float64] | list[float]
) -> npt.NDArray[np.float64]:
    """Linear (NumPy-default) quantiles via the native core."""
    data = _as_f64(data, "data")
    probs_arr = np.ascontiguousarray(probs, dtype=np.float64)
    if probs_arr.ndim != 1 or len(probs_arr) == 0:
        raise ValueError("probs must be a non-empty 1-D array")
    out = np.empty(len(probs_arr), dtype=np.float64)
    written = _lib.xyg_quantiles(
        _ptr_f64(data),
        len(data),
        _ptr_f64(probs_arr),
        len(probs_arr),
        _ptr_f64(out),
    )
    if written == _USIZE_MAX:
        raise ValueError("quantiles require finite probabilities in [0, 1]")
    return out


def box_stats(
    data: npt.NDArray[np.float64],
) -> tuple[float, float, float, float, float, npt.NDArray[np.float64]]:
    """Tukey box-plot stats: q1, median, q3, whisker low/high, outliers."""
    data = _as_f64(data, "data")
    stats = np.empty(5, dtype=np.float64)
    outliers = np.empty(len(data), dtype=np.float64)
    n_out = ctypes.c_size_t()
    ok = _lib.xyg_box_stats(
        _ptr_f64(data),
        len(data),
        _ptr_f64(stats),
        _ptr_f64(outliers) if len(data) else 0,
        len(data),
        ctypes.byref(n_out),
    )
    if ok != 1:
        raise RuntimeError("xyg native box_stats failed (output undefined)")
    return (
        float(stats[0]),
        float(stats[1]),
        float(stats[2]),
        float(stats[3]),
        float(stats[4]),
        outliers[: int(n_out.value)].copy(),
    )


def box_geometry(
    values: npt.NDArray[np.float64],
    offsets: npt.NDArray[np.uintp],
    centers: npt.NDArray[np.float64],
    width: float,
    orientation: str,
    show_outliers: bool,
) -> dict[str, Any]:
    """Grouped Tukey statistics and canonical box-part geometry from Rust."""
    values = _as_f64(values, "values")
    centers = _as_f64(centers, "centers")
    offsets = np.ascontiguousarray(offsets, dtype=np.uintp)
    code = {"vertical": 0, "horizontal": 1}.get(orientation, -1)
    n_outliers = ctypes.c_size_t()

    def call(outputs: list[npt.NDArray[Any] | None], group_cap: int, outlier_cap: int) -> int:
        pointers = [0 if value is None else value.ctypes.data for value in outputs]
        return int(
            _lib.xyg_box_geometry(
                _ptr_f64(values),
                len(values),
                offsets.ctypes.data,
                len(offsets),
                _ptr_f64(centers),
                len(centers),
                float(width),
                code,
                int(show_outliers),
                ctypes.byref(n_outliers),
                *pointers,
                group_cap,
                outlier_cap,
            )
        )

    required = call([None] * 4, 0, 0)
    if required == _USIZE_MAX or required <= 0 or required > 2_000:
        raise ValueError("invalid bounded box geometry")
    outliers = int(n_outliers.value)
    if outliers < 0 or required * 5 + outliers > 10_000:
        raise ValueError("invalid bounded box geometry")
    active = np.empty(required, dtype=np.uint32)
    records = np.empty((required, 25))
    outlier_offsets = np.empty(required + 1, dtype=np.uintp)
    outlier_records = np.empty((outliers, 3))
    if call([active, records, outlier_offsets, outlier_records], required, outliers) != required:
        raise ValueError("invalid bounded box geometry")
    body = tuple(records[:, index].copy() for index in range(5, 9))
    whiskers = tuple(
        records[:, [9 + segment * 4 + coordinate for segment in range(3)]].reshape(-1)
        for coordinate in range(4)
    )
    medians = tuple(records[:, index].copy() for index in range(21, 25))
    group_stats = []
    for index in range(required):
        start, end = int(outlier_offsets[index]), int(outlier_offsets[index + 1])
        group_stats.append((*map(float, records[index, :5]), outlier_records[start:end, 0].copy()))
    return {
        "active_groups": active,
        "group_stats": group_stats,
        "body": body,
        "whiskers": whiskers,
        "medians": medians,
        "outlier_x": outlier_records[:, 1].copy() if show_outliers else np.empty(0),
        "outlier_y": outlier_records[:, 2].copy() if show_outliers else np.empty(0),
    }


HEX_REDUCE_COUNT = 0
HEX_REDUCE_MEAN = 1
HEX_REDUCE_SUM = 2


def _hexbin_grid_and_range(
    gridsize: int | tuple[int, int],
    range: tuple[tuple[float, float], tuple[float, float]] | None,
) -> tuple[int, int, float, float, float, float, int]:
    if isinstance(gridsize, (int, np.integer)) and not isinstance(gridsize, (bool, np.bool_)):
        w, h = int(gridsize), 0
    elif isinstance(gridsize, (tuple, list)) and len(gridsize) == 2:
        w, h = int(gridsize[0]), int(gridsize[1])
    else:
        raise ValueError("hexbin gridsize must be a positive integer or (width, height)")
    if w < 2 or w > 2048:
        raise ValueError("hexbin gridsize dimensions must be in 2..=2048")
    if h != 0 and (h < 2 or h > 2048):
        raise ValueError("hexbin gridsize dimensions must be in 2..=2048")
    if range is None:
        return w, h, 0.0, 0.0, 0.0, 0.0, 0
    try:
        (raw_x0, raw_x1), (raw_y0, raw_y1) = range
    except (TypeError, ValueError) as exc:
        raise ValueError("hexbin range must be ((x0, x1), (y0, y1))") from exc
    x0, x1 = _finite_increasing(raw_x0, raw_x1, "hexbin x range")
    y0, y1 = _finite_increasing(raw_y0, raw_y1, "hexbin y range")
    return w, h, x0, x1, y0, y1, 1


def hexbin_ring(
    hex_dx: float, hex_dy: float
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Pointy-top hexagon vertex offsets scaled by cell pitch (ABI 210)."""
    probed = _lib.xyg_hexbin_ring(float(hex_dx), float(hex_dy), 0, 0, 0)
    if probed == _USIZE_MAX:
        raise ValueError("invalid hexbin-ring request")
    n = int(probed)
    out_x = np.empty(n, dtype=np.float64)
    out_y = np.empty(n, dtype=np.float64)
    written = _lib.xyg_hexbin_ring(
        float(hex_dx),
        float(hex_dy),
        _ptr_f64(out_x),
        _ptr_f64(out_y),
        n,
    )
    if written == _USIZE_MAX or written != n:
        raise ValueError("invalid hexbin-ring request")
    return out_x, out_y


def hexbin_ingress(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    *,
    gridsize: int | tuple[int, int],
    range: tuple[tuple[float, float], tuple[float, float]] | None = None,
    C: npt.NDArray[np.float64] | None = None,
) -> tuple[tuple[float, float], tuple[float, float], int, int]:
    """Rust-owned hexbin finite-pair domain and default grid aspect."""
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("hexbin x and y must have equal length")
    w, h, x0, x1, y0, y1, use_range = _hexbin_grid_and_range(gridsize, range)
    c_arr = None if C is None else _as_f64(C, "C")
    if c_arr is not None and len(c_arr) != len(x):
        raise ValueError("hexbin C must have the same length as x and y")
    out_x0 = ctypes.c_double()
    out_x1 = ctypes.c_double()
    out_y0 = ctypes.c_double()
    out_y1 = ctypes.c_double()
    out_w = ctypes.c_size_t()
    out_h = ctypes.c_size_t()
    ok = _lib.xyg_hexbin_ingress(
        _ptr_f64(x),
        _ptr_f64(y),
        0 if c_arr is None else _ptr_f64(c_arr),
        len(x),
        w,
        h,
        x0,
        x1,
        y0,
        y1,
        use_range,
        ctypes.byref(out_x0),
        ctypes.byref(out_x1),
        ctypes.byref(out_y0),
        ctypes.byref(out_y1),
        ctypes.byref(out_w),
        ctypes.byref(out_h),
    )
    if not ok:
        raise ValueError("hexbin x and y must contain at least one finite pair")
    return (
        (float(out_x0.value), float(out_x1.value)),
        (float(out_y0.value), float(out_y1.value)),
        int(out_w.value),
        int(out_h.value),
    )


def hexbin(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    *,
    gridsize: int | tuple[int, int],
    range: tuple[tuple[float, float], tuple[float, float]] | None = None,
    mincnt: int = 0,
    C: npt.NDArray[np.float64] | None = None,
    reduce: str = "count",
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    float,
    float,
]:
    """Hexagonal binning via ``xyg_hexbin`` (count / mean / sum).

    Rust owns finite-pair filtering, automatic domain, and default grid
    aspect. Returns ``(centers_x, centers_y, metrics, counts, dx, dy)``.
    """
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("hexbin x and y must have equal length")
    w, h, x0, x1, y0, y1, use_range = _hexbin_grid_and_range(gridsize, range)
    if mincnt < 0:
        raise ValueError("hexbin mincnt must be nonnegative")
    reduce_key = str(reduce).strip().lower()
    reduce_map = {
        "count": HEX_REDUCE_COUNT,
        "mean": HEX_REDUCE_MEAN,
        "sum": HEX_REDUCE_SUM,
    }
    if reduce_key not in reduce_map:
        raise ValueError("hexbin reduce must be 'count', 'mean', or 'sum'")
    reduce_code = reduce_map[reduce_key]
    c_arr = None if C is None else _as_f64(C, "C")
    if c_arr is not None and len(c_arr) != len(x):
        raise ValueError("hexbin C must have the same length as x and y")
    if reduce_code != HEX_REDUCE_COUNT and c_arr is None:
        raise ValueError("hexbin mean/sum reduce requires C")
    # Auto height is at most ``w``; allocate the conservative square lattice.
    h_cap = w if h == 0 else h
    capacity = (w + 1) * (h_cap + 1) + w * h_cap
    out_cx = np.empty(capacity, dtype=np.float64)
    out_cy = np.empty(capacity, dtype=np.float64)
    out_metric = np.empty(capacity, dtype=np.float64)
    out_counts = np.empty(capacity, dtype=np.float64)
    dx = ctypes.c_double()
    dy = ctypes.c_double()
    written = _lib.xyg_hexbin(
        _ptr_f64(x),
        _ptr_f64(y),
        0 if c_arr is None else _ptr_f64(c_arr),
        len(x),
        w,
        h,
        x0,
        x1,
        y0,
        y1,
        use_range,
        int(mincnt),
        reduce_code,
        _ptr_f64(out_cx),
        _ptr_f64(out_cy),
        _ptr_f64(out_metric),
        _ptr_f64(out_counts),
        capacity,
        ctypes.byref(dx),
        ctypes.byref(dy),
    )
    if written == _USIZE_MAX:
        raise ValueError("hexbin x and y must contain at least one finite pair")
    n = int(written)
    return (
        out_cx[:n].copy(),
        out_cy[:n].copy(),
        out_metric[:n].copy(),
        out_counts[:n].copy(),
        float(dx.value),
        float(dy.value),
    )


def hexbin_groups(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    *,
    gridsize: int | tuple[int, int],
    range: tuple[tuple[float, float], tuple[float, float]] | None = None,
    mincnt: int = 0,
    C: npt.NDArray[np.float64] | None = None,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.uint32],
    npt.NDArray[np.uint32],
    npt.NDArray[np.uint32],
    float,
    float,
]:
    """Occupied hex-cell memberships via ``xyg_hexbin_groups``.

    Returns ``(centers_x, centers_y, counts, starts, lengths, indices, dx, dy)``.
    ``indices[starts[i]:starts[i]+lengths[i]]`` are original-row ids for cell
    ``i``. Hosts apply a custom reducer to ``C[indices[...]]``.
    """
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("hexbin x and y must have equal length")
    w, h, x0, x1, y0, y1, use_range = _hexbin_grid_and_range(gridsize, range)
    if mincnt < 0:
        raise ValueError("hexbin mincnt must be nonnegative")
    c_arr = None if C is None else _as_f64(C, "C")
    if c_arr is not None and len(c_arr) != len(x):
        raise ValueError("hexbin C must have the same length as x and y")
    h_cap = w if h == 0 else h
    cell_capacity = (w + 1) * (h_cap + 1) + w * h_cap
    out_cx = np.empty(cell_capacity, dtype=np.float64)
    out_cy = np.empty(cell_capacity, dtype=np.float64)
    out_counts = np.empty(cell_capacity, dtype=np.float64)
    out_starts = np.empty(cell_capacity, dtype=np.uint32)
    out_lens = np.empty(cell_capacity, dtype=np.uint32)
    out_indices = np.empty(len(x), dtype=np.uint32)
    n_indices = ctypes.c_size_t()
    dx = ctypes.c_double()
    dy = ctypes.c_double()
    written = _lib.xyg_hexbin_groups(
        _ptr_f64(x),
        _ptr_f64(y),
        0 if c_arr is None else _ptr_f64(c_arr),
        len(x),
        w,
        h,
        x0,
        x1,
        y0,
        y1,
        use_range,
        int(mincnt),
        _ptr_f64(out_cx),
        _ptr_f64(out_cy),
        _ptr_f64(out_counts),
        out_starts.ctypes.data,
        out_lens.ctypes.data,
        cell_capacity,
        out_indices.ctypes.data,
        len(out_indices),
        ctypes.byref(n_indices),
        ctypes.byref(dx),
        ctypes.byref(dy),
    )
    if written == _USIZE_MAX:
        raise ValueError("hexbin x and y must contain at least one finite pair")
    n = int(written)
    n_idx = int(n_indices.value)
    return (
        out_cx[:n].copy(),
        out_cy[:n].copy(),
        out_counts[:n].copy(),
        out_starts[:n].copy(),
        out_lens[:n].copy(),
        out_indices[:n_idx].copy(),
        float(dx.value),
        float(dy.value),
    )


def legend_normalize(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    x_domain: tuple[float, float],
    y_domain: tuple[float, float],
    *,
    x_reverse: bool = False,
    y_reverse: bool = False,
    x_scale: int = 0,
    y_scale: int = 0,
    x_constant: float = 1.0,
    y_constant: float = 1.0,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]] | None:
    """Display-space occupancy sample via ``xyg_legend_normalize`` (ABI 120).

    Returns ``None`` when the series has no finite visible pair. Scale codes
    are 0=linear, 1=log, 2=symlog.
    """
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("legend_normalize x and y must have equal length")
    n = len(x)
    capacity = min(n, 512) if n else 0
    out_x = np.empty(capacity, dtype=np.float64)
    out_y = np.empty(capacity, dtype=np.float64)
    written = _lib.xyg_legend_normalize(
        _ptr_f64(x),
        _ptr_f64(y),
        n,
        float(x_domain[0]),
        float(x_domain[1]),
        float(y_domain[0]),
        float(y_domain[1]),
        int(bool(x_reverse)),
        int(bool(y_reverse)),
        int(x_scale),
        int(y_scale),
        float(x_constant),
        float(y_constant),
        _ptr_f64(out_x) if capacity else 0,
        _ptr_f64(out_y) if capacity else 0,
        capacity,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid legend_normalize arguments")
    if written == 0:
        return None
    return out_x[: int(written)].copy(), out_y[: int(written)].copy()


def legend_best_loc(
    xs: npt.NDArray[np.float64],
    ys: npt.NDArray[np.float64],
    starts: npt.NDArray[np.uintp],
    label_lens: npt.NDArray[np.uint32],
) -> int:
    """Matplotlib ``loc="best"`` candidate index via ``xyg_legend_best_loc``."""
    xs = _as_f64(xs, "xs")
    ys = _as_f64(ys, "ys")
    if len(xs) != len(ys):
        raise ValueError("legend_best_loc xs and ys must have equal length")
    starts = np.ascontiguousarray(starts, dtype=np.uintp)
    label_lens = np.ascontiguousarray(label_lens, dtype=np.uint32)
    code = int(
        _lib.xyg_legend_best_loc(
            _ptr_f64(xs),
            _ptr_f64(ys),
            len(xs),
            starts.ctypes.data if len(starts) else 0,
            len(starts),
            label_lens.ctypes.data if len(label_lens) else 0,
            len(label_lens),
        )
    )
    if code < 0:
        raise ValueError("invalid legend_best_loc arguments")
    return code


def ribbon_edge(
    x0: float,
    x1: float,
    ya: float,
    yb: float,
    steps: int = 96,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Flatten one d3 ``curveBumpX`` edge via ``xyg_ribbon_edge`` (ABI 121)."""
    steps = int(steps)
    if steps <= 0:
        raise ValueError("ribbon_edge steps must be positive")
    n = steps + 1
    out_x = np.empty(n, dtype=np.float64)
    out_y = np.empty(n, dtype=np.float64)
    written = _lib.xyg_ribbon_edge(
        float(x0),
        float(x1),
        float(ya),
        float(yb),
        steps,
        _ptr_f64(out_x),
        _ptr_f64(out_y),
        n,
    )
    if written == _USIZE_MAX or written > n:
        raise ValueError("invalid ribbon_edge arguments")
    return out_x[: int(written)].copy(), out_y[: int(written)].copy()


def ribbon_polygon(
    x0: float,
    x1: float,
    src_lo: float,
    src_hi: float,
    dst_lo: float,
    dst_hi: float,
    steps: int = 96,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Closed flow-band polygon via ``xyg_ribbon_polygon`` (ABI 121)."""
    steps = int(steps)
    if steps <= 0:
        raise ValueError("ribbon_polygon steps must be positive")
    n = 2 * (steps + 1)
    out_x = np.empty(n, dtype=np.float64)
    out_y = np.empty(n, dtype=np.float64)
    written = _lib.xyg_ribbon_polygon(
        float(x0),
        float(x1),
        float(src_lo),
        float(src_hi),
        float(dst_lo),
        float(dst_hi),
        steps,
        _ptr_f64(out_x),
        _ptr_f64(out_y),
        n,
    )
    if written == _USIZE_MAX or written > n:
        raise ValueError("invalid ribbon_polygon arguments")
    return out_x[: int(written)].copy(), out_y[: int(written)].copy()


def monotone_tangents(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Fritsch–Carlson tangents via ``xyg_monotone_tangents`` (ABI 121)."""
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("monotone_tangents x and y must have equal length")
    n = len(x)
    out = np.empty(n, dtype=np.float64)
    written = _lib.xyg_monotone_tangents(
        _ptr_f64(x),
        _ptr_f64(y),
        n,
        _ptr_f64(out) if n else 0,
        n,
    )
    if written == _USIZE_MAX or written != n:
        raise ValueError("invalid monotone_tangents arguments")
    return out


def curve_flatten(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    bezier_steps: int = 16,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Data-space Hermite flatten via ``xyg_curve_flatten`` (ABI 121)."""
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("curve_flatten x and y must have equal length")
    bezier_steps = int(bezier_steps)
    n = len(x)
    capacity = 0 if n == 0 else (1 if n == 1 else 1 + (n - 1) * bezier_steps)
    out_x = np.empty(capacity, dtype=np.float64)
    out_y = np.empty(capacity, dtype=np.float64)
    written = _lib.xyg_curve_flatten(
        _ptr_f64(x),
        _ptr_f64(y),
        n,
        bezier_steps,
        _ptr_f64(out_x) if capacity else 0,
        _ptr_f64(out_y) if capacity else 0,
        capacity,
    )
    if written == _USIZE_MAX or written > capacity:
        raise ValueError("invalid curve_flatten arguments")
    return out_x[: int(written)].copy(), out_y[: int(written)].copy()


def step_arrays(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    mode: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Expand compact vertices into a step polyline (ABI 211).

    ``mode`` is ``1`` pre, ``2`` mid, ``3`` post. ``n < 2`` is identity.
    Empty native pointers are ``0``.
    """
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("step_arrays x and y must have equal length")
    mode = int(mode)
    n = len(x)
    probed = _lib.xyg_step_arrays(
        _ptr_f64(x) if n else 0,
        _ptr_f64(y) if n else 0,
        n,
        mode,
        0,
        0,
        0,
    )
    if probed == _USIZE_MAX:
        raise ValueError("invalid step-arrays request")
    count = int(probed)
    if count == 0:
        return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
    out_x = np.empty(count, dtype=np.float64)
    out_y = np.empty(count, dtype=np.float64)
    written = _lib.xyg_step_arrays(
        _ptr_f64(x) if n else 0,
        _ptr_f64(y) if n else 0,
        n,
        mode,
        _ptr_f64(out_x),
        _ptr_f64(out_y),
        count,
    )
    if written == _USIZE_MAX or written != count:
        raise ValueError("invalid step-arrays request")
    return out_x, out_y


def marker_path_scale(
    cx: float,
    cy: float,
    scale: float,
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Pixel-space authored marker vertices via ``xyg_marker_path_scale`` (ABI 212).

    Writes ``out_x = cx + scale * x``, ``out_y = cy - scale * y``. Empty native
    pointers are ``0``.
    """
    x = _as_f64(x, "x")
    y = _as_f64(y, "y")
    if len(x) != len(y):
        raise ValueError("marker_path_scale x and y must have equal length")
    n = len(x)
    probed = _lib.xyg_marker_path_scale(
        float(cx),
        float(cy),
        float(scale),
        _ptr_f64(x) if n else 0,
        _ptr_f64(y) if n else 0,
        n,
        0,
        0,
        0,
    )
    if probed == _USIZE_MAX:
        raise ValueError("invalid marker-path-scale request")
    count = int(probed)
    if count == 0:
        return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
    out_x = np.empty(count, dtype=np.float64)
    out_y = np.empty(count, dtype=np.float64)
    written = _lib.xyg_marker_path_scale(
        float(cx),
        float(cy),
        float(scale),
        _ptr_f64(x) if n else 0,
        _ptr_f64(y) if n else 0,
        n,
        _ptr_f64(out_x),
        _ptr_f64(out_y),
        count,
    )
    if written == _USIZE_MAX or written != count:
        raise ValueError("invalid marker-path-scale request")
    return out_x, out_y


def arrow_geometry(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    style: npt.ArrayLike,
) -> npt.NDArray[np.float64]:
    """Packed annotation-arrow geometry via ``xyg_arrow_geometry`` (ABI 217)."""
    style = _as_f64(np.asarray(style, dtype=np.float64).reshape(-1), "style")
    if len(style) not in (0, 12):
        raise ValueError("arrow_geometry style must have length 0 or 12")
    out = np.empty(11, dtype=np.float64)
    ok = _lib.xyg_arrow_geometry(
        float(x0),
        float(y0),
        float(x1),
        float(y1),
        _ptr_f64(style) if len(style) else 0,
        len(style),
        _ptr_f64(out),
        11,
    )
    if ok != 1:
        raise RuntimeError("xyg native arrow_geometry failed (output undefined)")
    return out


def arrow_shaft_points(
    p0x: float,
    p0y: float,
    p1x: float,
    p1y: float,
    cx: float,
    cy: float,
    has_control: bool,
    elbow: bool,
    samples: int = 0,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Shaft polyline via ``xyg_arrow_shaft_points`` (ABI 217)."""
    probed = _lib.xyg_arrow_shaft_points(
        float(p0x),
        float(p0y),
        float(p1x),
        float(p1y),
        float(cx),
        float(cy),
        int(bool(has_control)),
        int(bool(elbow)),
        int(samples),
        0,
        0,
        0,
    )
    if probed == _USIZE_MAX:
        raise ValueError("invalid arrow-shaft-points request")
    count = int(probed)
    if count == 0:
        return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
    out_x = np.empty(count, dtype=np.float64)
    out_y = np.empty(count, dtype=np.float64)
    written = _lib.xyg_arrow_shaft_points(
        float(p0x),
        float(p0y),
        float(p1x),
        float(p1y),
        float(cx),
        float(cy),
        int(bool(has_control)),
        int(bool(elbow)),
        int(samples),
        _ptr_f64(out_x),
        _ptr_f64(out_y),
        count,
    )
    if written == _USIZE_MAX or written != count:
        raise ValueError("invalid arrow-shaft-points request")
    return out_x, out_y


def arrow_end_decoration(
    px: float,
    py: float,
    dx: float,
    dy: float,
    style: str,
    head: float,
) -> tuple[int, npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Endpoint decoration via ``xyg_arrow_end_decoration`` (ABI 217)."""
    encoded = str(style).encode("utf-8")
    kind = ctypes.c_int32(-1)
    probed = _lib.xyg_arrow_end_decoration(
        float(px),
        float(py),
        float(dx),
        float(dy),
        encoded if encoded else 0,
        len(encoded),
        float(head),
        0,
        0,
        0,
        ctypes.byref(kind),
    )
    if probed == _USIZE_MAX or int(kind.value) < 0:
        raise ValueError("invalid arrow-end-decoration request")
    count = int(probed)
    if count == 0:
        return int(kind.value), np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
    out_x = np.empty(count, dtype=np.float64)
    out_y = np.empty(count, dtype=np.float64)
    kind = ctypes.c_int32(-1)
    written = _lib.xyg_arrow_end_decoration(
        float(px),
        float(py),
        float(dx),
        float(dy),
        encoded if encoded else 0,
        len(encoded),
        float(head),
        _ptr_f64(out_x),
        _ptr_f64(out_y),
        count,
        ctypes.byref(kind),
    )
    if written == _USIZE_MAX or written != count or int(kind.value) < 0:
        raise ValueError("invalid arrow-end-decoration request")
    return int(kind.value), out_x, out_y


def arrow_taper_polygon(
    x: npt.ArrayLike,
    y: npt.ArrayLike,
    width_start: float,
    width_end: float,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Tapered shaft polygon via ``xyg_arrow_taper_polygon`` (ABI 217)."""
    x = _as_f64(np.asarray(x, dtype=np.float64).reshape(-1), "x")
    y = _as_f64(np.asarray(y, dtype=np.float64).reshape(-1), "y")
    if len(x) != len(y):
        raise ValueError("arrow_taper_polygon x and y must have equal length")
    n = len(x)
    probed = _lib.xyg_arrow_taper_polygon(
        _ptr_f64(x) if n else 0,
        _ptr_f64(y) if n else 0,
        n,
        float(width_start),
        float(width_end),
        0,
        0,
        0,
    )
    if probed == _USIZE_MAX:
        raise ValueError("invalid arrow-taper-polygon request")
    count = int(probed)
    if count == 0:
        return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
    out_x = np.empty(count, dtype=np.float64)
    out_y = np.empty(count, dtype=np.float64)
    written = _lib.xyg_arrow_taper_polygon(
        _ptr_f64(x) if n else 0,
        _ptr_f64(y) if n else 0,
        n,
        float(width_start),
        float(width_end),
        _ptr_f64(out_x),
        _ptr_f64(out_y),
        count,
    )
    if written == _USIZE_MAX or written != count:
        raise ValueError("invalid arrow-taper-polygon request")
    return out_x, out_y


def arrow_trim_polyline_end(
    x: npt.ArrayLike,
    y: npt.ArrayLike,
    trim: float,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Trim arclength from a polyline end via ``xyg_arrow_trim_polyline_end`` (ABI 217)."""
    x = _as_f64(np.asarray(x, dtype=np.float64).reshape(-1), "x")
    y = _as_f64(np.asarray(y, dtype=np.float64).reshape(-1), "y")
    if len(x) != len(y):
        raise ValueError("arrow_trim_polyline_end x and y must have equal length")
    n = len(x)
    probed = _lib.xyg_arrow_trim_polyline_end(
        _ptr_f64(x) if n else 0,
        _ptr_f64(y) if n else 0,
        n,
        float(trim),
        0,
        0,
        0,
    )
    if probed == _USIZE_MAX:
        raise ValueError("invalid arrow-trim-polyline-end request")
    count = int(probed)
    if count == 0:
        return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
    out_x = np.empty(count, dtype=np.float64)
    out_y = np.empty(count, dtype=np.float64)
    written = _lib.xyg_arrow_trim_polyline_end(
        _ptr_f64(x) if n else 0,
        _ptr_f64(y) if n else 0,
        n,
        float(trim),
        _ptr_f64(out_x),
        _ptr_f64(out_y),
        count,
    )
    if written == _USIZE_MAX or written != count:
        raise ValueError("invalid arrow-trim-polyline-end request")
    return out_x, out_y


def rounded_rect_poly(
    x: float,
    y: float,
    w: float,
    h: float,
    r_tip: float,
    r_base: float,
    tip_top: bool,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """CW rounded-rect outline via ``xyg_rounded_rect_poly`` (ABI 121)."""
    out_x = np.empty(20, dtype=np.float64)
    out_y = np.empty(20, dtype=np.float64)
    written = _lib.xyg_rounded_rect_poly(
        float(x),
        float(y),
        float(w),
        float(h),
        float(r_tip),
        float(r_base),
        int(bool(tip_top)),
        _ptr_f64(out_x),
        _ptr_f64(out_y),
        20,
    )
    if written == _USIZE_MAX or written > 20:
        raise ValueError("invalid rounded_rect_poly arguments")
    return out_x[: int(written)].copy(), out_y[: int(written)].copy()


def violin_density(
    data: npt.NDArray[np.float64],
    n_bins: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Histogram + fixed smooth kernel; returns ``(edges, density)``."""
    data = _as_f64(data, "data")
    n_bins = int(n_bins)
    if n_bins < 4 or n_bins > 1024:
        raise ValueError("violin bins must be an integer between 4 and 1024")
    edges = np.empty(n_bins + 1, dtype=np.float64)
    density = np.empty(n_bins, dtype=np.float64)
    ok = _lib.xyg_violin_density(
        _ptr_f64(data),
        len(data),
        n_bins,
        _ptr_f64(edges),
        _ptr_f64(density),
    )
    if ok != 1:
        raise ValueError("violin density requires at least one finite value")
    return edges, density


def violin_rects(
    values: npt.NDArray[np.float64],
    offsets: npt.NDArray[np.uintp],
    centers: npt.NDArray[np.float64],
    n_bins: int,
    width: float,
    orientation: str,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.uint32],
    list[npt.NDArray[np.float64]],
    list[npt.NDArray[np.float64]],
]:
    values = _as_f64(values, "values")
    centers = _as_f64(centers, "centers")
    offsets = np.ascontiguousarray(offsets, dtype=np.uintp)
    code = {"vertical": 0, "horizontal": 1}.get(orientation, -1)
    required = int(
        _lib.xyg_violin_rects(
            _ptr_f64(values),
            len(values),
            offsets.ctypes.data,
            len(offsets),
            _ptr_f64(centers),
            len(centers),
            int(n_bins),
            float(width),
            code,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
    )
    if required == _USIZE_MAX:
        raise ValueError("invalid bounded violin geometry")
    active = required // int(n_bins)
    x0 = np.empty(required)
    y0 = np.empty(required)
    x1 = np.empty(required)
    y1 = np.empty(required)
    groups = np.empty(active, dtype=np.uint32)
    edges = np.empty(active * (int(n_bins) + 1))
    density = np.empty(required)
    written = int(
        _lib.xyg_violin_rects(
            _ptr_f64(values),
            len(values),
            offsets.ctypes.data,
            len(offsets),
            _ptr_f64(centers),
            len(centers),
            int(n_bins),
            float(width),
            code,
            _ptr_f64(x0),
            _ptr_f64(y0),
            _ptr_f64(x1),
            _ptr_f64(y1),
            groups.ctypes.data,
            _ptr_f64(edges),
            _ptr_f64(density),
            required,
        )
    )
    if written != required:
        raise ValueError("invalid bounded violin geometry")
    return (
        x0,
        y0,
        x1,
        y1,
        groups,
        [row.copy() for row in edges.reshape(active, int(n_bins) + 1)],
        [row.copy() for row in density.reshape(active, int(n_bins))],
    )


def histogram_edges(
    data: npt.NDArray[np.float64],
    *,
    range: tuple[float, float] | None = None,
    method: str = "auto",
) -> npt.NDArray[np.float64]:
    """Uniform histogram edges via Rust.

    ``method="auto"`` matches NumPy ``bins="auto"`` (min of Sturges bandwidth
    and Freedman–Diaconis bandwidth floored by ``sqrt/2``). ``method="sturges"``
    is Sturges alone.
    """
    data = _as_f64(data, "data")
    key = str(method).strip().lower()
    method_map = {"auto": 0, "sturges": 1}
    if key not in method_map:
        raise ValueError("histogram_edges method must be 'auto' or 'sturges'")
    if range is None:
        use_range = 0
        lo = hi = 0.0
    else:
        use_range = 1
        lo, hi = _finite_increasing(range[0], range[1], "histogram range")
    # ABI 98 caps Rust auto resolution at 10,000 bins (10,001 edges).
    capacity = 10_001
    out = np.empty(capacity, dtype=np.float64)
    written = _lib.xyg_histogram_edges(
        _ptr_f64(data),
        len(data),
        lo,
        hi,
        use_range,
        method_map[key],
        _ptr_f64(out),
        capacity,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid histogram_edges arguments")
    return out[: int(written)].copy()


def histogram_mark_edges(
    data: npt.NDArray[np.float64],
    *,
    range: tuple[float, float] | None = None,
    method: str = "auto",
    n_bins: int = 0,
) -> npt.NDArray[np.float64]:
    """Composition histogram edges via ``xyg_histogram_mark_edges``.

    ``method`` is ``"auto"``, ``"sturges"``, or ``"uniform"``. Empty finite
    auto/sturges use ten bins over ``range`` or ``[0, 1]``; uniform bins use
    the authored range or Rust ``auto_domain``.
    """
    data = _as_f64(data, "data")
    key = str(method).strip().lower()
    method_map = {"auto": 0, "sturges": 1, "uniform": 2}
    if key not in method_map:
        raise ValueError("histogram_mark_edges method must be 'auto', 'sturges', or 'uniform'")
    if range is None:
        use_range = 0
        lo = hi = 0.0
    else:
        use_range = 1
        lo, hi = _finite_increasing(range[0], range[1], "histogram range")
    n_bins = int(n_bins)
    if n_bins < 0:
        raise ValueError("histogram bins must be positive")
    capacity = 10_001
    out = np.empty(capacity, dtype=np.float64)
    written = _lib.xyg_histogram_mark_edges(
        _ptr_f64(data),
        len(data),
        lo,
        hi,
        use_range,
        method_map[key],
        n_bins,
        _ptr_f64(out),
        capacity,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid histogram_mark_edges arguments")
    return out[: int(written)].copy()


def contour_levels(
    data: npt.NDArray[np.float64],
    n_levels: int = 0,
) -> npt.NDArray[np.float64]:
    """Composition contour isolines via ``xyg_contour_levels``.

    ``n_levels > 0`` spaces interior samples across ``auto_domain`` of finite
    ``data``. ``n_levels == 0`` sorts ``data`` as authored levels.
    """
    data = _as_f64(data, "data")
    n_levels = int(n_levels)
    if n_levels < 0:
        raise ValueError("contour levels must be between 1 and 256")
    capacity = 256
    out = np.empty(capacity, dtype=np.float64)
    written = _lib.xyg_contour_levels(
        _ptr_f64(data),
        len(data),
        n_levels,
        _ptr_f64(out),
        capacity,
    )
    if written == _USIZE_MAX:
        raise ValueError("invalid contour_levels arguments")
    return out[: int(written)].copy()


WIND_ROSE_MAX_SECTORS = 3600
WIND_ROSE_MAX_EDGES = 256


def wind_rose_bins(
    directions: npt.NDArray[np.float64],
    speeds: npt.NDArray[np.float64],
    sectors: int,
    speed_edges: npt.NDArray[np.float64] | None = None,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64], int]:
    """Directional/speed binning via ``xy_wind_rose_bins``.

    Returns ``(edges, centres, counts, n_obs)`` where ``counts`` is shaped
    ``(n_bands, sectors)`` row-major. ``speed_edges=None`` derives quartile
    upper edges (3-significant-figure rounding, top edge ceiled).
    """
    directions = _as_f64(directions, "directions")
    speeds = _as_f64(speeds, "speeds")
    if len(directions) != len(speeds):
        raise ValueError("wind_rose directions and speeds must be the same length")
    sectors = int(sectors)
    if sectors < 3 or sectors > WIND_ROSE_MAX_SECTORS:
        raise ValueError(f"wind_rose sectors must be in 3..={WIND_ROSE_MAX_SECTORS}")
    if speed_edges is None:
        edges_in = None
        n_edges = 0
        capacity_edges = 4
    else:
        edges_in = _as_f64(speed_edges, "speed_edges")
        n_edges = len(edges_in)
        if n_edges == 0 or n_edges > WIND_ROSE_MAX_EDGES:
            raise ValueError("wind_rose speed_bins must contain at least one edge")
        capacity_edges = n_edges
    out_edges = np.empty(capacity_edges, dtype=np.float64)
    out_centres = np.empty(sectors, dtype=np.float64)
    capacity_counts = capacity_edges * sectors
    out_counts = np.empty(capacity_counts, dtype=np.float64)
    n_obs = ctypes.c_size_t()
    written = _lib.xyg_wind_rose_bins(
        _ptr_f64(directions),
        _ptr_f64(speeds),
        len(directions),
        sectors,
        0 if edges_in is None else _ptr_f64(edges_in),
        n_edges,
        _ptr_f64(out_edges),
        capacity_edges,
        _ptr_f64(out_centres),
        _ptr_f64(out_counts),
        capacity_counts,
        ctypes.byref(n_obs),
    )
    if written == _USIZE_MAX:
        if edges_in is not None and n_edges > 0:
            finite = np.isfinite(directions) & np.isfinite(speeds)
            if np.any(finite):
                fastest = float(np.max(speeds[finite]))
                uniq = np.unique(edges_in[np.isfinite(edges_in)])
                if uniq.size and float(uniq[-1]) < fastest:
                    raise ValueError(
                        f"wind_rose speed_bins top edge {float(uniq[-1]):g} is below the "
                        f"fastest observation {fastest:g}, which would drop it from "
                        "every band. Raise the last edge to cover the data."
                    )
            if not np.all(np.isfinite(edges_in)):
                raise ValueError("wind_rose speed_bins edges must all be finite")
        raise ValueError("wind_rose needs at least one finite observation")
    n_bands = int(written)
    counts = out_counts[: n_bands * sectors].reshape(n_bands, sectors).copy()
    return out_edges[:n_bands].copy(), out_centres.copy(), counts, int(n_obs.value)


def contourf_densify(
    z: npt.NDArray[np.float64],
    xpos: npt.NDArray[np.float64],
    ypos: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Bilinear densify of a contour field via ``xy_contourf_densify``."""
    z = np.asarray(z, dtype=np.float64)
    if z.ndim != 2 or min(z.shape) < 2:
        raise ValueError("contourf densify z must be a 2-D matrix with ≥2 rows/columns")
    rows, cols = z.shape
    xpos = _as_f64(xpos, "xpos")
    ypos = _as_f64(ypos, "ypos")
    if len(xpos) != cols or len(ypos) != rows:
        raise ValueError("contourf densify xpos/ypos must match z columns/rows")

    def _sample_count(size: int) -> int:
        if size > 512:
            return size
        return min(512, max(256, (size - 1) * 8 + 1))

    out_rows = _sample_count(rows)
    out_cols = _sample_count(cols)
    out_z = np.empty(out_rows * out_cols, dtype=np.float64)
    out_x = np.empty(out_cols, dtype=np.float64)
    out_y = np.empty(out_rows, dtype=np.float64)
    got_rows = ctypes.c_size_t()
    got_cols = ctypes.c_size_t()
    ok = _lib.xyg_contourf_densify(
        _ptr_f64(np.ascontiguousarray(z)),
        rows,
        cols,
        _ptr_f64(xpos),
        _ptr_f64(ypos),
        _ptr_f64(out_z),
        _ptr_f64(out_x),
        _ptr_f64(out_y),
        out_z.size,
        out_x.size,
        out_y.size,
        ctypes.byref(got_rows),
        ctypes.byref(got_cols),
    )
    if ok != 1:
        raise ValueError("invalid contourf densify arguments")
    r, c = int(got_rows.value), int(got_cols.value)
    return out_z[: r * c].reshape(r, c).copy(), out_x[:c].copy(), out_y[:r].copy()


def contourf_bands(
    z: npt.NDArray[np.float64],
    xpos: npt.NDArray[np.float64],
    ypos: npt.NDArray[np.float64],
    edges: npt.NDArray[np.float64],
    *,
    extend_min: bool = False,
    extend_max: bool = False,
) -> tuple[tuple[npt.NDArray[np.float64], ...], npt.NDArray[np.int64]]:
    """Corner-mask contourf band triangles via ``xy_contourf_bands``.

    Returns ``((x0, y0, x1, y1, x2, y2), slots)`` matching
    ``marks._contourf_corner_triangles``.
    """
    z = np.asarray(z, dtype=np.float64)
    if z.ndim != 2 or min(z.shape) < 2:
        raise ValueError("contourf bands z must be a 2-D matrix with ≥2 rows/columns")
    rows, cols = z.shape
    xpos = _as_f64(xpos, "xpos")
    ypos = _as_f64(ypos, "ypos")
    edges = _as_f64(edges, "edges")
    if len(xpos) != cols or len(ypos) != rows:
        raise ValueError("contourf bands xpos/ypos must match z columns/rows")
    if len(edges) < 2:
        raise ValueError("contourf bands needs at least two edges")
    needed = _lib.xyg_contourf_bands(
        _ptr_f64(np.ascontiguousarray(z)),
        rows,
        cols,
        _ptr_f64(xpos),
        _ptr_f64(ypos),
        _ptr_f64(edges),
        len(edges),
        1 if extend_min else 0,
        1 if extend_max else 0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    if needed == _USIZE_MAX:
        raise ValueError("invalid contourf bands arguments")
    n = int(needed)
    if n == 0:
        empty = tuple(np.empty(0, dtype=np.float64) for _ in range(6))
        return empty, np.empty(0, dtype=np.int64)
    cols_out = [np.empty(n, dtype=np.float64) for _ in range(6)]
    slots = np.empty(n, dtype=np.int64)
    written = _lib.xyg_contourf_bands(
        _ptr_f64(np.ascontiguousarray(z)),
        rows,
        cols,
        _ptr_f64(xpos),
        _ptr_f64(ypos),
        _ptr_f64(edges),
        len(edges),
        1 if extend_min else 0,
        1 if extend_max else 0,
        cols_out[0].ctypes.data,
        cols_out[1].ctypes.data,
        cols_out[2].ctypes.data,
        cols_out[3].ctypes.data,
        cols_out[4].ctypes.data,
        cols_out[5].ctypes.data,
        slots.ctypes.data,
        n,
    )
    if written != n:
        raise RuntimeError("native contourf_bands returned an inconsistent triangle count")
    return tuple(cols_out), slots


# xyg_css_check kinds — keep in sync with `crates/xyg-core/src/lib.rs`.
CSS_DECLARATION = 0
CSS_COLOR = 1
CSS_LENGTH = 2
CSS_NUMBER = 3


def css_check(
    kind: int, value: str, prop: str = ""
) -> tuple[int, Optional[tuple[float, float, float, float]]]:
    """Validate a CSS value against the native grammar (`crates/xyg-engine/src/css.rs`).

    Returns ``(status, rgba)``: status 1 = parsed statically, 2 = valid but
    browser-resolved (`var()`/`oklch()`/`calc()`/unknown-property
    passthrough), negative = error code (see `xyg_css_check` docs). ``rgba``
    is the 0..1 channel tuple for statically-resolved colors, else None
    (`currentColor` parses with no static channels). The error-message
    mapping lives in `_validate.py`; this wrapper stays mechanical.
    """
    vb = value.encode("utf-8")
    pb = prop.encode("utf-8")
    out = (ctypes.c_float * 4)(float("nan"), 0.0, 0.0, 0.0)
    status = int(_lib.xyg_css_check(kind, pb or None, len(pb), vb or None, len(vb), out))
    wrote = status == 1 and out[0] == out[0]  # NaN sentinel: untouched = no static color
    return status, (out[0], out[1], out[2], out[3]) if wrote else None


def chunked_columns_open(path: str) -> int:
    encoded = path.encode("utf-8")
    handle = int(_lib.xyg_chunked_columns_open(encoded, len(encoded)))
    if handle == 0:
        raise ValueError(f"cannot open checked XYGC artifact {path!r}")
    return handle


def chunked_columns_rows(handle: int) -> int:
    rows = int(_lib.xyg_chunked_columns_rows(ctypes.c_uint64(handle)))
    if rows == (1 << 64) - 1:
        raise ValueError("stale chunked-column handle")
    return rows


def chunked_columns_overview(
    handle: int, max_points: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, int]]:
    if (
        not isinstance(max_points, int)
        or isinstance(max_points, bool)
        or not 1 <= max_points <= 1_000_000
    ):
        raise ValueError("chunked-column max_points must be an integer in [1, 1,000,000]")
    rows = np.empty(max_points, dtype=np.uint64)
    x = np.empty(max_points, dtype=np.float64)
    y = np.empty(max_points, dtype=np.float64)
    stats = (ctypes.c_uint64 * 2)()
    written = int(
        _lib.xyg_chunked_columns_overview(
            handle,
            max_points,
            rows.ctypes.data,
            x.ctypes.data,
            y.ctypes.data,
            stats,
        )
    )
    if written == _USIZE_MAX:
        raise ValueError("chunked-column overview read failed: invalid or stale request")
    return (
        rows[:written],
        x[:written],
        y[:written],
        {
            "available_points": int(stats[0]),
            "source_rows": int(stats[1]),
            "detail_rows_read": 0,
        },
    )


def chunked_columns_cancel_before(handle: int, generation: int) -> None:
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or not 0 <= generation < (1 << 64)
    ):
        raise ValueError("chunked-column generation must be an integer in [0, 2^64)")
    if _lib.xyg_chunked_columns_cancel_before(handle, generation) != 1:
        raise ValueError("stale chunked-column handle")


def chunked_columns_read(
    handle: int,
    x_range: tuple[float, float],
    y_range: tuple[float, float] | None,
    *,
    budget_bytes: int,
    generation: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    if not isinstance(budget_bytes, int) or isinstance(budget_bytes, bool) or budget_bytes < 16:
        raise ValueError("chunked-column read budget must be at least 16 bytes")
    if budget_bytes >= 1 << 64:
        raise ValueError("chunked-column read budget must be smaller than 2^64 bytes")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or not 0 <= generation < (1 << 64)
    ):
        raise ValueError("chunked-column generation must be an integer in [0, 2^64)")
    capacity = int(budget_bytes) // 16
    x = np.empty(capacity, dtype=np.float64)
    y = np.empty(capacity, dtype=np.float64)
    stats = (ctypes.c_uint64 * 6)()
    yr = y_range or (0.0, 0.0)
    written = int(
        _lib.xyg_chunked_columns_read(
            handle,
            *x_range,
            *yr,
            int(y_range is not None),
            budget_bytes,
            generation,
            x.ctypes.data,
            y.ctypes.data,
            capacity,
            stats,
        )
    )
    if written == _USIZE_MAX:
        if int(stats[5]) == 4 and stats[4]:
            raise ValueError(
                f"chunked-column viewport read needs {int(stats[4])} bytes, "
                f"exceeding the {int(stats[3])}-byte read budget"
            )
        reason = {
            1: "I/O failure",
            2: "corrupt artifact",
            3: "invalid viewport bounds",
            5: "cancelled by newer viewport",
            6: "output capacity too small",
        }.get(int(stats[5]), "invalid request")
        raise ValueError(f"chunked-column viewport read failed: {reason}")
    provenance = dict(
        zip(
            ("generation", "first_chunk", "chunks_considered", "chunks_read", "bytes_read"),
            (int(stats[i]) for i in range(5)),
            strict=True,
        )
    )
    return x[:written], y[:written], provenance


def chunked_columns_read_page(
    handle: int,
    x_range: tuple[float, float],
    y_range: tuple[float, float] | None,
    *,
    budget_bytes: int,
    generation: int,
    cursor: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, int | bool]]:
    if (
        not isinstance(budget_bytes, int)
        or isinstance(budget_bytes, bool)
        or not 16 <= budget_bytes < (1 << 64)
    ):
        raise ValueError("chunked-column page budget must be an integer in [16, 2^64)")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or not 0 <= generation < (1 << 64)
    ):
        raise ValueError("chunked-column generation must be an integer in [0, 2^64)")
    if not isinstance(cursor, int) or isinstance(cursor, bool) or not 0 <= cursor < (1 << 32):
        raise ValueError("chunked-column page cursor must be an integer in [0, 2^32)")
    capacity = budget_bytes // 16
    x = np.empty(capacity, dtype=np.float64)
    y = np.empty(capacity, dtype=np.float64)
    stats = (ctypes.c_uint64 * 8)()
    yr = y_range or (0.0, 0.0)
    written = int(
        _lib.xyg_chunked_columns_read_page(
            handle,
            *x_range,
            *yr,
            int(y_range is not None),
            budget_bytes,
            generation,
            cursor,
            x.ctypes.data,
            y.ctypes.data,
            capacity,
            stats,
        )
    )
    if written == _USIZE_MAX:
        if int(stats[7]) == 4:
            raise ValueError(
                f"chunked-column page needs {int(stats[4])} bytes, exceeding the {int(stats[5])}-byte page budget"
            )
        reason = {
            1: "I/O failure",
            2: "corrupt artifact",
            3: "invalid cursor or viewport bounds",
            5: "cancelled by newer viewport",
            6: "output capacity too small",
        }.get(int(stats[7]), "invalid request")
        raise ValueError(f"chunked-column page read failed: {reason}")
    provenance: dict[str, int | bool] = {
        "generation": int(stats[0]),
        "first_chunk": int(stats[1]),
        "chunks_considered": int(stats[2]),
        "chunks_read": int(stats[3]),
        "bytes_read": int(stats[4]),
        "next_cursor": int(stats[5]),
        "done": bool(stats[6]),
    }
    return x[:written], y[:written], provenance


def chunked_columns_free(handle: int) -> bool:
    return _lib.xyg_chunked_columns_free(ctypes.c_uint64(handle)) == 1
