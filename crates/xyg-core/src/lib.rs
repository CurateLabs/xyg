//! C ABI shell for the XYG native core (design dossier §32).
//!
//! Marshaling, pointer/length validation, panic shielding, ABI version, and
//! `extern "C"` entry points live here. Chart algorithms and deterministic
//! product policy live in `xyg-engine`. One cdylib per platform
//! (`libxyg_core`) serves Python ctypes and Node koffi.
//!
//! Canonical f64 columns live in `xyg-engine::stream` behind `xyg_stream_*`
//! handles (ABI 59). Hosts coerce ingest and hold the opaque handle; they
//! do not own the growable backing store. Out-of-core memmap columns remain
//! host-owned (they cannot sit behind this first in-RAM handle).
//!
//! Safety contract (enforced by `python/xy/_native.py` and
//! `packages/xy-node/src/native.js`): non-empty inputs use non-null, properly
//! aligned pointers sized as documented per function. Empty inputs are
//! accepted without dereferencing their pointers; invalid pointer/argument
//! combinations return the documented error sentinel instead of panicking
//! across the C boundary. Hosts bind and check `xyg_abi_version` before any
//! other symbol.

#![allow(clippy::too_many_arguments)] // C ABI entry points; arity is the contract

use xyg_engine::css;
use xyg_engine::graph;
use xyg_engine::hexbin;
use xyg_engine::kernels;
use xyg_engine::kernels::ZoneMap;
use xyg_engine::lod_plan;
use xyg_engine::projection;
use xyg_engine::raster;
use xyg_engine::sankey;
use xyg_engine::stats;
use xyg_engine::stream;
use xyg_engine::svg;
use xyg_engine::tiles;
use xyg_engine::transition;

fn finite_gt(lo: f64, hi: f64) -> bool {
    lo.is_finite() && hi.is_finite() && hi > lo
}

fn finite_ordered(lo: f64, hi: f64) -> bool {
    lo.is_finite() && hi.is_finite() && hi >= lo
}

/// Panic backstop for the C ABI: a Rust panic must never unwind across
/// `extern "C"` into the host interpreter — that is undefined behavior and in
/// practice aborts the embedding CPython process. Any panic (an internal
/// assert, a worker-join failure, an OOM unwind) maps to the calling entry
/// point's error sentinel instead; output buffers may then be partially
/// written, exactly like the existing invalid-argument paths, and callers
/// already treat the sentinel as "output undefined". `AssertUnwindSafe` is
/// sound because nothing observes the closure's captures after a panic. This
/// backstop only operates when the target supports panic unwinding; on
/// panic-abort targets such as wasm32, an internal panic aborts the instance.
fn ffi_guard<R>(sentinel: R, body: impl FnOnce() -> R) -> R {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(body)).unwrap_or(sentinel)
}

/// Convert parallel pointer/length arrays into call-scoped immutable slices.
/// Empty spans may carry null pointers; no slice outlives the FFI call.
unsafe fn borrowed_byte_spans<'a>(
    pointers: *const *const u8,
    lengths: *const usize,
    count: usize,
) -> Option<Vec<&'a [u8]>> {
    if count == 0 {
        return Some(Vec::new());
    }
    if pointers.is_null() || lengths.is_null() {
        return None;
    }
    let pointers = std::slice::from_raw_parts(pointers, count);
    let lengths = std::slice::from_raw_parts(lengths, count);
    let mut spans = Vec::with_capacity(count);
    for (&pointer, &length) in pointers.iter().zip(lengths) {
        if length == 0 {
            spans.push(&[][..]);
        } else if pointer.is_null() {
            return None;
        } else {
            spans.push(std::slice::from_raw_parts(pointer, length));
        }
    }
    Some(spans)
}

/// ABI version — bumped on any signature change. The Python wrapper checks this
/// at load time and refuses a mismatched library loudly (§33 comm-versioning
/// rule, applied to the in-process boundary).
pub const ABI_VERSION: u32 = 60;
const FACTORIZE_CAPACITY_EXCEEDED: usize = usize::MAX - 1;

#[no_mangle]
pub extern "C" fn xyg_abi_version() -> u32 {
    ABI_VERSION
}

/// Encode homogeneous fixed-width NumPy records as stable animation identity
/// keys. `kind` is 0 for UTF-32 Unicode, 1 for fixed bytes, 2 for bool, 3 for
/// signed integers, 4 for unsigned integers, and 5 for f64. Integer widths are
/// 1/2/4/8 bytes; Unicode width is a positive multiple of four. `swap_endian`
/// must be zero or one.
///
/// Returns 0 on success, 1 for scalar data this kernel declines to tokenize
/// (the caller falls back to its reference encoder), 2 for a duplicate token,
/// 3 for a digest collision, and 4 for invalid arguments. Statuses 1, 2, and 3
/// write `out_error_first`/`out_error_index`: the offending row for 1, and the
/// prior/current pair for 2 and 3. Status 4 writes neither, and is a caller
/// bug rather than a data property — keeping it distinct from 1 stops a
/// layout-contract drift from degrading silently into the slow path.
///
/// # Safety
/// For non-empty input, `data` addresses `len * width` readable bytes and each
/// key output addresses `len` writable u32s. Error outputs address one writable
/// usize each. Input and output spans must not overlap.
#[no_mangle]
pub unsafe extern "C" fn xyg_transition_keys_fixed(
    data: *const u8,
    len: usize,
    width: usize,
    kind: u32,
    swap_endian: i32,
    out_lo: *mut u32,
    out_hi: *mut u32,
    out_error_first: *mut usize,
    out_error_index: *mut usize,
) -> i32 {
    if !matches!(swap_endian, 0 | 1) {
        return 4;
    }
    if len == 0 {
        return 0;
    }
    if out_error_first.is_null() || out_error_index.is_null() {
        return 4;
    }
    let byte_len = match len.checked_mul(width) {
        Some(value) if width > 0 => value,
        _ => return 4,
    };
    if data.is_null() || out_lo.is_null() || out_hi.is_null() {
        return 4;
    }
    let data = std::slice::from_raw_parts(data, byte_len);
    let low = std::slice::from_raw_parts_mut(out_lo, len);
    let high = std::slice::from_raw_parts_mut(out_hi, len);
    ffi_guard(4, || {
        match transition::encode_fixed_into(data, width, kind, swap_endian != 0, low, high) {
            Ok(()) => 0,
            Err(transition::TransitionKeyError::Invalid { index }) => match index {
                Some(index) => {
                    *out_error_first = index;
                    *out_error_index = index;
                    1
                }
                None => 4,
            },
            Err(transition::TransitionKeyError::Duplicate { first, index }) => {
                *out_error_first = first;
                *out_error_index = index;
                2
            }
            Err(transition::TransitionKeyError::Collision { first, index }) => {
                *out_error_first = first;
                *out_error_index = index;
                3
            }
        }
    })
}

/// Serialize parallel f64 screen coordinates into SVG polyline path data.
/// Returns the required byte count, or `usize::MAX` for invalid inputs. When
/// `out_cap` is too small no bytes are written, allowing callers to retry.
///
/// # Safety
/// `x` and `y` must point to `len` readable f64s. When `out_cap` is sufficient,
/// `out` must point to `out_cap` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_svg_poly_path(
    x: *const f64,
    y: *const f64,
    len: usize,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if len == 0 || x.is_null() || y.is_null() {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    let Some(path) = ffi_guard(None, || svg::poly_path(x, y)) else {
        return usize::MAX;
    };
    let required = path.len();
    if out_cap < required {
        return required;
    }
    if out.is_null() {
        return usize::MAX;
    }
    std::slice::from_raw_parts_mut(out, out_cap)[..required].copy_from_slice(path.as_bytes());
    required
}

/// Factor `len` fixed-width records into first-seen u32 codes. Returns the
/// number of unique records or `usize::MAX` on invalid pointers/dimensions.
///
/// # Safety
/// `data` must address `len * width` readable bytes. `out_codes` and
/// `out_unique_indices` must each address `len` writable u32 values.
#[no_mangle]
pub unsafe extern "C" fn xyg_factorize_fixed(
    data: *const u8,
    len: usize,
    width: usize,
    out_codes: *mut u32,
    out_unique_indices: *mut u32,
) -> usize {
    if len == 0 {
        return 0;
    }
    let byte_len = match len.checked_mul(width) {
        Some(value) if width > 0 => value,
        _ => return usize::MAX,
    };
    if data.is_null() || out_codes.is_null() || out_unique_indices.is_null() {
        return usize::MAX;
    }
    let data = std::slice::from_raw_parts(data, byte_len);
    let codes = std::slice::from_raw_parts_mut(out_codes, len);
    let unique_indices = std::slice::from_raw_parts_mut(out_unique_indices, len);
    ffi_guard(usize::MAX, || {
        kernels::factorize_fixed_into(data, width, codes, unique_indices).unwrap_or(usize::MAX)
    })
}

/// Palette-sized fixed-record factorization with one u8 code per row. Returns
/// `usize::MAX - 1` when `unique_capacity` is exceeded so the caller can retry
/// the general u32 path, and `usize::MAX` for invalid arguments/panics.
///
/// # Safety
/// `data`/`out_codes` address `len * width` readable bytes / `len` writable
/// bytes. `out_unique_indices` addresses `unique_capacity` writable u32s.
#[no_mangle]
pub unsafe extern "C" fn xyg_factorize_fixed_u8(
    data: *const u8,
    len: usize,
    width: usize,
    out_codes: *mut u8,
    out_unique_indices: *mut u32,
    unique_capacity: usize,
) -> usize {
    if len == 0 {
        return 0;
    }
    let byte_len = match len.checked_mul(width) {
        Some(value) if width > 0 => value,
        _ => return usize::MAX,
    };
    if unique_capacity == 0
        || unique_capacity > 256
        || data.is_null()
        || out_codes.is_null()
        || out_unique_indices.is_null()
    {
        return usize::MAX;
    }
    let data = std::slice::from_raw_parts(data, byte_len);
    let codes = std::slice::from_raw_parts_mut(out_codes, len);
    let unique_indices = std::slice::from_raw_parts_mut(out_unique_indices, unique_capacity);
    ffi_guard(usize::MAX, || {
        kernels::factorize_fixed_u8_into(data, width, codes, unique_indices)
            .unwrap_or(FACTORIZE_CAPACITY_EXCEEDED)
    })
}

/// Palette-sized fixed-record factorization with exact per-code u64 counts.
/// Counts use the same first-seen order as `out_unique_indices`. Return and
/// pointer semantics match [`xyg_factorize_fixed_u8`].
///
/// # Safety
/// `out_counts` addresses `unique_capacity` writable u64 values in addition
/// to the spans required by [`xyg_factorize_fixed_u8`].
#[no_mangle]
pub unsafe extern "C" fn xyg_factorize_fixed_u8_counts(
    data: *const u8,
    len: usize,
    width: usize,
    out_codes: *mut u8,
    out_unique_indices: *mut u32,
    out_counts: *mut u64,
    unique_capacity: usize,
) -> usize {
    if len == 0 {
        return 0;
    }
    let byte_len = match len.checked_mul(width) {
        Some(value) if width > 0 => value,
        _ => return usize::MAX,
    };
    if unique_capacity == 0
        || unique_capacity > 256
        || data.is_null()
        || out_codes.is_null()
        || out_unique_indices.is_null()
        || out_counts.is_null()
    {
        return usize::MAX;
    }
    let data = std::slice::from_raw_parts(data, byte_len);
    let codes = std::slice::from_raw_parts_mut(out_codes, len);
    let unique_indices = std::slice::from_raw_parts_mut(out_unique_indices, unique_capacity);
    let counts = std::slice::from_raw_parts_mut(out_counts, unique_capacity);
    ffi_guard(usize::MAX, || {
        kernels::factorize_fixed_u8_counts_into(data, width, codes, unique_indices, counts)
            .unwrap_or(FACTORIZE_CAPACITY_EXCEEDED)
    })
}

/// Compact factorization for one-codepoint NumPy Unicode records. The bounded
/// Unicode scalar domain uses direct lookup instead of record hashing. Return
/// semantics match [`xyg_factorize_fixed_u8_counts`].
///
/// # Safety
/// `data` addresses `len` readable u32 records. Output spans follow
/// [`xyg_factorize_fixed_u8_counts`].
#[no_mangle]
pub unsafe extern "C" fn xyg_factorize_unicode1_u8_counts(
    data: *const u32,
    len: usize,
    swap_endian: i32,
    out_codes: *mut u8,
    out_unique_indices: *mut u32,
    out_counts: *mut u64,
    unique_capacity: usize,
) -> usize {
    if len == 0 {
        return 0;
    }
    if unique_capacity == 0
        || unique_capacity > 256
        || !matches!(swap_endian, 0 | 1)
        || data.is_null()
        || out_codes.is_null()
        || out_unique_indices.is_null()
        || out_counts.is_null()
    {
        return usize::MAX;
    }
    let data = std::slice::from_raw_parts(data, len);
    let codes = std::slice::from_raw_parts_mut(out_codes, len);
    let unique_indices = std::slice::from_raw_parts_mut(out_unique_indices, unique_capacity);
    let counts = std::slice::from_raw_parts_mut(out_counts, unique_capacity);
    ffi_guard(usize::MAX, || {
        kernels::factorize_unicode1_u8_counts_into(
            data,
            swap_endian != 0,
            codes,
            unique_indices,
            counts,
        )
        .unwrap_or(FACTORIZE_CAPACITY_EXCEEDED)
    })
}

/// Remap byte codes in place. Returns 1 on success and 0 for invalid input or
/// a code outside the mapping.
///
/// # Safety
/// `values` addresses `len` writable bytes and `mapping` addresses
/// `mapping_len` readable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_remap_u8(
    values: *mut u8,
    len: usize,
    mapping: *const u8,
    mapping_len: usize,
) -> i32 {
    if len == 0 {
        return 1;
    }
    if values.is_null() || mapping.is_null() || mapping_len == 0 {
        return 0;
    }
    let values = std::slice::from_raw_parts_mut(values, len);
    let mapping = std::slice::from_raw_parts(mapping, mapping_len);
    ffi_guard(0, || kernels::remap_u8_inplace(values, mapping) as i32)
}

/// CSS value validation (styling contract; `src/css.rs`). `kind` selects the
/// grammar: `0` = property declaration (`prop` + `value`), `1` = color
/// (`value` only), `2` = length token list, `3` = number.
///
/// Returns `1` when the value parsed statically (for `kind == 1` the RGBA
/// channels are written to `out_rgba` when it is non-null and the color is
/// statically resolvable — `currentColor` parses without static channels),
/// `2` when the value is valid but browser-resolved (`var()`, `oklch()`,
/// `calc()`, unknown-property passthrough), `0` on invalid pointers or
/// non-UTF-8 input, and a negative error code otherwise: -1 empty, -2 unsafe
/// character (`;`/`{`/`}`/`</`/control), -3 unbalanced quotes or parens,
/// -4 bad hex, -5 bad color syntax, -6 unknown color name, -7 bad number,
/// -8 bad unit, -9 unknown function, -10 bad property name.
///
/// # Safety
/// `value` must point to `value_len` readable bytes (`prop`/`prop_len`
/// likewise; `prop` may be null only when `prop_len == 0`); `out_rgba`, when
/// non-null, must point to 4 writable f32s.
#[no_mangle]
pub unsafe extern "C" fn xyg_css_check(
    kind: u32,
    prop: *const u8,
    prop_len: usize,
    value: *const u8,
    value_len: usize,
    out_rgba: *mut f32,
) -> i32 {
    // Null-with-length is invalid; empty inputs never dereference (the same
    // contract as the buffer kernels — a null pointer is only legal at len 0).
    if (value.is_null() && value_len > 0) || (prop.is_null() && prop_len > 0) {
        return 0;
    }
    let bytes = |p: *const u8, n: usize| -> &[u8] {
        if n == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(p, n)
        }
    };
    let (Ok(value), Ok(prop)) = (
        std::str::from_utf8(bytes(value, value_len)),
        std::str::from_utf8(bytes(prop, prop_len)),
    ) else {
        return 0;
    };
    ffi_guard(0, || {
        let checked = match kind {
            0 => css::check_declaration(prop, value),
            1 => css::parse_color(value),
            2 => {
                let toks: Vec<&str> = value.split_whitespace().collect();
                if toks.is_empty() {
                    Err(css::CssErr::Empty)
                } else {
                    toks.iter()
                        .try_fold(css::Checked::Parsed(None), |acc, tok| {
                            Ok(match (acc, css::check_length_token(tok)?) {
                                (css::Checked::Passthrough, _) | (_, css::Checked::Passthrough) => {
                                    css::Checked::Passthrough
                                }
                                _ => css::Checked::Parsed(None),
                            })
                        })
                }
            }
            3 => value
                .trim()
                .parse::<f64>()
                .ok()
                .filter(|v| v.is_finite())
                .map(|_| css::Checked::Parsed(None))
                .ok_or(css::CssErr::BadNumber),
            _ => return 0,
        };
        match checked {
            Ok(css::Checked::Parsed(rgba)) => {
                if let (Some(c), false) = (rgba, out_rgba.is_null()) {
                    std::slice::from_raw_parts_mut(out_rgba, 4).copy_from_slice(&c);
                }
                1
            }
            Ok(css::Checked::Passthrough) => 2,
            Err(e) => -(e as i32),
        }
    })
}

/// Zone maps (§22) over `data[0..len]` in chunks of `chunk_size`.
///
/// Output arrays must each hold `ceil(len / chunk_size)` elements.
/// The final two arrays contain the positive-only min/max values used by log
/// autorange; empty positive chunks retain `+∞`/`-∞` sentinels.
/// Returns the number of chunks written.
///
/// # Safety
/// `data` must point to `len` readable f64s; each out pointer to
/// `ceil(len/chunk_size)` writable elements; `chunk_size > 0`.
#[no_mangle]
pub unsafe extern "C" fn xyg_zone_maps(
    data: *const f64,
    len: usize,
    chunk_size: usize,
    out_min: *mut f64,
    out_max: *mut f64,
    out_count: *mut u64,
    out_null_count: *mut u64,
    out_sum: *mut f64,
    out_sum_sq: *mut f64,
    out_positive_min: *mut f64,
    out_positive_max: *mut f64,
) -> usize {
    if chunk_size == 0 {
        return usize::MAX;
    }
    if len == 0 {
        return 0;
    }
    let n_chunks = len.div_ceil(chunk_size);
    if data.is_null()
        || out_min.is_null()
        || out_max.is_null()
        || out_count.is_null()
        || out_null_count.is_null()
        || out_sum.is_null()
        || out_sum_sq.is_null()
        || out_positive_min.is_null()
        || out_positive_max.is_null()
    {
        return usize::MAX;
    }
    let data = std::slice::from_raw_parts(data, len);
    let zms = match ffi_guard(None, || Some(kernels::zone_maps(data, chunk_size))) {
        Some(z) => z,
        None => return usize::MAX,
    };
    debug_assert_eq!(zms.len(), n_chunks);
    for (i, zm) in zms.iter().enumerate() {
        let ZoneMap {
            min,
            max,
            positive_min,
            positive_max,
            count,
            null_count,
            sum,
            sum_sq,
        } = *zm;
        *out_min.add(i) = min;
        *out_max.add(i) = max;
        *out_count.add(i) = count;
        *out_null_count.add(i) = null_count;
        *out_sum.add(i) = sum;
        *out_sum_sq.add(i) = sum_sq;
        *out_positive_min.add(i) = positive_min;
        *out_positive_max.add(i) = positive_max;
    }
    zms.len()
}

/// Paired zone maps for equal-length x/y columns. Each output buffer contains
/// `ceil(len / chunk_size)` stable `repr(C)` [`ZoneMap`] records.
///
/// # Safety
/// `x` and `y` address `len` readable f64s; `out_x` and `out_y` address the
/// required number of writable [`ZoneMap`] records.
#[no_mangle]
pub unsafe extern "C" fn xyg_zone_maps_pair(
    x: *const f64,
    y: *const f64,
    len: usize,
    chunk_size: usize,
    out_x: *mut ZoneMap,
    out_y: *mut ZoneMap,
) -> usize {
    if chunk_size == 0 {
        return usize::MAX;
    }
    if len == 0 {
        return 0;
    }
    if x.is_null() || y.is_null() || out_x.is_null() || out_y.is_null() {
        return usize::MAX;
    }
    let n_chunks = len.div_ceil(chunk_size);
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    let Some((x_maps, y_maps)) = ffi_guard(None, || kernels::zone_maps_pair(x, y, chunk_size))
    else {
        return usize::MAX;
    };
    debug_assert_eq!(x_maps.len(), n_chunks);
    debug_assert_eq!(y_maps.len(), n_chunks);
    std::slice::from_raw_parts_mut(out_x, n_chunks).copy_from_slice(&x_maps);
    std::slice::from_raw_parts_mut(out_y, n_chunks).copy_from_slice(&y_maps);
    n_chunks
}

/// Offset-encode (§4/§16): `out[i] = (data[i] - offset) * scale` as f32.
/// Returns 1 on success (including the empty no-op), 0 on null arguments —
/// callers must treat 0 as "output undefined".
///
/// # Safety
/// `data` must point to `len` readable f64s, `out` to `len` writable f32s.
#[no_mangle]
pub unsafe extern "C" fn xyg_encode_f32(
    data: *const f64,
    len: usize,
    offset: f64,
    scale: f64,
    out: *mut f32,
) -> i32 {
    if len == 0 {
        return 1;
    }
    if data.is_null() || out.is_null() {
        return 0;
    }
    let data = std::slice::from_raw_parts(data, len);
    let out = std::slice::from_raw_parts_mut(out, len);
    ffi_guard(0, || {
        kernels::encode_f32_into(data, offset, scale, out);
        1
    })
}

/// M4 decimation (§5 Tier 1): source indices of {first, min, max, last} per
/// bucket over the visible window `[x0, x1)`. `x` must be ascending.
///
/// `out` must hold `4 * n_buckets` u32s. Returns the count written, or
/// `usize::MAX` on invalid arguments (non-finite bounds, x1 <= x0,
/// n_buckets == 0, `len > u32::MAX`, or a `4 * n_buckets` that overflows).
///
/// # Safety
/// `x`/`y` must point to `len` readable f64s; `out` to `4 * n_buckets`
/// writable u32s.
#[no_mangle]
pub unsafe extern "C" fn xyg_m4_indices(
    x: *const f64,
    y: *const f64,
    len: usize,
    x0: f64,
    x1: f64,
    n_buckets: usize,
    out: *mut u32,
) -> usize {
    if n_buckets == 0 || !finite_gt(x0, x1) {
        return usize::MAX;
    }
    // Emitted indices are u32 row ids: a longer column would wrap them into
    // valid-looking wrong rows. The in-tree caller never ships one, but the
    // ABI must not depend on that.
    if len > u32::MAX as usize {
        return usize::MAX;
    }
    // Same defensive posture as xyg_rasterize: a caller-supplied size product
    // must not wrap in release builds into a too-short slice.
    let out_len = match n_buckets.checked_mul(4) {
        Some(n) => n,
        None => return usize::MAX,
    };
    if len == 0 {
        return 0;
    }
    if x.is_null() || y.is_null() {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    let idx = match ffi_guard(None, || Some(kernels::m4_indices(x, y, x0, x1, n_buckets))) {
        Some(idx) => idx,
        None => return usize::MAX,
    };
    if idx.is_empty() {
        return 0;
    }
    if out.is_null() {
        return usize::MAX;
    }
    let out = std::slice::from_raw_parts_mut(out, out_len);
    out[..idx.len()].copy_from_slice(&idx);
    idx.len()
}

/// Fused M4 decimation for a parallel x/y pair. Unlike `xyg_m4_indices`, this
/// writes the selected values directly and avoids returning an index array for
/// Python to gather through NumPy. SVG and PNG payload construction both use
/// this entry point, so their common reduction path stays native.
///
/// Returns the number of values written, or `usize::MAX` on invalid input.
/// `out_x` and `out_y` must each hold `4 * n_buckets` f64 values.
///
/// # Safety
/// `x` and `y` must point to `len` readable f64s; both output pointers must
/// address the documented writable capacity.
#[no_mangle]
pub unsafe extern "C" fn xyg_m4_points(
    x: *const f64,
    y: *const f64,
    len: usize,
    x0: f64,
    x1: f64,
    n_buckets: usize,
    out_x: *mut f64,
    out_y: *mut f64,
) -> usize {
    if n_buckets == 0 || !finite_gt(x0, x1) || len > u32::MAX as usize {
        return usize::MAX;
    }
    let out_len = match n_buckets.checked_mul(4) {
        Some(n) => n,
        None => return usize::MAX,
    };
    if len == 0 {
        return 0;
    }
    if x.is_null() || y.is_null() || out_x.is_null() || out_y.is_null() {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    let Some(idx) = ffi_guard(None, || Some(kernels::m4_indices(x, y, x0, x1, n_buckets))) else {
        return usize::MAX;
    };
    let out_x = std::slice::from_raw_parts_mut(out_x, out_len);
    let out_y = std::slice::from_raw_parts_mut(out_y, out_len);
    for (dst, &source) in idx.iter().enumerate() {
        let source = source as usize;
        out_x[dst] = x[source];
        out_y[dst] = y[source];
    }
    idx.len()
}

/// Native stacked-series layout. `values`, `out_lower`, and `out_upper` are
/// row-major `rows * cols` f64 buffers. `baseline` uses the generic engine
/// layout ids documented by `kernels::stacked_bounds_into`.
///
/// # Safety
/// Every pointer must address `rows * cols` readable/writable f64 values.
#[no_mangle]
pub unsafe extern "C" fn xyg_stacked_bounds(
    values: *const f64,
    rows: usize,
    cols: usize,
    baseline: u32,
    out_lower: *mut f64,
    out_upper: *mut f64,
) -> i32 {
    let Some(len) = rows.checked_mul(cols) else {
        return 0;
    };
    if len == 0 || values.is_null() || out_lower.is_null() || out_upper.is_null() {
        return 0;
    }
    let values = std::slice::from_raw_parts(values, len);
    let lower = std::slice::from_raw_parts_mut(out_lower, len);
    let upper = std::slice::from_raw_parts_mut(out_upper, len);
    ffi_guard(0, || {
        i32::from(kernels::stacked_bounds_into(
            values, rows, cols, baseline, lower, upper,
        ))
    })
}

/// Grouped / stacked / normalized bar rectangle offsets (ABI 57).
///
/// `values` is row-major `n_series * n_items`. `width` / `base` are length 1
/// or `n_items`. `mode`: 0=grouped, 1=stacked, 2=normalized. `orientation`:
/// 0=vertical, 1=horizontal. Writes `n_series * n_items` rects into the four
/// output buffers. Returns 1 on success, 0 on invalid args (including
/// normalized mode with a negative value).
///
/// # Safety
/// Pointers address the lengths described by their adjacent arguments; outs
/// address at least `n_series * n_items` writable f64s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_bar_stack(
    pos: *const f64,
    n_items: usize,
    values: *const f64,
    n_series: usize,
    width: *const f64,
    width_len: usize,
    base: *const f64,
    base_len: usize,
    mode: u32,
    orientation: u32,
    out_x0: *mut f64,
    out_x1: *mut f64,
    out_y0: *mut f64,
    out_y1: *mut f64,
) -> i32 {
    let Some(len) = n_series.checked_mul(n_items) else {
        return 0;
    };
    if len == 0
        || pos.is_null()
        || values.is_null()
        || width.is_null()
        || base.is_null()
        || width_len == 0
        || base_len == 0
        || out_x0.is_null()
        || out_x1.is_null()
        || out_y0.is_null()
        || out_y1.is_null()
    {
        return 0;
    }
    let pos = std::slice::from_raw_parts(pos, n_items);
    let values = std::slice::from_raw_parts(values, len);
    let width = std::slice::from_raw_parts(width, width_len);
    let base = std::slice::from_raw_parts(base, base_len);
    let out_x0 = std::slice::from_raw_parts_mut(out_x0, len);
    let out_x1 = std::slice::from_raw_parts_mut(out_x1, len);
    let out_y0 = std::slice::from_raw_parts_mut(out_y0, len);
    let out_y1 = std::slice::from_raw_parts_mut(out_y1, len);
    ffi_guard(0, || {
        i32::from(kernels::bar_stack_into(
            pos,
            values,
            n_series,
            n_items,
            width,
            base,
            mode,
            orientation,
            out_x0,
            out_x1,
            out_y0,
            out_y1,
        ))
    })
}

/// Weighted 2-D histogram with arbitrary edges. A null `weights` pointer means
/// unit weights; all other buffers are caller-owned f64 arrays.
///
/// # Safety
/// Input pointers address the lengths described by their adjacent arguments;
/// `out` addresses `(x_edge_len - 1) * (y_edge_len - 1)` writable f64s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_histogram2d(
    x: *const f64,
    y: *const f64,
    weights: *const f64,
    len: usize,
    x_edges: *const f64,
    x_edge_len: usize,
    y_edges: *const f64,
    y_edge_len: usize,
    out: *mut f64,
) -> i32 {
    if x_edge_len < 2
        || y_edge_len < 2
        || (len > 0 && (x.is_null() || y.is_null()))
        || x_edges.is_null()
        || y_edges.is_null()
        || out.is_null()
    {
        return 0;
    }
    let Some(out_len) = (x_edge_len - 1).checked_mul(y_edge_len - 1) else {
        return 0;
    };
    let x = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(x, len)
    };
    let y = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(y, len)
    };
    let weights = if weights.is_null() {
        None
    } else {
        Some(std::slice::from_raw_parts(weights, len))
    };
    let x_edges = std::slice::from_raw_parts(x_edges, x_edge_len);
    let y_edges = std::slice::from_raw_parts(y_edges, y_edge_len);
    let out = std::slice::from_raw_parts_mut(out, out_len);
    ffi_guard(0, || {
        i32::from(kernels::histogram2d_into(
            x, y, weights, x_edges, y_edges, out,
        ))
    })
}

/// Expand a rectilinear or curvilinear quadrilateral grid into two triangles
/// per finite cell. Returns the written triangle count or `usize::MAX` on
/// invalid arguments.
///
/// # Safety
/// `values` addresses `cell_rows * cell_cols` f64s. Coordinate lengths are
/// explicit; each output addresses `2 * cell_rows * cell_cols` writable f64s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_quad_mesh_triangles(
    x: *const f64,
    x_len: usize,
    y: *const f64,
    y_len: usize,
    values: *const f64,
    cell_rows: usize,
    cell_cols: usize,
    layout: u32,
    out_x0: *mut f64,
    out_y0: *mut f64,
    out_x1: *mut f64,
    out_y1: *mut f64,
    out_x2: *mut f64,
    out_y2: *mut f64,
    out_values: *mut f64,
) -> usize {
    let Some(cell_count) = cell_rows.checked_mul(cell_cols) else {
        return usize::MAX;
    };
    let Some(capacity) = cell_count.checked_mul(2) else {
        return usize::MAX;
    };
    if cell_count == 0
        || x.is_null()
        || y.is_null()
        || values.is_null()
        || out_x0.is_null()
        || out_y0.is_null()
        || out_x1.is_null()
        || out_y1.is_null()
        || out_x2.is_null()
        || out_y2.is_null()
        || out_values.is_null()
    {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, x_len);
    let y = std::slice::from_raw_parts(y, y_len);
    let values = std::slice::from_raw_parts(values, cell_count);
    let x0 = std::slice::from_raw_parts_mut(out_x0, capacity);
    let y0 = std::slice::from_raw_parts_mut(out_y0, capacity);
    let x1 = std::slice::from_raw_parts_mut(out_x1, capacity);
    let y1 = std::slice::from_raw_parts_mut(out_y1, capacity);
    let x2 = std::slice::from_raw_parts_mut(out_x2, capacity);
    let y2 = std::slice::from_raw_parts_mut(out_y2, capacity);
    let scalar = std::slice::from_raw_parts_mut(out_values, capacity);
    ffi_guard(usize::MAX, || {
        kernels::quad_mesh_triangles_into(
            x, y, values, cell_rows, cell_cols, layout, x0, y0, x1, y1, x2, y2, scalar,
        )
        .unwrap_or(usize::MAX)
    })
}

/// Circular/annular sector tessellation. With `capacity == 0`, output pointers
/// may be null and the required triangle count is returned.
///
/// # Safety
/// Inputs address `len` values; non-null outputs address `capacity` f64s each.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_sector_triangles(
    values: *const f64,
    len: usize,
    explode: *const f64,
    center_x: f64,
    center_y: f64,
    radius: f64,
    inner_radius: f64,
    start_degrees: f64,
    counterclockwise: i32,
    normalize: i32,
    out_x0: *mut f64,
    out_y0: *mut f64,
    out_x1: *mut f64,
    out_y1: *mut f64,
    out_x2: *mut f64,
    out_y2: *mut f64,
    out_sector: *mut f64,
    capacity: usize,
) -> usize {
    if len == 0
        || values.is_null()
        || !matches!(counterclockwise, 0 | 1)
        || !matches!(normalize, 0 | 1)
        || (capacity > 0
            && (out_x0.is_null()
                || out_y0.is_null()
                || out_x1.is_null()
                || out_y1.is_null()
                || out_x2.is_null()
                || out_y2.is_null()
                || out_sector.is_null()))
    {
        return usize::MAX;
    }
    let values = std::slice::from_raw_parts(values, len);
    let explode = if explode.is_null() {
        &[][..]
    } else {
        std::slice::from_raw_parts(explode, len)
    };
    ffi_guard(usize::MAX, || {
        if capacity == 0 {
            return kernels::sector_triangles_into(
                values,
                explode,
                center_x,
                center_y,
                radius,
                inner_radius,
                start_degrees,
                counterclockwise == 1,
                normalize == 1,
                &mut [],
                &mut [],
                &mut [],
                &mut [],
                &mut [],
                &mut [],
                &mut [],
            )
            .unwrap_or(usize::MAX);
        }
        let x0 = std::slice::from_raw_parts_mut(out_x0, capacity);
        let y0 = std::slice::from_raw_parts_mut(out_y0, capacity);
        let x1 = std::slice::from_raw_parts_mut(out_x1, capacity);
        let y1 = std::slice::from_raw_parts_mut(out_y1, capacity);
        let x2 = std::slice::from_raw_parts_mut(out_x2, capacity);
        let y2 = std::slice::from_raw_parts_mut(out_y2, capacity);
        let sector = std::slice::from_raw_parts_mut(out_sector, capacity);
        kernels::sector_triangles_into(
            values,
            explode,
            center_x,
            center_y,
            radius,
            inner_radius,
            start_degrees,
            counterclockwise == 1,
            normalize == 1,
            x0,
            y0,
            x1,
            y1,
            x2,
            y2,
            sector,
        )
        .unwrap_or(usize::MAX)
    })
}

/// Windowed real FFT, caller-owned nonnegative-frequency outputs.
///
/// # Safety
/// `data` addresses `len` f64s and each output addresses `nfft / 2 + 1` f64s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_rfft(
    data: *const f64,
    len: usize,
    nfft: usize,
    sample_rate: f64,
    out_frequency: *mut f64,
    out_real: *mut f64,
    out_imag: *mut f64,
) -> i32 {
    if len == 0
        || data.is_null()
        || out_frequency.is_null()
        || out_real.is_null()
        || out_imag.is_null()
    {
        return 0;
    }
    let bins = nfft / 2 + 1;
    let data = std::slice::from_raw_parts(data, len);
    let frequency = std::slice::from_raw_parts_mut(out_frequency, bins);
    let real = std::slice::from_raw_parts_mut(out_real, bins);
    let imag = std::slice::from_raw_parts_mut(out_imag, bins);
    ffi_guard(0, || {
        i32::from(kernels::rfft_into(
            data,
            nfft,
            sample_rate,
            frequency,
            real,
            imag,
        ))
    })
}

/// Native Welch auto/cross spectra. Null `y` computes only the x autospectrum.
///
/// # Safety
/// Non-null inputs address `len` f64s and all outputs address `nfft / 2 + 1` f64s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_welch_spectra(
    x: *const f64,
    y: *const f64,
    len: usize,
    nfft: usize,
    noverlap: usize,
    sample_rate: f64,
    out_frequency: *mut f64,
    out_pxx: *mut f64,
    out_pyy: *mut f64,
    out_pxy_real: *mut f64,
    out_pxy_imag: *mut f64,
) -> i32 {
    if len == 0
        || x.is_null()
        || out_frequency.is_null()
        || out_pxx.is_null()
        || out_pyy.is_null()
        || out_pxy_real.is_null()
        || out_pxy_imag.is_null()
    {
        return 0;
    }
    let bins = nfft / 2 + 1;
    let x = std::slice::from_raw_parts(x, len);
    let y = if y.is_null() {
        None
    } else {
        Some(std::slice::from_raw_parts(y, len))
    };
    let frequency = std::slice::from_raw_parts_mut(out_frequency, bins);
    let pxx = std::slice::from_raw_parts_mut(out_pxx, bins);
    let pyy = std::slice::from_raw_parts_mut(out_pyy, bins);
    let pxy_real = std::slice::from_raw_parts_mut(out_pxy_real, bins);
    let pxy_imag = std::slice::from_raw_parts_mut(out_pxy_imag, bins);
    ffi_guard(0, || {
        i32::from(kernels::welch_spectra_into(
            x,
            y,
            nfft,
            noverlap,
            sample_rate,
            frequency,
            pxx,
            pyy,
            pxy_real,
            pxy_imag,
        ))
    })
}

/// Time-major spectrogram power grid. Output sizes are derived from the
/// caller's `nfft`, `noverlap`, and input length.
///
/// # Safety
/// `data` addresses `len` f64s and outputs address the derived sizes.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_spectrogram(
    data: *const f64,
    len: usize,
    nfft: usize,
    noverlap: usize,
    sample_rate: f64,
    out_frequency: *mut f64,
    out_time: *mut f64,
    out_power: *mut f64,
) -> i32 {
    if len == 0
        || data.is_null()
        || nfft == 0
        || noverlap >= nfft
        || out_frequency.is_null()
        || out_time.is_null()
        || out_power.is_null()
    {
        return 0;
    }
    let bins = nfft / 2 + 1;
    let segments = if len <= nfft {
        1
    } else {
        1 + (len - nfft) / (nfft - noverlap)
    };
    let Some(power_len) = bins.checked_mul(segments) else {
        return 0;
    };
    let data = std::slice::from_raw_parts(data, len);
    let frequency = std::slice::from_raw_parts_mut(out_frequency, bins);
    let time = std::slice::from_raw_parts_mut(out_time, segments);
    let power = std::slice::from_raw_parts_mut(out_power, power_len);
    ffi_guard(0, || {
        i32::from(kernels::spectrogram_into(
            data,
            nfft,
            noverlap,
            sample_rate,
            frequency,
            time,
            power,
        ))
    })
}

/// Lag correlation used by acorr/xcorr.
///
/// # Safety
/// Inputs address `len` f64s; outputs address `2 * max_lag + 1` f64s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_correlation(
    x: *const f64,
    y: *const f64,
    len: usize,
    max_lag: usize,
    normalize: i32,
    out_lag: *mut f64,
    out_correlation: *mut f64,
) -> i32 {
    if len == 0
        || x.is_null()
        || y.is_null()
        || !matches!(normalize, 0 | 1)
        || out_lag.is_null()
        || out_correlation.is_null()
    {
        return 0;
    }
    let Some(output_len) = max_lag
        .checked_mul(2)
        .and_then(|value| value.checked_add(1))
    else {
        return 0;
    };
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    let lag = std::slice::from_raw_parts_mut(out_lag, output_len);
    let correlation = std::slice::from_raw_parts_mut(out_correlation, output_len);
    ffi_guard(0, || {
        i32::from(kernels::correlation_into(
            x,
            y,
            max_lag,
            normalize == 1,
            lag,
            correlation,
        ))
    })
}

/// Weighted empirical CDF. Returns the number of coalesced values or
/// `usize::MAX` when the inputs are invalid.
///
/// # Safety
/// Inputs address `len` readable f64s and outputs address `len` writable f64s.
#[no_mangle]
pub unsafe extern "C" fn xyg_weighted_ecdf(
    values: *const f64,
    weights: *const f64,
    len: usize,
    out_values: *mut f64,
    out_cumulative: *mut f64,
) -> usize {
    if len == 0
        || values.is_null()
        || weights.is_null()
        || out_values.is_null()
        || out_cumulative.is_null()
    {
        return usize::MAX;
    }
    let values = std::slice::from_raw_parts(values, len);
    let weights = std::slice::from_raw_parts(weights, len);
    let output_values = std::slice::from_raw_parts_mut(out_values, len);
    let cumulative = std::slice::from_raw_parts_mut(out_cumulative, len);
    ffi_guard(usize::MAX, || {
        kernels::weighted_ecdf_into(values, weights, output_values, cumulative)
            .unwrap_or(usize::MAX)
    })
}

/// Expand indexed topology into independent filled triangles.
///
/// # Safety
/// All pointers address the element counts derived from adjacent length arguments.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_indexed_triangles(
    x: *const f64,
    y: *const f64,
    vertex_count: usize,
    triangles: *const i64,
    face_count: usize,
    values: *const f64,
    value_len: usize,
    value_mode: u32,
    out_x0: *mut f64,
    out_y0: *mut f64,
    out_x1: *mut f64,
    out_y1: *mut f64,
    out_x2: *mut f64,
    out_y2: *mut f64,
    out_values: *mut f64,
) -> usize {
    let Some(index_count) = face_count.checked_mul(3) else {
        return usize::MAX;
    };
    if x.is_null()
        || y.is_null()
        || triangles.is_null()
        || (value_len > 0 && values.is_null())
        || out_x0.is_null()
        || out_y0.is_null()
        || out_x1.is_null()
        || out_y1.is_null()
        || out_x2.is_null()
        || out_y2.is_null()
        || out_values.is_null()
    {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, vertex_count);
    let y = std::slice::from_raw_parts(y, vertex_count);
    let triangles = std::slice::from_raw_parts(triangles, index_count);
    let values = if value_len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(values, value_len)
    };
    let x0 = std::slice::from_raw_parts_mut(out_x0, face_count);
    let y0 = std::slice::from_raw_parts_mut(out_y0, face_count);
    let x1 = std::slice::from_raw_parts_mut(out_x1, face_count);
    let y1 = std::slice::from_raw_parts_mut(out_y1, face_count);
    let x2 = std::slice::from_raw_parts_mut(out_x2, face_count);
    let y2 = std::slice::from_raw_parts_mut(out_y2, face_count);
    let scalar = std::slice::from_raw_parts_mut(out_values, face_count);
    ffi_guard(usize::MAX, || {
        kernels::indexed_triangles_into(
            x, y, triangles, values, value_mode, x0, y0, x1, y1, x2, y2, scalar,
        )
        .unwrap_or(usize::MAX)
    })
}

/// Emit unique line segments for indexed triangle edges.
///
/// # Safety
/// Vertex inputs address `vertex_count`, topology addresses `face_count * 3`,
/// and each output addresses that same topology length.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_triangle_edges(
    x: *const f64,
    y: *const f64,
    vertex_count: usize,
    triangles: *const i64,
    face_count: usize,
    out_x0: *mut f64,
    out_x1: *mut f64,
    out_y0: *mut f64,
    out_y1: *mut f64,
) -> usize {
    let Some(capacity) = face_count.checked_mul(3) else {
        return usize::MAX;
    };
    if x.is_null()
        || y.is_null()
        || triangles.is_null()
        || out_x0.is_null()
        || out_x1.is_null()
        || out_y0.is_null()
        || out_y1.is_null()
    {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, vertex_count);
    let y = std::slice::from_raw_parts(y, vertex_count);
    let triangles = std::slice::from_raw_parts(triangles, capacity);
    let x0 = std::slice::from_raw_parts_mut(out_x0, capacity);
    let x1 = std::slice::from_raw_parts_mut(out_x1, capacity);
    let y0 = std::slice::from_raw_parts_mut(out_y0, capacity);
    let y1 = std::slice::from_raw_parts_mut(out_y1, capacity);
    ffi_guard(usize::MAX, || {
        kernels::triangle_edges_into(x, y, triangles, x0, x1, y0, y1).unwrap_or(usize::MAX)
    })
}

/// Delaunay topology for finite unique 2-D points. `out` addresses
/// `capacity * 3` writable i64 indices; returns the face count.
///
/// # Safety
/// `x` and `y` address `len` f64s; `out` addresses `capacity * 3` i64s.
#[no_mangle]
pub unsafe extern "C" fn xyg_delaunay_triangles(
    x: *const f64,
    y: *const f64,
    len: usize,
    out: *mut i64,
    capacity: usize,
) -> usize {
    if len < 3 || x.is_null() || y.is_null() || out.is_null() {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    ffi_guard(usize::MAX, || {
        let Some(triangles) = kernels::delaunay_triangles(x, y) else {
            return usize::MAX;
        };
        if triangles.len() > capacity {
            return usize::MAX;
        }
        let Some(output_len) = capacity.checked_mul(3) else {
            return usize::MAX;
        };
        let output = std::slice::from_raw_parts_mut(out, output_len);
        for (index, triangle) in triangles.iter().enumerate() {
            output[index * 3..index * 3 + 3].copy_from_slice(triangle);
        }
        triangles.len()
    })
}

/// Ear-clipping topology for a finite simple polygon. `capacity` is the
/// number of output faces, and `out` addresses `capacity * 3` i64 indices.
///
/// # Safety
/// `x` and `y` address `len` f64s; `out` addresses `capacity * 3` i64s.
#[no_mangle]
pub unsafe extern "C" fn xyg_polygon_triangles(
    x: *const f64,
    y: *const f64,
    len: usize,
    out: *mut i64,
    capacity: usize,
) -> usize {
    if len < 3 || x.is_null() || y.is_null() || out.is_null() {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    ffi_guard(usize::MAX, || {
        let Some(triangles) = kernels::polygon_triangles(x, y) else {
            return usize::MAX;
        };
        if triangles.len() > capacity {
            return usize::MAX;
        }
        let Some(output_len) = capacity.checked_mul(3) else {
            return usize::MAX;
        };
        let output = std::slice::from_raw_parts_mut(out, output_len);
        for (index, triangle) in triangles.iter().enumerate() {
            output[index * 3..index * 3 + 3].copy_from_slice(triangle);
        }
        triangles.len()
    })
}

/// Indexed triangular isoline extraction. `capacity == 0` queries the segment
/// count; otherwise all five outputs address `capacity` writable f64s.
///
/// # Safety
/// Inputs and outputs address the element counts described by their length arguments.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_marching_triangles(
    x: *const f64,
    y: *const f64,
    z: *const f64,
    vertex_count: usize,
    triangles: *const i64,
    face_count: usize,
    levels: *const f64,
    level_count: usize,
    out_x0: *mut f64,
    out_x1: *mut f64,
    out_y0: *mut f64,
    out_y1: *mut f64,
    out_levels: *mut f64,
    capacity: usize,
) -> usize {
    let Some(index_count) = face_count.checked_mul(3) else {
        return usize::MAX;
    };
    if x.is_null()
        || y.is_null()
        || z.is_null()
        || triangles.is_null()
        || (level_count > 0 && levels.is_null())
        || (capacity > 0
            && (out_x0.is_null()
                || out_x1.is_null()
                || out_y0.is_null()
                || out_y1.is_null()
                || out_levels.is_null()))
    {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, vertex_count);
    let y = std::slice::from_raw_parts(y, vertex_count);
    let z = std::slice::from_raw_parts(z, vertex_count);
    let triangles = std::slice::from_raw_parts(triangles, index_count);
    let levels = if level_count == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(levels, level_count)
    };
    ffi_guard(usize::MAX, || {
        if capacity == 0 {
            return kernels::marching_triangles_into(
                x,
                y,
                z,
                triangles,
                levels,
                &mut [],
                &mut [],
                &mut [],
                &mut [],
                &mut [],
            )
            .unwrap_or(usize::MAX);
        }
        let x0 = std::slice::from_raw_parts_mut(out_x0, capacity);
        let x1 = std::slice::from_raw_parts_mut(out_x1, capacity);
        let y0 = std::slice::from_raw_parts_mut(out_y0, capacity);
        let y1 = std::slice::from_raw_parts_mut(out_y1, capacity);
        let out_levels = std::slice::from_raw_parts_mut(out_levels, capacity);
        kernels::marching_triangles_into(x, y, z, triangles, levels, x0, x1, y0, y1, out_levels)
            .unwrap_or(usize::MAX)
    })
}

/// Vector origins/components to instanced shaft + arrowhead segments.
/// Returns the written segment count or `usize::MAX` on invalid arguments.
///
/// # Safety
/// Inputs address `len` f64 values; outputs address `3 * len` writable f64s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_vector_segments(
    x: *const f64,
    y: *const f64,
    u: *const f64,
    v: *const f64,
    len: usize,
    scale: f64,
    pivot: u32,
    head_ratio: f64,
    out_x0: *mut f64,
    out_x1: *mut f64,
    out_y0: *mut f64,
    out_y1: *mut f64,
) -> usize {
    let Some(capacity) = len.checked_mul(3) else {
        return usize::MAX;
    };
    if len == 0 {
        return 0;
    }
    if x.is_null()
        || y.is_null()
        || u.is_null()
        || v.is_null()
        || out_x0.is_null()
        || out_x1.is_null()
        || out_y0.is_null()
        || out_y1.is_null()
    {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    let u = std::slice::from_raw_parts(u, len);
    let v = std::slice::from_raw_parts(v, len);
    let x0 = std::slice::from_raw_parts_mut(out_x0, capacity);
    let x1 = std::slice::from_raw_parts_mut(out_x1, capacity);
    let y0 = std::slice::from_raw_parts_mut(out_y0, capacity);
    let y1 = std::slice::from_raw_parts_mut(out_y1, capacity);
    ffi_guard(usize::MAX, || {
        kernels::vector_segments_into(x, y, u, v, scale, pivot, head_ratio, x0, x1, y0, y1)
            .unwrap_or(usize::MAX)
    })
}

/// Regular-grid streamline integration. With `capacity == 0`, returns the
/// required segment count without writing outputs; otherwise writes four
/// parallel segment columns and returns the same count.
///
/// # Safety
/// Coordinate/vector buffers and optional outputs have the dimensions given
/// by `rows`, `cols`, and `capacity`.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_streamlines(
    x_coords: *const f64,
    cols: usize,
    y_coords: *const f64,
    rows: usize,
    u: *const f64,
    v: *const f64,
    density: f64,
    max_steps: usize,
    out_x0: *mut f64,
    out_x1: *mut f64,
    out_y0: *mut f64,
    out_y1: *mut f64,
    capacity: usize,
) -> usize {
    let Some(len) = rows.checked_mul(cols) else {
        return usize::MAX;
    };
    if rows < 2
        || cols < 2
        || x_coords.is_null()
        || y_coords.is_null()
        || u.is_null()
        || v.is_null()
        || (capacity > 0
            && (out_x0.is_null() || out_x1.is_null() || out_y0.is_null() || out_y1.is_null()))
    {
        return usize::MAX;
    }
    let x_coords = std::slice::from_raw_parts(x_coords, cols);
    let y_coords = std::slice::from_raw_parts(y_coords, rows);
    let u = std::slice::from_raw_parts(u, len);
    let v = std::slice::from_raw_parts(v, len);
    ffi_guard(usize::MAX, || {
        let Some(segments) = kernels::streamlines(x_coords, y_coords, u, v, density, max_steps)
        else {
            return usize::MAX;
        };
        if capacity == 0 {
            return segments.len();
        }
        if capacity < segments.len() {
            return usize::MAX;
        }
        let x0 = std::slice::from_raw_parts_mut(out_x0, capacity);
        let x1 = std::slice::from_raw_parts_mut(out_x1, capacity);
        let y0 = std::slice::from_raw_parts_mut(out_y0, capacity);
        let y1 = std::slice::from_raw_parts_mut(out_y1, capacity);
        for (index, &(sx0, sx1, sy0, sy1)) in segments.iter().enumerate() {
            x0[index] = sx0;
            x1[index] = sx1;
            y0[index] = sy0;
            y1[index] = sy1;
        }
        segments.len()
    })
}

/// Marching-squares isoline extraction over a regular grid. The first call
/// may pass `capacity == 0` and null output pointers to query the required
/// segment count; a later call writes the five parallel f64 output arrays.
/// Returns the required/written segment count, or `usize::MAX` on invalid
/// arguments or a panic inside the kernel.
///
/// # Safety
/// `z` points to `rows * cols` readable f64s; `x_coords` has `cols` values;
/// `y_coords` has `rows` values; `levels` has `n_levels` values. When capacity
/// is nonzero, every output pointer points to `capacity` writable f64s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_marching_squares(
    z: *const f64,
    rows: usize,
    cols: usize,
    x_coords: *const f64,
    y_coords: *const f64,
    levels: *const f64,
    n_levels: usize,
    corner_mask: u8,
    out_x0: *mut f64,
    out_x1: *mut f64,
    out_y0: *mut f64,
    out_y1: *mut f64,
    out_levels: *mut f64,
    capacity: usize,
) -> usize {
    if rows < 2 || cols < 2 {
        return usize::MAX;
    }
    let z_len = match rows.checked_mul(cols) {
        Some(n) => n,
        None => return usize::MAX,
    };
    if z.is_null() || x_coords.is_null() || y_coords.is_null() {
        return usize::MAX;
    }
    if n_levels > 0 && levels.is_null() {
        return usize::MAX;
    }
    if capacity > 0
        && (out_x0.is_null()
            || out_x1.is_null()
            || out_y0.is_null()
            || out_y1.is_null()
            || out_levels.is_null())
    {
        return usize::MAX;
    }
    let z = std::slice::from_raw_parts(z, z_len);
    let x_coords = std::slice::from_raw_parts(x_coords, cols);
    let y_coords = std::slice::from_raw_parts(y_coords, rows);
    let levels = if n_levels == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(levels, n_levels)
    };
    if !x_coords.windows(2).all(|pair| pair[1] > pair[0])
        || !y_coords.windows(2).all(|pair| pair[1] > pair[0])
        || !x_coords.iter().all(|value| value.is_finite())
        || !y_coords.iter().all(|value| value.is_finite())
        || !levels.iter().all(|value| value.is_finite())
    {
        return usize::MAX;
    }
    ffi_guard(usize::MAX, || {
        if capacity == 0 {
            let (empty_x0, empty_x1, empty_y0, empty_y1, empty_levels) = (
                &mut [][..],
                &mut [][..],
                &mut [][..],
                &mut [][..],
                &mut [][..],
            );
            kernels::marching_squares_into(
                z,
                rows,
                cols,
                x_coords,
                y_coords,
                levels,
                corner_mask != 0,
                empty_x0,
                empty_x1,
                empty_y0,
                empty_y1,
                empty_levels,
            )
        } else {
            let x0_out = std::slice::from_raw_parts_mut(out_x0, capacity);
            let x1_out = std::slice::from_raw_parts_mut(out_x1, capacity);
            let y0_out = std::slice::from_raw_parts_mut(out_y0, capacity);
            let y1_out = std::slice::from_raw_parts_mut(out_y1, capacity);
            let level_out = std::slice::from_raw_parts_mut(out_levels, capacity);
            kernels::marching_squares_into(
                z,
                rows,
                cols,
                x_coords,
                y_coords,
                levels,
                corner_mask != 0,
                x0_out,
                x1_out,
                y0_out,
                y1_out,
                level_out,
            )
        }
    })
}

/// 2D density aggregation (§5 Tier 2): additively bin points into a `w × h`
/// grid over the viewport. `out` must be `w * h` f32s (fully overwritten).
///
/// # Safety
/// `x`/`y` must point to `len` readable f64s; `out` to `w * h` writable f32s;
/// `w > 0 && h > 0` and finite increasing bounds.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_bin_2d(
    x: *const f64,
    y: *const f64,
    len: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    w: usize,
    h: usize,
    out: *mut f32,
) -> i32 {
    let bad = w == 0 || h == 0 || !finite_gt(x0, x1) || !finite_gt(y0, y1);
    if bad {
        return 0;
    }
    if out.is_null() {
        return 0;
    }
    let grid_len = match w.checked_mul(h) {
        Some(n) => n,
        None => return 0,
    };
    let (x, y) = if len == 0 {
        (&[][..], &[][..])
    } else {
        if x.is_null() || y.is_null() {
            return 0;
        }
        (
            std::slice::from_raw_parts(x, len),
            std::slice::from_raw_parts(y, len),
        )
    };
    let out = std::slice::from_raw_parts_mut(out, grid_len);
    ffi_guard(0, || {
        kernels::bin_2d(x, y, x0, x1, y0, y1, w, h, out);
        1
    })
}

/// f32-input density bin for the out-of-core spatial index (`_spatial.py`):
/// bins memmap'd f32 (lon, lat) directly into a `w*h` f32 grid, skipping the
/// f64 widening that dominates a windowed gather. Bit-identical to `xyg_bin_2d`
/// over the same points cast to f64. Returns 1 on success, 0 on bad args.
///
/// # Safety
/// `x`/`y` must each point to `len` readable f32 (or be null iff `len == 0`);
/// `out` must point to `w*h` writable f32.
#[no_mangle]
pub unsafe extern "C" fn xyg_bin_2d_f32(
    x: *const f32,
    y: *const f32,
    len: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    w: usize,
    h: usize,
    out: *mut f32,
) -> i32 {
    let bad = w == 0 || h == 0 || !finite_gt(x0, x1) || !finite_gt(y0, y1);
    if bad || out.is_null() {
        return 0;
    }
    let grid_len = match w.checked_mul(h) {
        Some(n) => n,
        None => return 0,
    };
    let (x, y) = if len == 0 {
        (&[][..], &[][..])
    } else {
        if x.is_null() || y.is_null() {
            return 0;
        }
        (
            std::slice::from_raw_parts(x, len),
            std::slice::from_raw_parts(y, len),
        )
    };
    let out = std::slice::from_raw_parts_mut(out, grid_len);
    ffi_guard(0, || {
        kernels::bin_2d_f32(x, y, x0, x1, y0, y1, w, h, out);
        1
    })
}

/// Marshal the C-side color source for mean-color binning: exactly one of
/// `idx` (one LUT index per point, with `lut`/`lut_len` as 1..=256 RGBA8
/// entries) or `rgba` (straight-alpha RGBA8, 4 bytes per point) must be
/// non-null. Returns `None` for any other shape.
///
/// # Safety
/// Non-null pointers must address the documented lengths for `len` points.
unsafe fn color_source_from_raw<'a>(
    len: usize,
    idx: *const u8,
    rgba: *const u8,
    lut: *const u8,
    lut_len: usize,
) -> Option<kernels::BinColorSource<'a>> {
    match (idx.is_null(), rgba.is_null()) {
        (false, true) => {
            if lut.is_null() || lut_len == 0 || lut_len > 256 {
                return None;
            }
            Some(kernels::BinColorSource::Indexed {
                idx: std::slice::from_raw_parts(idx, len),
                lut: std::slice::from_raw_parts(lut as *const [u8; 4], lut_len),
            })
        }
        (true, false) => Some(kernels::BinColorSource::Rgba(std::slice::from_raw_parts(
            rgba,
            len * 4,
        ))),
        _ => None,
    }
}

/// Mean-color companion grid to `xyg_bin_2d` (§5 Tier 2, LOD doc §2): fill
/// `out` (`w*h*4` straight-alpha RGBA8, row 0 = bottom) with each cell's
/// alpha-weighted mean point color (linear-light average, sRGB bytes out)
/// and mean point alpha. Cell membership is bit-identical to `xyg_bin_2d`.
/// Returns 1 on success, 0 on invalid arguments.
///
/// # Safety
/// `x`/`y` must point to `len` readable f64s; the color source pointers must
/// satisfy `color_source_from_raw`; `out` must address `w*h*4` writable bytes.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_bin_2d_mean_color(
    x: *const f64,
    y: *const f64,
    len: usize,
    idx: *const u8,
    rgba: *const u8,
    lut: *const u8,
    lut_len: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    w: usize,
    h: usize,
    out: *mut u8,
) -> i32 {
    if w == 0 || h == 0 || !finite_gt(x0, x1) || !finite_gt(y0, y1) || out.is_null() {
        return 0;
    }
    let Some(grid_len) = w.checked_mul(h).and_then(|n| n.checked_mul(4)) else {
        return 0;
    };
    let out = std::slice::from_raw_parts_mut(out, grid_len);
    if len == 0 {
        out.fill(0);
        return 1;
    }
    if x.is_null() || y.is_null() {
        return 0;
    }
    let Some(colors) = color_source_from_raw(len, idx, rgba, lut, lut_len) else {
        return 0;
    };
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    ffi_guard(0, || {
        kernels::bin_2d_mean_color(x, y, &colors, x0, x1, y0, y1, w, h, out);
        1
    })
}

/// Native PNG rasterizer (dossier Phase 3). Paints a Python-built display list
/// (`cmd[0..cmd_len]`, see `raster.rs`/`_raster.py`) into a caller-owned
/// straight-alpha RGBA8 framebuffer `out` of `w*h*4` bytes. Returns 1 on
/// success, 0 on a malformed command buffer or size mismatch (output undefined).
///
/// # Safety
/// `cmd` must point to `cmd_len` readable bytes (or be null iff `cmd_len == 0`);
/// `out` must point to `w*h*4` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_rasterize(
    cmd: *const u8,
    cmd_len: usize,
    out: *mut u8,
    w: usize,
    h: usize,
) -> i32 {
    if out.is_null() || w == 0 || h == 0 {
        return 0;
    }
    let out_len = match w.checked_mul(h).and_then(|n| n.checked_mul(4)) {
        Some(n) => n,
        None => return 0,
    };
    let cmds = if cmd_len == 0 {
        &[][..]
    } else if cmd.is_null() {
        return 0;
    } else {
        std::slice::from_raw_parts(cmd, cmd_len)
    };
    let out = std::slice::from_raw_parts_mut(out, out_len);
    ffi_guard(0, || raster::rasterize_into(cmds, w, h, out) as i32)
}

/// Rasterize a display list that may reference an immutable external byte
/// arena. The arena is borrowed only for this synchronous call; no pointer is
/// retained by Rust. This keeps large already-built grids out of the command
/// buffer without changing their ownership.
///
/// # Safety
/// Pointer contracts match `xyg_rasterize`; `data` must point to `data_len`
/// readable bytes, or be null iff `data_len == 0`.
#[no_mangle]
pub unsafe extern "C" fn xyg_rasterize_data(
    cmd: *const u8,
    cmd_len: usize,
    data: *const u8,
    data_len: usize,
    out: *mut u8,
    w: usize,
    h: usize,
) -> i32 {
    if out.is_null() || w == 0 || h == 0 {
        return 0;
    }
    let out_len = match w.checked_mul(h).and_then(|n| n.checked_mul(4)) {
        Some(n) => n,
        None => return 0,
    };
    let cmds = if cmd_len == 0 {
        &[][..]
    } else if cmd.is_null() {
        return 0;
    } else {
        std::slice::from_raw_parts(cmd, cmd_len)
    };
    let arena = if data_len == 0 {
        &[][..]
    } else if data.is_null() {
        return 0;
    } else {
        std::slice::from_raw_parts(data, data_len)
    };
    let out = std::slice::from_raw_parts_mut(out, out_len);
    ffi_guard(0, || {
        raster::rasterize_data_into(cmds, arena, w, h, out) as i32
    })
}

/// Rasterize with multiple immutable arenas, used by static export to borrow
/// canonical arrays alongside the ordinary owned payload blob.
///
/// # Safety
/// `span_ptrs` and `span_lens` must each contain `span_count` readable entries;
/// every non-empty span pointer must address its declared readable byte range.
/// Other pointer contracts match `xyg_rasterize`.
#[no_mangle]
pub unsafe extern "C" fn xyg_rasterize_spans(
    cmd: *const u8,
    cmd_len: usize,
    span_ptrs: *const *const u8,
    span_lens: *const usize,
    span_count: usize,
    out: *mut u8,
    w: usize,
    h: usize,
) -> i32 {
    if out.is_null() || w == 0 || h == 0 {
        return 0;
    }
    let out_len = match w.checked_mul(h).and_then(|n| n.checked_mul(4)) {
        Some(n) => n,
        None => return 0,
    };
    let cmds = if cmd_len == 0 {
        &[][..]
    } else if cmd.is_null() {
        return 0;
    } else {
        std::slice::from_raw_parts(cmd, cmd_len)
    };
    let Some(spans) = borrowed_byte_spans(span_ptrs, span_lens, span_count) else {
        return 0;
    };
    let out = std::slice::from_raw_parts_mut(out, out_len);
    ffi_guard(0, || {
        raster::rasterize_spans_into(cmds, &spans, w, h, out) as i32
    })
}

/// Fused native raster + fast PNG encoder. Returns the PNG byte count written
/// to `out`, or `usize::MAX` when the command stream is malformed, dimensions
/// overflow, or `out_capacity` is insufficient.
///
/// # Safety
/// Pointer contracts match `xyg_rasterize`; `out` must point to
/// `out_capacity` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_rasterize_png(
    cmd: *const u8,
    cmd_len: usize,
    out: *mut u8,
    out_capacity: usize,
    w: usize,
    h: usize,
) -> usize {
    if out.is_null() || out_capacity == 0 || w == 0 || h == 0 {
        return usize::MAX;
    }
    let cmds = if cmd_len == 0 {
        &[][..]
    } else if cmd.is_null() {
        return usize::MAX;
    } else {
        std::slice::from_raw_parts(cmd, cmd_len)
    };
    let out = std::slice::from_raw_parts_mut(out, out_capacity);
    ffi_guard(usize::MAX, || {
        raster::rasterize_png_into(cmds, w, h, out).unwrap_or(usize::MAX)
    })
}

/// Fused PNG rasterizer with the synchronous external arena accepted by
/// `xyg_rasterize_data`.
///
/// # Safety
/// Pointer contracts match `xyg_rasterize_data`; `out` must point to
/// `out_capacity` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_rasterize_png_data(
    cmd: *const u8,
    cmd_len: usize,
    data: *const u8,
    data_len: usize,
    out: *mut u8,
    out_capacity: usize,
    w: usize,
    h: usize,
) -> usize {
    if out.is_null() || out_capacity == 0 || w == 0 || h == 0 {
        return usize::MAX;
    }
    let cmds = if cmd_len == 0 {
        &[][..]
    } else if cmd.is_null() {
        return usize::MAX;
    } else {
        std::slice::from_raw_parts(cmd, cmd_len)
    };
    let arena = if data_len == 0 {
        &[][..]
    } else if data.is_null() {
        return usize::MAX;
    } else {
        std::slice::from_raw_parts(data, data_len)
    };
    let out = std::slice::from_raw_parts_mut(out, out_capacity);
    ffi_guard(usize::MAX, || {
        raster::rasterize_png_data_into(cmds, arena, w, h, out).unwrap_or(usize::MAX)
    })
}

/// Fused PNG rasterizer backed by multiple synchronous immutable arenas.
///
/// # Safety
/// Span contracts match `xyg_rasterize_spans`; output contracts match
/// `xyg_rasterize_png`.
#[no_mangle]
pub unsafe extern "C" fn xyg_rasterize_png_spans(
    cmd: *const u8,
    cmd_len: usize,
    span_ptrs: *const *const u8,
    span_lens: *const usize,
    span_count: usize,
    out: *mut u8,
    out_capacity: usize,
    w: usize,
    h: usize,
) -> usize {
    if out.is_null() || out_capacity == 0 || w == 0 || h == 0 {
        return usize::MAX;
    }
    let cmds = if cmd_len == 0 {
        &[][..]
    } else if cmd.is_null() {
        return usize::MAX;
    } else {
        std::slice::from_raw_parts(cmd, cmd_len)
    };
    let Some(spans) = borrowed_byte_spans(span_ptrs, span_lens, span_count) else {
        return usize::MAX;
    };
    let out = std::slice::from_raw_parts_mut(out, out_capacity);
    ffi_guard(usize::MAX, || {
        raster::rasterize_png_spans_into(cmds, &spans, w, h, out).unwrap_or(usize::MAX)
    })
}

/// Native heatmap scalar-to-RGBA mapper used by the static raster path.
/// Returns 1 on success and 0 on invalid dimensions or pointers.
///
/// # Safety
/// `raw` contains `w*h` readable f64 values, `stops` contains
/// `stop_count*3` readable bytes, and `out` contains `w*h*4` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_heatmap_rgba(
    raw: *const f64,
    w: usize,
    h: usize,
    stops: *const u8,
    stop_count: usize,
    alpha: u8,
    out: *mut u8,
) -> i32 {
    let Some(len) = w.checked_mul(h) else {
        return 0;
    };
    if len == 0 || stop_count == 0 || raw.is_null() || stops.is_null() || out.is_null() {
        return 0;
    }
    let Some(out_len) = len.checked_mul(4) else {
        return 0;
    };
    let Some(stop_len) = stop_count.checked_mul(3) else {
        return 0;
    };
    let raw = std::slice::from_raw_parts(raw, len);
    let stop_bytes = std::slice::from_raw_parts(stops, stop_len);
    let stops = std::slice::from_raw_parts(stop_bytes.as_ptr().cast::<[u8; 3]>(), stop_count);
    let out = std::slice::from_raw_parts_mut(out, out_len);
    ffi_guard(0, || {
        kernels::heatmap_rgba_into(raw, w, h, stops, alpha, out) as i32
    })
}

/// Native log-u8 density colormap used by the static raster path. Returns 1
/// on success and 0 on invalid dimensions, values, or pointers.
///
/// # Safety
/// `encoded` contains `w*h` readable bytes, `stops` contains `stop_count*3`
/// readable bytes, and `out` contains `w*h*4` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_density_rgba(
    encoded: *const u8,
    w: usize,
    h: usize,
    maximum: f64,
    stops: *const u8,
    stop_count: usize,
    opacity: f64,
    out: *mut u8,
) -> i32 {
    let Some(len) = w.checked_mul(h) else {
        return 0;
    };
    let Some(out_len) = len.checked_mul(4) else {
        return 0;
    };
    let Some(stop_len) = stop_count.checked_mul(3) else {
        return 0;
    };
    if len == 0 || stop_count == 0 || encoded.is_null() || stops.is_null() || out.is_null() {
        return 0;
    }
    let encoded = std::slice::from_raw_parts(encoded, len);
    let stop_bytes = std::slice::from_raw_parts(stops, stop_len);
    let stops = std::slice::from_raw_parts(stop_bytes.as_ptr().cast::<[u8; 3]>(), stop_count);
    let out = std::slice::from_raw_parts_mut(out, out_len);
    ffi_guard(0, || {
        kernels::density_rgba_into(encoded, w, h, maximum, stops, opacity, out) as i32
    })
}

/// Log-encode a density grid into the one-byte wire/texture representation.
/// Returns 1 on success and writes the original grid maximum.
///
/// # Safety
/// `grid` addresses `len` readable f32 values, `out` addresses `len` writable
/// bytes, and `out_max` addresses one writable f64.
#[no_mangle]
pub unsafe extern "C" fn xyg_density_log_u8(
    grid: *const f32,
    len: usize,
    out: *mut u8,
    out_max: *mut f64,
) -> i32 {
    if out_max.is_null() || (len > 0 && (grid.is_null() || out.is_null())) {
        return 0;
    }
    let grid = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(grid, len)
    };
    let out = if len == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out, len)
    };
    ffi_guard(0, || {
        *out_max = kernels::density_log_u8_into(grid, out);
        1
    })
}

/// Fused density scan (§5 Tier 2): one pass writing BOTH the count grid
/// (bin_2d semantics: half-open finite window) and the ascending in-window
/// row indices (range_indices semantics: inclusive window). Each output is
/// bitwise identical to its standalone kernel. Returns the index count, or
/// `usize::MAX` on invalid arguments.
///
/// # Safety
/// `x`/`y` must point to `len` readable f64s; `grid` to `w*h` writable f32s;
/// `idx` to `len` writable u32s.
#[no_mangle]
pub unsafe extern "C" fn xyg_bin_2d_indices(
    x: *const f64,
    y: *const f64,
    len: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    w: usize,
    h: usize,
    grid: *mut f32,
    idx: *mut u32,
) -> usize {
    let bad = w == 0 || h == 0 || !finite_gt(x0, x1) || !finite_gt(y0, y1);
    if bad || grid.is_null() {
        return usize::MAX;
    }
    // u32 index ceiling + unwrappable grid size — see xyg_m4_indices.
    if len > u32::MAX as usize {
        return usize::MAX;
    }
    let grid_len = match w.checked_mul(h) {
        Some(n) => n,
        None => return usize::MAX,
    };
    let (x, y, idx) = if len == 0 {
        (&[][..], &[][..], &mut [][..])
    } else {
        if x.is_null() || y.is_null() || idx.is_null() {
            return usize::MAX;
        }
        (
            std::slice::from_raw_parts(x, len),
            std::slice::from_raw_parts(y, len),
            std::slice::from_raw_parts_mut(idx, len),
        )
    };
    let grid = std::slice::from_raw_parts_mut(grid, grid_len);
    if len == 0 {
        grid.fill(0.0);
        return 0;
    }
    ffi_guard(usize::MAX, || {
        kernels::bin_2d_indices(x, y, x0, x1, y0, y1, w, h, grid, idx)
    })
}

/// Full-domain density first paint: one traversal writes the `bin_2d` grid
/// and samples implicit row ids `0..len` with the same SplitMix predicate as
/// `xyg_sample_range_indices`. Returns the exact sample length; rows are copied
/// only when `capacity` is sufficient. `usize::MAX` reports invalid arguments.
///
/// # Safety
/// `x`/`y` must point to `len` readable f64s; `grid` to `w*h` writable f32s.
/// When `capacity > 0`, `out` must point to `capacity` writable u32s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_bin_2d_sample_range(
    x: *const f64,
    y: *const f64,
    len: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    w: usize,
    h: usize,
    seed: u64,
    threshold: u64,
    grid: *mut f32,
    out: *mut u32,
    capacity: usize,
) -> usize {
    if w == 0
        || h == 0
        || !finite_gt(x0, x1)
        || !finite_gt(y0, y1)
        || grid.is_null()
        || len > u32::MAX as usize
        || capacity > len
        || (capacity > 0 && out.is_null())
    {
        return usize::MAX;
    }
    let grid_len = match w.checked_mul(h) {
        Some(value) => value,
        None => return usize::MAX,
    };
    let (x, y) = if len == 0 {
        (&[][..], &[][..])
    } else {
        if x.is_null() || y.is_null() {
            return usize::MAX;
        }
        (
            std::slice::from_raw_parts(x, len),
            std::slice::from_raw_parts(y, len),
        )
    };
    let grid = std::slice::from_raw_parts_mut(grid, grid_len);
    if len == 0 {
        grid.fill(0.0);
        return 0;
    }
    let out_rows = if capacity == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out, capacity)
    };
    ffi_guard(usize::MAX, || {
        kernels::bin_2d_sample_range(x, y, x0, x1, y0, y1, w, h, seed, threshold, grid, out_rows)
    })
}

/// Categorical counterpart to [`xyg_bin_2d_sample_range`]. Exact factorization
/// counts define the per-code sampling thresholds and avoid a recount; the
/// resulting grid and sampled rows match the standalone bin and counted
/// stratified sampler. Returns `usize::MAX` on malformed arguments/codes.
///
/// # Safety
/// `x`/`y`/`groups` must point to `len` readable values and `counts` to
/// `n_groups` readable u64 values. Remaining output contracts match
/// [`xyg_bin_2d_sample_range`].
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_bin_2d_stratified_sample_range_u8_counted(
    x: *const f64,
    y: *const f64,
    groups: *const u8,
    len: usize,
    counts: *const u64,
    n_groups: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    w: usize,
    h: usize,
    seed: u64,
    fraction: f64,
    min_count: u64,
    grid: *mut f32,
    out: *mut u32,
    capacity: usize,
) -> usize {
    if w == 0
        || h == 0
        || !finite_gt(x0, x1)
        || !finite_gt(y0, y1)
        || !fraction.is_finite()
        || fraction <= 0.0
        || grid.is_null()
        || counts.is_null()
        || n_groups == 0
        || n_groups > 256
        || len > u32::MAX as usize
        || capacity > len
        || (capacity > 0 && out.is_null())
    {
        return usize::MAX;
    }
    let grid_len = match w.checked_mul(h) {
        Some(value) => value,
        None => return usize::MAX,
    };
    let counts = std::slice::from_raw_parts(counts, n_groups);
    let (x, y, groups) = if len == 0 {
        (&[][..], &[][..], &[][..])
    } else {
        if x.is_null() || y.is_null() || groups.is_null() {
            return usize::MAX;
        }
        (
            std::slice::from_raw_parts(x, len),
            std::slice::from_raw_parts(y, len),
            std::slice::from_raw_parts(groups, len),
        )
    };
    let grid = std::slice::from_raw_parts_mut(grid, grid_len);
    ffi_guard(usize::MAX, || {
        let Some(selected) = kernels::bin_2d_stratified_sample_range_u8_counted(
            x, y, groups, counts, x0, x1, y0, y1, w, h, seed, fraction, min_count, grid,
        ) else {
            return usize::MAX;
        };
        let written = selected.len();
        if written > 0 && written <= capacity {
            std::ptr::copy_nonoverlapping(selected.as_ptr(), out, written);
        }
        written
    })
}

/// Non-decreasing + NaN-poisoned check (`next >= prev` for every pair; any
/// NaN fails its pairs) — the line/area sorted-ingest predicate (§28).
/// Returns 1 when sorted, 0 when not. Null `data` with `len > 0` returns 0
/// (callers then sort, which is always safe). Empty and single-element
/// inputs are sorted.
///
/// # Safety
/// `data` must point to `len` readable f64s (may be null only when `len == 0`).
#[no_mangle]
pub unsafe extern "C" fn xyg_is_sorted(data: *const f64, len: usize) -> i32 {
    if len < 2 {
        return 1;
    }
    if data.is_null() {
        return 0;
    }
    let data = std::slice::from_raw_parts(data, len);
    ffi_guard(0, || i32::from(kernels::is_sorted_f64(data)))
}

/// NaN-skipping min/max (autorange primitive). Returns 1 and writes the result,
/// or 0 if the input is empty / all-NaN.
///
/// # Safety
/// `data` must point to `len` readable f64s; out pointers to one writable f64.
#[no_mangle]
pub unsafe extern "C" fn xyg_min_max(
    data: *const f64,
    len: usize,
    out_min: *mut f64,
    out_max: *mut f64,
) -> i32 {
    if len == 0 {
        return 0;
    }
    if data.is_null() || out_min.is_null() || out_max.is_null() {
        return 0;
    }
    let data = std::slice::from_raw_parts(data, len);
    match ffi_guard(None, || kernels::min_max(data)) {
        Some((mn, mx)) => {
            *out_min = mn;
            *out_max = mx;
            1
        }
        None => 0,
    }
}

/// Uniform fixed-bin histogram. Returns the count of finite in-range values, or
/// `usize::MAX` on invalid arguments. `out_counts` must hold `n_bins` f64s.
///
/// # Safety
/// `data` must point to `len` readable f64s; `out_counts` to `n_bins` writable
/// f64s; `n_bins > 0` and `lo`/`hi` finite increasing.
#[no_mangle]
pub unsafe extern "C" fn xyg_histogram_uniform(
    data: *const f64,
    len: usize,
    lo: f64,
    hi: f64,
    n_bins: usize,
    density: i32,
    out_counts: *mut f64,
) -> usize {
    let bad = n_bins == 0 || !finite_gt(lo, hi);
    if bad {
        return usize::MAX;
    }
    if out_counts.is_null() {
        return usize::MAX;
    }
    let data = if len == 0 {
        &[][..]
    } else {
        if data.is_null() {
            return usize::MAX;
        }
        std::slice::from_raw_parts(data, len)
    };
    let out = std::slice::from_raw_parts_mut(out_counts, n_bins);
    let total = match ffi_guard(None, || Some(kernels::histogram_uniform(data, lo, hi, out))) {
        Some(t) => t,
        None => return usize::MAX,
    };
    if density != 0 && total > 0 {
        let bin_w = (hi - lo) / n_bins as f64;
        let denom = total as f64 * bin_w;
        for c in out.iter_mut() {
            *c /= denom;
        }
    }
    total as usize
}

/// Normalize f64 values into f32 `[0,1]`. `nan_mode=0` maps non-finite values to
/// 0.0; `nan_mode=1` maps them to f32 NaN. Returns 1 on success (including the
/// empty no-op), 0 on null arguments or a non-finite/inverted domain — the
/// former silent-void failure left the output buffer uninitialized with no way
/// to detect it.
///
/// # Safety
/// `data` must point to `len` readable f64s; `out` to `len` writable f32s.
#[no_mangle]
pub unsafe extern "C" fn xyg_normalize_f32(
    data: *const f64,
    len: usize,
    lo: f64,
    hi: f64,
    nan_mode: i32,
    out: *mut f32,
) -> i32 {
    if len == 0 {
        return 1;
    }
    if data.is_null() || out.is_null() || !finite_gt(lo, hi) {
        return 0;
    }
    let data = std::slice::from_raw_parts(data, len);
    let out = std::slice::from_raw_parts_mut(out, len);
    let nan_value = if nan_mode == 1 { f32::NAN } else { 0.0 };
    ffi_guard(0, || {
        kernels::normalize_f32_into(data, lo, hi, nan_value, out);
        1
    })
}

/// Deterministic sampling mask (§5/§17): `out[i] = 1` iff
/// `splitmix64(ids[i] + seed) <= threshold`. Bit-identical to
/// `xy.lod.hash_row_ids` thresholding, fused into one pass.
/// Returns 1 on success (including the empty no-op), 0 on null arguments.
///
/// # Safety
/// `ids` must point to `len` readable u64s; `out` to `len` writable u8s.
#[no_mangle]
pub unsafe extern "C" fn xyg_sample_mask(
    ids: *const u64,
    len: usize,
    seed: u64,
    threshold: u64,
    out: *mut u8,
) -> i32 {
    if len == 0 {
        return 1;
    }
    if ids.is_null() || out.is_null() {
        return 0;
    }
    let ids = std::slice::from_raw_parts(ids, len);
    let out = std::slice::from_raw_parts_mut(out, len);
    ffi_guard(0, || {
        kernels::sample_mask(ids, seed, threshold, out);
        1
    })
}

/// `xyg_sample_mask` over u32 row indices: each id widens to u64 in-register,
/// bit-identical to widening the full array first without that allocation.
///
/// # Safety
/// `ids` must point to `len` readable u32s; `out` to `len` writable u8s.
#[no_mangle]
pub unsafe extern "C" fn xyg_sample_mask_u32(
    ids: *const u32,
    len: usize,
    seed: u64,
    threshold: u64,
    out: *mut u8,
) -> i32 {
    if len == 0 {
        return 1;
    }
    if ids.is_null() || out.is_null() {
        return 0;
    }
    let ids = std::slice::from_raw_parts(ids, len);
    let out = std::slice::from_raw_parts_mut(out, len);
    ffi_guard(0, || {
        kernels::sample_mask(ids, seed, threshold, out);
        1
    })
}

/// Deterministically sample implicit row ids `0..size`. Returns the required
/// output length; values are written only when `capacity` is sufficient.
/// `usize::MAX` reports an invalid size/pointer combination.
///
/// # Safety
/// When `capacity > 0`, `out` must point to `capacity` writable u32 values.
#[no_mangle]
pub unsafe extern "C" fn xyg_sample_range_indices(
    size: usize,
    seed: u64,
    threshold: u64,
    out: *mut u32,
    capacity: usize,
) -> usize {
    if size > u32::MAX as usize || (capacity > 0 && out.is_null()) {
        return usize::MAX;
    }
    let output = if capacity == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out, capacity)
    };
    ffi_guard(usize::MAX, || {
        kernels::sample_range_indices_into(size, seed, threshold, output)
    })
}

/// Category-stratified sampling for implicit row ids `0..len` with compact
/// u8 group codes. Returns the required output length; ascending row indices
/// are written only when `capacity` is sufficient. `usize::MAX` reports
/// invalid arguments or a group code outside `0..n_groups`.
///
/// # Safety
/// `groups` must point to `len` readable u8 values. When `capacity > 0`,
/// `out` must point to `capacity` writable u32 values.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_stratified_sample_range_u8(
    groups: *const u8,
    len: usize,
    n_groups: usize,
    seed: u64,
    fraction: f64,
    min_count: u64,
    out: *mut u32,
    capacity: usize,
) -> usize {
    if len > u32::MAX as usize
        || n_groups == 0
        || n_groups > 256
        || !fraction.is_finite()
        || fraction <= 0.0
        || (len > 0 && groups.is_null())
        || (capacity > 0 && out.is_null())
    {
        return usize::MAX;
    }
    let groups = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(groups, len)
    };
    ffi_guard(usize::MAX, || {
        let Some(selected) =
            kernels::stratified_sample_range_u8(groups, n_groups, seed, fraction, min_count)
        else {
            return usize::MAX;
        };
        if !selected.is_empty() && selected.len() <= capacity {
            let output = std::slice::from_raw_parts_mut(out, capacity);
            output[..selected.len()].copy_from_slice(&selected);
        }
        selected.len()
    })
}

/// Count-reusing variant of [`xyg_stratified_sample_range_u8`]. `counts`
/// contains `n_groups` exact per-code counts from compact factorization,
/// avoiding a source-sized recount before sampling.
///
/// # Safety
/// `counts` must point to `n_groups` readable u64 values. Other spans follow
/// [`xyg_stratified_sample_range_u8`].
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_stratified_sample_range_u8_counted(
    groups: *const u8,
    len: usize,
    counts: *const u64,
    n_groups: usize,
    seed: u64,
    fraction: f64,
    min_count: u64,
    out: *mut u32,
    capacity: usize,
) -> usize {
    if len > u32::MAX as usize
        || n_groups == 0
        || n_groups > 256
        || !fraction.is_finite()
        || fraction <= 0.0
        || counts.is_null()
        || (len > 0 && groups.is_null())
        || (capacity > 0 && out.is_null())
    {
        return usize::MAX;
    }
    let groups = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(groups, len)
    };
    let counts = std::slice::from_raw_parts(counts, n_groups);
    ffi_guard(usize::MAX, || {
        let Some(selected) =
            kernels::stratified_sample_range_u8_counted(groups, counts, seed, fraction, min_count)
        else {
            return usize::MAX;
        };
        if !selected.is_empty() && selected.len() <= capacity {
            let output = std::slice::from_raw_parts_mut(out, capacity);
            output[..selected.len()].copy_from_slice(&selected);
        }
        selected.len()
    })
}

/// Category-stratified sampling mask (§5/§17): per-category keep fractions
/// scale as `min(1, fraction * sqrt(len / count))` and every category keeps at
/// least `min(min_count, count)` of its lowest-hash rows. Bit-identical to the
/// per-category NumPy reference in `xy.lod` (parity-tested), fused
/// into one pass instead of O(len · n_groups) rescans.
///
/// Returns 1 on success (including the empty no-op), 0 on null arguments, a
/// non-finite or non-positive `fraction`, or a group code `>= n_groups`
/// (output undefined).
///
/// # Safety
/// `ids` must point to `len` readable u64s, `groups` to `len` readable u32s,
/// `out` to `len` writable u8s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_stratified_sample_mask(
    ids: *const u64,
    groups: *const u32,
    len: usize,
    n_groups: usize,
    seed: u64,
    fraction: f64,
    min_count: u64,
    out: *mut u8,
) -> i32 {
    if len == 0 {
        return 1;
    }
    if ids.is_null()
        || groups.is_null()
        || out.is_null()
        || n_groups == 0
        || !fraction.is_finite()
        || fraction <= 0.0
    {
        return 0;
    }
    let ids = std::slice::from_raw_parts(ids, len);
    let groups = std::slice::from_raw_parts(groups, len);
    let out = std::slice::from_raw_parts_mut(out, len);
    ffi_guard(0, || {
        kernels::stratified_sample_mask(ids, groups, n_groups, seed, fraction, min_count, out)
            as i32
    })
}

/// `xyg_stratified_sample_mask` over u32 row indices, with the same in-register
/// widening contract as [`xyg_sample_mask_u32`].
///
/// # Safety
/// `ids` and `groups` must point to `len` readable u32s; `out` to `len`
/// writable u8s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_stratified_sample_mask_u32(
    ids: *const u32,
    groups: *const u32,
    len: usize,
    n_groups: usize,
    seed: u64,
    fraction: f64,
    min_count: u64,
    out: *mut u8,
) -> i32 {
    if len == 0 {
        return 1;
    }
    if ids.is_null()
        || groups.is_null()
        || out.is_null()
        || n_groups == 0
        || !fraction.is_finite()
        || fraction <= 0.0
    {
        return 0;
    }
    let ids = std::slice::from_raw_parts(ids, len);
    let groups = std::slice::from_raw_parts(groups, len);
    let out = std::slice::from_raw_parts_mut(out, len);
    ffi_guard(0, || {
        kernels::stratified_sample_mask(ids, groups, n_groups, seed, fraction, min_count, out)
            as i32
    })
}

/// Return the number of rows valid across `n_columns` f64 columns. A set bit
/// in `positive_mask` requires that column to be positive as well as finite.
/// With zero capacity this is an allocation-free parallel query; otherwise
/// ascending u32 row IDs are written when they fit. `usize::MAX` is invalid.
///
/// # Safety
/// `columns` must point to `n_columns` readable pointers, each addressing
/// `len` f64 values (a null data pointer is allowed only when `len == 0`).
/// When `capacity > 0`, `out` must address that many writable u32 values.
#[no_mangle]
pub unsafe extern "C" fn xyg_valid_indices_f64(
    columns: *const *const f64,
    n_columns: usize,
    len: usize,
    positive_mask: u64,
    out: *mut u32,
    capacity: usize,
) -> usize {
    if columns.is_null()
        || n_columns == 0
        || n_columns > 64
        || len > u32::MAX as usize
        || capacity > len
        || (capacity > 0 && out.is_null())
        || (n_columns < 64 && positive_mask >> n_columns != 0)
    {
        return usize::MAX;
    }
    let pointers = std::slice::from_raw_parts(columns, n_columns);
    let mut slices = Vec::with_capacity(n_columns);
    for &pointer in pointers {
        if len > 0 && pointer.is_null() {
            return usize::MAX;
        }
        slices.push(if len == 0 {
            &[][..]
        } else {
            std::slice::from_raw_parts(pointer, len)
        });
    }
    ffi_guard(usize::MAX, || {
        if capacity == 0 {
            kernels::valid_row_count_f64(&slices, positive_mask).unwrap_or(usize::MAX)
        } else {
            let output = std::slice::from_raw_parts_mut(out, capacity);
            if capacity == len {
                kernels::valid_row_indices_parallel_f64(&slices, positive_mask, output)
                    .unwrap_or(usize::MAX)
            } else {
                kernels::valid_row_indices_f64(&slices, positive_mask, output).unwrap_or(usize::MAX)
            }
        }
    })
}

/// Canonical row indices inside an inclusive rectangular window. Returns the
/// count written. `out` must hold `len` u32s.
///
/// # Safety
/// `x`/`y` must point to `len` readable f64s; `out` to `len` writable u32s.
#[no_mangle]
pub unsafe extern "C" fn xyg_range_indices(
    x: *const f64,
    y: *const f64,
    len: usize,
    lo_x: f64,
    hi_x: f64,
    lo_y: f64,
    hi_y: f64,
    out: *mut u32,
) -> usize {
    if !finite_ordered(lo_x, hi_x) || !finite_ordered(lo_y, hi_y) {
        return usize::MAX;
    }
    // u32 index ceiling — see xyg_m4_indices.
    if len > u32::MAX as usize {
        return usize::MAX;
    }
    if len == 0 {
        return 0;
    }
    if x.is_null() || y.is_null() || out.is_null() {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    let out = std::slice::from_raw_parts_mut(out, len);
    ffi_guard(usize::MAX, || {
        kernels::range_indices(x, y, lo_x, hi_x, lo_y, hi_y, out)
    })
}

/// Canonical row ids from `rows` that fall inside the rectangular window —
/// the row-restricted twin of `xyg_range_indices`, shaped like
/// `xyg_polygon_select`. Returns the count written; `out` must hold `n_rows`
/// u32s. Row ids must be < `len`; an out-of-range id returns the error
/// sentinel on every target, including panic-abort ones where the kernel's own
/// indexing panic could not (see `kernels::range_scan_rows`).
///
/// # Safety
/// `x`/`y` must point to `len` readable f64s, `rows` to `n_rows` readable
/// u32s, and `out` to `n_rows` writable u32s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_range_indices_rows(
    x: *const f64,
    y: *const f64,
    len: usize,
    rows: *const u32,
    n_rows: usize,
    lo_x: f64,
    hi_x: f64,
    lo_y: f64,
    hi_y: f64,
    out: *mut u32,
) -> usize {
    if !finite_ordered(lo_x, hi_x) || !finite_ordered(lo_y, hi_y) {
        return usize::MAX;
    }
    // u32 index ceiling — see xyg_m4_indices.
    if len > u32::MAX as usize {
        return usize::MAX;
    }
    if n_rows == 0 {
        return 0;
    }
    if x.is_null() || y.is_null() || rows.is_null() || out.is_null() {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    let rows = std::slice::from_raw_parts(rows, n_rows);
    let out = std::slice::from_raw_parts_mut(out, n_rows);
    ffi_guard(usize::MAX, || {
        kernels::range_indices_rows(x, y, rows, lo_x, hi_x, lo_y, hi_y, out).unwrap_or(usize::MAX)
    })
}

/// Canonical row ids from `rows` that fall inside the lasso polygon, by
/// even-odd ray casting. Returns the count written; `out` must hold
/// `n_rows` u32s. A polygon of fewer than 3 vertices selects nothing. Row ids
/// must be < `len`; an out-of-range id returns the error sentinel on every
/// target (see `kernels::range_scan_rows`).
///
/// # Safety
/// `x`/`y` must point to `len` readable f64s, `rows` to `n_rows` readable
/// u32s, `poly_x`/`poly_y` to `n_poly` readable f64s, and `out` to `n_rows`
/// writable u32s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_polygon_select(
    x: *const f64,
    y: *const f64,
    len: usize,
    rows: *const u32,
    n_rows: usize,
    poly_x: *const f64,
    poly_y: *const f64,
    n_poly: usize,
    out: *mut u32,
) -> usize {
    // u32 index ceiling — see xyg_m4_indices.
    if len > u32::MAX as usize {
        return usize::MAX;
    }
    if n_rows == 0 {
        return 0;
    }
    // Fewer than three vertices encloses nothing. Answer before building any
    // slice: `from_raw_parts` requires a non-null, aligned pointer even at
    // length zero, so a caller passing null for an empty polygon must not
    // reach the constructions below.
    if n_poly < 3 {
        return 0;
    }
    if x.is_null() || y.is_null() || rows.is_null() || out.is_null() {
        return usize::MAX;
    }
    if poly_x.is_null() || poly_y.is_null() {
        return usize::MAX;
    }
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    let rows = std::slice::from_raw_parts(rows, n_rows);
    let poly_x = std::slice::from_raw_parts(poly_x, n_poly);
    let poly_y = std::slice::from_raw_parts(poly_y, n_poly);
    let out = std::slice::from_raw_parts_mut(out, n_rows);
    ffi_guard(usize::MAX, || {
        kernels::polygon_select(x, y, rows, poly_x, poly_y, out).unwrap_or(usize::MAX)
    })
}

/// Per-point local log density for a subset. Returns 1 on success, 0 on invalid
/// grid/window arguments.
///
/// # Safety
/// `x`/`y` must point to `len` readable f64s; `out` to `len` writable f32s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_local_log_density(
    x: *const f64,
    y: *const f64,
    len: usize,
    lo_x: f64,
    hi_x: f64,
    lo_y: f64,
    hi_y: f64,
    w: usize,
    h: usize,
    out: *mut f32,
) -> i32 {
    let bad = w == 0 || h == 0 || !finite_gt(lo_x, hi_x) || !finite_gt(lo_y, hi_y);
    if bad {
        return 0;
    }
    if len == 0 {
        return 1;
    }
    if x.is_null() || y.is_null() || out.is_null() {
        return 0;
    }
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    let out = std::slice::from_raw_parts_mut(out, len);
    ffi_guard(0, || {
        kernels::local_log_density(x, y, lo_x, hi_x, lo_y, hi_y, w, h, out);
        1
    })
}

// -- tile pyramid (§5 Tier 3): opaque u64 handles, engine doc §3.3 ------------

/// Build a count pyramid over the given bounds. Returns a nonzero handle, or
/// 0 on invalid arguments. The handle must be released with xyg_pyramid_free.
/// # Safety
/// `x`/`y` must point to `len` readable f64s.
#[no_mangle]
pub unsafe extern "C" fn xyg_pyramid_build(
    x: *const f64,
    y: *const f64,
    len: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    base_dim: u32,
) -> u64 {
    if x.is_null() || y.is_null() || len == 0 {
        return 0;
    }
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    ffi_guard(0, || {
        match tiles::build(x, y, x0, x1, y0, y1, base_dim as usize) {
            Some(p) => tiles::reg_insert(p),
            None => 0,
        }
    })
}

/// Build a pyramid with mean-color planes (LOD doc §2/§4.1) for a
/// channel-bearing trace. Same handle registry and geometry as
/// `xyg_pyramid_build`; color source as in `xyg_bin_2d_mean_color`. Returns the
/// handle, or 0 on invalid arguments.
///
/// # Safety
/// `x`/`y` must point to `len` readable f64s; color source pointers must
/// satisfy `color_source_from_raw`.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_pyramid_build_color(
    x: *const f64,
    y: *const f64,
    len: usize,
    idx: *const u8,
    rgba: *const u8,
    lut: *const u8,
    lut_len: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    base_dim: u32,
) -> u64 {
    if x.is_null() || y.is_null() || len == 0 {
        return 0;
    }
    let Some(colors) = color_source_from_raw(len, idx, rgba, lut, lut_len) else {
        return 0;
    };
    let x = std::slice::from_raw_parts(x, len);
    let y = std::slice::from_raw_parts(y, len);
    ffi_guard(0, || {
        match tiles::build_color(x, y, &colors, x0, x1, y0, y1, base_dim as usize) {
            Some(p) => tiles::reg_insert(p),
            None => 0,
        }
    })
}

/// Increment a live pyramid from an appended point batch. Returns 1 when the
/// update was applied, or 0 for a stale/busy handle, invalid pointers/lengths,
/// or a finite point outside the pyramid's original domain. A rejected update
/// never partially mutates the pyramid.
///
/// # Safety
/// `x`/`y` must point to `len` readable f64s (or may be null when `len == 0`).
#[no_mangle]
pub unsafe extern "C" fn xyg_pyramid_append(
    handle: u64,
    x: *const f64,
    y: *const f64,
    len: usize,
) -> i32 {
    if len > 0 && (x.is_null() || y.is_null()) {
        return 0;
    }
    let x = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(x, len)
    };
    let y = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(y, len)
    };
    ffi_guard(0, || {
        tiles::reg_append(handle, x, y).unwrap_or(false) as i32
    })
}

/// Approximate in-window count from the finest level. 1 on success, 0 on a
/// stale/invalid handle or bad arguments.
/// # Safety
/// `out_count` must point to a writable f64.
#[no_mangle]
pub unsafe extern "C" fn xyg_pyramid_count(
    handle: u64,
    lo_x: f64,
    hi_x: f64,
    lo_y: f64,
    hi_y: f64,
    out_count: *mut f64,
) -> i32 {
    if out_count.is_null() || !finite_gt(lo_x, hi_x) || !finite_gt(lo_y, hi_y) {
        return 0;
    }
    ffi_guard(0, || {
        match tiles::reg_with(handle, |p| tiles::count(p, lo_x, hi_x, lo_y, hi_y)) {
            Some(c) => {
                *out_count = c;
                1
            }
            None => 0,
        }
    })
}

/// Compose the window into a w×h grid. Returns the level used (>= 0),
/// -1 on stale handle/bad args, -2 when the window outresolves the pyramid
/// (caller must fall back to an exact re-bin and disclose it, §28).
/// # Safety
/// `out` must point to `w * h` writable f32s.
#[no_mangle]
pub unsafe extern "C" fn xyg_pyramid_compose(
    handle: u64,
    lo_x: f64,
    hi_x: f64,
    lo_y: f64,
    hi_y: f64,
    w: usize,
    h: usize,
    max_upsample: usize,
    out: *mut f32,
) -> i32 {
    if out.is_null() || w == 0 || h == 0 || !finite_gt(lo_x, hi_x) || !finite_gt(lo_y, hi_y) {
        return -1;
    }
    let out_len = match w.checked_mul(h) {
        Some(n) => n,
        None => return -1,
    };
    let out = std::slice::from_raw_parts_mut(out, out_len);
    let max_upsample = max_upsample.max(1);
    ffi_guard(-1, || {
        match tiles::reg_with(handle, |p| {
            tiles::compose(p, lo_x, hi_x, lo_y, hi_y, w, h, max_upsample, out)
        }) {
            Some(Some(level)) => level as i32,
            Some(None) => -2,
            None => -1,
        }
    })
}

/// `xyg_pyramid_compose` plus the mean-color plane: fills `out` with the same
/// f32 counts (bit-identical) and `out_rgba` (`w*h*4`, straight-alpha RGBA8)
/// with the composed mean colors. Returns the level used (>= 0), -1 for bad
/// arguments/stale handle, or -2 when the window outresolves the pyramid OR
/// the pyramid carries no color planes — the caller re-bins exactly either way.
///
/// # Safety
/// `out` must address `w*h` writable f32s and `out_rgba` `w*h*4` writable bytes.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_pyramid_compose_color(
    handle: u64,
    lo_x: f64,
    hi_x: f64,
    lo_y: f64,
    hi_y: f64,
    w: usize,
    h: usize,
    max_upsample: usize,
    out: *mut f32,
    out_rgba: *mut u8,
) -> i32 {
    if out.is_null()
        || out_rgba.is_null()
        || w == 0
        || h == 0
        || !finite_gt(lo_x, hi_x)
        || !finite_gt(lo_y, hi_y)
    {
        return -1;
    }
    let Some(out_len) = w.checked_mul(h) else {
        return -1;
    };
    // Zero forgives a caller that forgot the knob; the count-only entry point
    // applies the same floor.
    let max_upsample = max_upsample.max(1);
    let out = std::slice::from_raw_parts_mut(out, out_len);
    let out_rgba = std::slice::from_raw_parts_mut(out_rgba, out_len * 4);
    ffi_guard(-1, || {
        match tiles::reg_with(handle, |p| {
            tiles::compose_color(p, lo_x, hi_x, lo_y, hi_y, w, h, max_upsample, out, out_rgba)
        }) {
            Some(Some(level)) => level as i32,
            Some(None) => -2,
            None => -1,
        }
    })
}

/// Release a pyramid. 1 if it existed, 0 for stale/unknown handles.
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_pyramid_free(handle: u64) -> i32 {
    ffi_guard(0, || if tiles::reg_remove(handle) { 1 } else { 0 })
}

/// Build a count pyramid by reading canonical x/y through stream handles
/// rather than host-passed arrays. Returns a nonzero handle, or 0 on a
/// stale stream, length mismatch, or invalid bounds/`base_dim`.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_pyramid_build_from_stream(
    x_handle: u64,
    y_handle: u64,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    base_dim: u32,
) -> u64 {
    ffi_guard(0, || {
        match tiles::build_from_stream(x_handle, y_handle, x0, x1, y0, y1, base_dim as usize) {
            Some(p) => tiles::reg_insert(p),
            None => 0,
        }
    })
}

/// Increment a live pyramid from the tail of two stream handles. `tail_len`
/// is the number of rows just appended. Returns 1 when applied, or 0 on a
/// stale/busy handle, stream mismatch, domain growth, or a colored pyramid.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_pyramid_append_from_stream(
    handle: u64,
    x_handle: u64,
    y_handle: u64,
    tail_len: usize,
) -> i32 {
    ffi_guard(0, || {
        tiles::reg_append_from_stream(handle, x_handle, y_handle, tail_len).unwrap_or(false) as i32
    })
}

// -- canonical stream store (engine doc §5): opaque u64 handles --------------

/// Create a stream, optionally seeded with `len` f64s. Empty input may pass
/// a null pointer. Returns a nonzero handle, or 0 on invalid pointers.
///
/// # Safety
/// For `len > 0`, `data` must address `len` readable f64s.
#[no_mangle]
pub unsafe extern "C" fn xyg_stream_new(data: *const f64, len: usize) -> u64 {
    if len > 0 && data.is_null() {
        return 0;
    }
    let data = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(data, len)
    };
    ffi_guard(0, || stream::reg_insert(stream::StreamColumn::new(data)))
}

/// Append `len` f64s. Returns 1 on success, 0 on a stale/busy handle or
/// invalid pointers. Empty appends are a successful no-op.
///
/// # Safety
/// For `len > 0`, `data` must address `len` readable f64s.
#[no_mangle]
pub unsafe extern "C" fn xyg_stream_append(handle: u64, data: *const f64, len: usize) -> i32 {
    if len > 0 && data.is_null() {
        return 0;
    }
    let data = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(data, len)
    };
    ffi_guard(0, || {
        stream::reg_with_mut(handle, |c| c.append(data)).is_some() as i32
    })
}

/// Compute (or refresh) zone maps. Returns 1 on success, 0 on a stale/busy
/// handle. Idempotent when the stream is already sealed at the live length.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_stream_seal(handle: u64) -> i32 {
    ffi_guard(0, || {
        stream::reg_with_mut(handle, |c| c.seal()).is_some() as i32
    })
}

/// Free a stream handle. Returns 1 if it existed, 0 for stale/unknown.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_stream_free(handle: u64) -> i32 {
    ffi_guard(0, || if stream::reg_remove(handle) { 1 } else { 0 })
}

/// Live length. `usize::MAX` on a stale handle.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_stream_len(handle: u64) -> usize {
    ffi_guard(usize::MAX, || {
        stream::reg_with(handle, |c| c.len()).unwrap_or(usize::MAX)
    })
}

/// Allocation capacity in values (growth slack included, §27). `usize::MAX`
/// on a stale handle.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_stream_capacity(handle: u64) -> usize {
    ffi_guard(usize::MAX, || {
        stream::reg_with(handle, |c| c.capacity()).unwrap_or(usize::MAX)
    })
}

/// Copy `len` values into caller-owned `out`. `len` must equal the live
/// length (0 is a successful no-op). Returns 1 on success, 0 otherwise.
///
/// # Safety
/// For `len > 0`, `out` must address `len` writable f64s.
#[no_mangle]
pub unsafe extern "C" fn xyg_stream_copy(handle: u64, out: *mut f64, len: usize) -> i32 {
    if len > 0 && out.is_null() {
        return 0;
    }
    ffi_guard(0, || {
        stream::reg_with(handle, |c| {
            if c.len() != len {
                return 0;
            }
            if len > 0 {
                std::slice::from_raw_parts_mut(out, len).copy_from_slice(c.values());
            }
            1
        })
        .unwrap_or(0)
    })
}

/// Borrow the live contiguous buffer. The pointer is valid until the next
/// append that reallocates, or `xyg_stream_free`. Empty streams write a
/// null pointer and length 0. Returns 1 on success, 0 on a stale handle.
///
/// # Safety
/// `out_ptr` and `out_len` must be writable.
#[no_mangle]
pub unsafe extern "C" fn xyg_stream_data(
    handle: u64,
    out_ptr: *mut *const f64,
    out_len: *mut usize,
) -> i32 {
    if out_ptr.is_null() || out_len.is_null() {
        return 0;
    }
    ffi_guard(0, || {
        stream::reg_with(handle, |c| {
            let s = c.values();
            *out_ptr = if s.is_empty() {
                std::ptr::null()
            } else {
                s.as_ptr()
            };
            *out_len = s.len();
            1
        })
        .unwrap_or(0)
    })
}

/// Copy sealed zone maps into caller-owned planes (same layout as
/// `xyg_zone_maps`). Returns the chunk count, 0 for an empty sealed stream,
/// or `usize::MAX` on a stale handle, unsealed stream, or null outputs.
///
/// # Safety
/// Each `out_*` must address `ceil(len / ZONE_CHUNK)` writable elements when
/// `len > 0`.
#[no_mangle]
pub unsafe extern "C" fn xyg_stream_zone_maps(
    handle: u64,
    out_min: *mut f64,
    out_max: *mut f64,
    out_count: *mut u64,
    out_null_count: *mut u64,
    out_sum: *mut f64,
    out_sum_sq: *mut f64,
    out_positive_min: *mut f64,
    out_positive_max: *mut f64,
) -> usize {
    ffi_guard(usize::MAX, || {
        stream::reg_with(handle, |c| {
            if !c.is_sealed() {
                return usize::MAX;
            }
            let zms = c.zones();
            if zms.is_empty() {
                return 0;
            }
            if out_min.is_null()
                || out_max.is_null()
                || out_count.is_null()
                || out_null_count.is_null()
                || out_sum.is_null()
                || out_sum_sq.is_null()
                || out_positive_min.is_null()
                || out_positive_max.is_null()
            {
                return usize::MAX;
            }
            for (i, zm) in zms.iter().enumerate() {
                *out_min.add(i) = zm.min;
                *out_max.add(i) = zm.max;
                *out_count.add(i) = zm.count;
                *out_null_count.add(i) = zm.null_count;
                *out_sum.add(i) = zm.sum;
                *out_sum_sq.add(i) = zm.sum_sq;
                *out_positive_min.add(i) = zm.positive_min;
                *out_positive_max.add(i) = zm.positive_max;
            }
            zms.len()
        })
        .unwrap_or(usize::MAX)
    })
}

// ---------------------------------------------------------------------------
// Graph display layouts / force ticks / CSR / LOD (graph-mark.md). Indices u64.
// ---------------------------------------------------------------------------

/// Descriptor for a canonical GraphForge graph projection. Every UUID buffer
/// is tightly packed `count * 16` bytes. Parent buffers are optional as a
/// pair; `parent_validity[i]` is zero or one. All input is copied into Rust.
#[repr(C)]
pub struct XygGraphProjectionDescriptor {
    pub node_ids: *const u8,
    pub node_count: u64,
    pub edge_ids: *const u8,
    pub edge_count: u64,
    pub source_ids: *const u8,
    pub target_ids: *const u8,
    pub parent_ids: *const u8,
    pub parent_validity: *const u8,
    pub directed: u32,
    pub reserved: u32,
}

unsafe fn projection_uuid_slice<'a>(
    ptr: *const u8,
    count: u64,
) -> Result<&'a [projection::Uuid], projection::ProjectionError> {
    let count =
        usize::try_from(count).map_err(|_| projection::ProjectionError::CapacityExceeded)?;
    if count == 0 {
        return Ok(&[]);
    }
    if ptr.is_null() {
        return Err(projection::ProjectionError::InvalidArgument);
    }
    // `[u8; 16]` has alignment one, so any readable packed Arrow fixed-size
    // binary buffer is valid without host-side copying or alignment repair.
    Ok(std::slice::from_raw_parts(
        ptr.cast::<projection::Uuid>(),
        count,
    ))
}

/// Create a Rust-owned canonical projection handle. Status codes are stable:
/// 0 success; -1 bad arguments; -2 capacity overflow; -3 nil/malformed UUID;
/// -4 duplicate node; -5 duplicate edge; -6 missing endpoint; -7 stale
/// handle; -8 undersized output buffer.
///
/// # Safety
/// `descriptor` and `out_handle` must be valid for reads/writes. Every
/// non-empty descriptor buffer must cover its declared count (UUID buffers
/// contain `count * 16` bytes); optional parent pointers are both null or both
/// valid for `node_count` entries.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_projection_create(
    descriptor: *const XygGraphProjectionDescriptor,
    out_handle: *mut u64,
) -> i32 {
    if descriptor.is_null() || out_handle.is_null() {
        return projection::ProjectionError::InvalidArgument as i32;
    }
    *out_handle = 0;
    ffi_guard(projection::ProjectionError::InvalidArgument as i32, || {
        let descriptor = &*descriptor;
        if descriptor.reserved != 0 || descriptor.directed > 1 {
            return projection::ProjectionError::InvalidArgument as i32;
        }
        let node_ids = match projection_uuid_slice(descriptor.node_ids, descriptor.node_count) {
            Ok(value) => value,
            Err(error) => return error as i32,
        };
        let edge_ids = match projection_uuid_slice(descriptor.edge_ids, descriptor.edge_count) {
            Ok(value) => value,
            Err(error) => return error as i32,
        };
        let source_ids = match projection_uuid_slice(descriptor.source_ids, descriptor.edge_count) {
            Ok(value) => value,
            Err(error) => return error as i32,
        };
        let target_ids = match projection_uuid_slice(descriptor.target_ids, descriptor.edge_count) {
            Ok(value) => value,
            Err(error) => return error as i32,
        };
        let parents = if descriptor.parent_ids.is_null() && descriptor.parent_validity.is_null() {
            None
        } else if descriptor.parent_ids.is_null() || descriptor.parent_validity.is_null() {
            return projection::ProjectionError::InvalidArgument as i32;
        } else {
            let ids = match projection_uuid_slice(descriptor.parent_ids, descriptor.node_count) {
                Ok(value) => value,
                Err(error) => return error as i32,
            };
            let count = match usize::try_from(descriptor.node_count) {
                Ok(value) => value,
                Err(_) => return projection::ProjectionError::CapacityExceeded as i32,
            };
            Some((
                ids,
                std::slice::from_raw_parts(descriptor.parent_validity, count),
            ))
        };
        match projection::GraphProjection::new(
            node_ids,
            edge_ids,
            source_ids,
            target_ids,
            parents,
            descriptor.directed == 1,
        ) {
            Ok(value) => {
                *out_handle = projection::reg_insert(value);
                0
            }
            Err(error) => error as i32,
        }
    })
}

/// Read projection counts and directedness.
///
/// # Safety
/// All output pointers must be non-null and valid for one value.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_projection_counts(
    handle: u64,
    out_nodes: *mut u64,
    out_edges: *mut u64,
    out_directed: *mut u32,
) -> i32 {
    if out_nodes.is_null() || out_edges.is_null() || out_directed.is_null() {
        return projection::ProjectionError::InvalidArgument as i32;
    }
    ffi_guard(projection::ProjectionError::InvalidArgument as i32, || {
        projection::reg_with(handle, |value| {
            *out_nodes = value.node_ids().len() as u64;
            *out_edges = value.edge_ids().len() as u64;
            *out_directed = u32::from(value.directed());
        })
        .map_or(projection::ProjectionError::StaleHandle as i32, |_| 0)
    })
}

unsafe fn projection_copy_ids(handle: u64, output: *mut u8, capacity: u64, nodes: bool) -> i32 {
    ffi_guard(projection::ProjectionError::InvalidArgument as i32, || {
        projection::reg_with(handle, |value| {
            let ids = if nodes {
                value.node_ids()
            } else {
                value.edge_ids()
            };
            if capacity < ids.len() as u64 {
                return projection::ProjectionError::OutputCapacity as i32;
            }
            if !ids.is_empty() && output.is_null() {
                return projection::ProjectionError::InvalidArgument as i32;
            }
            if !ids.is_empty() {
                std::ptr::copy_nonoverlapping(ids.as_ptr().cast::<u8>(), output, ids.len() * 16);
            }
            0
        })
        .unwrap_or(projection::ProjectionError::StaleHandle as i32)
    })
}

/// Copy canonical node UUID bytes.
///
/// # Safety
/// For a non-empty projection, `output` must cover `capacity * 16` bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_projection_copy_node_ids(
    handle: u64,
    output: *mut u8,
    capacity: u64,
) -> i32 {
    projection_copy_ids(handle, output, capacity, true)
}

/// Copy canonical edge UUID bytes.
///
/// # Safety
/// For a non-empty projection, `output` must cover `capacity * 16` bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_projection_copy_edge_ids(
    handle: u64,
    output: *mut u8,
    capacity: u64,
) -> i32 {
    projection_copy_ids(handle, output, capacity, false)
}

/// Copy dense source and target indices.
///
/// # Safety
/// For non-empty edges, both output pointers must each cover `capacity`
/// `u64` values.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_projection_copy_endpoints(
    handle: u64,
    out_sources: *mut u64,
    out_targets: *mut u64,
    capacity: u64,
) -> i32 {
    ffi_guard(projection::ProjectionError::InvalidArgument as i32, || {
        projection::reg_with(handle, |value| {
            let len = value.sources().len();
            if capacity < len as u64 {
                return projection::ProjectionError::OutputCapacity as i32;
            }
            if len != 0 && (out_sources.is_null() || out_targets.is_null()) {
                return projection::ProjectionError::InvalidArgument as i32;
            }
            if len != 0 {
                std::ptr::copy_nonoverlapping(value.sources().as_ptr(), out_sources, len);
                std::ptr::copy_nonoverlapping(value.targets().as_ptr(), out_targets, len);
            }
            0
        })
        .unwrap_or(projection::ProjectionError::StaleHandle as i32)
    })
}

/// Copy dense parent indices and their byte validity plane.
///
/// # Safety
/// For non-empty nodes, `out_parents` must cover `capacity` `u64` values and
/// `out_validity` must cover `capacity` bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_projection_copy_parents(
    handle: u64,
    out_parents: *mut u64,
    out_validity: *mut u8,
    capacity: u64,
) -> i32 {
    ffi_guard(projection::ProjectionError::InvalidArgument as i32, || {
        projection::reg_with(handle, |value| {
            let len = value.parents().len();
            if capacity < len as u64 {
                return projection::ProjectionError::OutputCapacity as i32;
            }
            if len != 0 && (out_parents.is_null() || out_validity.is_null()) {
                return projection::ProjectionError::InvalidArgument as i32;
            }
            if len != 0 {
                std::ptr::copy_nonoverlapping(value.parents().as_ptr(), out_parents, len);
                std::ptr::copy_nonoverlapping(value.parent_validity().as_ptr(), out_validity, len);
            }
            0
        })
        .unwrap_or(projection::ProjectionError::StaleHandle as i32)
    })
}

/// Destroy a projection handle.
///
/// # Safety
/// The caller must serialize use of this handle so no other call uses it after
/// destruction. Stale handles are rejected without dereferencing host memory.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_projection_destroy(handle: u64) -> i32 {
    ffi_guard(projection::ProjectionError::InvalidArgument as i32, || {
        if projection::reg_remove(handle) {
            0
        } else {
            projection::ProjectionError::StaleHandle as i32
        }
    })
}

/// One-shot graph layout. `layout` is LAYOUT_* from `graph`. Returns 0 on
/// success, -1 on invalid args. `preset` requires `in_x`/`in_y`; others may
/// pass null. `roots` is optional for breadthfirst/radial (null → default).
///
/// # Safety
/// Non-empty edge arrays and outputs must be valid for the given lengths.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_layout(
    layout: u32,
    n_nodes: u64,
    n_edges: u64,
    sources: *const u64,
    targets: *const u64,
    in_x: *const f64,
    in_y: *const f64,
    roots: *const u64,
    n_roots: u64,
    seed: u64,
    out_x: *mut f64,
    out_y: *mut f64,
) -> i32 {
    if n_nodes > (usize::MAX as u64) || n_edges > (usize::MAX as u64) {
        return -1;
    }
    let n = n_nodes as usize;
    let e = n_edges as usize;
    if out_x.is_null() || out_y.is_null() {
        return -1;
    }
    let out_x = std::slice::from_raw_parts_mut(out_x, n);
    let out_y = std::slice::from_raw_parts_mut(out_y, n);
    let sources = if e == 0 {
        &[][..]
    } else if sources.is_null() {
        return -1;
    } else {
        std::slice::from_raw_parts(sources, e)
    };
    let targets = if e == 0 {
        &[][..]
    } else if targets.is_null() {
        return -1;
    } else {
        std::slice::from_raw_parts(targets, e)
    };
    ffi_guard(-1, || {
        let ok = match layout {
            graph::LAYOUT_PRESET => {
                if in_x.is_null() || in_y.is_null() {
                    return -1;
                }
                let ix = std::slice::from_raw_parts(in_x, n);
                let iy = std::slice::from_raw_parts(in_y, n);
                graph::layout_preset(ix, iy, out_x, out_y)
            }
            graph::LAYOUT_GRID => {
                graph::layout_grid(n, out_x, out_y);
                true
            }
            graph::LAYOUT_CIRCLE => {
                graph::layout_circle(n, out_x, out_y);
                true
            }
            graph::LAYOUT_FORCE
            | graph::LAYOUT_BARNES_HUT
            | graph::LAYOUT_SPRING
            | graph::LAYOUT_FORCEATLAS2
            | graph::LAYOUT_KAMADA_KAWAI
            | graph::LAYOUT_YIFANHU
            | graph::LAYOUT_LINLOG
            | graph::LAYOUT_STRESS => graph::layout_force_family(
                layout, n_nodes, sources, targets, seed, 300, out_x, out_y,
            ),
            graph::LAYOUT_BREADTHFIRST => {
                let roots_slice = if n_roots == 0 || roots.is_null() {
                    &[][..]
                } else {
                    std::slice::from_raw_parts(roots, n_roots as usize)
                };
                graph::layout_breadthfirst(n_nodes, sources, targets, roots_slice, out_x, out_y)
            }
            graph::LAYOUT_HIERARCHICAL => {
                let roots_slice = if n_roots == 0 || roots.is_null() {
                    &[][..]
                } else {
                    std::slice::from_raw_parts(roots, n_roots as usize)
                };
                graph::layout_hierarchical(n_nodes, sources, targets, roots_slice, out_x, out_y)
            }
            graph::LAYOUT_AUTO => graph::layout_auto(n_nodes, sources, targets, out_x, out_y, seed),
            graph::LAYOUT_RADIAL => {
                let root = if n_roots == 0 || roots.is_null() {
                    0
                } else {
                    *roots
                };
                graph::layout_radial(n_nodes, sources, targets, root, out_x, out_y)
            }
            graph::LAYOUT_CONCENTRIC => {
                let mut deg = vec![0u64; n];
                for (&s, &t) in sources.iter().zip(targets.iter()) {
                    if (s as usize) < n {
                        deg[s as usize] += 1;
                    }
                    if (t as usize) < n {
                        deg[t as usize] += 1;
                    }
                }
                graph::layout_concentric(n, &deg, out_x, out_y)
            }
            _ => return -1,
        };
        if ok {
            0
        } else {
            -1
        }
    })
}

/// Create a progressive force-layout handle. Returns 0 on failure; else a
/// non-zero handle. Optional `in_x`/`in_y` seed positions.
/// `algorithm` is a `graph::LAYOUT_*` force-family id (`LAYOUT_FORCE` default).
/// Kamada–Kawai / stress with `n > STRESS_LAYOUT_MAX_N` fall back to FR.
///
/// # Safety
/// Edge arrays must be valid for `n_edges` when non-zero.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_force_create(
    n_nodes: u64,
    n_edges: u64,
    sources: *const u64,
    targets: *const u64,
    in_x: *const f64,
    in_y: *const f64,
    seed: u64,
    algorithm: u32,
    out_handle: *mut u64,
) -> i32 {
    if out_handle.is_null() || n_edges > (usize::MAX as u64) {
        return -1;
    }
    let e = n_edges as usize;
    let sources = if e == 0 {
        &[][..]
    } else if sources.is_null() {
        return -1;
    } else {
        std::slice::from_raw_parts(sources, e)
    };
    let targets = if e == 0 {
        &[][..]
    } else if targets.is_null() {
        return -1;
    } else {
        std::slice::from_raw_parts(targets, e)
    };
    let init = if in_x.is_null() || in_y.is_null() {
        None
    } else {
        let n = n_nodes as usize;
        Some((
            std::slice::from_raw_parts(in_x, n),
            std::slice::from_raw_parts(in_y, n),
        ))
    };
    ffi_guard(-1, || {
        let handle = match init {
            Some((ix, iy)) => graph::force_create(
                n_nodes,
                sources,
                targets,
                Some(ix),
                Some(iy),
                seed,
                algorithm,
            ),
            None => graph::force_create(n_nodes, sources, targets, None, None, seed, algorithm),
        };
        match handle {
            Some(h) => {
                *out_handle = h;
                0
            }
            None => -1,
        }
    })
}

/// Advance a force handle by `steps` and write positions. Returns 0 on
/// success and writes remaining alpha to `out_alpha`; -1 on bad handle/args.
///
/// # Safety
/// Outputs must hold `n_nodes` f64s matching the create call.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_force_tick(
    handle: u64,
    n_nodes: u64,
    steps: u32,
    out_x: *mut f64,
    out_y: *mut f64,
    out_alpha: *mut f64,
) -> i32 {
    if out_x.is_null() || out_y.is_null() || out_alpha.is_null() {
        return -1;
    }
    let n = n_nodes as usize;
    let out_x = std::slice::from_raw_parts_mut(out_x, n);
    let out_y = std::slice::from_raw_parts_mut(out_y, n);
    ffi_guard(-1, || {
        match graph::force_tick(handle, steps, out_x, out_y) {
            Some(alpha) => {
                *out_alpha = alpha;
                0
            }
            None => -1,
        }
    })
}

/// Destroy a force handle. Returns 1 if it existed, 0 otherwise.
///
/// # Safety
/// `handle` is an opaque id from `xyg_graph_force_create`; any other value is a
/// no-op. The function is `unsafe` to match the rest of the C ABI surface.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_force_destroy(handle: u64) -> i32 {
    ffi_guard(0, || if graph::force_destroy(handle) { 1 } else { 0 })
}

/// Build undirected/directed CSR. Caller sizes `out_offsets` to n_nodes+1 and
/// `out_neighbors` to the directed edge count (or 2*|E| undirected upper bound);
/// on success writes actual neighbor count to `out_neighbor_len`.
///
/// # Safety
/// All non-null buffers must match the documented lengths.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_build_csr(
    n_nodes: u64,
    n_edges: u64,
    sources: *const u64,
    targets: *const u64,
    directed: i32,
    out_offsets: *mut u64,
    out_neighbors: *mut u64,
    neighbors_cap: u64,
    out_neighbor_len: *mut u64,
) -> i32 {
    if out_offsets.is_null() || out_neighbors.is_null() || out_neighbor_len.is_null() {
        return -1;
    }
    let e = n_edges as usize;
    let sources = if e == 0 {
        &[][..]
    } else if sources.is_null() {
        return -1;
    } else {
        std::slice::from_raw_parts(sources, e)
    };
    let targets = if e == 0 {
        &[][..]
    } else if targets.is_null() {
        return -1;
    } else {
        std::slice::from_raw_parts(targets, e)
    };
    ffi_guard(-1, || {
        let Some((offsets, neighbors)) = graph::build_csr(n_nodes, sources, targets, directed != 0)
        else {
            return -1;
        };
        if neighbors.len() as u64 > neighbors_cap {
            return -1;
        }
        let off = std::slice::from_raw_parts_mut(out_offsets, n_nodes as usize + 1);
        off.copy_from_slice(&offsets);
        let nei = std::slice::from_raw_parts_mut(out_neighbors, neighbors.len());
        nei.copy_from_slice(&neighbors);
        *out_neighbor_len = neighbors.len() as u64;
        0
    })
}

/// LOD decision helper. Writes tier (0 direct / 1 edge sample / 2 aggregate)
/// and edges_kept. Returns 0.
///
/// # Safety
/// `out_tier` and `out_edges_kept` must be non-null writable u32/u64 slots.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_lod_decision(
    n_nodes: u64,
    n_edges: u64,
    node_budget: u64,
    edge_budget: u64,
    out_tier: *mut u32,
    out_edges_kept: *mut u64,
) -> i32 {
    if out_tier.is_null() || out_edges_kept.is_null() {
        return -1;
    }
    ffi_guard(-1, || {
        let d = graph::lod_decide(n_nodes, n_edges, node_budget, edge_budget);
        *out_tier = d.tier as u32;
        *out_edges_kept = d.edges_kept;
        0
    })
}

/// Cluster LOD aggregate: grid/hash centroids when `|V|` exceeds `node_budget`,
/// plus a recorded §28 decision (`out_tier` / `out_edges_kept`). Returns 0 on
/// success, writing `out_count` centroids and one member cluster id per node.
///
/// # Safety
/// `x`/`y` and `out_member_of` must hold `n_nodes` values when non-empty.
/// Centroid outputs must hold `n_nodes` values under budget, otherwise
/// `node_budget` values. `out_tier` / `out_edges_kept` must be non-null.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_cluster_aggregate(
    n_nodes: u64,
    n_edges: u64,
    x: *const f64,
    y: *const f64,
    node_budget: u64,
    edge_budget: u64,
    out_x: *mut f64,
    out_y: *mut f64,
    out_count: *mut u64,
    out_member_of: *mut u64,
    out_tier: *mut u32,
    out_edges_kept: *mut u64,
) -> i32 {
    if n_nodes > (usize::MAX as u64)
        || out_count.is_null()
        || out_tier.is_null()
        || out_edges_kept.is_null()
    {
        return -1;
    }
    let n = n_nodes as usize;
    if n > 0 && (x.is_null() || y.is_null() || out_member_of.is_null()) {
        return -1;
    }
    let out_cap_u64 = if n_nodes <= node_budget {
        n_nodes
    } else {
        node_budget
    };
    let Ok(out_cap) = usize::try_from(out_cap_u64) else {
        return -1;
    };
    if out_cap > 0 && (out_x.is_null() || out_y.is_null()) {
        return -1;
    }

    let x = if n == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(x, n)
    };
    let y = if n == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(y, n)
    };
    let out_member_of = if n == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_member_of, n)
    };
    let out_x = if out_cap == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_x, out_cap)
    };
    let out_y = if out_cap == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_y, out_cap)
    };

    ffi_guard(-1, || {
        match graph::cluster_aggregate(
            n_nodes,
            n_edges,
            x,
            y,
            node_budget,
            edge_budget,
            out_x,
            out_y,
            &mut *out_count,
            out_member_of,
        ) {
            Some(d) => {
                *out_tier = d.tier as u32;
                *out_edges_kept = d.edges_kept;
                0
            }
            None => -1,
        }
    })
}

/// Build a perceptually bounded render graph (§1 / graph-mark.md).
///
/// Writes reduced node centroids, per-source `out_member_of`, and edges in
/// **cluster index space** (multi-edges collapsed), all within
/// `node_budget` / `edge_budget`. Optional viewport when `viewport_enabled != 0`.
/// Records §28 tier into `out_tier` / `out_edges_kept`. Returns 0 on success.
///
/// # Safety
/// Non-empty buffers must match documented lengths; edge outputs need capacity
/// `edge_budget`; node outputs need `min(n_nodes, node_budget)` (or active
/// count under viewport — callers should size to `node_budget`).
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_build_render(
    n_nodes: u64,
    n_edges: u64,
    x: *const f64,
    y: *const f64,
    sources: *const u64,
    targets: *const u64,
    node_budget: u64,
    edge_budget: u64,
    viewport_enabled: i32,
    vp_x0: f64,
    vp_y0: f64,
    vp_x1: f64,
    vp_y1: f64,
    out_node_x: *mut f64,
    out_node_y: *mut f64,
    out_member_of: *mut u64,
    out_edge_sources: *mut u64,
    out_edge_targets: *mut u64,
    out_n_nodes: *mut u64,
    out_n_edges: *mut u64,
    out_tier: *mut u32,
    out_edges_kept: *mut u64,
) -> i32 {
    if n_nodes > (usize::MAX as u64)
        || n_edges > (usize::MAX as u64)
        || out_n_nodes.is_null()
        || out_n_edges.is_null()
        || out_tier.is_null()
        || out_edges_kept.is_null()
    {
        return -1;
    }
    let n = n_nodes as usize;
    let e = n_edges as usize;
    if n > 0 && (x.is_null() || y.is_null() || out_member_of.is_null()) {
        return -1;
    }
    let node_budget = node_budget.max(1);
    let edge_budget = edge_budget.max(1);
    let Ok(out_node_cap) = usize::try_from(node_budget.min(n_nodes.max(1))) else {
        return -1;
    };
    let Ok(out_edge_cap) = usize::try_from(edge_budget) else {
        return -1;
    };
    if out_node_cap > 0 && (out_node_x.is_null() || out_node_y.is_null()) {
        return -1;
    }
    if out_edge_cap > 0 && (out_edge_sources.is_null() || out_edge_targets.is_null()) {
        return -1;
    }

    let x = if n == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(x, n)
    };
    let y = if n == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(y, n)
    };
    let sources = if e == 0 {
        &[][..]
    } else if sources.is_null() {
        return -1;
    } else {
        std::slice::from_raw_parts(sources, e)
    };
    let targets = if e == 0 {
        &[][..]
    } else if targets.is_null() {
        return -1;
    } else {
        std::slice::from_raw_parts(targets, e)
    };
    let out_member_of = if n == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_member_of, n)
    };
    let out_node_x = if out_node_cap == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_node_x, out_node_cap)
    };
    let out_node_y = if out_node_cap == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_node_y, out_node_cap)
    };
    let out_edge_sources = if out_edge_cap == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_edge_sources, out_edge_cap)
    };
    let out_edge_targets = if out_edge_cap == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_edge_targets, out_edge_cap)
    };
    let viewport = if viewport_enabled != 0 {
        Some(graph::Viewport {
            x0: vp_x0,
            y0: vp_y0,
            x1: vp_x1,
            y1: vp_y1,
        })
    } else {
        None
    };

    ffi_guard(-1, || {
        match graph::build_render(
            n_nodes,
            x,
            y,
            sources,
            targets,
            node_budget,
            edge_budget,
            viewport,
            out_node_x,
            out_node_y,
            out_member_of,
            out_edge_sources,
            out_edge_targets,
            &mut *out_n_nodes,
            &mut *out_n_edges,
        ) {
            Some(d) => {
                *out_tier = d.tier as u32;
                *out_edges_kept = d.edges_kept;
                0
            }
            None => -1,
        }
    })
}

/// Sample edge indices into `out_indices` (capacity `budget`). Returns count.
///
/// # Safety
/// `out_indices` must be non-null and writable for `budget` `u64`s when
/// `budget > 0`.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_sample_edges(
    n_edges: u64,
    budget: u64,
    out_indices: *mut u64,
) -> u64 {
    if out_indices.is_null() || budget == 0 {
        return 0;
    }
    let out = std::slice::from_raw_parts_mut(out_indices, budget as usize);
    ffi_guard(0, || graph::sample_edges(n_edges, budget, out))
}

// ---------------------------------------------------------------------------
// Sankey layout (sankey.rs). Dense u64 node indices; hosts own name resolution.
// ---------------------------------------------------------------------------

/// Place a Sankey diagram in a unit box.
///
/// Inputs (`sources`/`targets`/`values`) each have length `n_links`. Outputs:
/// - `out_x0`/`out_y0`/`out_x1`/`out_y1`/`out_layer`/`out_value`: length `n_nodes`
/// - `out_source_y0`/`out_source_y1`/`out_target_y0`/`out_target_y1`: length `n_links`
/// - `out_layers`: single u32, number of columns
/// - `out_err_nodes` (capacity `n_nodes`) + `out_err_n`: on cycle (`-2`) the
///   cyclic node indices; on padding (`-3`) `[layer, count]` with `*out_err_n=2`
///
/// `align`: 0=justify, 1=left, 2=right, 3=center.
///
/// Returns `0` on success, `-1` invalid args, `-2` cycle, `-3` padding refusal.
///
/// # Safety
/// Non-empty input/output pointers must be valid for the documented lengths.
#[no_mangle]
pub unsafe extern "C" fn xyg_sankey_layout(
    n_nodes: u64,
    n_links: u64,
    sources: *const u64,
    targets: *const u64,
    values: *const f64,
    node_width: f64,
    node_padding: f64,
    align: u32,
    iterations: u32,
    out_x0: *mut f64,
    out_y0: *mut f64,
    out_x1: *mut f64,
    out_y1: *mut f64,
    out_layer: *mut u32,
    out_value: *mut f64,
    out_source_y0: *mut f64,
    out_source_y1: *mut f64,
    out_target_y0: *mut f64,
    out_target_y1: *mut f64,
    out_layers: *mut u32,
    out_err_nodes: *mut u64,
    out_err_n: *mut u64,
) -> i32 {
    if n_nodes > (usize::MAX as u64) || n_links > (usize::MAX as u64) {
        return -1;
    }
    let n = n_nodes as usize;
    let e = n_links as usize;
    if n == 0
        || e == 0
        || sources.is_null()
        || targets.is_null()
        || values.is_null()
        || out_x0.is_null()
        || out_y0.is_null()
        || out_x1.is_null()
        || out_y1.is_null()
        || out_layer.is_null()
        || out_value.is_null()
        || out_source_y0.is_null()
        || out_source_y1.is_null()
        || out_target_y0.is_null()
        || out_target_y1.is_null()
        || out_layers.is_null()
        || out_err_nodes.is_null()
        || out_err_n.is_null()
    {
        return -1;
    }
    let sources = std::slice::from_raw_parts(sources, e);
    let targets = std::slice::from_raw_parts(targets, e);
    let values = std::slice::from_raw_parts(values, e);
    let out_x0 = std::slice::from_raw_parts_mut(out_x0, n);
    let out_y0 = std::slice::from_raw_parts_mut(out_y0, n);
    let out_x1 = std::slice::from_raw_parts_mut(out_x1, n);
    let out_y1 = std::slice::from_raw_parts_mut(out_y1, n);
    let out_layer = std::slice::from_raw_parts_mut(out_layer, n);
    let out_value = std::slice::from_raw_parts_mut(out_value, n);
    let out_source_y0 = std::slice::from_raw_parts_mut(out_source_y0, e);
    let out_source_y1 = std::slice::from_raw_parts_mut(out_source_y1, e);
    let out_target_y0 = std::slice::from_raw_parts_mut(out_target_y0, e);
    let out_target_y1 = std::slice::from_raw_parts_mut(out_target_y1, e);
    let out_err_nodes = std::slice::from_raw_parts_mut(out_err_nodes, n);
    ffi_guard(-1, || {
        match sankey::compute_layout(
            n,
            sources,
            targets,
            values,
            node_width,
            node_padding,
            align,
            iterations,
        ) {
            Ok(layout) => {
                out_x0.copy_from_slice(&layout.x0);
                out_y0.copy_from_slice(&layout.y0);
                out_x1.copy_from_slice(&layout.x1);
                out_y1.copy_from_slice(&layout.y1);
                out_layer.copy_from_slice(&layout.layer);
                out_value.copy_from_slice(&layout.value);
                out_source_y0.copy_from_slice(&layout.source_y0);
                out_source_y1.copy_from_slice(&layout.source_y1);
                out_target_y0.copy_from_slice(&layout.target_y0);
                out_target_y1.copy_from_slice(&layout.target_y1);
                *out_layers = layout.layers;
                *out_err_n = 0;
                0
            }
            Err(sankey::LayoutError::Invalid) => -1,
            Err(sankey::LayoutError::Cycle(ids)) => {
                let count = ids.len().min(n);
                out_err_nodes[..count].copy_from_slice(&ids[..count]);
                *out_err_n = count as u64;
                -2
            }
            Err(sankey::LayoutError::Padding { layer, count }) => {
                if n >= 2 {
                    out_err_nodes[0] = u64::from(layer);
                    out_err_nodes[1] = u64::from(count);
                    *out_err_n = 2;
                } else {
                    *out_err_n = 0;
                }
                -3
            }
        }
    })
}

// ---------------------------------------------------------------------------
// View LOD plan + distribution stats (lod_plan.rs / stats.rs).
// Hosts validate inputs and assemble string mode names; Rust owns the math.
// ---------------------------------------------------------------------------

/// Hysteresis-guarded drill decision (§5). Writes `1`/`0` into `out_exact`.
/// Returns 1 on success, 0 when budget/exit_factor are non-finite or ≤ 0.
///
/// # Safety
/// `out_exact` must be writable.
#[no_mangle]
pub unsafe extern "C" fn xyg_drill_decision(
    visible: u64,
    budget: f64,
    in_drill: i32,
    exit_factor: f64,
    out_exact: *mut i32,
) -> i32 {
    if out_exact.is_null() {
        return 0;
    }
    match ffi_guard(None, || {
        lod_plan::drill_decision(visible, budget, in_drill != 0, exit_factor)
    }) {
        Some(exact) => {
            *out_exact = if exact { 1 } else { 0 };
            1
        }
        None => 0,
    }
}

/// Screen-bounded aggregation grid (§5/§28). Returns 1 on success, 0 on bad policy.
///
/// # Safety
/// `out_w`/`out_h` must be writable.
#[no_mangle]
pub unsafe extern "C" fn xyg_lod_grid_shape(
    px_w: i32,
    px_h: i32,
    visible: u64,
    target_per_cell: f64,
    out_w: *mut i32,
    out_h: *mut i32,
) -> i32 {
    if out_w.is_null() || out_h.is_null() {
        return 0;
    }
    match ffi_guard(None, || {
        lod_plan::grid_shape(px_w, px_h, visible, target_per_cell)
    }) {
        Some((w, h)) => {
            *out_w = w;
            *out_h = h;
            1
        }
        None => 0,
    }
}

/// Chart-agnostic numeric LOD plan for a viewport. Mode is `MODE_DIRECT` (0)
/// or `MODE_AGGREGATE` (1); hosts map those to wire strings.
///
/// Returns 1 on success, 0 on invalid policy / null outs.
///
/// # Safety
/// All out pointers must be writable.
#[no_mangle]
pub unsafe extern "C" fn xyg_lod_plan(
    visible: u64,
    budget: f64,
    in_drill: i32,
    exit_factor: f64,
    px_w: i32,
    px_h: i32,
    target_per_cell: f64,
    out_exact: *mut i32,
    out_mode: *mut u32,
    out_grid_w: *mut i32,
    out_grid_h: *mut i32,
) -> i32 {
    if out_exact.is_null() || out_mode.is_null() || out_grid_w.is_null() || out_grid_h.is_null() {
        return 0;
    }
    match ffi_guard(None, || {
        lod_plan::plan(
            visible,
            budget,
            in_drill != 0,
            exit_factor,
            px_w,
            px_h,
            target_per_cell,
        )
    }) {
        Some(plan) => {
            *out_exact = if plan.exact { 1 } else { 0 };
            *out_mode = plan.mode;
            *out_grid_w = plan.grid_w;
            *out_grid_h = plan.grid_h;
            1
        }
        None => 0,
    }
}

/// Linear (NumPy-default) quantiles for probabilities in `[0, 1]`.
///
/// Writes `n_probs` f64s into `out`. Returns the finite sample count used, or
/// `usize::MAX` on invalid arguments (null outs, empty probs, bad probabilities).
/// Empty finite input still succeeds: every out slot is NaN and the return is 0.
///
/// # Safety
/// `data`/`probs`/`out` must be valid for the given lengths when non-empty.
#[no_mangle]
pub unsafe extern "C" fn xyg_quantiles(
    data: *const f64,
    len: usize,
    probs: *const f64,
    n_probs: usize,
    out: *mut f64,
) -> usize {
    if n_probs == 0 || out.is_null() || probs.is_null() {
        return usize::MAX;
    }
    let data = if len == 0 {
        &[][..]
    } else {
        if data.is_null() {
            return usize::MAX;
        }
        std::slice::from_raw_parts(data, len)
    };
    let probs = std::slice::from_raw_parts(probs, n_probs);
    let out = std::slice::from_raw_parts_mut(out, n_probs);
    match ffi_guard(None, || stats::quantiles(data, probs)) {
        Some(values) => {
            out.copy_from_slice(&values);
            data.iter().filter(|v| v.is_finite()).count()
        }
        None => usize::MAX,
    }
}

/// Tukey box-plot stats: `[q1, median, q3, whisker_low, whisker_high]` plus
/// outliers. Returns 1 on success (including empty → NaN stats / 0 outliers),
/// 0 on null/undersized buffers.
///
/// # Safety
/// `out_stats` must hold 5 f64s; `out_outliers` holds `outliers_cap` f64s when
/// non-null; `out_n_outliers` is writable.
#[no_mangle]
pub unsafe extern "C" fn xyg_box_stats(
    data: *const f64,
    len: usize,
    out_stats: *mut f64,
    out_outliers: *mut f64,
    outliers_cap: usize,
    out_n_outliers: *mut usize,
) -> i32 {
    if out_stats.is_null() || out_n_outliers.is_null() {
        return 0;
    }
    if outliers_cap > 0 && out_outliers.is_null() {
        return 0;
    }
    let data = if len == 0 {
        &[][..]
    } else {
        if data.is_null() {
            return 0;
        }
        std::slice::from_raw_parts(data, len)
    };
    let stats = ffi_guard(
        stats::BoxStats {
            q1: f64::NAN,
            median: f64::NAN,
            q3: f64::NAN,
            low: f64::NAN,
            high: f64::NAN,
            outliers: Vec::new(),
        },
        || stats::box_stats(data),
    );
    let out_stats = std::slice::from_raw_parts_mut(out_stats, 5);
    out_stats[0] = stats.q1;
    out_stats[1] = stats.median;
    out_stats[2] = stats.q3;
    out_stats[3] = stats.low;
    out_stats[4] = stats.high;
    let n = stats.outliers.len();
    *out_n_outliers = n;
    if n > outliers_cap {
        return 0;
    }
    if n > 0 {
        let out = std::slice::from_raw_parts_mut(out_outliers, outliers_cap);
        out[..n].copy_from_slice(&stats.outliers);
    }
    1
}

/// Matplotlib-compatible hex binning. `reduce` is 0=count, 1=mean, 2=sum.
/// `c` may be null when `reduce=count`. Writes up to `capacity` occupied (or
/// threshold-passing) cells into the parallel out buffers and sets `*out_dx` /
/// `*out_dy`. Returns the cell count written, or `usize::MAX` on invalid args /
/// undersized capacity.
///
/// # Safety
/// Non-empty inputs and all out pointers must be valid for the given lengths.
#[no_mangle]
pub unsafe extern "C" fn xyg_hexbin(
    x: *const f64,
    y: *const f64,
    c: *const f64,
    len: usize,
    grid_w: usize,
    grid_h: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    mincnt: usize,
    reduce: i32,
    out_cx: *mut f64,
    out_cy: *mut f64,
    out_metric: *mut f64,
    out_counts: *mut f64,
    capacity: usize,
    out_dx: *mut f64,
    out_dy: *mut f64,
) -> usize {
    let Some(reduce) = hexbin::HexReduce::from_i32(reduce) else {
        return usize::MAX;
    };
    if out_cx.is_null()
        || out_cy.is_null()
        || out_metric.is_null()
        || out_counts.is_null()
        || out_dx.is_null()
        || out_dy.is_null()
    {
        return usize::MAX;
    }
    let (xs, ys) = if len == 0 {
        (&[][..], &[][..])
    } else {
        if x.is_null() || y.is_null() {
            return usize::MAX;
        }
        (
            std::slice::from_raw_parts(x, len),
            std::slice::from_raw_parts(y, len),
        )
    };
    let cs = if c.is_null() {
        None
    } else if len == 0 {
        Some(&[][..])
    } else {
        Some(std::slice::from_raw_parts(c, len))
    };
    let result = match ffi_guard(None, || {
        hexbin::hexbin(xs, ys, cs, grid_w, grid_h, x0, x1, y0, y1, mincnt, reduce)
    }) {
        Some(r) => r,
        None => return usize::MAX,
    };
    let n = result.centers_x.len();
    if n > capacity {
        return usize::MAX;
    }
    *out_dx = result.dx;
    *out_dy = result.dy;
    if n > 0 {
        std::slice::from_raw_parts_mut(out_cx, capacity)[..n].copy_from_slice(&result.centers_x);
        std::slice::from_raw_parts_mut(out_cy, capacity)[..n].copy_from_slice(&result.centers_y);
        std::slice::from_raw_parts_mut(out_metric, capacity)[..n].copy_from_slice(&result.metrics);
        std::slice::from_raw_parts_mut(out_counts, capacity)[..n].copy_from_slice(&result.counts);
    }
    n
}

/// Violin density: uniform histogram + fixed `[1,2,3,2,1]` smooth kernel with
/// coverage normalization. Writes `n_bins + 1` edges and `n_bins` density
/// values. Returns 1 on success, 0 when there is no finite sample or args are
/// invalid (`n_bins` outside `4..=1024`, null outs).
///
/// # Safety
/// `out_edges` holds `n_bins + 1` f64s; `out_density` holds `n_bins` f64s.
#[no_mangle]
pub unsafe extern "C" fn xyg_violin_density(
    data: *const f64,
    len: usize,
    n_bins: usize,
    out_edges: *mut f64,
    out_density: *mut f64,
) -> i32 {
    if out_edges.is_null() || out_density.is_null() || !(4..=1024).contains(&n_bins) {
        return 0;
    }
    let data = if len == 0 {
        &[][..]
    } else {
        if data.is_null() {
            return 0;
        }
        std::slice::from_raw_parts(data, len)
    };
    let Some(result) = ffi_guard(None, || stats::violin_density(data, n_bins)) else {
        return 0;
    };
    std::slice::from_raw_parts_mut(out_edges, n_bins + 1).copy_from_slice(&result.edges);
    std::slice::from_raw_parts_mut(out_density, n_bins).copy_from_slice(&result.density);
    1
}

/// Uniform histogram edges. `method` is 0 = NumPy `bins="auto"` (Sturges vs
/// Freedman–Diaconis with sqrt/2 floor — see `stats::histogram_edges`), 1 =
/// Sturges alone. When `use_range` is 0, `lo`/`hi` are ignored and outer edges
/// come from the finite sample (empty → `[0,1]`). Returns the number of edges
/// written (`n_bins + 1`), or `usize::MAX` on invalid args / undersized capacity.
///
/// # Safety
/// `out_edges` must hold `capacity` writable f64s when non-null.
#[no_mangle]
pub unsafe extern "C" fn xyg_histogram_edges(
    data: *const f64,
    len: usize,
    lo: f64,
    hi: f64,
    use_range: i32,
    method: i32,
    out_edges: *mut f64,
    capacity: usize,
) -> usize {
    let Some(method) = stats::HistogramEdgesMethod::from_i32(method) else {
        return usize::MAX;
    };
    if out_edges.is_null() || capacity == 0 {
        return usize::MAX;
    }
    let data = if len == 0 {
        &[][..]
    } else {
        if data.is_null() {
            return usize::MAX;
        }
        std::slice::from_raw_parts(data, len)
    };
    let range = if use_range != 0 { Some((lo, hi)) } else { None };
    let Some(edges) = ffi_guard(None, || stats::histogram_edges(data, range, method)) else {
        return usize::MAX;
    };
    if edges.len() > capacity {
        return usize::MAX;
    }
    std::slice::from_raw_parts_mut(out_edges, capacity)[..edges.len()].copy_from_slice(&edges);
    edges.len()
}

/// Wind-rose directional/speed binning. When `n_speed_edges == 0`, quartile
/// upper edges are derived from finite speeds; otherwise `speed_edges` is
/// uniqued/sorted and must cover the fastest observation. Writes `n_bands`
/// edges, `sectors` centres (degrees), and `n_bands * sectors` counts
/// (row-major `[band][sector]`). Returns `n_bands`, or `usize::MAX` on
/// invalid arguments / undersized capacity. Sets `*out_n_obs` to the finite
/// observation count on success.
///
/// # Safety
/// Non-empty inputs and all out pointers must be valid for the given lengths.
#[no_mangle]
pub unsafe extern "C" fn xyg_wind_rose_bins(
    directions: *const f64,
    speeds: *const f64,
    len: usize,
    sectors: usize,
    speed_edges: *const f64,
    n_speed_edges: usize,
    out_edges: *mut f64,
    capacity_edges: usize,
    out_centres: *mut f64,
    out_counts: *mut f64,
    capacity_counts: usize,
    out_n_obs: *mut usize,
) -> usize {
    if out_edges.is_null()
        || out_centres.is_null()
        || out_counts.is_null()
        || out_n_obs.is_null()
        || capacity_edges == 0
        || capacity_counts == 0
    {
        return usize::MAX;
    }
    let (dirs, mags) = if len == 0 {
        (&[][..], &[][..])
    } else {
        if directions.is_null() || speeds.is_null() {
            return usize::MAX;
        }
        (
            std::slice::from_raw_parts(directions, len),
            std::slice::from_raw_parts(speeds, len),
        )
    };
    let authored = if n_speed_edges == 0 {
        None
    } else {
        if speed_edges.is_null() {
            return usize::MAX;
        }
        Some(std::slice::from_raw_parts(speed_edges, n_speed_edges))
    };
    let Some(result) = ffi_guard(None, || {
        stats::wind_rose_bins(dirs, mags, sectors, authored)
    }) else {
        return usize::MAX;
    };
    let n_bands = result.edges.len();
    if n_bands > capacity_edges
        || result.counts.len() > capacity_counts
        || result.centres.len() != sectors
    {
        return usize::MAX;
    }
    std::slice::from_raw_parts_mut(out_edges, capacity_edges)[..n_bands]
        .copy_from_slice(&result.edges);
    std::slice::from_raw_parts_mut(out_centres, sectors).copy_from_slice(&result.centres);
    std::slice::from_raw_parts_mut(out_counts, capacity_counts)[..result.counts.len()]
        .copy_from_slice(&result.counts);
    *out_n_obs = result.n_obs;
    n_bands
}

/// Bilinear densify of a contourf scalar field (paired with
/// `xyg_contourf_bands` for corner-mask triangles). Writes densified
/// `out_z` (row-major), `out_x`, `out_y` and sets `*out_rows` / `*out_cols`.
/// Returns 1 on success, 0 on invalid shape/capacity/null outs.
///
/// # Safety
/// `z` is `rows * cols` row-major; `xpos`/`ypos` match `cols`/`rows`; outs hold
/// at least the densified capacities.
#[no_mangle]
pub unsafe extern "C" fn xyg_contourf_densify(
    z: *const f64,
    rows: usize,
    cols: usize,
    xpos: *const f64,
    ypos: *const f64,
    out_z: *mut f64,
    out_x: *mut f64,
    out_y: *mut f64,
    out_z_cap: usize,
    out_x_cap: usize,
    out_y_cap: usize,
    out_rows: *mut usize,
    out_cols: *mut usize,
) -> i32 {
    if z.is_null()
        || xpos.is_null()
        || ypos.is_null()
        || out_z.is_null()
        || out_x.is_null()
        || out_y.is_null()
        || out_rows.is_null()
        || out_cols.is_null()
        || rows < 2
        || cols < 2
    {
        return 0;
    }
    let Some((want_rows, want_cols)) = kernels::contourf_densify_shape(rows, cols) else {
        return 0;
    };
    if out_z_cap < want_rows.saturating_mul(want_cols)
        || out_x_cap < want_cols
        || out_y_cap < want_rows
    {
        return 0;
    }
    let z = std::slice::from_raw_parts(z, rows * cols);
    let xpos = std::slice::from_raw_parts(xpos, cols);
    let ypos = std::slice::from_raw_parts(ypos, rows);
    let out_z = std::slice::from_raw_parts_mut(out_z, out_z_cap);
    let out_x = std::slice::from_raw_parts_mut(out_x, out_x_cap);
    let out_y = std::slice::from_raw_parts_mut(out_y, out_y_cap);
    let Some((orows, ocols)) = ffi_guard(None, || {
        kernels::contourf_densify(z, rows, cols, xpos, ypos, out_z, out_x, out_y)
    }) else {
        return 0;
    };
    *out_rows = orows;
    *out_cols = ocols;
    1
}

/// Contourf corner-mask band triangles (ABI 57). Clips one-masked-corner
/// cells into ContourPy-style band triangles. Returns the triangle count
/// (`usize::MAX` on invalid args). Empty outs (capacity 0) are a count
/// query; undersized capacity still returns the full required count after
/// writing the prefix that fits.
///
/// # Safety
/// `z` is `rows * cols` row-major; `xpos`/`ypos` match `cols`/`rows`;
/// `edges` is `n_edges` strictly increasing finite levels (≥2). Outs are
/// either all null with capacity 0, or each address `capacity` writables.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_contourf_bands(
    z: *const f64,
    rows: usize,
    cols: usize,
    xpos: *const f64,
    ypos: *const f64,
    edges: *const f64,
    n_edges: usize,
    extend_min: u8,
    extend_max: u8,
    out_x0: *mut f64,
    out_y0: *mut f64,
    out_x1: *mut f64,
    out_y1: *mut f64,
    out_x2: *mut f64,
    out_y2: *mut f64,
    out_slots: *mut i64,
    capacity: usize,
) -> usize {
    if z.is_null()
        || xpos.is_null()
        || ypos.is_null()
        || edges.is_null()
        || n_edges < 2
        || rows < 2
        || cols < 2
    {
        return usize::MAX;
    }
    let Some(z_len) = rows.checked_mul(cols) else {
        return usize::MAX;
    };
    let z = std::slice::from_raw_parts(z, z_len);
    let xpos = std::slice::from_raw_parts(xpos, cols);
    let ypos = std::slice::from_raw_parts(ypos, rows);
    let edges = std::slice::from_raw_parts(edges, n_edges);
    let query = capacity == 0
        && out_x0.is_null()
        && out_y0.is_null()
        && out_x1.is_null()
        && out_y1.is_null()
        && out_x2.is_null()
        && out_y2.is_null()
        && out_slots.is_null();
    if !query
        && (out_x0.is_null()
            || out_y0.is_null()
            || out_x1.is_null()
            || out_y1.is_null()
            || out_x2.is_null()
            || out_y2.is_null()
            || out_slots.is_null())
    {
        return usize::MAX;
    }
    let (ox0, oy0, ox1, oy1, ox2, oy2, slots) = if query {
        (
            &mut [][..],
            &mut [][..],
            &mut [][..],
            &mut [][..],
            &mut [][..],
            &mut [][..],
            &mut [][..],
        )
    } else {
        (
            std::slice::from_raw_parts_mut(out_x0, capacity),
            std::slice::from_raw_parts_mut(out_y0, capacity),
            std::slice::from_raw_parts_mut(out_x1, capacity),
            std::slice::from_raw_parts_mut(out_y1, capacity),
            std::slice::from_raw_parts_mut(out_x2, capacity),
            std::slice::from_raw_parts_mut(out_y2, capacity),
            std::slice::from_raw_parts_mut(out_slots, capacity),
        )
    };
    ffi_guard(usize::MAX, || {
        kernels::contourf_bands_into(
            z,
            rows,
            cols,
            xpos,
            ypos,
            edges,
            extend_min != 0,
            extend_max != 0,
            ox0,
            oy0,
            ox1,
            oy1,
            ox2,
            oy2,
            slots,
        )
        .unwrap_or(usize::MAX)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[cfg(panic = "unwind")]
    fn ffi_guard_maps_panic_to_sentinel() {
        // A panic anywhere behind the C ABI must become the entry point's
        // error sentinel, never an unwind across `extern "C"` (which would
        // abort the embedding interpreter).
        let hook = std::panic::take_hook();
        std::panic::set_hook(Box::new(|_| {})); // silence the expected panic
        let got = ffi_guard(usize::MAX, || panic!("deliberate test panic"));
        std::panic::set_hook(hook);
        assert_eq!(got, usize::MAX);
        assert_eq!(ffi_guard(0i32, || 1i32), 1);
    }

    #[test]
    fn transition_key_ffi_reports_duplicate_rows_and_invalid_data() {
        let values = [7i16, -2, 7];
        let mut low = [0u32; 3];
        let mut high = [0u32; 3];
        let mut first = usize::MAX;
        let mut index = usize::MAX;
        unsafe {
            assert_eq!(
                xyg_transition_keys_fixed(
                    values.as_ptr().cast(),
                    values.len(),
                    std::mem::size_of::<i16>(),
                    transition::KIND_SIGNED,
                    0,
                    low.as_mut_ptr(),
                    high.as_mut_ptr(),
                    &mut first,
                    &mut index,
                ),
                2
            );
        }
        assert_eq!((first, index), (0, 2));

        let nonfinite = f64::INFINITY;
        first = usize::MAX;
        index = usize::MAX;
        unsafe {
            assert_eq!(
                xyg_transition_keys_fixed(
                    (&nonfinite as *const f64).cast(),
                    1,
                    std::mem::size_of::<f64>(),
                    transition::KIND_FLOAT64,
                    0,
                    low.as_mut_ptr(),
                    high.as_mut_ptr(),
                    &mut first,
                    &mut index,
                ),
                1
            );
        }
        assert_eq!((first, index), (0, 0));
    }

    #[test]
    fn transition_key_ffi_accepts_empty_null_spans_and_rejects_bad_pointers() {
        unsafe {
            assert_eq!(
                xyg_transition_keys_fixed(
                    std::ptr::null(),
                    0,
                    0,
                    transition::KIND_BYTES,
                    0,
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                ),
                0
            );
            assert_eq!(
                xyg_transition_keys_fixed(
                    std::ptr::null(),
                    1,
                    1,
                    transition::KIND_BYTES,
                    0,
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                ),
                4
            );
            // A layout the caller should never send is status 4, not the
            // status-1 "declined this data" that means "use the oracle".
            let row = [0u8; 3];
            let mut low = [0u32];
            let mut high = [0u32];
            let mut first = usize::MAX;
            let mut index = usize::MAX;
            assert_eq!(
                xyg_transition_keys_fixed(
                    row.as_ptr(),
                    1,
                    3,
                    transition::KIND_UNICODE,
                    0,
                    low.as_mut_ptr(),
                    high.as_mut_ptr(),
                    &mut first,
                    &mut index,
                ),
                4
            );
            assert_eq!((first, index), (usize::MAX, usize::MAX));
            assert_eq!(
                xyg_transition_keys_fixed(
                    row.as_ptr(),
                    1,
                    1,
                    transition::KIND_BYTES,
                    7,
                    low.as_mut_ptr(),
                    high.as_mut_ptr(),
                    &mut first,
                    &mut index,
                ),
                4
            );
        }
    }

    #[test]
    #[cfg(target_pointer_width = "64")]
    fn index_emitting_entry_points_reject_u32_overflowing_len() {
        // Emitted row indices are u32: a column longer than u32::MAX would
        // wrap into valid-looking wrong rows. The guards fire before any
        // pointer is dereferenced, so tiny arrays with an absurd `len` are
        // safe to pass here.
        let x = [0.0f64, 1.0];
        let y = [0.0f64, 1.0];
        let too_long = u32::MAX as usize + 1;
        let groups = [0u8, 0];
        let counts = [2u64];
        let validity_columns = [x.as_ptr(), y.as_ptr()];
        let mut idx = [0u32; 8];
        let mut grid = [0f32; 4];
        unsafe {
            assert_eq!(
                xyg_m4_indices(
                    x.as_ptr(),
                    y.as_ptr(),
                    too_long,
                    0.0,
                    1.0,
                    2,
                    idx.as_mut_ptr()
                ),
                usize::MAX
            );
            assert_eq!(
                xyg_range_indices(
                    x.as_ptr(),
                    y.as_ptr(),
                    too_long,
                    0.0,
                    1.0,
                    0.0,
                    1.0,
                    idx.as_mut_ptr()
                ),
                usize::MAX
            );
            assert_eq!(
                xyg_valid_indices_f64(
                    validity_columns.as_ptr(),
                    validity_columns.len(),
                    too_long,
                    0,
                    idx.as_mut_ptr(),
                    idx.len(),
                ),
                usize::MAX
            );
            assert_eq!(
                xyg_bin_2d_indices(
                    x.as_ptr(),
                    y.as_ptr(),
                    too_long,
                    0.0,
                    1.0,
                    0.0,
                    1.0,
                    2,
                    2,
                    grid.as_mut_ptr(),
                    idx.as_mut_ptr()
                ),
                usize::MAX
            );
            assert_eq!(
                xyg_bin_2d_sample_range(
                    x.as_ptr(),
                    y.as_ptr(),
                    too_long,
                    0.0,
                    1.0,
                    0.0,
                    1.0,
                    2,
                    2,
                    0,
                    0,
                    grid.as_mut_ptr(),
                    idx.as_mut_ptr(),
                    idx.len(),
                ),
                usize::MAX
            );
            assert_eq!(
                xyg_bin_2d_stratified_sample_range_u8_counted(
                    x.as_ptr(),
                    y.as_ptr(),
                    groups.as_ptr(),
                    too_long,
                    counts.as_ptr(),
                    1,
                    0.0,
                    1.0,
                    0.0,
                    1.0,
                    2,
                    2,
                    0,
                    0.5,
                    1,
                    grid.as_mut_ptr(),
                    idx.as_mut_ptr(),
                    idx.len(),
                ),
                usize::MAX
            );
        }
    }

    #[test]
    #[cfg(target_pointer_width = "64")]
    fn grid_size_products_that_overflow_are_rejected() {
        // In release builds an unchecked `w * h` wraps silently and the slice
        // built from it is shorter than the kernel-side expectation; every
        // grid entry point must refuse instead (xyg_rasterize already did).
        let x = [0.5f64];
        let y = [0.5f64];
        let groups = [0u8];
        let counts = [1u64];
        let huge = usize::MAX / 2 + 1; // huge * 2 wraps to 0
        let mut grid = [0f32; 4];
        let mut idx = [0u32; 4];
        unsafe {
            assert_eq!(
                xyg_bin_2d(
                    x.as_ptr(),
                    y.as_ptr(),
                    1,
                    0.0,
                    1.0,
                    0.0,
                    1.0,
                    huge,
                    2,
                    grid.as_mut_ptr()
                ),
                0
            );
            assert_eq!(
                xyg_bin_2d_indices(
                    x.as_ptr(),
                    y.as_ptr(),
                    1,
                    0.0,
                    1.0,
                    0.0,
                    1.0,
                    huge,
                    2,
                    grid.as_mut_ptr(),
                    idx.as_mut_ptr()
                ),
                usize::MAX
            );
            assert_eq!(
                xyg_bin_2d_sample_range(
                    x.as_ptr(),
                    y.as_ptr(),
                    1,
                    0.0,
                    1.0,
                    0.0,
                    1.0,
                    huge,
                    2,
                    0,
                    0,
                    grid.as_mut_ptr(),
                    idx.as_mut_ptr(),
                    1,
                ),
                usize::MAX
            );
            assert_eq!(
                xyg_bin_2d_stratified_sample_range_u8_counted(
                    x.as_ptr(),
                    y.as_ptr(),
                    groups.as_ptr(),
                    1,
                    counts.as_ptr(),
                    1,
                    0.0,
                    1.0,
                    0.0,
                    1.0,
                    huge,
                    2,
                    0,
                    0.5,
                    1,
                    grid.as_mut_ptr(),
                    idx.as_mut_ptr(),
                    1,
                ),
                usize::MAX
            );
            assert_eq!(
                xyg_m4_indices(
                    x.as_ptr(),
                    y.as_ptr(),
                    1,
                    0.0,
                    1.0,
                    usize::MAX / 4 + 1, // n_buckets * 4 wraps
                    idx.as_mut_ptr()
                ),
                usize::MAX
            );
            assert_eq!(
                xyg_pyramid_compose(0, 0.0, 1.0, 0.0, 1.0, huge, 2, 2, grid.as_mut_ptr()),
                -1
            );
        }
    }

    #[test]
    fn graph_projection_abi_roundtrip_and_stable_errors() {
        let nodes = [[1u8; 16], [2u8; 16]];
        let edges = [[3u8; 16], [4u8; 16]];
        let sources = [[1u8; 16], [1u8; 16]];
        let targets = [[2u8; 16], [2u8; 16]];
        let descriptor = XygGraphProjectionDescriptor {
            node_ids: nodes.as_ptr().cast(),
            node_count: 2,
            edge_ids: edges.as_ptr().cast(),
            edge_count: 2,
            source_ids: sources.as_ptr().cast(),
            target_ids: targets.as_ptr().cast(),
            parent_ids: std::ptr::null(),
            parent_validity: std::ptr::null(),
            directed: 1,
            reserved: 0,
        };
        let mut handle = 0;
        unsafe {
            assert_eq!(xyg_graph_projection_create(&descriptor, &mut handle), 0);
            let (mut n, mut e, mut directed) = (0, 0, 0);
            assert_eq!(
                xyg_graph_projection_counts(handle, &mut n, &mut e, &mut directed),
                0
            );
            assert_eq!((n, e, directed), (2, 2, 1));
            let (mut dense_sources, mut dense_targets) = ([u64::MAX; 2], [u64::MAX; 2]);
            assert_eq!(
                xyg_graph_projection_copy_endpoints(
                    handle,
                    dense_sources.as_mut_ptr(),
                    dense_targets.as_mut_ptr(),
                    2
                ),
                0
            );
            assert_eq!(dense_sources, [0, 0]);
            assert_eq!(dense_targets, [1, 1]);
            assert_eq!(
                xyg_graph_projection_copy_endpoints(
                    handle,
                    dense_sources.as_mut_ptr(),
                    dense_targets.as_mut_ptr(),
                    1
                ),
                -8
            );
            assert_eq!(xyg_graph_projection_destroy(handle), 0);
            assert_eq!(xyg_graph_projection_destroy(handle), -7);
            assert_eq!(
                xyg_graph_projection_counts(handle, &mut n, &mut e, &mut directed),
                -7
            );
        }
    }

    #[test]
    fn graph_projection_abi_rejects_missing_endpoint() {
        let nodes = [[1u8; 16]];
        let edges = [[2u8; 16]];
        let sources = [[1u8; 16]];
        let targets = [[9u8; 16]];
        let descriptor = XygGraphProjectionDescriptor {
            node_ids: nodes.as_ptr().cast(),
            node_count: 1,
            edge_ids: edges.as_ptr().cast(),
            edge_count: 1,
            source_ids: sources.as_ptr().cast(),
            target_ids: targets.as_ptr().cast(),
            parent_ids: std::ptr::null(),
            parent_validity: std::ptr::null(),
            directed: 0,
            reserved: 0,
        };
        let mut handle = 0;
        unsafe {
            assert_eq!(xyg_graph_projection_create(&descriptor, &mut handle), -6);
        }
        assert_eq!(handle, 0);
    }
}
