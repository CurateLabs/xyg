//! C ABI shell for the XYG native core (design dossier §32).
//!
//! Marshaling, pointer/length validation, panic shielding, ABI version, and
//! `extern "C"` entry points live here. Chart algorithms and deterministic
//! product policy live in `xyg-engine`. One cdylib per platform
//! (`libxyg_core`) serves Python ctypes and Node koffi.
//!
//! Canonical f64 columns live in `xyg-engine::stream` behind `xyg_stream_*`
//! handles (introduced in ABI 59). Hosts coerce ingest and hold the opaque handle; they
//! do not own the growable backing store. Out-of-core memmap columns remain
//! host-owned (they cannot sit behind this first in-RAM handle).
//!
//! Safety contract (enforced by `python/xyg/_native.py` and
//! `packages/xy-node/src/native.js`): non-empty inputs use non-null, properly
//! aligned pointers sized as documented per function. Empty inputs are
//! accepted without dereferencing their pointers; invalid pointer/argument
//! combinations return the documented error sentinel instead of panicking
//! across the C boundary. Hosts bind and check `xyg_abi_version` before any
//! other symbol.

#![allow(clippy::too_many_arguments)] // C ABI entry points; arity is the contract

use xyg_engine::auto_domain;
use xyg_engine::autorange::{rect_zero_baseline_flags, AutorangeError};
#[cfg(not(target_os = "emscripten"))]
use xyg_engine::chunked_columns;
use xyg_engine::css;
use xyg_engine::figure_autorange;
use xyg_engine::geo;
use xyg_engine::graph;
use xyg_engine::hexbin;
use xyg_engine::jpeg;
use xyg_engine::kernels;
use xyg_engine::kernels::ZoneMap;
use xyg_engine::lod_plan;
use xyg_engine::pdf;
use xyg_engine::png_encode;
use xyg_engine::projection;
use xyg_engine::raster;
use xyg_engine::sankey;
use xyg_engine::scene;
use xyg_engine::scene_annotations::{self, AnnotationError};
use xyg_engine::scene_colorbar::{self, ColorbarError};
use xyg_engine::scene_figure_support_reason;
use xyg_engine::scene_legend::{self, LegendError};
use xyg_engine::scene_pack::{self, PackError};
use xyg_engine::scene_public_export_reason;
use xyg_engine::scene_style::{self, MarkStyleError};
use xyg_engine::stats;
use xyg_engine::stream;
use xyg_engine::svg;
use xyg_engine::temporal;
use xyg_engine::temporal_controller;
use xyg_engine::temporal_graph;
#[cfg(not(target_os = "emscripten"))]
use xyg_engine::tile_store;
use xyg_engine::tiles;
use xyg_engine::transition;
use xyg_engine::webp;

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
pub const ABI_VERSION: u32 = 117;

/// Version of the bounded canonical scene record schema.
#[no_mangle]
pub extern "C" fn xyg_scene_version() -> u32 {
    scene::SCENE_VERSION
}

/// Query Rust's stable support diagnostic for a literal authored-feature mask.
/// Returns the required UTF-8 byte count (zero means supported), or
/// `usize::MAX` for an unknown request version/feature bit. When `out_cap` is
/// sufficient, writes the diagnostic without a trailing NUL.
///
/// # Safety
/// When `out_cap` is non-zero, `out` must address that many writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_support_reason(
    request_version: u32,
    features: u64,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if out_cap > 0 && out.is_null() {
        return usize::MAX;
    }
    ffi_guard(usize::MAX, || {
        let Ok(reason) = scene::scene_support_reason(request_version, features) else {
            return usize::MAX;
        };
        let bytes = reason.as_bytes();
        if out_cap >= bytes.len() && !bytes.is_empty() {
            std::ptr::copy_nonoverlapping(bytes.as_ptr(), out, bytes.len());
        }
        bytes.len()
    })
}

/// Query Rust's public static-export support diagnostic for a packed `XYEP`
/// envelope. Returns the required UTF-8 byte count (zero means supported), or
/// `usize::MAX` for a malformed or version-mismatched envelope. When `out_cap`
/// is sufficient, writes the diagnostic without a trailing NUL. Hosts only
/// pack literal figure metadata; allowlists and wording stay in Rust.
///
/// # Safety
/// `input` must address `len` readable bytes when `len` is non-zero. When
/// `out_cap` is non-zero, `out` must address that many writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_public_export_reason(
    input: *const u8,
    len: usize,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if (len > 0 && input.is_null()) || (out_cap > 0 && out.is_null()) {
        return usize::MAX;
    }
    ffi_guard(usize::MAX, || {
        let bytes = if len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(input, len)
        };
        let Ok(reason) = scene_public_export_reason(bytes) else {
            return usize::MAX;
        };
        let encoded = reason.as_bytes();
        if out_cap >= encoded.len() && !encoded.is_empty() {
            std::ptr::copy_nonoverlapping(encoded.as_ptr(), out, encoded.len());
        }
        encoded.len()
    })
}

/// Query Rust's figure-compile support diagnostic for a packed `XYFS`
/// envelope. Returns the required UTF-8 byte count (zero means supported), or
/// `usize::MAX` for a malformed or version-mismatched envelope. When `out_cap`
/// is sufficient, writes the diagnostic without a trailing NUL. Hosts pack
/// literal observations plus axis ids/keys; feature mapping and the axis
/// allowlist stay in Rust.
///
/// # Safety
/// `input` must address `len` readable bytes when `len` is non-zero. When
/// `out_cap` is non-zero, `out` must address that many writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_figure_support_reason(
    input: *const u8,
    len: usize,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if (len > 0 && input.is_null()) || (out_cap > 0 && out.is_null()) {
        return usize::MAX;
    }
    ffi_guard(usize::MAX, || {
        let bytes = if len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(input, len)
        };
        let Ok(reason) = scene_figure_support_reason(bytes) else {
            return usize::MAX;
        };
        let encoded = reason.as_bytes();
        if out_cap >= encoded.len() && !encoded.is_empty() {
            std::ptr::copy_nonoverlapping(encoded.as_ptr(), out, encoded.len());
        }
        encoded.len()
    })
}

/// Resolve packed `XYMS` v1 mark styles to fill/stroke RGBA8 and stroke
/// width. Hosts pack kind, opacities, authored CSS strings, and width
/// fields; per-kind defaults and CSS→RGBA8 stay in Rust. Returns the mark
/// count on success. `-1` malformed, `-2` unknown version, `-3` over the
/// mark/CSS budget, `-4` when `out` is too small.
///
/// Each output record is 16 bytes: fill RGBA8, stroke RGBA8, little-endian
/// f64 width.
///
/// # Safety
/// `input` must address `len` readable bytes when `len` is non-zero. When
/// `out_cap` is non-zero, `out` must address that many writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_resolve_mark_styles(
    input: *const u8,
    len: usize,
    out: *mut u8,
    out_cap: usize,
) -> i32 {
    if (len > 0 && input.is_null()) || (out_cap > 0 && out.is_null()) {
        return -(MarkStyleError::Length as i32);
    }
    ffi_guard(-(MarkStyleError::Length as i32), || {
        let bytes = if len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(input, len)
        };
        match scene_style::resolve_mark_styles(bytes) {
            Ok(styles) => {
                let needed = styles.len().saturating_mul(16);
                if needed > out_cap {
                    return -(MarkStyleError::Output as i32);
                }
                let dest = if needed == 0 {
                    &mut []
                } else {
                    std::slice::from_raw_parts_mut(out, out_cap)
                };
                match scene_style::encode_mark_styles(&styles, dest) {
                    Ok(count) => count,
                    Err(error) => -(error as i32),
                }
            }
            Err(error) => -(error as i32),
        }
    })
}

/// Overlay packed `XYCH` v1 chrome onto the 200-byte Scene style input.
///
/// Hosts pack background CSS, per-axis sides, paint flags, opacities, widths,
/// and CSS strings; default RGBA, default widths, `grid_opacity` scaling of
/// the default grid color, and CSS→RGBA8 stay in Rust. Returns 200 on
/// success. `-1` malformed, `-2` unknown version, `-3` over the axis/CSS
/// budget, `-4` when `out` is too small.
///
/// # Safety
/// `input` must address `len` readable bytes when `len` is non-zero. When
/// `out_cap` is non-zero, `out` must address that many writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_resolve_chrome_style(
    input: *const u8,
    len: usize,
    out: *mut u8,
    out_cap: usize,
) -> i32 {
    if (len > 0 && input.is_null()) || (out_cap > 0 && out.is_null()) {
        return -(MarkStyleError::Length as i32);
    }
    ffi_guard(-(MarkStyleError::Length as i32), || {
        let bytes = if len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(input, len)
        };
        match scene_style::resolve_chrome_style(bytes) {
            Ok(style) => {
                if scene::SCENE_CHROME_STYLE_INPUT_BYTES > out_cap {
                    return -(MarkStyleError::Output as i32);
                }
                let dest = if out_cap == 0 {
                    &mut []
                } else {
                    std::slice::from_raw_parts_mut(out, out_cap)
                };
                match scene_style::encode_chrome_style(&style, dest) {
                    Ok(count) => count,
                    Err(error) => -(error as i32),
                }
            }
            Err(error) => -(error as i32),
        }
    })
}

/// Pack one Figure trace's columns into Scene rows.
///
/// Hosts pass authoring kind, style ref, trace id, diameter/symbol, optional
/// extras (hex pitch, heatmap shape), and up to six f64 columns. Rust owns
/// Scene record kinds, stable-id splitting, expansion-mode assignment,
/// ribbon/triangle doubling, heatmap lattice framing, and finite-coordinate
/// rejection. Returns the row count on success. `-1` malformed, `-2`
/// reserved, `-3` over the mark budget, `-4` when `out` is too small, `-5`
/// when a required coordinate is non-finite.
///
/// Each output record is 56 bytes: kind, symbol, expansion mode, pad,
/// little-endian u32 style_ref, u64 stable_id, and five f64 fields
/// (diameter, x0, y0, x1, y1).
///
/// # Safety
/// Each non-zero `nK` requires `colK` to address that many readable f64s.
/// When `out_cap` is non-zero, `out` must address that many writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_pack_trace(
    pack_kind: u8,
    flags: u8,
    step_mode: u8,
    symbol: u8,
    style_ref: u32,
    trace_id: u64,
    diameter: f64,
    extra0: f64,
    extra1: f64,
    col0: *const f64,
    n0: usize,
    col1: *const f64,
    n1: usize,
    col2: *const f64,
    n2: usize,
    col3: *const f64,
    n3: usize,
    col4: *const f64,
    n4: usize,
    col5: *const f64,
    n5: usize,
    out: *mut u8,
    out_cap: usize,
) -> i32 {
    if out_cap > 0 && out.is_null() {
        return -(PackError::Length as i32);
    }
    ffi_guard(-(PackError::Length as i32), || {
        let slice = |ptr: *const f64, n: usize| -> Result<&[f64], i32> {
            if n == 0 {
                Ok(&[])
            } else if ptr.is_null() {
                Err(-(PackError::Length as i32))
            } else {
                Ok(std::slice::from_raw_parts(ptr, n))
            }
        };
        let columns = [
            match slice(col0, n0) {
                Ok(value) => value,
                Err(code) => return code,
            },
            match slice(col1, n1) {
                Ok(value) => value,
                Err(code) => return code,
            },
            match slice(col2, n2) {
                Ok(value) => value,
                Err(code) => return code,
            },
            match slice(col3, n3) {
                Ok(value) => value,
                Err(code) => return code,
            },
            match slice(col4, n4) {
                Ok(value) => value,
                Err(code) => return code,
            },
            match slice(col5, n5) {
                Ok(value) => value,
                Err(code) => return code,
            },
        ];
        match scene_pack::pack_trace(scene_pack::TracePackInput {
            pack_kind,
            flags,
            step_mode,
            symbol,
            style_ref,
            trace_id,
            diameter,
            extra0,
            extra1,
            columns: &columns,
        }) {
            Ok(rows) => {
                let needed = rows
                    .len()
                    .saturating_mul(scene_pack::PACKED_SCENE_ROW_BYTES);
                if needed > out_cap {
                    return -(PackError::Output as i32);
                }
                let dest = if out_cap == 0 {
                    &mut []
                } else {
                    std::slice::from_raw_parts_mut(out, out_cap)
                };
                match scene_pack::encode_packed_rows(&rows, dest) {
                    Ok(count) => count,
                    Err(error) => -(error as i32),
                }
            }
            Err(error) => -(error as i32),
        }
    })
}

/// Expand packed rule/band/marker annotation scalars into Scene rows.
///
/// Hosts pass a table of 40-byte rows (kind, axis, symbol, style ref, index,
/// value0, value1, size) plus the primary x/y domains. Rust owns stable-id
/// tags, domain spanning, and finite rejection. Returns the row count on
/// success. `-1` malformed, `-3` over the mark budget, `-4` when `out` is too
/// small, `-5` when a required coordinate is non-finite.
///
/// Output records match `xyg_scene_pack_trace` (56 bytes each).
///
/// # Safety
/// `rows` addresses `rows_len` readable bytes when `rows_len` is non-zero.
/// When `out_cap` is non-zero, `out` must address that many writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_pack_annotation_marks(
    rows: *const u8,
    rows_len: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    out: *mut u8,
    out_cap: usize,
) -> i32 {
    if (rows_len > 0 && rows.is_null()) || (out_cap > 0 && out.is_null()) {
        return -(PackError::Length as i32);
    }
    ffi_guard(-(PackError::Length as i32), || {
        let bytes = if rows_len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(rows, rows_len)
        };
        let parsed = match scene_pack::parse_annotation_mark_rows(bytes) {
            Ok(value) => value,
            Err(error) => return -(error as i32),
        };
        match scene_pack::pack_annotation_marks(&parsed, x0, x1, y0, y1) {
            Ok(packed) => {
                let needed = packed
                    .len()
                    .saturating_mul(scene_pack::PACKED_SCENE_ROW_BYTES);
                if needed > out_cap {
                    return -(PackError::Output as i32);
                }
                let dest = if out_cap == 0 {
                    &mut []
                } else {
                    std::slice::from_raw_parts_mut(out, out_cap)
                };
                match scene_pack::encode_packed_rows(&packed, dest) {
                    Ok(count) => count,
                    Err(error) => -(error as i32),
                }
            }
            Err(error) => -(error as i32),
        }
    })
}

/// Frame a primary Scene legend as XYLG bytes.
///
/// Hosts pass loc/flags, font sizes, paints, title, 16-byte entry meta, and
/// concatenated labels. Rust owns the XYLG header, entry table, text offsets,
/// and bounded-text rejection. Returns the byte count on success, `0` when
/// there are no entries, `-1` malformed, `-2` reserved, `-3` over the
/// legend budget, `-4` when `out` is too small, `-5` for an invalid font
/// size, or `-6` for an unknown location code.
///
/// Entry meta is `n_entries` records of 16 bytes: little-endian u32
/// style_ref, kind, symbol, two pad bytes, fill RGBA8, stroke RGBA8.
/// `label_lens` is `n_entries` little-endian u32 lengths that concatenate
/// to `labels_len`.
///
/// # Safety
/// Non-zero lengths require readable pointers. When `out_cap` is non-zero,
/// `out` must address that many writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_pack_legend(
    loc: u8,
    flags: u8,
    font_size: f64,
    title_font_size: f64,
    text_rgba: *const u8,
    frame_fill_rgba: *const u8,
    title: *const u8,
    title_len: usize,
    n_entries: u32,
    entry_meta: *const u8,
    entry_meta_len: usize,
    label_lens: *const u32,
    labels: *const u8,
    labels_len: usize,
    out: *mut u8,
    out_cap: usize,
) -> i32 {
    if out_cap > 0 && out.is_null() {
        return -(LegendError::Length as i32);
    }
    ffi_guard(-(LegendError::Length as i32), || {
        let rgba4 = |ptr: *const u8| -> Result<[u8; 4], i32> {
            if ptr.is_null() {
                Ok([0; 4])
            } else {
                Ok(std::slice::from_raw_parts(ptr, 4).try_into().unwrap())
            }
        };
        let text_rgba = match rgba4(text_rgba) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let frame_fill_rgba = match rgba4(frame_fill_rgba) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let title = if title_len == 0 {
            &[][..]
        } else if title.is_null() {
            return -(LegendError::Length as i32);
        } else {
            std::slice::from_raw_parts(title, title_len)
        };
        let n = n_entries as usize;
        let meta = if entry_meta_len == 0 {
            &[][..]
        } else if entry_meta.is_null() {
            return -(LegendError::Length as i32);
        } else {
            std::slice::from_raw_parts(entry_meta, entry_meta_len)
        };
        let lens = if n == 0 {
            &[][..]
        } else if label_lens.is_null() {
            return -(LegendError::Length as i32);
        } else {
            std::slice::from_raw_parts(label_lens, n)
        };
        let labels = if labels_len == 0 {
            &[][..]
        } else if labels.is_null() {
            return -(LegendError::Length as i32);
        } else {
            std::slice::from_raw_parts(labels, labels_len)
        };
        let entries = match scene_legend::entries_from_meta(meta, lens, labels) {
            Ok(value) => value,
            Err(error) => return -(error as i32),
        };
        match scene_legend::pack_legend(scene_legend::LegendFrameInput {
            loc,
            flags,
            font_size,
            title_font_size,
            text_rgba,
            frame_fill_rgba,
            title,
            entries: &entries,
        }) {
            Ok(bytes) => {
                if bytes.len() > out_cap {
                    return -(LegendError::Output as i32);
                }
                if bytes.is_empty() {
                    return 0;
                }
                let dest = std::slice::from_raw_parts_mut(out, out_cap);
                dest[..bytes.len()].copy_from_slice(&bytes);
                match i32::try_from(bytes.len()) {
                    Ok(count) => count,
                    Err(_) => -(LegendError::Limit as i32),
                }
            }
            Err(error) => -(error as i32),
        }
    })
}

/// Frame a primary Scene colorbar as XYCB v2 bytes.
///
/// Hosts pass horizontal/minor flags, domain, text RGBA, title, stop
/// values/RGBA, and optional ticks. Rust owns the XYCB header, stop/tick
/// tables, domain-span checks, and bounded-text rejection. Returns the byte
/// count on success. `-1` malformed, `-2` reserved, `-3` over the colorbar
/// budget, `-4` when `out` is too small, `-5` when a required value is
/// non-finite, `-6` when stops are unordered or miss the domain, or `-7`
/// when ticks are unordered or outside the domain.
///
/// `flags` bit 0 is horizontal (`side=bottom`); bit 2 is `minor_ticks`.
/// Stop RGBA is `n_stops * 4` bytes. `ticks` may be null when `n_ticks` is 0.
///
/// # Safety
/// Non-zero lengths require readable pointers. When `out_cap` is non-zero,
/// `out` must address that many writable bytes. `text_rgba` must address
/// four readable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_pack_colorbar(
    flags: u8,
    lo: f64,
    hi: f64,
    text_rgba: *const u8,
    title: *const u8,
    title_len: usize,
    n_stops: u32,
    stop_values: *const f64,
    stop_rgba: *const u8,
    stop_rgba_len: usize,
    n_ticks: u32,
    ticks: *const f64,
    out: *mut u8,
    out_cap: usize,
) -> i32 {
    if out_cap > 0 && out.is_null() {
        return -(ColorbarError::Length as i32);
    }
    if text_rgba.is_null() {
        return -(ColorbarError::Length as i32);
    }
    ffi_guard(-(ColorbarError::Length as i32), || {
        let title = if title_len == 0 {
            &[][..]
        } else if title.is_null() {
            return -(ColorbarError::Length as i32);
        } else {
            std::slice::from_raw_parts(title, title_len)
        };
        let n_stops = n_stops as usize;
        let n_ticks = n_ticks as usize;
        let values = if n_stops == 0 {
            &[][..]
        } else if stop_values.is_null() {
            return -(ColorbarError::Length as i32);
        } else {
            std::slice::from_raw_parts(stop_values, n_stops)
        };
        let rgba = if stop_rgba_len == 0 {
            &[][..]
        } else if stop_rgba.is_null() {
            return -(ColorbarError::Length as i32);
        } else {
            std::slice::from_raw_parts(stop_rgba, stop_rgba_len)
        };
        if rgba.len() != n_stops.saturating_mul(4) {
            return -(ColorbarError::Length as i32);
        }
        let tick_values = if n_ticks == 0 {
            &[][..]
        } else if ticks.is_null() {
            return -(ColorbarError::Length as i32);
        } else {
            std::slice::from_raw_parts(ticks, n_ticks)
        };
        let mut stops = Vec::with_capacity(n_stops);
        for (index, &value) in values.iter().enumerate() {
            let at = index * 4;
            stops.push(scene_colorbar::ColorbarStop {
                value,
                rgba: rgba[at..at + 4].try_into().unwrap(),
            });
        }
        match scene_colorbar::pack_colorbar(scene_colorbar::ColorbarFrameInput {
            flags,
            lo,
            hi,
            text_rgba: std::slice::from_raw_parts(text_rgba, 4).try_into().unwrap(),
            title,
            stops: &stops,
            ticks: tick_values,
        }) {
            Ok(bytes) => {
                if bytes.len() > out_cap {
                    return -(ColorbarError::Output as i32);
                }
                if bytes.is_empty() {
                    return 0;
                }
                let dest = std::slice::from_raw_parts_mut(out, out_cap);
                dest[..bytes.len()].copy_from_slice(&bytes);
                match i32::try_from(bytes.len()) {
                    Ok(count) => count,
                    Err(_) => -(ColorbarError::Limit as i32),
                }
            }
            Err(error) => -(error as i32),
        }
    })
}

/// Frame primary Scene annotations as XYAD bytes.
///
/// Hosts pass compact per-family row meta plus concatenated UTF-8 labels.
/// Rust owns XYAT/XYAL/XYAR/XYAC/XYAW table layout, version selection, the
/// XYAD envelope, and bounded-text rejection. Returns the byte count on
/// success, `0` when every family is empty, `-1` malformed, `-2` reserved,
/// `-3` over the annotation budget, `-4` when `out` is too small, `-5`
/// non-finite, `-6` empty/NUL/CR/invalid text, or `-7` duplicate ids or a
/// border without a fill.
///
/// Text meta is `n_text` records of 40 bytes, attached 32, arrows 60,
/// callouts 76, wrapped 64. Label length arrays concatenate to the matching
/// text payload. Count-zero families may pass null pointers.
///
/// # Safety
/// Non-zero lengths require readable pointers. When `out_cap` is non-zero,
/// `out` must address that many writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_pack_annotations(
    n_text: u32,
    text_meta: *const u8,
    text_meta_len: usize,
    text_lens: *const u32,
    texts: *const u8,
    texts_len: usize,
    n_attached: u32,
    attached_meta: *const u8,
    attached_meta_len: usize,
    attached_lens: *const u32,
    attached_texts: *const u8,
    attached_texts_len: usize,
    n_arrows: u32,
    arrow_meta: *const u8,
    arrow_meta_len: usize,
    n_callouts: u32,
    callout_meta: *const u8,
    callout_meta_len: usize,
    callout_lens: *const u32,
    callout_texts: *const u8,
    callout_texts_len: usize,
    n_wrapped: u32,
    wrapped_meta: *const u8,
    wrapped_meta_len: usize,
    wrapped_lens: *const u32,
    wrapped_texts: *const u8,
    wrapped_texts_len: usize,
    out: *mut u8,
    out_cap: usize,
) -> i32 {
    if out_cap > 0 && out.is_null() {
        return -(AnnotationError::Length as i32);
    }
    ffi_guard(-(AnnotationError::Length as i32), || {
        let bytes = |ptr: *const u8, len: usize| -> Result<&[u8], i32> {
            if len == 0 {
                Ok(&[])
            } else if ptr.is_null() {
                Err(-(AnnotationError::Length as i32))
            } else {
                Ok(std::slice::from_raw_parts(ptr, len))
            }
        };
        let lens = |ptr: *const u32, n: usize| -> Result<&[u32], i32> {
            if n == 0 {
                Ok(&[])
            } else if ptr.is_null() {
                Err(-(AnnotationError::Length as i32))
            } else {
                Ok(std::slice::from_raw_parts(ptr, n))
            }
        };
        let text_meta = match bytes(text_meta, text_meta_len) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let text_lens = match lens(text_lens, n_text as usize) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let texts = match bytes(texts, texts_len) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let attached_meta = match bytes(attached_meta, attached_meta_len) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let attached_lens = match lens(attached_lens, n_attached as usize) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let attached_texts = match bytes(attached_texts, attached_texts_len) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let arrow_meta = match bytes(arrow_meta, arrow_meta_len) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let callout_meta = match bytes(callout_meta, callout_meta_len) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let callout_lens = match lens(callout_lens, n_callouts as usize) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let callout_texts = match bytes(callout_texts, callout_texts_len) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let wrapped_meta = match bytes(wrapped_meta, wrapped_meta_len) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let wrapped_lens = match lens(wrapped_lens, n_wrapped as usize) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let wrapped_texts = match bytes(wrapped_texts, wrapped_texts_len) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let text_rows = match scene_annotations::text_rows_from_meta(text_meta, text_lens, texts) {
            Ok(value) => value,
            Err(error) => return -(error as i32),
        };
        let attached_rows = match scene_annotations::attached_rows_from_meta(
            attached_meta,
            attached_lens,
            attached_texts,
        ) {
            Ok(value) => value,
            Err(error) => return -(error as i32),
        };
        let arrow_rows = match scene_annotations::arrow_rows_from_meta(arrow_meta) {
            Ok(value) => value,
            Err(error) => return -(error as i32),
        };
        let callout_rows = match scene_annotations::callout_rows_from_meta(
            callout_meta,
            callout_lens,
            callout_texts,
        ) {
            Ok(value) => value,
            Err(error) => return -(error as i32),
        };
        let wrapped_rows = match scene_annotations::wrapped_rows_from_meta(
            wrapped_meta,
            wrapped_lens,
            wrapped_texts,
        ) {
            Ok(value) => value,
            Err(error) => return -(error as i32),
        };
        if text_rows.len() != n_text as usize
            || attached_rows.len() != n_attached as usize
            || arrow_rows.len() != n_arrows as usize
            || callout_rows.len() != n_callouts as usize
            || wrapped_rows.len() != n_wrapped as usize
        {
            return -(AnnotationError::Length as i32);
        }
        match scene_annotations::pack_annotations(scene_annotations::AnnotationFrameInput {
            texts: &text_rows,
            attached: &attached_rows,
            arrows: &arrow_rows,
            callouts: &callout_rows,
            wrapped: &wrapped_rows,
        }) {
            Ok(bytes) => {
                if bytes.len() > out_cap {
                    return -(AnnotationError::Output as i32);
                }
                if bytes.is_empty() {
                    return 0;
                }
                let dest = std::slice::from_raw_parts_mut(out, out_cap);
                dest[..bytes.len()].copy_from_slice(&bytes);
                match i32::try_from(bytes.len()) {
                    Ok(count) => count,
                    Err(_) => -(AnnotationError::Limit as i32),
                }
            }
            Err(error) => -(error as i32),
        }
    })
}

/// Resolve a packed `XYAR` v1 envelope to the product axis range.
///
/// Writes `(lo, hi)` on success and returns 0. Hosts pack axis options,
/// per-trace column extents, and rectangle zero-baseline predicates; padding,
/// log-positive extents, polar defaults, reverse, degenerate widening, the
/// default 3% margin, and zero-baseline pinning stay in Rust. Returns `-1`
/// for a malformed envelope, `-2` for an unknown version, `-3` when the
/// envelope exceeds the trace/column budget, or `-4` when a log axis has no
/// positive finite value.
///
/// # Safety
/// `input` must address `len` readable bytes when `len` is non-zero.
/// `out_lo` and `out_hi` must be writable.
#[no_mangle]
pub unsafe extern "C" fn xyg_figure_autorange(
    input: *const u8,
    len: usize,
    out_lo: *mut f64,
    out_hi: *mut f64,
) -> i32 {
    if (len > 0 && input.is_null()) || out_lo.is_null() || out_hi.is_null() {
        return -(AutorangeError::Length as i32);
    }
    ffi_guard(-(AutorangeError::Length as i32), || {
        let bytes = if len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(input, len)
        };
        match figure_autorange(bytes) {
            Ok((lo, hi)) => {
                *out_lo = lo;
                *out_hi = hi;
                0
            }
            Err(error) => -(error as i32),
        }
    })
}

/// Expand a possibly-degenerate scalar domain the way `Figure._auto_domain`
/// does. `has_bounds == 0` writes `(0, 1)`. Returns 0 on success or `-1`
/// when an output pointer is null.
///
/// # Safety
/// `out_lo` and `out_hi` must be writable.
#[no_mangle]
pub unsafe extern "C" fn xyg_auto_domain(
    has_bounds: u32,
    lo: f64,
    hi: f64,
    out_lo: *mut f64,
    out_hi: *mut f64,
) -> i32 {
    if out_lo.is_null() || out_hi.is_null() {
        return -1;
    }
    ffi_guard(-1, || {
        let (resolved_lo, resolved_hi) = if has_bounds == 0 {
            auto_domain(None)
        } else {
            auto_domain(Some((lo, hi)))
        };
        *out_lo = resolved_lo;
        *out_hi = resolved_hi;
        0
    })
}

/// Scan one rectangle baseline/value pair for zero-baseline pinning.
/// Returns the packed predicate byte, or `0xFF` when lengths/pointers are
/// invalid. Hosts pack that byte into `XYAR`; Rust still owns the pin.
///
/// # Safety
/// When `n` is non-zero, `base` and `value` must address `n` readable f64s.
#[no_mangle]
pub unsafe extern "C" fn xyg_rect_zero_baseline_flags(
    base: *const f64,
    value: *const f64,
    n: usize,
) -> u8 {
    if n > 0 && (base.is_null() || value.is_null()) {
        return 0xFF;
    }
    ffi_guard(0xFF, || {
        let base = if n == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(base, n)
        };
        let value = if n == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(value, n)
        };
        rect_zero_baseline_flags(base, value)
    })
}

/// Compute Cartesian default gutters for the Scene-eligible export subset.
///
/// Writes `left`, `right`, `top`, `bottom` into `out_margins` (length 4) on
/// success and returns 4. `authored_padding` may be null (use compact/regular
/// defaults) or address four f64 values in `(top, right, bottom, left)` order.
/// Title, axis-label, and numeric-format buffers may be null when the matching
/// length is 0. Numeric formats are bounded UTF-8 without embedded NUL and use
/// the engine-owned `<prefix>(,).N[f|%]<suffix>` grammar; invalid grammar
/// preserves deterministic default labels.
/// `colorbar_side` is `0` for none, `1` for right, or `2` for bottom; Rust
/// reserves the bounded outer lane when present.
///
/// # Safety
/// When non-null, text buffers must address the given UTF-8 byte counts.
/// `out_margins` must address four writable f64 values.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_plot_layout(
    viewport_width: f64,
    viewport_height: f64,
    authored_padding: *const f64,
    x_kind: u32,
    x_lo: f64,
    x_hi: f64,
    x_constant: f64,
    x_mask_nonpositive: i32,
    y_kind: u32,
    y_lo: f64,
    y_hi: f64,
    y_constant: f64,
    y_mask_nonpositive: i32,
    title: *const u8,
    title_len: usize,
    x_label: *const u8,
    x_label_len: usize,
    y_label: *const u8,
    y_label_len: usize,
    x_format: *const u8,
    x_format_len: usize,
    y_format: *const u8,
    y_format_len: usize,
    colorbar_side: u32,
    out_margins: *mut f64,
) -> usize {
    if !matches!(x_mask_nonpositive, 0 | 1)
        || !matches!(y_mask_nonpositive, 0 | 1)
        || title_len > scene::MAX_SCENE_TEXT_BYTES
        || x_label_len > scene::MAX_SCENE_TEXT_BYTES
        || y_label_len > scene::MAX_SCENE_TEXT_BYTES
        || x_format_len > scene::MAX_SCENE_AXIS_FORMAT_BYTES
        || y_format_len > scene::MAX_SCENE_AXIS_FORMAT_BYTES
        || (title_len > 0 && title.is_null())
        || (x_label_len > 0 && x_label.is_null())
        || (y_label_len > 0 && y_label.is_null())
        || (x_format_len > 0 && x_format.is_null())
        || (y_format_len > 0 && y_format.is_null())
        || out_margins.is_null()
    {
        return usize::MAX;
    }
    let scale_kind = |value| match value {
        0 => Some(scene::ScaleKind::Linear),
        1 => Some(scene::ScaleKind::Log),
        2 => Some(scene::ScaleKind::SymLog),
        _ => None,
    };
    let (Some(x_kind), Some(y_kind)) = (scale_kind(x_kind), scale_kind(y_kind)) else {
        return usize::MAX;
    };
    let colorbar_side = match colorbar_side {
        0 => scene::ColorbarSide::None,
        1 => scene::ColorbarSide::Right,
        2 => scene::ColorbarSide::Bottom,
        _ => return usize::MAX,
    };
    let padding = if authored_padding.is_null() {
        None
    } else {
        let values = std::slice::from_raw_parts(authored_padding, 4);
        Some([values[0], values[1], values[2], values[3]])
    };
    let title = if title_len == 0 {
        ""
    } else {
        match std::str::from_utf8(std::slice::from_raw_parts(title, title_len)) {
            Ok(text) => text,
            Err(_) => return usize::MAX,
        }
    };
    let x_label = if x_label_len == 0 {
        ""
    } else {
        match std::str::from_utf8(std::slice::from_raw_parts(x_label, x_label_len)) {
            Ok(text) => text,
            Err(_) => return usize::MAX,
        }
    };
    let y_label = if y_label_len == 0 {
        ""
    } else {
        match std::str::from_utf8(std::slice::from_raw_parts(y_label, y_label_len)) {
            Ok(text) => text,
            Err(_) => return usize::MAX,
        }
    };
    let axis_format = |pointer: *const u8, length: usize| -> Option<Option<&str>> {
        if length == 0 {
            return Some(None);
        }
        let text = std::str::from_utf8(std::slice::from_raw_parts(pointer, length)).ok()?;
        (!text.contains('\0')).then_some(Some(text))
    };
    let (Some(x_format), Some(y_format)) = (
        axis_format(x_format, x_format_len),
        axis_format(y_format, y_format_len),
    ) else {
        return usize::MAX;
    };
    let Some(margins) = ffi_guard(None, || {
        scene::cartesian_scene_margins(scene::CartesianLayoutRequest {
            viewport_width,
            viewport_height,
            authored_padding: padding,
            title,
            x_label,
            y_label,
            x_kind,
            x_lo,
            x_hi,
            x_constant,
            x_mask_nonpositive: x_mask_nonpositive != 0,
            x_format,
            y_kind,
            y_lo,
            y_hi,
            y_constant,
            y_mask_nonpositive: y_mask_nonpositive != 0,
            y_format,
            colorbar_side,
        })
        .ok()
    }) else {
        return usize::MAX;
    };
    let out = std::slice::from_raw_parts_mut(out_margins, 4);
    out[0] = margins.0;
    out[1] = margins.1;
    out[2] = margins.2;
    out[3] = margins.3;
    4
}

/// Build canonical axis ticks.
///
/// `kind` is:
/// - `0` linear
/// - `1` base-10 log
/// - `2` category (`aux` = category count)
/// - `3` angular degrees
/// - `4` angular radians
/// - `5` time (UTC milliseconds since epoch)
/// - `6` symmetric log (`aux` = positive linear-region constant)
///
/// Returns the required tick count or `usize::MAX` for invalid arguments. The
/// labeled count and step are written only when `out_cap` is sufficient.
///
/// # Safety
/// Output buffers must each address `out_cap` writable values; scalar outputs
/// must address one writable value. Output spans must not overlap.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_axis_ticks(
    kind: u32,
    lo: f64,
    hi: f64,
    target: usize,
    aux: f64,
    out_ticks: *mut f64,
    out_labeled: *mut f64,
    out_labeled_len: *mut usize,
    out_step: *mut f64,
    out_cap: usize,
) -> usize {
    let result = ffi_guard(None, || match kind {
        0 => scene::linear_ticks(lo, hi, target).ok(),
        1 => scene::log_ticks(lo, hi, target).ok(),
        2 => {
            if !(aux.is_finite() && aux >= 1.0 && aux <= scene::MAX_SCENE_MARKS as f64) {
                return None;
            }
            scene::category_ticks(lo, hi, aux as usize, target).ok()
        }
        3 => scene::angular_ticks(lo, hi, true, target).ok(),
        4 => scene::angular_ticks(lo, hi, false, target).ok(),
        5 => scene::time_ticks(lo, hi, target).ok(),
        6 => scene::symlog_ticks(lo, hi, aux, target).ok(),
        _ => None,
    });
    let Some(result) = result else {
        return usize::MAX;
    };
    let required = result.ticks.len();
    if out_cap < required {
        return required;
    }
    if out_labeled_len.is_null()
        || out_step.is_null()
        || (required > 0 && (out_ticks.is_null() || out_labeled.is_null()))
    {
        return usize::MAX;
    }
    if required > 0 {
        std::slice::from_raw_parts_mut(out_ticks, out_cap)[..required]
            .copy_from_slice(&result.ticks);
        std::slice::from_raw_parts_mut(out_labeled, out_cap)[..result.labeled.len()]
            .copy_from_slice(&result.labeled);
    }
    *out_labeled_len = result.labeled.len();
    *out_step = result.step;
    required
}

/// Apply a canonical scene scale to a typed f64 buffer. `kind` is 0 linear,
/// 1 log, or 2 symlog. `operation` is 0 domain-to-scale coordinate, 1
/// domain-to-pixel, or 2 scale-coordinate-to-domain. Returns zero on success.
///
/// # Safety
/// Input and output must address `len` readable/writable f64 values and must
/// not overlap.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_scale_map(
    values: *const f64,
    len: usize,
    kind: u32,
    operation: u32,
    lo: f64,
    hi: f64,
    px0: f64,
    px1: f64,
    constant: f64,
    mask_nonpositive: i32,
    out: *mut f64,
) -> i32 {
    if len > scene::MAX_SCENE_MARKS
        || !matches!(mask_nonpositive, 0 | 1)
        || operation > 2
        || (len > 0 && (values.is_null() || out.is_null()))
    {
        return 1;
    }
    let kind = match kind {
        0 => scene::ScaleKind::Linear,
        1 => scene::ScaleKind::Log,
        2 => scene::ScaleKind::SymLog,
        _ => return 1,
    };
    let Ok(scale) = scene::AxisScale::new(kind, lo, hi, px0, px1, constant, mask_nonpositive != 0)
    else {
        return 1;
    };
    if len == 0 {
        return 0;
    }
    let input = std::slice::from_raw_parts(values, len);
    let output = std::slice::from_raw_parts_mut(out, len);
    ffi_guard(1, || {
        for (destination, value) in output.iter_mut().zip(input) {
            *destination = match operation {
                0 => scale.coord(*value),
                1 => scale.pixel(*value),
                _ => scale.value(*value),
            };
        }
        0
    })
}

/// Decode the optional versioned authoring envelope while accepting legacy raw
/// `XYAD` annotation bytes unchanged.
fn decode_scene_authoring_input(bytes: &[u8]) -> Option<(Option<&str>, Option<&str>, &[u8])> {
    if !bytes.starts_with(b"XYAF") {
        return Some((None, None, bytes));
    }
    if bytes.len() < 20 || u32::from_le_bytes(bytes[4..8].try_into().ok()?) != 1 {
        return None;
    }
    let x_len = u32::from_le_bytes(bytes[8..12].try_into().ok()?) as usize;
    let y_len = u32::from_le_bytes(bytes[12..16].try_into().ok()?) as usize;
    let annotation_len = u32::from_le_bytes(bytes[16..20].try_into().ok()?) as usize;
    if x_len > scene::MAX_SCENE_AXIS_FORMAT_BYTES || y_len > scene::MAX_SCENE_AXIS_FORMAT_BYTES {
        return None;
    }
    let x_end = 20usize.checked_add(x_len)?;
    let y_end = x_end.checked_add(y_len)?;
    let end = y_end.checked_add(annotation_len)?;
    if end != bytes.len() {
        return None;
    }
    fn decode_format(value: &[u8]) -> Option<Option<&str>> {
        if value.is_empty() {
            return Some(None);
        }
        let value = std::str::from_utf8(value).ok()?;
        (!value.contains('\0')).then_some(Some(value))
    }
    Some((
        decode_format(&bytes[20..x_end])?,
        decode_format(&bytes[x_end..y_end])?,
        &bytes[y_end..end],
    ))
}

/// Encode a bounded backend-neutral Scene v12 batch. Record kinds are scatter
/// (0), polyline vertex (1), and rectangle (2). Numeric output is little-endian
/// typed binary, never JSON. Optional UTF-8 title/axis-label pointers may be
/// null when the corresponding length is zero. `authored_text_annotations` may
/// carry the ABI 96 `XYAF` envelope for bounded primary-axis numeric formats;
/// this keeps the function below the 64-parameter host-binding ceiling without
/// changing Scene v25. Returns required bytes or `usize::MAX` on error.
///
/// # Safety
/// Every record input array must address `len` readable elements. The chrome
/// style pointer must address exactly `SCENE_CHROME_STYLE_INPUT_BYTES` bytes;
/// `expansion_modes` must address `len` bytes, each in the bounded ABI 104 enum;
/// each tick pointer must address its corresponding count when non-zero. Text
/// and bounded legend-input pointers must address `*_len` readable bytes when
/// non-zero. If capacity is sufficient, `out` must address `out_cap` writable
/// bytes.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_scene_batch_encode(
    viewport_width: f64,
    viewport_height: f64,
    margin_left: f64,
    margin_right: f64,
    margin_top: f64,
    margin_bottom: f64,
    x_axis_id: u64,
    x_kind: u32,
    x_lo: f64,
    x_hi: f64,
    x_constant: f64,
    x_mask_nonpositive: i32,
    y_axis_id: u64,
    y_kind: u32,
    y_lo: f64,
    y_hi: f64,
    y_constant: f64,
    y_mask_nonpositive: i32,
    chrome_style: *const u8,
    chrome_style_len: usize,
    x_major_ticks: *const f64,
    x_major_count: usize,
    x_major_auto: i32,
    x_minor_ticks: *const f64,
    x_minor_count: usize,
    y_major_ticks: *const f64,
    y_major_count: usize,
    y_major_auto: i32,
    y_minor_ticks: *const f64,
    y_minor_count: usize,
    x_tick_labels: *const u8,
    x_tick_labels_len: usize,
    y_tick_labels: *const u8,
    y_tick_labels_len: usize,
    authored_text_annotations: *const u8,
    authored_text_annotations_len: usize,
    kinds: *const u8,
    stable_ids: *const u64,
    style_refs: *const u32,
    fill_rgba: *const u8,
    stroke_rgba: *const u8,
    stroke_width: *const f64,
    style_count: usize,
    diameter: *const f64,
    symbols: *const u8,
    expansion_modes: *const u8,
    x0: *const f64,
    y0: *const f64,
    x1: *const f64,
    y1: *const f64,
    len: usize,
    title: *const u8,
    title_len: usize,
    x_label: *const u8,
    x_label_len: usize,
    y_label: *const u8,
    y_label_len: usize,
    legend_input: *const u8,
    legend_input_len: usize,
    colorbar_input: *const u8,
    colorbar_input_len: usize,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if len > scene::MAX_SCENE_MARKS
        || style_count > scene::MAX_SCENE_STYLES
        || !matches!(x_mask_nonpositive, 0 | 1)
        || !matches!(y_mask_nonpositive, 0 | 1)
        || chrome_style_len != scene::SCENE_CHROME_STYLE_INPUT_BYTES
        || chrome_style.is_null()
        || !matches!(x_major_auto, 0 | 1)
        || !matches!(y_major_auto, 0 | 1)
        || (x_major_auto == 1 && x_major_count != 0)
        || (y_major_auto == 1 && y_major_count != 0)
        || [x_major_count, x_minor_count, y_major_count, y_minor_count]
            .into_iter()
            .any(|count| count > scene::MAX_AXIS_TICKS)
        || (x_major_count > 0 && x_major_ticks.is_null())
        || (x_minor_count > 0 && x_minor_ticks.is_null())
        || (y_major_count > 0 && y_major_ticks.is_null())
        || (y_minor_count > 0 && y_minor_ticks.is_null())
        || x_tick_labels_len > scene::MAX_SCENE_TEXT_BYTES + scene::MAX_AXIS_TICKS * 4 + 12
        || y_tick_labels_len > scene::MAX_SCENE_TEXT_BYTES + scene::MAX_AXIS_TICKS * 4 + 12
        || (x_tick_labels_len > 0 && x_tick_labels.is_null())
        || (y_tick_labels_len > 0 && y_tick_labels.is_null())
        // `XYAD` carries two frames but one combined canonical label budget:
        // outer/header bytes plus the worst (all-XYAT) per-label framing.
        || authored_text_annotations_len
            > scene::MAX_SCENE_LABEL_TEXT_BYTES
                + scene::MAX_AUTHORED_TEXT_ANNOTATIONS * 24
                + 44
                + 20
                + scene::MAX_SCENE_AXIS_FORMAT_BYTES * 2
        || (authored_text_annotations_len > 0 && authored_text_annotations.is_null())
        || title_len > scene::MAX_SCENE_TEXT_BYTES
        || x_label_len > scene::MAX_SCENE_TEXT_BYTES
        || y_label_len > scene::MAX_SCENE_TEXT_BYTES
        || legend_input_len
            > scene::MAX_SCENE_LEGEND_TEXT_BYTES + scene::MAX_SCENE_LEGEND_ENTRIES * 24 + 48
        || colorbar_input_len > scene::MAX_SCENE_COLORBAR_INPUT_BYTES
        || (len > 0
            && (kinds.is_null()
                || stable_ids.is_null()
                || style_refs.is_null()
                || diameter.is_null()
                || symbols.is_null()
                || expansion_modes.is_null()
                || x0.is_null()
                || y0.is_null()
                || x1.is_null()
                || y1.is_null()))
        || (style_count > 0
            && (fill_rgba.is_null() || stroke_rgba.is_null() || stroke_width.is_null()))
        || (title_len > 0 && title.is_null())
        || (x_label_len > 0 && x_label.is_null())
        || (y_label_len > 0 && y_label.is_null())
        || (legend_input_len > 0 && legend_input.is_null())
        || (colorbar_input_len > 0 && colorbar_input.is_null())
    {
        return usize::MAX;
    }
    let scale_kind = |value| match value {
        0 => Some(scene::ScaleKind::Linear),
        1 => Some(scene::ScaleKind::Log),
        2 => Some(scene::ScaleKind::SymLog),
        _ => None,
    };
    let (Some(x_kind), Some(y_kind)) = (scale_kind(x_kind), scale_kind(y_kind)) else {
        return usize::MAX;
    };
    let Some(encoded) = ffi_guard(None, || {
        let x_tick_label_values = scene::decode_tick_labels(if x_tick_labels_len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(x_tick_labels, x_tick_labels_len)
        })
        .ok()?;
        let y_tick_label_values = scene::decode_tick_labels(if y_tick_labels_len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(y_tick_labels, y_tick_labels_len)
        })
        .ok()?;
        let authored_input = if authored_text_annotations_len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(authored_text_annotations, authored_text_annotations_len)
        };
        let (x_format, y_format, authored_text_bytes) =
            decode_scene_authoring_input(authored_input)?;
        // Final canonical gutters belong to Rust, after it has validated the
        // exact strings that all consumers will paint.  No host font/layout
        // measurement participates in this decision.
        let mut margin_left = margin_left;
        let mut margin_right = margin_right;
        let mut margin_bottom = margin_bottom;
        let visible_label_indices = |values: *const f64, count: usize, lo: f64, hi: f64| {
            if values.is_null() {
                return Vec::new();
            }
            let low = lo.min(hi);
            let high = lo.max(hi);
            std::slice::from_raw_parts(values, count)
                .iter()
                .enumerate()
                .filter_map(|(index, value)| (*value >= low && *value <= high).then_some(index))
                .collect::<Vec<_>>()
        };
        if let Some(labels) = &y_tick_label_values {
            let indices = visible_label_indices(y_major_ticks, y_major_count, y_lo, y_hi);
            let widest = indices
                .iter()
                .filter_map(|index| labels.get(*index))
                .map(|label| scene::scene_text_advance(label, 12.0))
                .fold(0.0, f64::max);
            margin_left = margin_left.max(8.0 + widest);
        }
        if let Some(labels) = &x_tick_label_values {
            let indices = visible_label_indices(x_major_ticks, x_major_count, x_lo, x_hi);
            margin_bottom = margin_bottom.max(24.0);
            if let Some(first) = indices.first().and_then(|index| labels.get(*index)) {
                margin_left = margin_left.max(8.0 + scene::scene_text_advance(first, 12.0) * 0.5);
            }
            if let Some(last) = indices.last().and_then(|index| labels.get(*index)) {
                margin_right = margin_right.max(8.0 + scene::scene_text_advance(last, 12.0) * 0.5);
            }
        }
        let layout = scene::PlotLayout::new(
            viewport_width,
            viewport_height,
            margin_left,
            margin_right,
            margin_top,
            margin_bottom,
        )
        .ok()?;
        let x_scale = scene::AxisScale::new(
            x_kind,
            x_lo,
            x_hi,
            layout.left,
            layout.right,
            x_constant,
            x_mask_nonpositive != 0,
        )
        .ok()?;
        let y_scale = scene::AxisScale::new(
            y_kind,
            y_lo,
            y_hi,
            layout.bottom,
            layout.top,
            y_constant,
            y_mask_nonpositive != 0,
        )
        .ok()?;
        let kinds = if len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(kinds, len)
        };
        let stable_ids = if len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(stable_ids, len)
        };
        let style_refs = if len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(style_refs, len)
        };
        let fill_rgba = if style_count == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(fill_rgba, style_count * 4)
        };
        let stroke_rgba = if style_count == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(stroke_rgba, style_count * 4)
        };
        let stroke_width = if style_count == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(stroke_width, style_count)
        };
        let diameter = if len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(diameter, len)
        };
        let symbols = if len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(symbols, len)
        };
        let f64s = |pointer| {
            if len == 0 {
                &[]
            } else {
                std::slice::from_raw_parts(pointer, len)
            }
        };
        let source_x0 = f64s(x0);
        let source_y0 = f64s(y0);
        let source_x1 = f64s(x1);
        let source_y1 = f64s(y1);
        let expansion_modes = if len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(expansion_modes, len)
        };
        let records = scene::expand_scene_records(
            scene::SceneExpansionInput {
                kinds,
                stable_ids,
                style_refs,
                diameter,
                symbols,
                x0: source_x0,
                y0: source_y0,
                x1: source_x1,
                y1: source_y1,
                expansion_modes,
            },
            x_scale,
            y_scale,
        )
        .ok()?;
        let title = if title_len == 0 {
            ""
        } else {
            std::str::from_utf8(std::slice::from_raw_parts(title, title_len)).ok()?
        };
        let x_label = if x_label_len == 0 {
            ""
        } else {
            std::str::from_utf8(std::slice::from_raw_parts(x_label, x_label_len)).ok()?
        };
        let y_label = if y_label_len == 0 {
            ""
        } else {
            std::str::from_utf8(std::slice::from_raw_parts(y_label, y_label_len)).ok()?
        };
        let text = scene::SceneChromeText::from_parts(title, x_label, y_label).ok()?;
        let legend_bytes = if legend_input_len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(legend_input, legend_input_len)
        };
        let legend = scene::SceneLegend::from_input(legend_bytes, style_count).ok()?;
        let colorbar_bytes = if colorbar_input_len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(colorbar_input, colorbar_input_len)
        };
        let colorbar = scene::SceneColorbar::from_input(colorbar_bytes).ok()?;
        let tick_values = |pointer: *const f64, count: usize| {
            if count == 0 {
                Vec::new()
            } else {
                std::slice::from_raw_parts(pointer, count).to_vec()
            }
        };
        let mut chrome = scene::SceneChromeStyle::from_style_input(
            std::slice::from_raw_parts(chrome_style, chrome_style_len),
            (x_major_auto == 0).then(|| tick_values(x_major_ticks, x_major_count)),
            tick_values(x_minor_ticks, x_minor_count),
            (y_major_auto == 0).then(|| tick_values(y_major_ticks, y_major_count)),
            tick_values(y_minor_ticks, y_minor_count),
        )
        .ok()?;
        chrome.x_tick_labels = x_tick_label_values;
        chrome.y_tick_labels = y_tick_label_values;
        scene::resolve_numeric_tick_formats(
            layout,
            x_scale,
            y_scale,
            &mut chrome,
            x_format,
            y_format,
        )
        .ok()?;
        let chrome = chrome.validated().ok()?;
        let batch = scene::SceneBatch::new_with_decorations_colorbar(
            layout,
            x_axis_id,
            y_axis_id,
            x_scale,
            y_scale,
            chrome,
            text,
            legend,
            colorbar,
            Vec::new(),
            &records.kinds,
            &records.stable_ids,
            &records.style_refs,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            &records.diameter,
            &records.symbols,
            &records.x0,
            &records.y0,
            &records.x1,
            &records.y1,
        )
        .ok()?;
        batch
            .with_authored_annotations(authored_text_bytes)
            .ok()
            .map(|batch| batch.encode())
    }) else {
        return usize::MAX;
    };
    let required = encoded.len();
    if out_cap < required {
        return required;
    }
    if required > 0 && out.is_null() {
        return usize::MAX;
    }
    std::slice::from_raw_parts_mut(out, out_cap)[..required].copy_from_slice(&encoded);
    required
}

/// Serialize one validated Scene v12 document as a complete SVG image.
/// Returns required bytes or `usize::MAX` for malformed input.
///
/// # Safety
/// `encoded` addresses `encoded_len` readable bytes. When capacity suffices,
/// `out` addresses `out_cap` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_svg(
    encoded: *const u8,
    encoded_len: usize,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if encoded.is_null() || encoded_len == 0 {
        return usize::MAX;
    }
    let Some(svg) = ffi_guard(None, || {
        scene::SceneDocument::decode(std::slice::from_raw_parts(encoded, encoded_len))
            .ok()
            .map(|document| document.to_svg().into_bytes())
    }) else {
        return usize::MAX;
    };
    let required = svg.len();
    if out_cap < required {
        return required;
    }
    if out.is_null() {
        return usize::MAX;
    }
    std::slice::from_raw_parts_mut(out, out_cap)[..required].copy_from_slice(&svg);
    required
}

/// Convert an xy-generated closed-subset SVG into a single-page vector PDF.
/// Returns required bytes, or `usize::MAX` for unsupported/malformed SVG. On
/// error, when `out_cap > 0` and `out` is non-null, the buffer receives the
/// UTF-8 `unsupported SVG feature: …` diagnostic (truncated, not NUL-padded).
///
/// # Safety
/// `svg` addresses `svg_len` readable bytes. When capacity suffices, `out`
/// addresses `out_cap` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_svg_to_pdf(
    svg: *const u8,
    svg_len: usize,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if svg.is_null() && svg_len > 0 {
        return usize::MAX;
    }
    let bytes = if svg_len == 0 {
        &[]
    } else {
        std::slice::from_raw_parts(svg, svg_len)
    };
    let Ok(text) = std::str::from_utf8(bytes) else {
        write_pdf_error(out, out_cap, "unsupported SVG feature: unparseable XML");
        return usize::MAX;
    };
    match ffi_guard(
        Err("unsupported SVG feature: unparseable XML".into()),
        || pdf::svg_to_pdf(text),
    ) {
        Ok(pdf) => {
            let required = pdf.len();
            if out_cap < required {
                return required;
            }
            if required > 0 && out.is_null() {
                return usize::MAX;
            }
            if required > 0 {
                std::slice::from_raw_parts_mut(out, out_cap)[..required].copy_from_slice(&pdf);
            }
            required
        }
        Err(message) => {
            write_pdf_error(out, out_cap, &message);
            usize::MAX
        }
    }
}

fn write_pdf_error(out: *mut u8, out_cap: usize, message: &str) {
    write_utf8_error(out, out_cap, message);
}

fn write_utf8_error(out: *mut u8, out_cap: usize, message: &str) {
    if out.is_null() || out_cap == 0 {
        return;
    }
    let bytes = message.as_bytes();
    let n = bytes.len().min(out_cap.saturating_sub(1));
    unsafe {
        let buf = std::slice::from_raw_parts_mut(out, out_cap);
        buf[..n].copy_from_slice(&bytes[..n]);
        buf[n] = 0;
    }
}

unsafe fn encode_image_output(
    required: usize,
    out: *mut u8,
    out_cap: usize,
    bytes: &[u8],
) -> usize {
    if out_cap < required {
        return required;
    }
    if required > 0 && out.is_null() {
        return usize::MAX;
    }
    if required > 0 {
        std::slice::from_raw_parts_mut(out, out_cap)[..required].copy_from_slice(bytes);
    }
    required
}

/// Encode packed RGB or RGBA8 pixels as a baseline sequential JFIF JPEG.
/// Returns required bytes, or `usize::MAX` on invalid input. On error, when
/// `out_cap > 0` and `out` is non-null, the buffer receives a UTF-8 diagnostic.
///
/// # Safety
/// `pixels` addresses `n` readable bytes. When capacity suffices, `out`
/// addresses `out_cap` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_encode_jpeg(
    pixels: *const u8,
    n: usize,
    width: usize,
    height: usize,
    channels: usize,
    quality: i32,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if pixels.is_null() && n > 0 {
        return usize::MAX;
    }
    let bytes = if n == 0 {
        &[]
    } else {
        std::slice::from_raw_parts(pixels, n)
    };
    match ffi_guard(Err("invalid JPEG input".into()), || {
        jpeg::encode_jpeg(bytes, width, height, channels, quality)
    }) {
        Ok(jpeg) => encode_image_output(jpeg.len(), out, out_cap, &jpeg),
        Err(message) => {
            write_utf8_error(out, out_cap, &message);
            usize::MAX
        }
    }
}

/// Encode packed RGB or RGBA8 pixels as a lossless VP8L WebP.
/// Returns required bytes, or `usize::MAX` on invalid input. On error, when
/// `out_cap > 0` and `out` is non-null, the buffer receives a UTF-8 diagnostic.
///
/// # Safety
/// `pixels` addresses `n` readable bytes. When capacity suffices, `out`
/// addresses `out_cap` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_encode_webp(
    pixels: *const u8,
    n: usize,
    width: usize,
    height: usize,
    channels: usize,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if pixels.is_null() && n > 0 {
        return usize::MAX;
    }
    let bytes = if n == 0 {
        &[]
    } else {
        std::slice::from_raw_parts(pixels, n)
    };
    match ffi_guard(Err("invalid WebP input".into()), || {
        webp::encode_webp(bytes, width, height, channels)
    }) {
        Ok(webp) => encode_image_output(webp.len(), out, out_cap, &webp),
        Err(message) => {
            write_utf8_error(out, out_cap, &message);
            usize::MAX
        }
    }
}

/// Encode packed RGB or RGBA8 pixels as a PNG (filter-0, zlib).
/// `mode` 0 auto-selects indexed palette when ≤256 unique colors, else
/// truecolor. `mode` 1 forces RGBA8 truecolor. `compression` is 0..=9.
/// Returns required bytes, or `usize::MAX` on invalid input. On error, when
/// `out_cap > 0` and `out` is non-null, the buffer receives a UTF-8 diagnostic.
///
/// # Safety
/// `pixels` addresses `n` readable bytes. When capacity suffices, `out`
/// addresses `out_cap` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_encode_png(
    pixels: *const u8,
    n: usize,
    width: usize,
    height: usize,
    channels: usize,
    mode: i32,
    compression: i32,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if pixels.is_null() && n > 0 {
        return usize::MAX;
    }
    let bytes = if n == 0 {
        &[]
    } else {
        std::slice::from_raw_parts(pixels, n)
    };
    match ffi_guard(Err("invalid PNG input".into()), || {
        png_encode::encode_png(bytes, width, height, channels, mode, compression)
    }) {
        Ok(png) => encode_image_output(png.len(), out, out_cap, &png),
        Err(message) => {
            write_utf8_error(out, out_cap, &message);
            usize::MAX
        }
    }
}

/// Compile one validated Scene v12 document to the existing raster display-list
/// command stream. Returns required bytes or `usize::MAX` on error.
///
/// # Safety
/// Pointer contracts match `xyg_scene_svg`.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_raster_commands(
    encoded: *const u8,
    encoded_len: usize,
    scale: f64,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if encoded.is_null() || encoded_len == 0 {
        return usize::MAX;
    }
    let Some(commands) = ffi_guard(None, || {
        scene::SceneDocument::decode(std::slice::from_raw_parts(encoded, encoded_len))
            .ok()?
            .to_raster_commands(scale)
            .ok()
    }) else {
        return usize::MAX;
    };
    let required = commands.len();
    if out_cap < required {
        return required;
    }
    if out.is_null() {
        return usize::MAX;
    }
    std::slice::from_raw_parts_mut(out, out_cap)[..required].copy_from_slice(&commands);
    required
}

/// Lower one validated Scene v12 document to the canonical browser painter-v9
/// byte stream. Returns required bytes or `usize::MAX` on error.
///
/// # Safety
/// Pointer contracts match `xyg_scene_svg`.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_browser_painter(
    encoded: *const u8,
    encoded_len: usize,
    max_bytes: usize,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if encoded.is_null() || encoded_len == 0 {
        return usize::MAX;
    }
    let Some(painter) = ffi_guard(None, || {
        scene::SceneDocument::decode(std::slice::from_raw_parts(encoded, encoded_len))
            .ok()?
            .to_browser_painter(max_bytes)
            .ok()
    }) else {
        return usize::MAX;
    };
    let required = painter.len();
    if out_cap < required {
        return required;
    }
    if out.is_null() {
        return usize::MAX;
    }
    std::slice::from_raw_parts_mut(out, out_cap)[..required].copy_from_slice(&painter);
    required
}
const FACTORIZE_CAPACITY_EXCEEDED: usize = usize::MAX - 1;

#[no_mangle]
pub extern "C" fn xyg_abi_version() -> u32 {
    ABI_VERSION
}

/// Maximum exact stable IDs accepted by one temporal coordination selection.
#[no_mangle]
pub extern "C" fn xyg_temporal_selection_limit() -> u64 {
    temporal_controller::MAX_COORDINATED_SELECTION_IDS as u64
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

/// Build and serialize a canonical built-in scatter scene as an SVG fragment.
/// Returns the required byte count, or `usize::MAX` for invalid inputs. When
/// `out_cap` is too small no bytes are written, allowing callers to retry.
///
/// RGBA buffers contain four bytes per mark. `visible` may be null to keep all
/// marks, otherwise it contains one byte per mark (zero hides the mark).
///
/// # Safety
/// Every non-null input must address the documented number of readable values.
/// When `out_cap` is sufficient, `out` must address `out_cap` writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_scatter_svg(
    x: *const f64,
    y: *const f64,
    diameter: *const f64,
    fill_rgba: *const u8,
    stroke_rgba: *const u8,
    stroke_width: *const f64,
    symbols: *const u8,
    visible: *const u8,
    fill_css: *const u8,
    fill_css_len: usize,
    stroke_css: *const u8,
    stroke_css_len: usize,
    len: usize,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if len > scene::MAX_SCENE_MARKS {
        return usize::MAX;
    }
    let rgba_len = match len.checked_mul(4) {
        Some(value) => value,
        None => return usize::MAX,
    };
    if len > 0
        && (x.is_null()
            || y.is_null()
            || diameter.is_null()
            || fill_rgba.is_null()
            || stroke_rgba.is_null()
            || stroke_width.is_null()
            || symbols.is_null())
    {
        return usize::MAX;
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
    let diameter = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(diameter, len)
    };
    let fill_rgba = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(fill_rgba, rgba_len)
    };
    let stroke_rgba = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(stroke_rgba, rgba_len)
    };
    let stroke_width = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(stroke_width, len)
    };
    let symbols = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(symbols, len)
    };
    let visible = if visible.is_null() {
        None
    } else {
        Some(std::slice::from_raw_parts(visible, len))
    };
    let fill_css = if fill_css_len == 0 {
        None
    } else if fill_css.is_null() {
        return usize::MAX;
    } else {
        match std::str::from_utf8(std::slice::from_raw_parts(fill_css, fill_css_len)) {
            Ok(value) => Some(value),
            Err(_) => return usize::MAX,
        }
    };
    let stroke_css = if stroke_css_len == 0 {
        None
    } else if stroke_css.is_null() {
        return usize::MAX;
    } else {
        match std::str::from_utf8(std::slice::from_raw_parts(stroke_css, stroke_css_len)) {
            Ok(value) => Some(value),
            Err(_) => return usize::MAX,
        }
    };
    let Some(svg) = ffi_guard(None, || {
        scene::ScatterScene::new(
            x,
            y,
            diameter,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            symbols,
            visible,
            fill_css,
            stroke_css,
        )
        .ok()
        .map(|scene| scene.to_svg())
    }) else {
        return usize::MAX;
    };
    let required = svg.len();
    if out_cap < required {
        return required;
    }
    if required > 0 && out.is_null() {
        return usize::MAX;
    }
    if required > 0 {
        std::slice::from_raw_parts_mut(out, out_cap)[..required].copy_from_slice(svg.as_bytes());
    }
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

/// Resolve a CSS color to RGBA8 the way Scene and native raster paint do.
/// `none` is transparent. Unparseable, passthrough, and `currentColor` use
/// the static blue-gray fallback so a mark is never invisible. `opacity`
/// multiplies the alpha channel. Returns 0 on success or `-1` when
/// `out_rgba` is null or `css` is not UTF-8.
///
/// # Safety
/// `css` must address `len` readable bytes when `len` is non-zero.
/// `out_rgba` must address 4 writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_css_color_rgba(
    css: *const u8,
    len: usize,
    opacity: f32,
    out_rgba: *mut u8,
) -> i32 {
    if out_rgba.is_null() || (len > 0 && css.is_null()) {
        return -1;
    }
    ffi_guard(-1, || {
        let bytes = if len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(css, len)
        };
        let Ok(value) = std::str::from_utf8(bytes) else {
            return -1;
        };
        let rgba = css::color_rgba8(value, opacity);
        std::slice::from_raw_parts_mut(out_rgba, 4).copy_from_slice(&rgba);
        0
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

/// Uniformly binned empirical CDF. Returns the compact written point count or
/// `usize::MAX` when the inputs are invalid. Results are committed only after
/// the complete Rust-owned result validates, so failures leave outputs intact.
///
/// # Safety
/// `values` addresses `len` readable f64s. Both outputs address `capacity`
/// writable, non-overlapping f64s. `use_range` is exactly zero or one.
#[no_mangle]
pub unsafe extern "C" fn xyg_binned_ecdf(
    values: *const f64,
    len: usize,
    n_bins: usize,
    lo: f64,
    hi: f64,
    use_range: i32,
    out_x: *mut f64,
    out_cumulative: *mut f64,
    capacity: usize,
) -> usize {
    let Some(required) = n_bins.checked_add(1) else {
        return usize::MAX;
    };
    let Some(output_bytes) = capacity.checked_mul(std::mem::size_of::<f64>()) else {
        return usize::MAX;
    };
    let x_start = out_x as usize;
    let cumulative_start = out_cumulative as usize;
    let Some(x_end) = x_start.checked_add(output_bytes) else {
        return usize::MAX;
    };
    let Some(cumulative_end) = cumulative_start.checked_add(output_bytes) else {
        return usize::MAX;
    };
    let outputs_overlap = x_start < cumulative_end && cumulative_start < x_end;
    if len == 0
        || values.is_null()
        || n_bins == 0
        || n_bins > stats::MAX_HISTOGRAM_BINS
        || !matches!(use_range, 0 | 1)
        || capacity < required
        || out_x.is_null()
        || out_cumulative.is_null()
        || outputs_overlap
    {
        return usize::MAX;
    }
    let values = std::slice::from_raw_parts(values, len);
    let range = (use_range == 1).then_some((lo, hi));
    let Some(result) = ffi_guard(None, || stats::binned_ecdf(values, n_bins, range)) else {
        return usize::MAX;
    };
    let written = result.x.len();
    debug_assert_eq!(written, result.cumulative.len());
    debug_assert!(written <= required);
    std::ptr::copy_nonoverlapping(result.x.as_ptr(), out_x, written);
    std::ptr::copy_nonoverlapping(result.cumulative.as_ptr(), out_cumulative, written);
    written
}

/// Authored-edge 1-D histogram. Returns the bin count or `usize::MAX` when the
/// inputs are invalid. Results are committed only after the complete Rust-owned
/// result validates, so failures leave `out_counts` intact.
///
/// # Safety
/// `values` addresses `len` readable f64s, or is unused when `len` is zero.
/// `edges` addresses `edge_len` readable f64s. `out_counts` addresses
/// `edge_len - 1` writable f64s that do not overlap either input. `density`
/// and `cumulative` are exactly zero or one.
#[no_mangle]
pub unsafe extern "C" fn xyg_histogram_bins(
    values: *const f64,
    len: usize,
    edges: *const f64,
    edge_len: usize,
    density: i32,
    cumulative: i32,
    out_counts: *mut f64,
) -> usize {
    let Some(n_bins) = edge_len.checked_sub(1) else {
        return usize::MAX;
    };
    let Some(edge_bytes) = edge_len.checked_mul(std::mem::size_of::<f64>()) else {
        return usize::MAX;
    };
    let Some(count_bytes) = n_bins.checked_mul(std::mem::size_of::<f64>()) else {
        return usize::MAX;
    };
    let Some(value_bytes) = len.checked_mul(std::mem::size_of::<f64>()) else {
        return usize::MAX;
    };
    let values_start = values as usize;
    let edges_start = edges as usize;
    let counts_start = out_counts as usize;
    let values_end = values_start.saturating_add(value_bytes);
    let Some(edges_end) = edges_start.checked_add(edge_bytes) else {
        return usize::MAX;
    };
    let Some(counts_end) = counts_start.checked_add(count_bytes) else {
        return usize::MAX;
    };
    let values_overlap =
        len > 0 && !values.is_null() && values_start < counts_end && counts_start < values_end;
    let edges_overlap = edges_start < counts_end && counts_start < edges_end;
    if n_bins == 0
        || n_bins > stats::MAX_HISTOGRAM_BINS
        || edges.is_null()
        || out_counts.is_null()
        || !matches!(density, 0 | 1)
        || !matches!(cumulative, 0 | 1)
        || values_overlap
        || edges_overlap
        || (len > 0 && values.is_null())
    {
        return usize::MAX;
    }
    let values = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(values, len)
    };
    let edges = std::slice::from_raw_parts(edges, edge_len);
    let Some(result) = ffi_guard(None, || {
        stats::histogram_bins(values, edges, density != 0, cumulative != 0)
    }) else {
        return usize::MAX;
    };
    debug_assert_eq!(result.len(), n_bins);
    std::ptr::copy_nonoverlapping(result.as_ptr(), out_counts, n_bins);
    n_bins
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
/// `xyg.lod.hash_row_ids` thresholding, fused into one pass.
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
/// per-category NumPy reference in `xyg.lod` (parity-tested), fused
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

// -- Phase-4 tile store (LOD doc §4 items 10–12, dossier §32b, roadmap D1–D7):
// disk-resident (level, tx, ty) 256² tiles behind their own opaque handles.

/// Snapshot a live pyramid into a disk tile store (one `XYTS` spill file per
/// pyramid, roadmap D1). Returns a nonzero store handle to release with
/// `xyg_tile_store_free`, or 0 on a stale pyramid handle / I/O failure. The
/// pyramid stays live and independent; the host frees it to reclaim the RAM
/// the spill exists to save. Nothing is resident after the snapshot — tiles
/// fault in on demand under the process-wide budget (D2–D3).
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
#[cfg(not(target_os = "emscripten"))]
pub unsafe extern "C" fn xyg_pyramid_spill(handle: u64) -> u64 {
    ffi_guard(0, || {
        match tiles::reg_with(handle, tile_store::TileStore::spill) {
            Some(Ok(store)) => tile_store::reg_insert(store),
            _ => 0,
        }
    })
}

/// Copy one tile's planes into caller buffers: `out_counts` receives the
/// 256² u32 count cells; `out_color` (nullable for count-only reads) the
/// 256² `[r, g, b, a]` u16 mean-color cells. Levels index 0 = finest,
/// matching `xyg_pyramid_compose` level reporting; tiles are row-major
/// `(ty, tx)` over `ceil(dim/256)` per side. 1 on success, 0 for a stale
/// handle, an out-of-range key, or a color request on a count-only store.
/// # Safety
/// `out_counts` must address 65 536 writable u32s; `out_color`, when
/// non-null, 65 536 × 4 writable u16s.
#[no_mangle]
#[cfg(not(target_os = "emscripten"))]
pub unsafe extern "C" fn xyg_tile_store_fetch(
    store: u64,
    level: u32,
    tx: u32,
    ty: u32,
    out_counts: *mut u32,
    out_color: *mut u16,
) -> i32 {
    if out_counts.is_null() {
        return 0;
    }
    let cells = tile_store::TILE_DIM * tile_store::TILE_DIM;
    let out_counts = std::slice::from_raw_parts_mut(out_counts, cells);
    let out_color = if out_color.is_null() {
        None
    } else {
        Some(std::slice::from_raw_parts_mut(
            out_color as *mut [u16; 4],
            cells,
        ))
    };
    ffi_guard(0, || {
        match tile_store::reg_with(store, |s| {
            s.fetch_into(level, tx, ty, out_counts, out_color)
        }) {
            Some(Ok(true)) => 1,
            _ => 0,
        }
    })
}

/// Compose the window from spilled tiles into a w×h grid — the tile-store
/// counterpart of `xyg_pyramid_compose`, bit-identical to it for the same
/// pyramid. Returns the level used (>= 0), -1 on stale handle/bad args or
/// I/O failure, -2 when the window outresolves the store (caller re-bins
/// exactly and discloses it, §28).
/// # Safety
/// `out` must point to `w * h` writable f32s.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
#[cfg(not(target_os = "emscripten"))]
pub unsafe extern "C" fn xyg_tile_store_compose(
    store: u64,
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
        match tile_store::reg_with(store, |s| {
            s.compose(lo_x, hi_x, lo_y, hi_y, w, h, max_upsample, out)
        }) {
            Some(Ok(Some(level))) => level as i32,
            Some(Ok(None)) => -2,
            _ => -1,
        }
    })
}

/// `xyg_tile_store_compose` plus the mean-color plane — the tile-store
/// counterpart of `xyg_pyramid_compose_color`, bit-identical to it. Returns
/// the level used (>= 0), -1 for bad arguments/stale handle/I/O failure, -2
/// when the window outresolves the store OR the store carries no color
/// planes — the caller re-bins exactly either way.
/// # Safety
/// `out` must address `w*h` writable f32s and `out_rgba` `w*h*4` writable bytes.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
#[cfg(not(target_os = "emscripten"))]
pub unsafe extern "C" fn xyg_tile_store_compose_color(
    store: u64,
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
    let max_upsample = max_upsample.max(1);
    let out = std::slice::from_raw_parts_mut(out, out_len);
    let out_rgba = std::slice::from_raw_parts_mut(out_rgba, out_len * 4);
    ffi_guard(-1, || {
        match tile_store::reg_with(store, |s| {
            s.compose_color(lo_x, hi_x, lo_y, hi_y, w, h, max_upsample, out, out_rgba)
        }) {
            Some(Ok(Some(level))) => level as i32,
            Some(Ok(None)) => -2,
            _ => -1,
        }
    })
}

/// Increment a count-only tile store from an appended point batch: touched
/// tiles fault in, increment, and are marked dirty (write-back on eviction),
/// so the composed result equals a from-scratch rebuild bit-for-bit (D4).
/// Returns 1 when applied; 0 for a stale handle, invalid pointers/lengths, a
/// colored store (refuse-and-rebuild stands), or a finite point outside the
/// store's original domain (domain growth invalidates the whole store — the
/// caller frees and respills). A rejected batch never partially mutates.
/// # Safety
/// `x`/`y` must point to `len` readable f64s (or may be null when `len == 0`).
#[no_mangle]
#[cfg(not(target_os = "emscripten"))]
pub unsafe extern "C" fn xyg_tile_store_append(
    store: u64,
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
        match tile_store::reg_with(store, |s| s.append(x, y)) {
            Some(Ok(true)) => 1,
            _ => 0,
        }
    })
}

/// Residency stats for §28 recording (`tiles: {hit, miss, resident_bytes,
/// spilled_bytes, budget_bytes, over_budget}` on tile-served replies, D3).
/// Fills `out` with six u64s in that order: cumulative fetch hits and misses
/// for this store, process-wide RAM-resident tile bytes (what the budget
/// governs, index metadata included per §27), this store's spill-file bytes,
/// the process-wide budget, and 1 when the last compose ran over budget
/// (pinned working set alone exceeded it) else 0. 1 on success, 0 on a
/// stale handle.
/// # Safety
/// `out` must address 6 writable u64s.
#[no_mangle]
#[cfg(not(target_os = "emscripten"))]
pub unsafe extern "C" fn xyg_tile_store_stats(store: u64, out: *mut u64) -> i32 {
    if out.is_null() {
        return 0;
    }
    let out = std::slice::from_raw_parts_mut(out, 6);
    ffi_guard(0, || match tile_store::reg_with(store, |s| s.stats()) {
        Some((hits, misses, resident, spilled, budget, over)) => {
            out[0] = hits;
            out[1] = misses;
            out[2] = resident;
            out[3] = spilled;
            out[4] = budget;
            out[5] = u64::from(over);
            1
        }
        None => 0,
    })
}

/// Set the process-wide resident-tile byte budget (`PYRAMID_RESIDENT_BYTES`,
/// D2 — one pool across all stores; hosts mirror the config knob here).
/// `bytes == 0` restores the 512 MiB default. Always returns 1.
/// # Safety
/// No pointer arguments.
#[no_mangle]
#[cfg(not(target_os = "emscripten"))]
pub unsafe extern "C" fn xyg_tile_budget_set(bytes: u64) -> i32 {
    ffi_guard(0, || {
        tile_store::budget_set(bytes);
        1
    })
}

/// Release a tile store: evicts everything and deletes its spill file (§27 —
/// the store is a rebuildable cache with process-scoped lifetime). 1 if it
/// existed, 0 for stale/unknown handles.
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
#[cfg(not(target_os = "emscripten"))]
pub unsafe extern "C" fn xyg_tile_store_free(store: u64) -> i32 {
    ffi_guard(0, || if tile_store::reg_remove(store) { 1 } else { 0 })
}

// Pyodide cannot provide the native filesystem-backed tile store, but the
// shared generated ABI must remain loadable. Export fail-closed stubs rather
// than omitting symbols and making every otherwise-supported kernel unusable.
#[cfg(target_os = "emscripten")]
mod wasm_tile_store_stubs {
    #[export_name = "xyg_pyramid_spill"]
    pub unsafe extern "C" fn pyramid_spill(_handle: u64) -> u64 {
        0
    }

    #[export_name = "xyg_tile_store_fetch"]
    pub unsafe extern "C" fn tile_store_fetch(
        _store: u64,
        _level: u32,
        _tx: u32,
        _ty: u32,
        _out_counts: *mut u32,
        _out_color: *mut u16,
    ) -> i32 {
        0
    }

    #[export_name = "xyg_tile_store_compose"]
    pub unsafe extern "C" fn tile_store_compose(
        _store: u64,
        _lo_x: f64,
        _hi_x: f64,
        _lo_y: f64,
        _hi_y: f64,
        _w: usize,
        _h: usize,
        _max_upsample: usize,
        _out: *mut f32,
    ) -> i32 {
        -1
    }

    #[export_name = "xyg_tile_store_compose_color"]
    pub unsafe extern "C" fn tile_store_compose_color(
        _store: u64,
        _lo_x: f64,
        _hi_x: f64,
        _lo_y: f64,
        _hi_y: f64,
        _w: usize,
        _h: usize,
        _max_upsample: usize,
        _out: *mut f32,
        _out_rgba: *mut u8,
    ) -> i32 {
        -1
    }

    #[export_name = "xyg_tile_store_append"]
    pub unsafe extern "C" fn tile_store_append(
        _store: u64,
        _x: *const f64,
        _y: *const f64,
        _len: usize,
    ) -> i32 {
        0
    }

    #[export_name = "xyg_tile_store_stats"]
    pub unsafe extern "C" fn tile_store_stats(_store: u64, _out: *mut u64) -> i32 {
        0
    }

    #[export_name = "xyg_tile_budget_set"]
    pub unsafe extern "C" fn tile_budget_set(_bytes: u64) -> i32 {
        0
    }

    #[export_name = "xyg_tile_store_free"]
    pub unsafe extern "C" fn tile_store_free(_store: u64) -> i32 {
        0
    }

    #[export_name = "xyg_chunked_columns_open"]
    pub unsafe extern "C" fn chunked_columns_open(_path: *const u8, _path_len: usize) -> u64 {
        0
    }

    #[export_name = "xyg_chunked_columns_cancel_before"]
    pub extern "C" fn chunked_columns_cancel_before(_store: u64, _generation: u64) -> i32 {
        0
    }

    #[export_name = "xyg_chunked_columns_rows"]
    pub extern "C" fn chunked_columns_rows(_store: u64) -> u64 {
        u64::MAX
    }

    #[export_name = "xyg_chunked_columns_overview"]
    pub unsafe extern "C" fn chunked_columns_overview(
        _store: u64,
        _max_points: usize,
        _out_rows: *mut u64,
        _out_x: *mut f64,
        _out_y: *mut f64,
        _out_stats: *mut u64,
    ) -> usize {
        usize::MAX
    }

    #[export_name = "xyg_chunked_columns_read"]
    pub unsafe extern "C" fn chunked_columns_read(
        _store: u64,
        _x0: f64,
        _x1: f64,
        _y0: f64,
        _y1: f64,
        _use_y: i32,
        _budget_bytes: u64,
        _generation: u64,
        _out_x: *mut f64,
        _out_y: *mut f64,
        _capacity: usize,
        _out_stats: *mut u64,
    ) -> usize {
        usize::MAX
    }

    #[export_name = "xyg_chunked_columns_read_page"]
    pub unsafe extern "C" fn chunked_columns_read_page(
        _store: u64,
        _x0: f64,
        _x1: f64,
        _y0: f64,
        _y1: f64,
        _use_y: i32,
        _budget_bytes: u64,
        _generation: u64,
        _cursor: u32,
        _out_x: *mut f64,
        _out_y: *mut f64,
        _capacity: usize,
        _out_stats: *mut u64,
    ) -> usize {
        usize::MAX
    }

    #[export_name = "xyg_chunked_columns_free"]
    pub extern "C" fn chunked_columns_free(_store: u64) -> i32 {
        0
    }
}

/// Open a checked local XYGC canonical-column artifact. Returns a nonzero
/// handle, or zero for invalid UTF-8, missing, partial or corrupt artifacts.
///
/// # Safety
/// `path` must address `path_len` readable bytes when `path_len > 0`.
#[cfg(not(target_os = "emscripten"))]
#[no_mangle]
pub unsafe extern "C" fn xyg_chunked_columns_open(path: *const u8, path_len: usize) -> u64 {
    ffi_guard(0, || {
        if path.is_null() || path_len == 0 {
            return 0;
        }
        let bytes = std::slice::from_raw_parts(path, path_len);
        let Ok(text) = std::str::from_utf8(bytes) else {
            return 0;
        };
        chunked_columns::reg_open(std::path::Path::new(text)).unwrap_or(0)
    })
}

/// Set the newest viewport generation. An in-flight older read observes this
/// between chunk reads and fails closed rather than publishing stale data.
#[cfg(not(target_os = "emscripten"))]
#[no_mangle]
pub extern "C" fn xyg_chunked_columns_cancel_before(store: u64, generation: u64) -> i32 {
    ffi_guard(0, || match chunked_columns::reg_get(store) {
        Some(s) => {
            s.set_generation(generation);
            1
        }
        None => 0,
    })
}

/// Return the canonical row count, or `u64::MAX` for a stale handle.
#[cfg(not(target_os = "emscripten"))]
#[no_mangle]
pub extern "C" fn xyg_chunked_columns_rows(store: u64) -> u64 {
    ffi_guard(u64::MAX, || {
        chunked_columns::reg_get(store).map_or(u64::MAX, |s| s.rows())
    })
}

/// Copy the precomputed, screen-bounded overview without reading canonical
/// detail rows. `out_stats` receives available overview points and source row
/// count. Returns points written or `usize::MAX` for an invalid request.
///
/// # Safety
/// Each output pointer must address `max_points` writable values and
/// `out_stats` must address two writable u64 values.
#[cfg(not(target_os = "emscripten"))]
#[no_mangle]
pub unsafe extern "C" fn xyg_chunked_columns_overview(
    store: u64,
    max_points: usize,
    out_rows: *mut u64,
    out_x: *mut f64,
    out_y: *mut f64,
    out_stats: *mut u64,
) -> usize {
    ffi_guard(usize::MAX, || {
        if max_points == 0
            || out_rows.is_null()
            || out_x.is_null()
            || out_y.is_null()
            || out_stats.is_null()
        {
            return usize::MAX;
        }
        let Some(s) = chunked_columns::reg_get(store) else {
            return usize::MAX;
        };
        let Ok(read) = s.overview(max_points) else {
            return usize::MAX;
        };
        for (index, point) in read.points.iter().enumerate() {
            *out_rows.add(index) = point.row;
            *out_x.add(index) = point.x;
            *out_y.add(index) = point.y;
        }
        let stats = std::slice::from_raw_parts_mut(out_stats, 2);
        stats[0] = u64::from(read.available);
        stats[1] = read.source_rows;
        read.points.len()
    })
}

/// Read exact rows matching an x/y viewport under a hard byte budget.
/// `out_stats[0..6]` receives generation, first chunk, chunks considered,
/// chunks read, bytes read and a stable error code (0 success, 1 I/O,
/// 2 corrupt, 3 bounds, 4 budget, 5 cancelled, 6 output capacity). Returns rows written, or `usize::MAX` on any
/// invalid/corrupt/cancelled/out-of-budget request. Hosts may retry with a
/// larger output capacity; capacity never weakens the read budget.
///
/// # Safety
/// `out_x` and `out_y` must each address `capacity` writable f64 values.
/// `out_stats` must address six writable u64 values.
#[cfg(not(target_os = "emscripten"))]
#[no_mangle]
pub unsafe extern "C" fn xyg_chunked_columns_read(
    store: u64,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    use_y: i32,
    budget_bytes: u64,
    generation: u64,
    out_x: *mut f64,
    out_y: *mut f64,
    capacity: usize,
    out_stats: *mut u64,
) -> usize {
    ffi_guard(usize::MAX, || {
        if out_x.is_null() || out_y.is_null() || out_stats.is_null() {
            return usize::MAX;
        }
        let Some(s) = chunked_columns::reg_get(store) else {
            return usize::MAX;
        };
        let stats = std::slice::from_raw_parts_mut(out_stats, 6);
        stats.fill(0);
        let y = if use_y == 0 { None } else { Some((y0, y1)) };
        let read = match s.read(x0, x1, y, budget_bytes, generation) {
            Ok(v) => v,
            Err(e) => {
                if let chunked_columns::Error::BudgetExceeded { needed, budget } = &e {
                    stats[3] = *budget;
                    stats[4] = *needed;
                }
                stats[5] = e.code();
                return usize::MAX;
            }
        };
        if read.x.len() > capacity {
            stats[4] = read.x.len() as u64;
            stats[5] = 6;
            return usize::MAX;
        }
        std::ptr::copy_nonoverlapping(read.x.as_ptr(), out_x, read.x.len());
        std::ptr::copy_nonoverlapping(read.y.as_ptr(), out_y, read.y.len());
        stats[0..5].copy_from_slice(&[
            read.generation,
            u64::from(read.first_chunk),
            u64::from(read.chunks_considered),
            u64::from(read.chunks_read),
            read.bytes_read,
        ]);
        read.x.len()
    })
}

/// Read one bounded, resumable viewport page. `cursor` is zero for the first
/// page or the exact `out_stats[5]` returned previously. Stats are generation,
/// first chunk, chunks considered/read, bytes read, next cursor, done, error.
/// Read error slot 7 first: on budget errors slots 4 and 5 instead contain the
/// required bytes and configured budget; on capacity errors slot 4 contains
/// the required element count.
///
/// # Safety
/// `out_x` and `out_y` must each address `capacity` writable f64 values;
/// `out_stats` must address eight writable u64 values.
#[cfg(not(target_os = "emscripten"))]
#[no_mangle]
pub unsafe extern "C" fn xyg_chunked_columns_read_page(
    store: u64,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    use_y: i32,
    budget_bytes: u64,
    generation: u64,
    cursor: u32,
    out_x: *mut f64,
    out_y: *mut f64,
    capacity: usize,
    out_stats: *mut u64,
) -> usize {
    ffi_guard(usize::MAX, || {
        if out_x.is_null() || out_y.is_null() || out_stats.is_null() {
            return usize::MAX;
        }
        let stats = std::slice::from_raw_parts_mut(out_stats, 8);
        stats.fill(0);
        let Some(s) = chunked_columns::reg_get(store) else {
            return usize::MAX;
        };
        let y = if use_y == 0 { None } else { Some((y0, y1)) };
        let page = match s.read_page(x0, x1, y, budget_bytes, generation, cursor) {
            Ok(v) => v,
            Err(e) => {
                if let chunked_columns::Error::BudgetExceeded { needed, budget } = &e {
                    stats[4] = *needed;
                    stats[5] = *budget;
                }
                stats[7] = e.code();
                return usize::MAX;
            }
        };
        if page.read.x.len() > capacity {
            stats[4] = page.read.x.len() as u64;
            stats[7] = 6;
            return usize::MAX;
        }
        std::ptr::copy_nonoverlapping(page.read.x.as_ptr(), out_x, page.read.x.len());
        std::ptr::copy_nonoverlapping(page.read.y.as_ptr(), out_y, page.read.y.len());
        stats[0..7].copy_from_slice(&[
            page.read.generation,
            u64::from(page.read.first_chunk),
            u64::from(page.read.chunks_considered),
            u64::from(page.read.chunks_read),
            page.read.bytes_read,
            u64::from(page.next_chunk),
            u64::from(page.done),
        ]);
        page.read.x.len()
    })
}

#[cfg(not(target_os = "emscripten"))]
#[no_mangle]
pub extern "C" fn xyg_chunked_columns_free(store: u64) -> i32 {
    ffi_guard(0, || i32::from(chunked_columns::reg_remove(store)))
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

// ---------------------------------------------------------------------------
// Temporal columns / interval indexes (#43). Instants are signed UTC micros.
// ---------------------------------------------------------------------------

/// Descriptor for a Rust-owned temporal column. `values` are unit-scaled i64
/// instants (see `unit`); `validity[i]` is 0 or 1. `timezone` is required
/// UTF-8 without NUL, length `timezone_len`. When `naive` is 1, hosts must
/// supply DST status/offset planes; when 0, values are already UTC.
#[repr(C)]
pub struct XygTemporalColumnDescriptor {
    pub values: *const i64,
    pub validity: *const u8,
    pub len: u64,
    pub unit: u32,
    pub timezone: *const u8,
    pub timezone_len: u32,
    pub naive: u32,
    pub disambiguation: u32,
    pub dst_status: *const u8,
    pub offset_seconds: *const i32,
    pub fold_later_offset_seconds: *const i32,
    pub reserved: u32,
}

/// Create a temporal column handle. Status codes: 0 success; negative
/// [`temporal::TemporalError`] values otherwise.
///
/// # Safety
/// `descriptor` / `out_handle` must be valid. Non-empty buffers must cover
/// `len` entries; timezone bytes must cover `timezone_len`.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_column_create(
    descriptor: *const XygTemporalColumnDescriptor,
    out_handle: *mut u64,
) -> i32 {
    if descriptor.is_null() || out_handle.is_null() {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    *out_handle = 0;
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let descriptor = &*descriptor;
        if descriptor.reserved != 0 || descriptor.naive > 1 {
            return temporal::TemporalError::InvalidArgument as i32;
        }
        let Some(unit) = temporal::TemporalPrecision::from_u32(descriptor.unit) else {
            return temporal::TemporalError::UnitUnsupported as i32;
        };
        let len = match usize::try_from(descriptor.len) {
            Ok(value) => value,
            Err(_) => return temporal::TemporalError::CapacityExceeded as i32,
        };
        let tz_len = match usize::try_from(descriptor.timezone_len) {
            Ok(value) => value,
            Err(_) => return temporal::TemporalError::InvalidArgument as i32,
        };
        if tz_len == 0 || descriptor.timezone.is_null() {
            return temporal::TemporalError::TimezoneRequired as i32;
        }
        let timezone =
            match std::str::from_utf8(std::slice::from_raw_parts(descriptor.timezone, tz_len)) {
                Ok(value) => value,
                Err(_) => return temporal::TemporalError::InvalidArgument as i32,
            };
        if len == 0 {
            return match temporal::TemporalColumn::from_utc_micros(&[], &[], timezone, unit) {
                Ok(column) => {
                    *out_handle = temporal::column_insert(column);
                    0
                }
                Err(error) => error as i32,
            };
        }
        if descriptor.values.is_null() || descriptor.validity.is_null() {
            return temporal::TemporalError::InvalidArgument as i32;
        }
        let values = std::slice::from_raw_parts(descriptor.values, len);
        let validity = std::slice::from_raw_parts(descriptor.validity, len);
        let result = if descriptor.naive == 0 {
            temporal::TemporalColumn::from_utc_unit(values, validity, timezone, unit)
        } else {
            let Some(policy) = temporal::DisambiguationPolicy::from_u32(descriptor.disambiguation)
            else {
                return temporal::TemporalError::InvalidArgument as i32;
            };
            if descriptor.dst_status.is_null()
                || descriptor.offset_seconds.is_null()
                || descriptor.fold_later_offset_seconds.is_null()
            {
                return temporal::TemporalError::InvalidArgument as i32;
            }
            temporal::TemporalColumn::from_naive_local_unit(
                values,
                validity,
                timezone,
                unit,
                std::slice::from_raw_parts(descriptor.dst_status, len),
                std::slice::from_raw_parts(descriptor.offset_seconds, len),
                std::slice::from_raw_parts(descriptor.fold_later_offset_seconds, len),
                policy,
            )
        };
        match result {
            Ok(column) => {
                *out_handle = temporal::column_insert(column);
                0
            }
            Err(error) => error as i32,
        }
    })
}

/// Read temporal column length / precision.
///
/// # Safety
/// Output pointers must be valid for one value each.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_column_meta(
    handle: u64,
    out_len: *mut u64,
    out_precision: *mut u32,
    out_timezone_len: *mut u32,
) -> i32 {
    if out_len.is_null() || out_precision.is_null() || out_timezone_len.is_null() {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal::column_with(handle, |column| {
            *out_len = column.len() as u64;
            *out_precision = column.precision() as u32;
            *out_timezone_len = column.timezone().len() as u32;
        })
        .map_or(temporal::TemporalError::StaleHandle as i32, |_| 0)
    })
}

/// Copy timezone UTF-8 bytes (no NUL terminator).
///
/// # Safety
/// `out_timezone` must cover `capacity` bytes when capacity > 0.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_column_timezone(
    handle: u64,
    out_timezone: *mut u8,
    capacity: u32,
) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal::column_with(handle, |column| {
            let bytes = column.timezone().as_bytes();
            if capacity < bytes.len() as u32 {
                return temporal::TemporalError::OutputCapacity as i32;
            }
            if !bytes.is_empty() {
                if out_timezone.is_null() {
                    return temporal::TemporalError::InvalidArgument as i32;
                }
                std::ptr::copy_nonoverlapping(bytes.as_ptr(), out_timezone, bytes.len());
            }
            0
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Copy UTC microsecond values and the validity plane.
///
/// # Safety
/// Non-empty outputs must cover `capacity` entries.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_column_copy(
    handle: u64,
    out_values: *mut i64,
    out_validity: *mut u8,
    capacity: u64,
) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal::column_with(handle, |column| {
            let len = column.len() as u64;
            if capacity < len {
                return temporal::TemporalError::OutputCapacity as i32;
            }
            if len != 0 && (out_values.is_null() || out_validity.is_null()) {
                return temporal::TemporalError::InvalidArgument as i32;
            }
            if len != 0 {
                std::ptr::copy_nonoverlapping(column.values().as_ptr(), out_values, column.len());
                std::ptr::copy_nonoverlapping(
                    column.validity().as_ptr(),
                    out_validity,
                    column.len(),
                );
            }
            0
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Destroy a temporal column handle.
///
/// # Safety
/// Callers must not use the handle after destruction.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_column_destroy(handle: u64) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        if temporal::column_remove(handle) {
            0
        } else {
            temporal::TemporalError::StaleHandle as i32
        }
    })
}

/// Descriptor for half-open interval endpoints. Null validity bits mark
/// unbounded endpoints; reversed finite intervals fail at build.
#[repr(C)]
pub struct XygTemporalIntervalDescriptor {
    pub starts: *const i64,
    pub start_valid: *const u8,
    pub ends: *const i64,
    pub end_valid: *const u8,
    pub len: u64,
    pub reserved: u32,
}

/// Build a deterministic interval index handle.
///
/// # Safety
/// Descriptor buffers must cover `len` entries when len > 0.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_interval_index_create(
    descriptor: *const XygTemporalIntervalDescriptor,
    out_handle: *mut u64,
) -> i32 {
    if descriptor.is_null() || out_handle.is_null() {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    *out_handle = 0;
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let descriptor = &*descriptor;
        if descriptor.reserved != 0 {
            return temporal::TemporalError::InvalidArgument as i32;
        }
        let len = match usize::try_from(descriptor.len) {
            Ok(value) => value,
            Err(_) => return temporal::TemporalError::CapacityExceeded as i32,
        };
        if len == 0 {
            return match temporal::IntervalIndex::build(temporal::IntervalEndpoints {
                starts: &[],
                start_valid: &[],
                ends: &[],
                end_valid: &[],
            }) {
                Ok(index) => {
                    *out_handle = temporal::index_insert(index);
                    0
                }
                Err(error) => error as i32,
            };
        }
        if descriptor.starts.is_null()
            || descriptor.start_valid.is_null()
            || descriptor.ends.is_null()
            || descriptor.end_valid.is_null()
        {
            return temporal::TemporalError::InvalidArgument as i32;
        }
        match temporal::IntervalIndex::build(temporal::IntervalEndpoints {
            starts: std::slice::from_raw_parts(descriptor.starts, len),
            start_valid: std::slice::from_raw_parts(descriptor.start_valid, len),
            ends: std::slice::from_raw_parts(descriptor.ends, len),
            end_valid: std::slice::from_raw_parts(descriptor.end_valid, len),
        }) {
            Ok(index) => {
                *out_handle = temporal::index_insert(index);
                0
            }
            Err(error) => error as i32,
        }
    })
}

/// Read interval index row count.
///
/// # Safety
/// `out_len` must be valid for one `u64`.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_interval_index_len(handle: u64, out_len: *mut u64) -> i32 {
    if out_len.is_null() {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal::index_with(handle, |index| {
            *out_len = index.len() as u64;
        })
        .map_or(temporal::TemporalError::StaleHandle as i32, |_| 0)
    })
}

/// Emit visibility at an instant into a host byte plane (0/1 per row).
///
/// # Safety
/// `out_visibility` must cover `capacity` bytes. `cancel_flag` may be null
/// (never cancelled) or point to a `u32` that becomes non-zero when cancelled.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_interval_visibility_at(
    handle: u64,
    instant_micros: i64,
    out_visibility: *mut u8,
    capacity: u64,
    budget: u64,
    cancel_flag: *const u32,
) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal::index_with(handle, |index| {
            let len = index.len() as u64;
            if capacity < len {
                return temporal::TemporalError::OutputCapacity as i32;
            }
            if len != 0 && out_visibility.is_null() {
                return temporal::TemporalError::InvalidArgument as i32;
            }
            let cancel = temporal::CancelFlag::new();
            if !cancel_flag.is_null() && *cancel_flag != 0 {
                cancel.cancel();
            }
            let budget = match usize::try_from(budget) {
                Ok(value) => value,
                Err(_) => return temporal::TemporalError::BudgetExceeded as i32,
            };
            let out = if len == 0 {
                &mut [][..]
            } else {
                std::slice::from_raw_parts_mut(out_visibility, index.len())
            };
            match index.visibility_at(instant_micros, out, &cancel, budget) {
                Ok(()) => 0,
                Err(error) => error as i32,
            }
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Filter event instants into a half-open `[range_start, range_end)` window.
/// Pass `range_start_valid`/`range_end_valid` as 0 for unbounded sides.
///
/// # Safety
/// Event buffers and `out_visibility` must cover `event_len` / `capacity`.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_events_in_range(
    event_micros: *const i64,
    event_valid: *const u8,
    event_len: u64,
    range_start: i64,
    range_start_valid: u32,
    range_end: i64,
    range_end_valid: u32,
    out_visibility: *mut u8,
    capacity: u64,
    budget: u64,
    cancel_flag: *const u32,
) -> i32 {
    if range_start_valid > 1 || range_end_valid > 1 {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let len = match usize::try_from(event_len) {
            Ok(value) => value,
            Err(_) => return temporal::TemporalError::CapacityExceeded as i32,
        };
        if capacity < event_len {
            return temporal::TemporalError::OutputCapacity as i32;
        }
        if len != 0 && (event_micros.is_null() || event_valid.is_null() || out_visibility.is_null())
        {
            return temporal::TemporalError::InvalidArgument as i32;
        }
        let cancel = temporal::CancelFlag::new();
        if !cancel_flag.is_null() && *cancel_flag != 0 {
            cancel.cancel();
        }
        let budget = match usize::try_from(budget) {
            Ok(value) => value,
            Err(_) => return temporal::TemporalError::BudgetExceeded as i32,
        };
        let events = if len == 0 {
            &[][..]
        } else {
            std::slice::from_raw_parts(event_micros, len)
        };
        let valid = if len == 0 {
            &[][..]
        } else {
            std::slice::from_raw_parts(event_valid, len)
        };
        let out = if len == 0 {
            &mut [][..]
        } else {
            std::slice::from_raw_parts_mut(out_visibility, len)
        };
        let start = if range_start_valid == 0 {
            None
        } else {
            Some(range_start)
        };
        let end = if range_end_valid == 0 {
            None
        } else {
            Some(range_end)
        };
        let probe = match temporal::IntervalIndex::build(temporal::IntervalEndpoints {
            starts: &[],
            start_valid: &[],
            ends: &[],
            end_valid: &[],
        }) {
            Ok(value) => value,
            Err(error) => return error as i32,
        };
        match probe.events_in_range(events, valid, start, end, out, &cancel, budget) {
            Ok(()) => 0,
            Err(error) => error as i32,
        }
    })
}

/// Destroy an interval index handle.
///
/// # Safety
/// Callers must not use the handle after destruction.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_interval_index_destroy(handle: u64) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        if temporal::index_remove(handle) {
            0
        } else {
            temporal::TemporalError::StaleHandle as i32
        }
    })
}

// ---------------------------------------------------------------------------
// TemporalController + linked-view coordination (#44).
// ---------------------------------------------------------------------------

/// Create descriptor for a temporal controller. `group_id` 0 = unlinked.
#[repr(C)]
pub struct XygTemporalControllerDescriptor {
    pub instance_id: u64,
    pub group_id: u64,
    pub domain_start: i64,
    pub domain_end: i64,
    pub cursor: i64,
    pub window: i64,
    pub step: i64,
    pub direction: i32,
    pub rate_milli: u32,
    pub loop_enabled: u32,
    pub reduced_motion: u32,
    pub reserved: u32,
}

/// Create a controller handle.
///
/// # Safety
/// `descriptor` / `out_handle` must be valid.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_create(
    descriptor: *const XygTemporalControllerDescriptor,
    out_handle: *mut u64,
) -> i32 {
    if descriptor.is_null() || out_handle.is_null() {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    *out_handle = 0;
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let descriptor = &*descriptor;
        if descriptor.reserved != 0 || descriptor.loop_enabled > 1 || descriptor.reduced_motion > 1
        {
            return temporal::TemporalError::InvalidArgument as i32;
        }
        let Some(direction) =
            temporal_controller::PlaybackDirection::from_i32(descriptor.direction)
        else {
            return temporal::TemporalError::InvalidArgument as i32;
        };
        match temporal_controller::TemporalController::create(
            descriptor.instance_id,
            descriptor.group_id,
            descriptor.domain_start,
            descriptor.domain_end,
            descriptor.cursor,
            descriptor.window,
            descriptor.step,
            direction,
            descriptor.rate_milli,
            descriptor.loop_enabled == 1,
            descriptor.reduced_motion == 1,
        ) {
            Ok(controller) => match temporal_controller::controller_insert(controller) {
                Ok(handle) => {
                    *out_handle = handle;
                    0
                }
                Err(error) => error as i32,
            },
            Err(error) => error as i32,
        }
    })
}

/// Copy controller state into host scalars.
///
/// # Safety
/// All output pointers must be valid for one value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_state(
    handle: u64,
    out_instance_id: *mut u64,
    out_group_id: *mut u64,
    out_domain_start: *mut i64,
    out_domain_end: *mut i64,
    out_range_start: *mut i64,
    out_range_end: *mut i64,
    out_cursor: *mut i64,
    out_window: *mut i64,
    out_step: *mut i64,
    out_direction: *mut i32,
    out_rate_milli: *mut u32,
    out_loop_enabled: *mut u32,
    out_playing: *mut u32,
    out_reduced_motion: *mut u32,
    out_revision: *mut u64,
    out_disposed: *mut u32,
    out_selection: *mut u64,
    selection_capacity: u64,
    out_selection_count: *mut u64,
) -> i32 {
    let Ok(selection_capacity) = usize::try_from(selection_capacity) else {
        return temporal::TemporalError::InvalidArgument as i32;
    };
    if out_instance_id.is_null()
        || out_group_id.is_null()
        || out_domain_start.is_null()
        || out_domain_end.is_null()
        || out_range_start.is_null()
        || out_range_end.is_null()
        || out_cursor.is_null()
        || out_window.is_null()
        || out_step.is_null()
        || out_direction.is_null()
        || out_rate_milli.is_null()
        || out_loop_enabled.is_null()
        || out_playing.is_null()
        || out_reduced_motion.is_null()
        || out_revision.is_null()
        || out_disposed.is_null()
        || out_selection_count.is_null()
        || (selection_capacity != 0 && out_selection.is_null())
    {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    *out_selection_count = 0;
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |controller| {
            let state = controller.state();
            *out_selection_count = state.selection.len() as u64;
            if selection_capacity < state.selection.len() {
                return temporal::TemporalError::OutputCapacity as i32;
            }
            *out_instance_id = state.instance_id;
            *out_group_id = state.group_id;
            *out_domain_start = state.domain_start;
            *out_domain_end = state.domain_end;
            *out_range_start = state.range_start;
            *out_range_end = state.range_end;
            *out_cursor = state.cursor;
            *out_window = state.window;
            *out_step = state.step;
            *out_direction = state.direction as i32;
            *out_rate_milli = state.rate_milli;
            *out_loop_enabled = u32::from(state.loop_enabled);
            *out_playing = u32::from(state.playing);
            *out_reduced_motion = u32::from(state.reduced_motion);
            *out_revision = state.revision;
            *out_disposed = u32::from(state.disposed);
            if !state.selection.is_empty() {
                std::ptr::copy_nonoverlapping(
                    state.selection.as_ptr(),
                    out_selection,
                    state.selection.len(),
                );
            }
            0
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Set selected half-open range.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_set_range(
    handle: u64,
    start: i64,
    end: i64,
) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| match c.set_range(start, end) {
            Ok(()) => 0,
            Err(e) => e as i32,
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Set cursor (re-centers window when possible).
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_set_cursor(handle: u64, cursor: i64) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| match c.set_cursor(cursor) {
            Ok(()) => 0,
            Err(e) => e as i32,
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Replace the exact stable-ID selection coordinated with temporal state.
///
/// # Safety
/// `ids` must reference `count` readable u64 values when count is nonzero.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_set_selection(
    handle: u64,
    ids: *const u64,
    count: u64,
) -> i32 {
    let Ok(count) = usize::try_from(count) else {
        return temporal::TemporalError::InvalidArgument as i32;
    };
    if count > temporal_controller::MAX_COORDINATED_SELECTION_IDS || (count != 0 && ids.is_null()) {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    let selection = if count == 0 {
        &[]
    } else {
        std::slice::from_raw_parts(ids, count)
    };
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| match c.set_selection(selection) {
            Ok(()) => 0,
            Err(e) => e as i32,
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Start playback when reduced motion is off.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_play(handle: u64) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| match c.play() {
            Ok(()) => 0,
            Err(e) => e as i32,
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Pause playback.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_pause(handle: u64) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| match c.pause() {
            Ok(()) => 0,
            Err(e) => e as i32,
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Advance one step along the current direction.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_step(handle: u64) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| match c.step() {
            Ok(()) => 0,
            Err(e) => e as i32,
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Set playback rate in milli-units (1000 = 1.0×).
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_set_rate_milli(
    handle: u64,
    rate_milli: u32,
) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| match c.set_rate_milli(rate_milli) {
            Ok(()) => 0,
            Err(e) => e as i32,
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Set playback direction (−1 reverse, +1 forward).
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_set_direction(handle: u64, direction: i32) -> i32 {
    let Some(direction) = temporal_controller::PlaybackDirection::from_i32(direction) else {
        return temporal::TemporalError::InvalidArgument as i32;
    };
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| match c.set_direction(direction) {
            Ok(()) => 0,
            Err(e) => e as i32,
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Enable or disable looping at domain bounds.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_set_loop(handle: u64, enabled: u32) -> i32 {
    if enabled > 1 {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| match c.set_loop(enabled == 1) {
            Ok(()) => 0,
            Err(e) => e as i32,
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Set reduced-motion policy (`play` becomes a no-op when enabled).
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_set_reduced_motion(
    handle: u64,
    enabled: u32,
) -> i32 {
    if enabled > 1 {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| {
            match c.set_reduced_motion(enabled == 1) {
                Ok(()) => 0,
                Err(e) => e as i32,
            }
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Host-clock tick. Writes 1 to `out_advanced` when the cursor moved.
///
/// # Safety
/// `out_advanced` must be valid for one `u32`.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_tick(
    handle: u64,
    dt_micros: i64,
    out_advanced: *mut u32,
) -> i32 {
    if out_advanced.is_null() {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| match c.tick(dt_micros) {
            Ok(advanced) => {
                *out_advanced = u32::from(advanced);
                0
            }
            Err(e) => e as i32,
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Poll and clear the pending outbound coordination event.
///
/// # Safety
/// Output pointers must be valid. Writes `out_has_event` 0/1 and initializes
/// every event field to zero when no event is available or the handle is stale.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_poll_event(
    handle: u64,
    out_has_event: *mut u32,
    out_group_id: *mut u64,
    out_source_instance: *mut u64,
    out_revision: *mut u64,
    out_range_start: *mut i64,
    out_range_end: *mut i64,
    out_cursor: *mut i64,
    out_window: *mut i64,
    out_selection: *mut u64,
    selection_capacity: u64,
    out_selection_count: *mut u64,
) -> i32 {
    let Ok(selection_capacity) = usize::try_from(selection_capacity) else {
        return temporal::TemporalError::InvalidArgument as i32;
    };
    if out_has_event.is_null()
        || out_group_id.is_null()
        || out_source_instance.is_null()
        || out_revision.is_null()
        || out_range_start.is_null()
        || out_range_end.is_null()
        || out_cursor.is_null()
        || out_window.is_null()
        || out_selection_count.is_null()
        || (selection_capacity != 0 && out_selection.is_null())
    {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    *out_has_event = 0;
    *out_group_id = 0;
    *out_source_instance = 0;
    *out_revision = 0;
    *out_range_start = 0;
    *out_range_end = 0;
    *out_cursor = 0;
    *out_window = 0;
    *out_selection_count = 0;
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| {
            if let Some(event) = c.pending_outbound() {
                *out_selection_count = event.selection.len() as u64;
                if selection_capacity < event.selection.len() {
                    return temporal::TemporalError::OutputCapacity as i32;
                }
            }
            if let Some(event) = c.take_outbound() {
                *out_has_event = 1;
                *out_group_id = event.group_id;
                *out_source_instance = event.source_instance;
                *out_revision = event.revision;
                *out_range_start = event.range_start;
                *out_range_end = event.range_end;
                *out_cursor = event.cursor;
                *out_window = event.window;
                *out_selection_count = event.selection.len() as u64;
                if !event.selection.is_empty() {
                    std::ptr::copy_nonoverlapping(
                        event.selection.as_ptr(),
                        out_selection,
                        event.selection.len(),
                    );
                }
            }
            0
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Apply an inbound coordination event. Writes 1 to `out_applied` on change.
///
/// # Safety
/// `out_applied` must be valid for one `u32`.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_apply_event(
    handle: u64,
    group_id: u64,
    source_instance: u64,
    revision: u64,
    range_start: i64,
    range_end: i64,
    cursor: i64,
    window: i64,
    selection: *const u64,
    selection_count: u64,
    out_applied: *mut u32,
) -> i32 {
    let Ok(selection_count) = usize::try_from(selection_count) else {
        return temporal::TemporalError::InvalidArgument as i32;
    };
    if out_applied.is_null()
        || selection_count > temporal_controller::MAX_COORDINATED_SELECTION_IDS
        || (selection_count != 0 && selection.is_null())
    {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    let selection = if selection_count == 0 {
        Vec::new()
    } else {
        std::slice::from_raw_parts(selection, selection_count).to_vec()
    };
    let event = temporal_controller::CoordinationEvent {
        group_id,
        source_instance,
        revision,
        range_start,
        range_end,
        cursor,
        window,
        selection,
    };
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| match c.apply_event(&event) {
            Ok(applied) => {
                *out_applied = u32::from(applied);
                0
            }
            Err(e) => e as i32,
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Same-process group deliver for the polled event fields.
///
/// # Safety
/// `out_applied` must be valid for one `u32`.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_coordinate_deliver(
    group_id: u64,
    source_instance: u64,
    revision: u64,
    range_start: i64,
    range_end: i64,
    cursor: i64,
    window: i64,
    selection: *const u64,
    selection_count: u64,
    out_applied: *mut u32,
) -> i32 {
    let Ok(selection_count) = usize::try_from(selection_count) else {
        return temporal::TemporalError::InvalidArgument as i32;
    };
    if out_applied.is_null()
        || selection_count > temporal_controller::MAX_COORDINATED_SELECTION_IDS
        || (selection_count != 0 && selection.is_null())
    {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    let selection = if selection_count == 0 {
        Vec::new()
    } else {
        std::slice::from_raw_parts(selection, selection_count).to_vec()
    };
    let event = temporal_controller::CoordinationEvent {
        group_id,
        source_instance,
        revision,
        range_start,
        range_end,
        cursor,
        window,
        selection,
    };
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        match temporal_controller::coordinate_deliver(&event) {
            Ok(n) => {
                *out_applied = n;
                0
            }
            Err(e) => e as i32,
        }
    })
}

/// Dispose a controller (stops playback; further ops fail with Disposed).
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_dispose(handle: u64) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        temporal_controller::controller_with_mut(handle, |c| match c.dispose() {
            Ok(()) => 0,
            Err(e) => e as i32,
        })
        .unwrap_or(temporal::TemporalError::StaleHandle as i32)
    })
}

/// Destroy the handle (after dispose or instead of it).
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_controller_destroy(handle: u64) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let _ = temporal_controller::controller_with_mut(handle, |c| {
            let _ = c.dispose();
        });
        if temporal_controller::controller_remove(handle) {
            0
        } else {
            temporal::TemporalError::StaleHandle as i32
        }
    })
}

// ---------------------------------------------------------------------------
// Identity-safe temporal graph filtering (#45). UUIDs are packed 16-byte IDs.
// ---------------------------------------------------------------------------

/// Bind a canonical projection to optional canonical temporal-column handles.
/// A zero column handle means that plane is unbounded/unbound.
#[repr(C)]
pub struct XygTemporalGraphDescriptor {
    pub projection_handle: u64,
    pub node_valid_from: u64,
    pub node_valid_to: u64,
    pub node_event_at: u64,
    pub edge_valid_from: u64,
    pub edge_valid_to: u64,
    pub edge_event_at: u64,
    pub reserved: u64,
}

/// Exact counts and scalar provenance for the most recently published frame.
#[repr(C)]
pub struct XygTemporalGraphSnapshotMeta {
    pub revision: u64,
    pub cursor_micros: i64,
    pub range_start_micros: i64,
    pub range_end_micros: i64,
    pub node_count: u64,
    pub edge_count: u64,
    pub visible_node_count: u64,
    pub visible_edge_count: u64,
    pub selected_visible_node_count: u64,
    pub selected_visible_edge_count: u64,
    pub pinned_visible_node_count: u64,
    pub selected_node_count: u64,
    pub selected_edge_count: u64,
    pub pinned_node_count: u64,
    pub focused_visible_kind: u32,
    pub focused_kind: u32,
    pub focused_visible_id: [u8; 16],
    pub focused_id: [u8; 16],
}

/// Output buffers for one exact frame/frozen-provenance snapshot. UUID
/// capacities count 16-byte identities, not bytes.
#[repr(C)]
pub struct XygTemporalGraphSnapshotBuffers {
    pub node_visibility: *mut u8,
    pub node_capacity: u64,
    pub edge_visibility: *mut u8,
    pub edge_capacity: u64,
    pub visible_node_ids: *mut u8,
    pub visible_node_capacity: u64,
    pub visible_edge_ids: *mut u8,
    pub visible_edge_capacity: u64,
    pub selected_visible_node_ids: *mut u8,
    pub selected_visible_node_capacity: u64,
    pub selected_visible_edge_ids: *mut u8,
    pub selected_visible_edge_capacity: u64,
    pub pinned_visible_node_ids: *mut u8,
    pub pinned_visible_node_capacity: u64,
    pub selected_node_ids: *mut u8,
    pub selected_node_capacity: u64,
    pub selected_edge_ids: *mut u8,
    pub selected_edge_capacity: u64,
    pub pinned_node_ids: *mut u8,
    pub pinned_node_capacity: u64,
}

struct NativeTemporalGraphState {
    graph: temporal_graph::TemporalGraph,
    frame: Option<temporal_graph::TemporalGraphFrame>,
    frozen: Option<temporal_graph::FrozenTemporalGraphState>,
}

struct NativeTemporalGraph {
    operation: std::sync::Mutex<()>,
    state: std::sync::Mutex<NativeTemporalGraphState>,
    active_cancel: std::sync::Mutex<Option<std::sync::Arc<temporal::CancelFlag>>>,
    disposed: std::sync::atomic::AtomicBool,
}

type TemporalGraphRegistry = (
    u64,
    std::collections::HashMap<u64, std::sync::Arc<NativeTemporalGraph>>,
);
static TEMPORAL_GRAPH_REGISTRY: std::sync::OnceLock<std::sync::Mutex<TemporalGraphRegistry>> =
    std::sync::OnceLock::new();

fn temporal_graph_registry() -> &'static std::sync::Mutex<TemporalGraphRegistry> {
    TEMPORAL_GRAPH_REGISTRY
        .get_or_init(|| std::sync::Mutex::new((0, std::collections::HashMap::new())))
}

fn temporal_graph_entry(handle: u64) -> Option<std::sync::Arc<NativeTemporalGraph>> {
    temporal_graph_registry()
        .lock()
        .expect("temporal graph registry poisoned")
        .1
        .get(&handle)
        .cloned()
}

fn optional_temporal_column(
    handle: u64,
) -> Result<Option<temporal::TemporalColumn>, temporal::TemporalError> {
    if handle == 0 {
        return Ok(None);
    }
    temporal::column_with(handle, Clone::clone)
        .map(Some)
        .ok_or(temporal::TemporalError::StaleHandle)
}

fn temporal_graph_entity_parts(entity: Option<temporal_graph::GraphEntity>) -> (u32, [u8; 16]) {
    match entity {
        None => (0, [0; 16]),
        Some(temporal_graph::GraphEntity::Node(id)) => (1, id),
        Some(temporal_graph::GraphEntity::Edge(id)) => (2, id),
    }
}

unsafe fn temporal_graph_uuid_slice<'a>(
    ptr: *const u8,
    count: u64,
) -> Result<&'a [projection::Uuid], temporal::TemporalError> {
    let count = usize::try_from(count).map_err(|_| temporal::TemporalError::CapacityExceeded)?;
    if count == 0 {
        return Ok(&[]);
    }
    if ptr.is_null() {
        return Err(temporal::TemporalError::InvalidArgument);
    }
    Ok(std::slice::from_raw_parts(
        ptr.cast::<projection::Uuid>(),
        count,
    ))
}

/// Create a Rust-owned temporal graph. All referenced identity/time planes are
/// copied before this call returns, so source handles may be destroyed later.
///
/// # Safety
/// `descriptor` and `out_handle` must be valid for one value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_graph_create(
    descriptor: *const XygTemporalGraphDescriptor,
    out_handle: *mut u64,
) -> i32 {
    if descriptor.is_null() || out_handle.is_null() {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    *out_handle = 0;
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let descriptor = &*descriptor;
        if descriptor.reserved != 0 || descriptor.projection_handle == 0 {
            return temporal::TemporalError::InvalidArgument as i32;
        }
        let columns = [
            descriptor.node_valid_from,
            descriptor.node_valid_to,
            descriptor.node_event_at,
            descriptor.edge_valid_from,
            descriptor.edge_valid_to,
            descriptor.edge_event_at,
        ];
        let mut owned = Vec::with_capacity(columns.len());
        for handle in columns {
            match optional_temporal_column(handle) {
                Ok(value) => owned.push(value),
                Err(error) => return error as i32,
            }
        }
        let bind = |projection: &projection::GraphProjection| {
            temporal_graph::TemporalGraph::bind(
                projection,
                temporal_graph::TemporalBindingInput {
                    valid_from: owned[0].as_ref(),
                    valid_to: owned[1].as_ref(),
                    event_at: owned[2].as_ref(),
                },
                temporal_graph::TemporalBindingInput {
                    valid_from: owned[3].as_ref(),
                    valid_to: owned[4].as_ref(),
                    event_at: owned[5].as_ref(),
                },
            )
        };
        let Some(result) = projection::reg_with(descriptor.projection_handle, bind) else {
            return temporal::TemporalError::StaleHandle as i32;
        };
        let graph = match result {
            Ok(graph) => graph,
            Err(error) => return error as i32,
        };
        let entry = std::sync::Arc::new(NativeTemporalGraph {
            operation: std::sync::Mutex::new(()),
            state: std::sync::Mutex::new(NativeTemporalGraphState {
                graph,
                frame: None,
                frozen: None,
            }),
            active_cancel: std::sync::Mutex::new(None),
            disposed: std::sync::atomic::AtomicBool::new(false),
        });
        let mut registry = temporal_graph_registry()
            .lock()
            .expect("temporal graph registry poisoned");
        let Some(next) = registry.0.checked_add(1) else {
            return temporal::TemporalError::CapacityExceeded as i32;
        };
        registry.0 = next;
        registry.1.insert(next, entry);
        *out_handle = next;
        0
    })
}

/// Atomically replace UUID-keyed selection.
///
/// # Safety
/// Non-empty UUID buffers contain `count * 16` readable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_graph_set_selection(
    handle: u64,
    node_ids: *const u8,
    node_count: u64,
    edge_ids: *const u8,
    edge_count: u64,
) -> i32 {
    let nodes = match temporal_graph_uuid_slice(node_ids, node_count) {
        Ok(ids) => ids,
        Err(error) => return error as i32,
    };
    let edges = match temporal_graph_uuid_slice(edge_ids, edge_count) {
        Ok(ids) => ids,
        Err(error) => return error as i32,
    };
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let Some(entry) = temporal_graph_entry(handle) else {
            return temporal::TemporalError::StaleHandle as i32;
        };
        let mut state = entry.state.lock().expect("temporal graph poisoned");
        state
            .graph
            .set_selection(nodes.iter().copied(), edges.iter().copied())
            .map_or_else(|error| error as i32, |()| 0)
    })
}

/// Replace focus. `kind`: 0 clear, 1 node, 2 edge.
///
/// # Safety
/// Kinds 1/2 require `id` to address exactly 16 readable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_graph_set_focus(
    handle: u64,
    kind: u32,
    id: *const u8,
) -> i32 {
    let entity = match kind {
        0 => None,
        1 | 2 if !id.is_null() => {
            let uuid = *id.cast::<projection::Uuid>();
            Some(if kind == 1 {
                temporal_graph::GraphEntity::Node(uuid)
            } else {
                temporal_graph::GraphEntity::Edge(uuid)
            })
        }
        _ => return temporal::TemporalError::InvalidArgument as i32,
    };
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let Some(entry) = temporal_graph_entry(handle) else {
            return temporal::TemporalError::StaleHandle as i32;
        };
        let result = entry
            .state
            .lock()
            .expect("temporal graph poisoned")
            .graph
            .set_focus(entity);
        result.map_or_else(|error| error as i32, |()| 0)
    })
}

/// Atomically replace UUID-keyed pinned nodes.
///
/// # Safety
/// A non-empty UUID buffer contains `count * 16` readable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_graph_set_pinned(
    handle: u64,
    node_ids: *const u8,
    node_count: u64,
) -> i32 {
    let nodes = match temporal_graph_uuid_slice(node_ids, node_count) {
        Ok(ids) => ids,
        Err(error) => return error as i32,
    };
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let Some(entry) = temporal_graph_entry(handle) else {
            return temporal::TemporalError::StaleHandle as i32;
        };
        let result = entry
            .state
            .lock()
            .expect("temporal graph poisoned")
            .graph
            .set_pinned_nodes(nodes.iter().copied());
        result.map_or_else(|error| error as i32, |()| 0)
    })
}

/// Return Rust's exact minimum work budget for one frame.
///
/// # Safety
/// `out_budget` must be valid for one `u64`.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_graph_required_budget(
    handle: u64,
    out_budget: *mut u64,
) -> i32 {
    if out_budget.is_null() {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let Some(entry) = temporal_graph_entry(handle) else {
            return temporal::TemporalError::StaleHandle as i32;
        };
        let state = entry.state.lock().expect("temporal graph poisoned");
        match state.graph.required_budget() {
            Ok(value) => {
                *out_budget = value as u64;
                0
            }
            Err(error) => error as i32,
        }
    })
}

/// Compute and publish a revisioned frame. Calls on one handle serialize;
/// `xyg_temporal_graph_cancel` remains callable from another thread.
#[no_mangle]
pub extern "C" fn xyg_temporal_graph_frame(
    handle: u64,
    revision: u64,
    cursor_micros: i64,
    range_start_micros: i64,
    range_end_micros: i64,
    budget: u64,
) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let Some(entry) = temporal_graph_entry(handle) else {
            return temporal::TemporalError::StaleHandle as i32;
        };
        let Ok(budget) = usize::try_from(budget) else {
            return temporal::TemporalError::CapacityExceeded as i32;
        };
        let _operation = entry
            .operation
            .lock()
            .expect("temporal graph operation poisoned");
        let cancel = std::sync::Arc::new(temporal::CancelFlag::new());
        let mut active = entry
            .active_cancel
            .lock()
            .expect("temporal graph cancel poisoned");
        if entry.disposed.load(std::sync::atomic::Ordering::Acquire) {
            return temporal::TemporalError::Disposed as i32;
        }
        *active = Some(cancel.clone());
        drop(active);
        let result = {
            let mut state = entry.state.lock().expect("temporal graph poisoned");
            state.graph.frame(
                revision,
                cursor_micros,
                range_start_micros,
                range_end_micros,
                &cancel,
                budget,
            )
        };
        *entry
            .active_cancel
            .lock()
            .expect("temporal graph cancel poisoned") = None;
        match result {
            Ok(frame) => {
                let mut state = entry.state.lock().expect("temporal graph poisoned");
                let frozen = match state.graph.freeze(&frame) {
                    Ok(value) => value,
                    Err(error) => return error as i32,
                };
                state.frame = Some(frame);
                state.frozen = Some(frozen);
                0
            }
            Err(error) => error as i32,
        }
    })
}

/// Cooperatively cancel the active frame computation, if any.
#[no_mangle]
pub extern "C" fn xyg_temporal_graph_cancel(handle: u64) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let Some(entry) = temporal_graph_entry(handle) else {
            return temporal::TemporalError::StaleHandle as i32;
        };
        if let Some(cancel) = entry
            .active_cancel
            .lock()
            .expect("temporal graph cancel poisoned")
            .as_ref()
        {
            cancel.cancel();
        }
        0
    })
}

/// Read exact scalar/count metadata for the last successful frame.
///
/// # Safety
/// `out_meta` must be valid for one value.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_graph_snapshot_meta(
    handle: u64,
    out_meta: *mut XygTemporalGraphSnapshotMeta,
) -> i32 {
    if out_meta.is_null() {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let Some(entry) = temporal_graph_entry(handle) else {
            return temporal::TemporalError::StaleHandle as i32;
        };
        let state = entry.state.lock().expect("temporal graph poisoned");
        let (Some(frame), Some(frozen)) = (&state.frame, &state.frozen) else {
            return temporal::TemporalError::StaleRevision as i32;
        };
        let (focused_visible_kind, focused_visible_id) =
            temporal_graph_entity_parts(frame.focused_visible());
        let (focused_kind, focused_id) = temporal_graph_entity_parts(frozen.focused);
        *out_meta = XygTemporalGraphSnapshotMeta {
            revision: frame.revision(),
            cursor_micros: frame.cursor_micros(),
            range_start_micros: frame.range_start_micros(),
            range_end_micros: frame.range_end_micros(),
            node_count: frame.node_visibility().len() as u64,
            edge_count: frame.edge_visibility().len() as u64,
            visible_node_count: frame.visible_node_ids().len() as u64,
            visible_edge_count: frame.visible_edge_ids().len() as u64,
            selected_visible_node_count: frame.selected_visible_node_ids().len() as u64,
            selected_visible_edge_count: frame.selected_visible_edge_ids().len() as u64,
            pinned_visible_node_count: frame.pinned_visible_node_ids().len() as u64,
            selected_node_count: frozen.selected_node_ids.len() as u64,
            selected_edge_count: frozen.selected_edge_ids.len() as u64,
            pinned_node_count: frozen.pinned_node_ids.len() as u64,
            focused_visible_kind,
            focused_kind,
            focused_visible_id,
            focused_id,
        };
        0
    })
}

unsafe fn temporal_graph_copy_bytes<T: Copy>(
    source: &[T],
    output: *mut T,
    capacity: u64,
) -> Result<(), temporal::TemporalError> {
    if capacity < source.len() as u64 {
        return Err(temporal::TemporalError::OutputCapacity);
    }
    if !source.is_empty() && output.is_null() {
        return Err(temporal::TemporalError::InvalidArgument);
    }
    if !source.is_empty() {
        std::ptr::copy_nonoverlapping(source.as_ptr(), output, source.len());
    }
    Ok(())
}

/// Copy all frame and frozen-membership buffers described by `snapshot_meta`.
/// UUID outputs are packed `capacity * 16` bytes; capacities count UUIDs.
///
/// # Safety
/// Every non-empty output must be writable for its declared capacity.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_graph_snapshot_copy(
    handle: u64,
    expected_revision: u64,
    buffers: *const XygTemporalGraphSnapshotBuffers,
) -> i32 {
    if buffers.is_null() {
        return temporal::TemporalError::InvalidArgument as i32;
    }
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let buffers = &*buffers;
        let Some(entry) = temporal_graph_entry(handle) else {
            return temporal::TemporalError::StaleHandle as i32;
        };
        let state = entry.state.lock().expect("temporal graph poisoned");
        let (Some(frame), Some(frozen)) = (&state.frame, &state.frozen) else {
            return temporal::TemporalError::StaleRevision as i32;
        };
        if frame.revision() != expected_revision {
            return temporal::TemporalError::StaleRevision as i32;
        }
        let copies = [
            temporal_graph_copy_bytes(
                frame.node_visibility(),
                buffers.node_visibility,
                buffers.node_capacity,
            ),
            temporal_graph_copy_bytes(
                frame.edge_visibility(),
                buffers.edge_visibility,
                buffers.edge_capacity,
            ),
            temporal_graph_copy_bytes(
                frame.visible_node_ids(),
                buffers.visible_node_ids.cast(),
                buffers.visible_node_capacity,
            ),
            temporal_graph_copy_bytes(
                frame.visible_edge_ids(),
                buffers.visible_edge_ids.cast(),
                buffers.visible_edge_capacity,
            ),
            temporal_graph_copy_bytes(
                frame.selected_visible_node_ids(),
                buffers.selected_visible_node_ids.cast(),
                buffers.selected_visible_node_capacity,
            ),
            temporal_graph_copy_bytes(
                frame.selected_visible_edge_ids(),
                buffers.selected_visible_edge_ids.cast(),
                buffers.selected_visible_edge_capacity,
            ),
            temporal_graph_copy_bytes(
                frame.pinned_visible_node_ids(),
                buffers.pinned_visible_node_ids.cast(),
                buffers.pinned_visible_node_capacity,
            ),
            temporal_graph_copy_bytes(
                &frozen.selected_node_ids,
                buffers.selected_node_ids.cast(),
                buffers.selected_node_capacity,
            ),
            temporal_graph_copy_bytes(
                &frozen.selected_edge_ids,
                buffers.selected_edge_ids.cast(),
                buffers.selected_edge_capacity,
            ),
            temporal_graph_copy_bytes(
                &frozen.pinned_node_ids,
                buffers.pinned_node_ids.cast(),
                buffers.pinned_node_capacity,
            ),
        ];
        copies
            .into_iter()
            .find_map(Result::err)
            .map_or(0, |error| error as i32)
    })
}

/// Destroy a temporal graph handle and cancel owned work first.
#[no_mangle]
pub extern "C" fn xyg_temporal_graph_destroy(handle: u64) -> i32 {
    ffi_guard(temporal::TemporalError::InvalidArgument as i32, || {
        let entry = {
            temporal_graph_registry()
                .lock()
                .expect("temporal graph registry poisoned")
                .1
                .remove(&handle)
        };
        let Some(entry) = entry else {
            return temporal::TemporalError::StaleHandle as i32;
        };
        entry
            .disposed
            .store(true, std::sync::atomic::Ordering::Release);
        if let Some(cancel) = entry
            .active_cancel
            .lock()
            .expect("temporal graph cancel poisoned")
            .as_ref()
        {
            cancel.cancel();
        }
        0
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
            | graph::LAYOUT_STRESS
            | graph::LAYOUT_COSE => graph::layout_force_family(
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
    if out_handle.is_null() {
        return -1;
    }
    *out_handle = 0;
    if n_edges > (usize::MAX as u64) {
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

/// Packed configurable CoSE ingress. Optional node arrays are either null or
/// exactly `n_nodes` long. `parents` uses [`graph::COSE_NO_PARENT`] for roots.
/// Bounds are `(x0, y0, x1, y1)` when `has_bounds != 0`.
#[repr(C)]
pub struct XygCoseDescriptor {
    pub in_x: *const f64,
    pub in_y: *const f64,
    pub pinned: *const u8,
    pub parents: *const u64,
    pub ideal_edge_length: f64,
    pub repulsion_strength: f64,
    pub gravity_strength: f64,
    pub cooling_factor: f64,
    pub overlap_padding: f64,
    pub component_spacing: f64,
    pub bounds: *const f64,
    pub has_bounds: u32,
    pub reserved: u32,
}

/// Create a progressive configurable CoSE handle.
///
/// Returns `0` and a non-zero handle on success; `-1` for malformed graph,
/// option, pin, compound, or bounds ingress. No host-side fallback is used.
///
/// # Safety
/// `descriptor` and `out_handle` must be valid. Edge arrays must address
/// `n_edges` entries. Each non-null node array in the descriptor must address
/// `n_nodes` entries; bounds must address four f64 values when enabled.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_force_create_cose(
    descriptor: *const XygCoseDescriptor,
    n_nodes: u64,
    n_edges: u64,
    sources: *const u64,
    targets: *const u64,
    seed: u64,
    out_handle: *mut u64,
) -> i32 {
    if descriptor.is_null()
        || out_handle.is_null()
        || n_nodes > usize::MAX as u64
        || n_edges > usize::MAX as u64
    {
        return -1;
    }
    *out_handle = 0;
    let descriptor = &*descriptor;
    if descriptor.reserved != 0 || descriptor.has_bounds > 1 {
        return -1;
    }
    if (descriptor.in_x.is_null()) != (descriptor.in_y.is_null()) {
        return -1;
    }
    let n = n_nodes as usize;
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
    let initial = if descriptor.in_x.is_null() {
        None
    } else {
        Some((
            std::slice::from_raw_parts(descriptor.in_x, n),
            std::slice::from_raw_parts(descriptor.in_y, n),
        ))
    };
    let pinned = if descriptor.pinned.is_null() {
        &[][..]
    } else {
        std::slice::from_raw_parts(descriptor.pinned, n)
    };
    let parents = if descriptor.parents.is_null() {
        &[][..]
    } else {
        std::slice::from_raw_parts(descriptor.parents, n)
    };
    let bounds = if descriptor.has_bounds == 0 {
        None
    } else if descriptor.bounds.is_null() {
        return -1;
    } else {
        let values = std::slice::from_raw_parts(descriptor.bounds, 4);
        Some([values[0], values[1], values[2], values[3]])
    };
    let options = graph::CoseOptions {
        ideal_edge_length: descriptor.ideal_edge_length,
        repulsion_strength: descriptor.repulsion_strength,
        gravity_strength: descriptor.gravity_strength,
        cooling_factor: descriptor.cooling_factor,
        overlap_padding: descriptor.overlap_padding,
        component_spacing: descriptor.component_spacing,
        bounds,
    };
    ffi_guard(-1, || {
        let handle = match initial {
            Some((x, y)) => graph::force_create_cose(
                n_nodes,
                sources,
                targets,
                Some(x),
                Some(y),
                seed,
                options,
                pinned,
                parents,
            ),
            None => graph::force_create_cose(
                n_nodes, sources, targets, None, None, seed, options, pinned, parents,
            ),
        };
        match handle {
            Some(handle) => {
                *out_handle = handle;
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
/// **cluster index space** (Aggregate collapses multi-edges; Direct preserves
/// parallels/self-loops), all within `node_budget` / `edge_budget`. Optional
/// viewport when `viewport_enabled != 0`.
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

/// Route render-graph edges into paint segments (#33).
///
/// Emits deterministic parallel/reciprocal offsets, triangular self-loops, and
/// optional directed arrowheads. `out_*` buffers must hold
/// `n_edges * EDGE_ROUTE_SEGMENTS_PER_EDGE` slots. Writes the segment count into
/// `out_n_segments` and returns 0 on success.
///
/// # Safety
/// Non-empty input/output pointers must be valid for the documented lengths.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_edge_route_segments(
    n_nodes: u64,
    n_edges: u64,
    x: *const f64,
    y: *const f64,
    sources: *const u64,
    targets: *const u64,
    directed: i32,
    separation: f64,
    loop_radius: f64,
    arrow_size: f64,
    out_x0: *mut f64,
    out_y0: *mut f64,
    out_x1: *mut f64,
    out_y1: *mut f64,
    out_edge_index: *mut u64,
    out_n_segments: *mut u64,
) -> i32 {
    if n_nodes > (usize::MAX as u64) || n_edges > (usize::MAX as u64) || out_n_segments.is_null() {
        return -1;
    }
    let n = n_nodes as usize;
    let e = n_edges as usize;
    let Some(cap) = e.checked_mul(xyg_engine::edge_route::EDGE_ROUTE_SEGMENTS_PER_EDGE) else {
        return -1;
    };
    if n > 0 && (x.is_null() || y.is_null()) {
        return -1;
    }
    if e > 0 && (sources.is_null() || targets.is_null()) {
        return -1;
    }
    if cap > 0
        && (out_x0.is_null()
            || out_y0.is_null()
            || out_x1.is_null()
            || out_y1.is_null()
            || out_edge_index.is_null())
    {
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
    } else {
        std::slice::from_raw_parts(sources, e)
    };
    let targets = if e == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(targets, e)
    };
    let out_x0 = if cap == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_x0, cap)
    };
    let out_y0 = if cap == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_y0, cap)
    };
    let out_x1 = if cap == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_x1, cap)
    };
    let out_y1 = if cap == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_y1, cap)
    };
    let out_edge_index = if cap == 0 {
        &mut [][..]
    } else {
        std::slice::from_raw_parts_mut(out_edge_index, cap)
    };

    ffi_guard(-1, || {
        match xyg_engine::edge_route::edge_route_segments(
            n_nodes,
            x,
            y,
            sources,
            targets,
            directed != 0,
            separation,
            loop_radius,
            arrow_size,
            out_x0,
            out_y0,
            out_x1,
            out_y1,
            out_edge_index,
        ) {
            Some(n_seg) => {
                *out_n_segments = n_seg;
                0
            }
            None => -1,
        }
    })
}

/// Resolve graph interaction flags using the shared visual-state precedence (#34).
///
/// # Safety
/// Non-empty input and output pointers must address `n` readable/writable elements.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_visual_state_resolve(
    n: u64,
    flags: *const u32,
    out: *mut u8,
) -> i32 {
    let Ok(n) = usize::try_from(n) else {
        return -1;
    };
    if n > 0 && (flags.is_null() || out.is_null()) {
        return -1;
    }
    ffi_guard(-1, || {
        let input = if n == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(flags, n)
        };
        let output = if n == 0 {
            &mut []
        } else {
            std::slice::from_raw_parts_mut(out, n)
        };
        if xyg_engine::graph_style::resolve_visual_states(input, output).is_some() {
            0
        } else {
            -1
        }
    })
}

/// Resolve versioned canonical GraphForge semantic fields into painter values (#34).
///
/// RGBA outputs address `n * 4` bytes; every other array addresses `n` elements.
/// The resolver validates the complete input before writing any output.
///
/// # Safety
/// Every non-empty pointer must address the documented readable/writable extent.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_semantic_style_resolve(
    version: u32,
    theme: u32,
    n: u64,
    classes: *const u8,
    epistemic: *const u8,
    statuses: *const u8,
    metric: *const f64,
    flags: *const u32,
    edge: i32,
    fill_rgba: *mut u8,
    stroke_rgba: *mut u8,
    halo_rgba: *mut u8,
    size: *mut f32,
    width: *mut f32,
    opacity: *mut f32,
    shape: *mut u8,
    dash: *mut u8,
    arrow: *mut u8,
    state: *mut u8,
    out_domain_lo: *mut f64,
    out_domain_hi: *mut f64,
) -> i32 {
    let Ok(n) = usize::try_from(n) else {
        return -1;
    };
    if version != xyg_engine::graph_style::RESOLVED_STYLE_VERSION
        || out_domain_lo.is_null()
        || out_domain_hi.is_null()
        || (n > 0 && [classes, epistemic, statuses].iter().any(|p| p.is_null()))
        || (n > 0
            && (metric.is_null()
                || flags.is_null()
                || fill_rgba.is_null()
                || stroke_rgba.is_null()
                || halo_rgba.is_null()
                || size.is_null()
                || width.is_null()
                || opacity.is_null()
                || shape.is_null()
                || dash.is_null()
                || arrow.is_null()
                || state.is_null()))
    {
        return -1;
    }
    ffi_guard(-1, || {
        macro_rules! input {
            ($p:expr) => {
                if n == 0 {
                    &[]
                } else {
                    std::slice::from_raw_parts($p, n)
                }
            };
        }
        let mut resolved = vec![
            xyg_engine::graph_style::ResolvedGraphStyle {
                fill: [0; 4],
                stroke: [0; 4],
                halo: [0; 4],
                size: 0.0,
                width: 0.0,
                opacity: 0.0,
                shape: 0,
                dash: 0,
                arrow: 0,
                state: 0,
            };
            n
        ];
        let Ok(theme) = u8::try_from(theme) else {
            return -1;
        };
        let Some(domain) = xyg_engine::graph_style::resolve_semantic_styles(
            xyg_engine::graph_style::SemanticStyleInput {
                classes: input!(classes),
                epistemic: input!(epistemic),
                statuses: input!(statuses),
                metric: input!(metric),
                flags: input!(flags),
                edge: edge != 0,
                theme,
            },
            &mut resolved,
        ) else {
            return -1;
        };
        for (i, style) in resolved.iter().enumerate() {
            std::ptr::copy_nonoverlapping(style.fill.as_ptr(), fill_rgba.add(i * 4), 4);
            std::ptr::copy_nonoverlapping(style.stroke.as_ptr(), stroke_rgba.add(i * 4), 4);
            std::ptr::copy_nonoverlapping(style.halo.as_ptr(), halo_rgba.add(i * 4), 4);
            *size.add(i) = style.size;
            *width.add(i) = style.width;
            *opacity.add(i) = style.opacity;
            *shape.add(i) = style.shape;
            *dash.add(i) = style.dash;
            *arrow.add(i) = style.arrow;
            *state.add(i) = style.state;
        }
        *out_domain_lo = domain.0;
        *out_domain_hi = domain.1;
        0
    })
}

/// Query/copy deterministic v1 GraphForge semantic legend descriptors (#34).
///
/// `out_count` always receives the required count after valid input. A zero
/// capacity is a query; insufficient nonzero capacity returns -2 atomically.
/// RGBA output addresses `capacity * 4` bytes, other outputs `capacity`.
///
/// # Safety
/// Inputs address `n` elements. Non-empty outputs address their declared capacity.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_semantic_legend(
    version: u32,
    theme: u32,
    n: u64,
    classes: *const u8,
    epistemic: *const u8,
    statuses: *const u8,
    capacity: u64,
    out_field: *mut u8,
    out_value: *mut u8,
    out_rgba: *mut u8,
    out_shape: *mut u8,
    out_count: *mut u64,
) -> i32 {
    let (Ok(n), Ok(capacity), Ok(theme)) = (
        usize::try_from(n),
        usize::try_from(capacity),
        u8::try_from(theme),
    ) else {
        return -1;
    };
    if version != xyg_engine::graph_style::RESOLVED_STYLE_VERSION
        || out_count.is_null()
        || (n > 0 && (classes.is_null() || epistemic.is_null() || statuses.is_null()))
        || (capacity > 0
            && (out_field.is_null()
                || out_value.is_null()
                || out_rgba.is_null()
                || out_shape.is_null()))
    {
        return -1;
    }
    ffi_guard(-1, || {
        macro_rules! input {
            ($p:expr) => {
                if n == 0 {
                    &[]
                } else {
                    std::slice::from_raw_parts($p, n)
                }
            };
        }
        let Some(entries) = xyg_engine::graph_style::semantic_legend(
            input!(classes),
            input!(epistemic),
            input!(statuses),
            theme,
        ) else {
            return -1;
        };
        *out_count = entries.len() as u64;
        if capacity == 0 {
            return 0;
        }
        if capacity < entries.len() {
            return -2;
        }
        for (i, entry) in entries.iter().enumerate() {
            *out_field.add(i) = entry.field;
            *out_value.add(i) = entry.value;
            *out_shape.add(i) = entry.shape;
            std::ptr::copy_nonoverlapping(entry.color.as_ptr(), out_rgba.add(i * 4), 4);
        }
        0
    })
}

/// Select graph labels under a deterministic Rust-owned budget (#34).
///
/// # Safety
/// Non-empty array pointers must address `n` elements and `out_count` must be writable.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_label_accept(
    n: u64,
    priorities: *const f64,
    budget: u64,
    floor: f64,
    out: *mut u8,
    out_count: *mut u64,
) -> i32 {
    let Ok(n) = usize::try_from(n) else {
        return -1;
    };
    if out_count.is_null() || (n > 0 && (priorities.is_null() || out.is_null())) {
        return -1;
    }
    ffi_guard(-1, || {
        let input = if n == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(priorities, n)
        };
        let output = if n == 0 {
            &mut []
        } else {
            std::slice::from_raw_parts_mut(out, n)
        };
        if let Some(count) = xyg_engine::graph_style::label_accept(input, budget, floor, output) {
            *out_count = count;
            0
        } else {
            -1
        }
    })
}

/// Compute direct compound membership and AABBs from the canonical parent map (#34).
///
/// # Safety
/// Every non-empty input/output pointer must address `n` elements of its declared type.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_graph_compound_bounds(
    n: u64,
    x: *const f64,
    y: *const f64,
    parents: *const u64,
    validity: *const u8,
    parent_of: *mut u64,
    is_compound: *mut u8,
    xmin: *mut f64,
    xmax: *mut f64,
    ymin: *mut f64,
    ymax: *mut f64,
) -> i32 {
    let Ok(n) = usize::try_from(n) else {
        return -1;
    };
    if n > 0
        && (x.is_null()
            || y.is_null()
            || parents.is_null()
            || validity.is_null()
            || parent_of.is_null()
            || is_compound.is_null()
            || xmin.is_null()
            || xmax.is_null()
            || ymin.is_null()
            || ymax.is_null())
    {
        return -1;
    }
    ffi_guard(-1, || {
        macro_rules! input {
            ($p:expr) => {
                if n == 0 {
                    &[]
                } else {
                    std::slice::from_raw_parts($p, n)
                }
            };
        }
        macro_rules! output {
            ($p:expr) => {
                if n == 0 {
                    &mut []
                } else {
                    std::slice::from_raw_parts_mut($p, n)
                }
            };
        }
        if xyg_engine::graph_style::compound_bounds(
            input!(x),
            input!(y),
            input!(parents),
            input!(validity),
            output!(parent_of),
            output!(is_compound),
            output!(xmin),
            output!(xmax),
            output!(ymin),
            output!(ymax),
        )
        .is_some()
        {
            0
        } else {
            -1
        }
    })
}

/// Apply one Rust-owned compound expand/collapse/toggle transition by stable
/// source-node identity. Aggregate LOD is rejected because its identities do
/// not correspond one-to-one with the source plane.
///
/// # Safety
/// Every non-empty plane addresses `n` elements; `out_changed` is writable.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn xyg_graph_compound_transition(
    n: u64,
    node_ids: *const u64,
    parents: *const u64,
    validity: *const u8,
    collapsed: *const u8,
    target_id: u64,
    action: u32,
    lod_tier: u32,
    out: *mut u8,
    out_changed: *mut u8,
) -> i32 {
    let (Ok(n), Ok(action), Ok(lod_tier)) = (
        usize::try_from(n),
        u8::try_from(action),
        u8::try_from(lod_tier),
    ) else {
        return -1;
    };
    if out_changed.is_null()
        || (n > 0
            && (node_ids.is_null()
                || parents.is_null()
                || validity.is_null()
                || collapsed.is_null()
                || out.is_null()))
    {
        return -1;
    }
    ffi_guard(-1, || {
        macro_rules! input {
            ($ptr:expr) => {
                if n == 0 {
                    &[]
                } else {
                    std::slice::from_raw_parts($ptr, n)
                }
            };
        }
        let output = if n == 0 {
            &mut []
        } else {
            std::slice::from_raw_parts_mut(out, n)
        };
        let Some(changed) = xyg_engine::graph_style::compound_collapse_transition(
            input!(node_ids),
            input!(parents),
            input!(validity),
            input!(collapsed),
            target_id,
            action,
            lod_tier,
            output,
        ) else {
            return -1;
        };
        *out_changed = u8::from(changed);
        0
    })
}

/// Pointer-only descriptor for Rust-owned semantic compound Scene compilation.
#[repr(C)]
pub struct XygGraphCompoundSceneDescriptor {
    pub version: u32,
    pub theme: u32,
    pub width: f64,
    pub height: f64,
    pub node_count: u64,
    pub edge_count: u64,
    pub title: *const u8,
    pub title_len: u64,
    pub x: *const f64,
    pub y: *const f64,
    pub node_classes: *const u8,
    pub node_epistemic: *const u8,
    pub node_statuses: *const u8,
    pub node_metric: *const f64,
    pub node_flags: *const u32,
    pub node_label_lengths: *const u32,
    pub sources: *const u64,
    pub targets: *const u64,
    pub edge_classes: *const u8,
    pub edge_epistemic: *const u8,
    pub edge_statuses: *const u8,
    pub edge_metric: *const f64,
    pub edge_flags: *const u32,
    pub edge_label_lengths: *const u32,
    pub label_payload: *const u8,
    pub label_payload_len: u64,
    pub parents: *const u64,
    pub parent_validity: *const u8,
    pub collapsed: *const u8,
    pub reserved: u64,
}

/// Compile semantic graph and compound/collapse planes to canonical Scene v12.
/// Returns required bytes, or `usize::MAX` for any malformed or over-limit input.
///
/// # Safety
/// The descriptor and every non-null plane must cover its declared count. If
/// `out_cap` is sufficient, `out` must address that many writable bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_graph_compound_scene(
    descriptor: *const XygGraphCompoundSceneDescriptor,
    out: *mut u8,
    out_cap: usize,
) -> usize {
    if descriptor.is_null() {
        return usize::MAX;
    }
    ffi_guard(usize::MAX, || {
        let d = &*descriptor;
        let Ok(n) = usize::try_from(d.node_count) else {
            return usize::MAX;
        };
        let Ok(e) = usize::try_from(d.edge_count) else {
            return usize::MAX;
        };
        let Ok(title_len) = usize::try_from(d.title_len) else {
            return usize::MAX;
        };
        let Ok(label_len) = usize::try_from(d.label_payload_len) else {
            return usize::MAX;
        };
        if d.reserved != 0
            || d.theme > u8::MAX as u32
            || n == 0
            || n.checked_add(e)
                .is_none_or(|v| v > xyg_engine::graph_style::MAX_SEMANTIC_GRAPH_SCENE_PRIMITIVES)
            || title_len > 4096
            || label_len > 8192
            || d.title.is_null()
            || d.x.is_null()
            || d.y.is_null()
            || d.node_classes.is_null()
            || d.node_epistemic.is_null()
            || d.node_statuses.is_null()
            || d.node_metric.is_null()
            || d.node_flags.is_null()
            || d.node_label_lengths.is_null()
            || d.parents.is_null()
            || d.parent_validity.is_null()
            || d.collapsed.is_null()
            || (e > 0
                && (d.sources.is_null()
                    || d.targets.is_null()
                    || d.edge_classes.is_null()
                    || d.edge_epistemic.is_null()
                    || d.edge_statuses.is_null()
                    || d.edge_metric.is_null()
                    || d.edge_flags.is_null()
                    || d.edge_label_lengths.is_null()))
            || (label_len > 0 && d.label_payload.is_null())
        {
            return usize::MAX;
        }
        let title_bytes = std::slice::from_raw_parts(d.title, title_len);
        let Ok(title) = std::str::from_utf8(title_bytes) else {
            return usize::MAX;
        };
        let node_lengths = std::slice::from_raw_parts(d.node_label_lengths, n);
        let edge_lengths = if e == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(d.edge_label_lengths, e)
        };
        let payload = if label_len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(d.label_payload, label_len)
        };
        let mut cursor = 0usize;
        let mut decode = |lengths: &[u32]| -> Option<Vec<&str>> {
            lengths
                .iter()
                .map(|&length| {
                    let end = cursor.checked_add(length as usize)?;
                    let text = std::str::from_utf8(payload.get(cursor..end)?).ok()?;
                    cursor = end;
                    Some(text)
                })
                .collect()
        };
        let Some(node_labels) = decode(node_lengths) else {
            return usize::MAX;
        };
        let Some(edge_labels) = decode(edge_lengths) else {
            return usize::MAX;
        };
        if cursor != payload.len() {
            return usize::MAX;
        }
        macro_rules! slice {
            ($ptr:expr, $len:expr) => {{
                if $len == 0 {
                    &[]
                } else {
                    std::slice::from_raw_parts($ptr, $len)
                }
            }};
        }
        let encoded = xyg_engine::graph_style::encode_compound_graph_scene(
            xyg_engine::graph_style::CompoundGraphSceneInput {
                graph: xyg_engine::graph_style::SemanticGraphSceneInput {
                    version: d.version,
                    width: d.width,
                    height: d.height,
                    theme: d.theme as u8,
                    title,
                    x: slice!(d.x, n),
                    y: slice!(d.y, n),
                    node_classes: slice!(d.node_classes, n),
                    node_epistemic: slice!(d.node_epistemic, n),
                    node_statuses: slice!(d.node_statuses, n),
                    node_metric: slice!(d.node_metric, n),
                    node_flags: slice!(d.node_flags, n),
                    node_labels: &node_labels,
                    sources: slice!(d.sources, e),
                    targets: slice!(d.targets, e),
                    edge_classes: slice!(d.edge_classes, e),
                    edge_epistemic: slice!(d.edge_epistemic, e),
                    edge_statuses: slice!(d.edge_statuses, e),
                    edge_metric: slice!(d.edge_metric, e),
                    edge_flags: slice!(d.edge_flags, e),
                    edge_labels: &edge_labels,
                },
                parents: slice!(d.parents, n),
                parent_validity: slice!(d.parent_validity, n),
                collapsed: slice!(d.collapsed, n),
            },
        );
        let Ok(encoded) = encoded else {
            return usize::MAX;
        };
        if out_cap >= encoded.len() {
            if !encoded.is_empty() && out.is_null() {
                return usize::MAX;
            }
            std::ptr::copy_nonoverlapping(encoded.as_ptr(), out, encoded.len());
        }
        encoded.len()
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

/// Compile grouped box samples into bounded canonical body, whisker/cap,
/// median, and optional outlier geometry. Returns the required active-group
/// count, or `usize::MAX` for invalid input. `out_n_outliers` receives the
/// statistical outlier count even when outlier geometry is disabled. Calls
/// with zero capacities are size queries.
///
/// # Safety
/// `values`, `offsets`, and `centers` must be aligned and readable for their
/// declared lengths; `offsets` and `out_n_outliers` must be non-null. For a
/// write call, `active_groups` must hold `group_cap` u32s, `group_records`
/// must hold `group_cap * 25` f64s, `outlier_offsets` must hold
/// `group_cap + 1` size_t values, and `outlier_records` must hold
/// `outlier_cap * 3` f64s. Group records are `[q1, median, q3, low, high,
/// body x0/y0/x1/y1, three whisker x0/y0/x1/y1 records, median x0/y0/x1/y1]`.
/// Outlier records are `[value, x, y]`; x/y are zero when outliers are hidden.
/// All writable
/// regions must be mutually non-overlapping and must not overlap readable
/// inputs for the duration of the call. Output pointers may be null for a size
/// query or when either supplied capacity is smaller than the required count.
#[no_mangle]
pub unsafe extern "C" fn xyg_box_geometry(
    values: *const f64,
    values_len: usize,
    offsets: *const usize,
    offsets_len: usize,
    centers: *const f64,
    centers_len: usize,
    width: f64,
    orientation: u32,
    show_outliers: i32,
    out_n_outliers: *mut usize,
    active_groups: *mut u32,
    group_records: *mut f64,
    outlier_offsets: *mut usize,
    outlier_records: *mut f64,
    group_cap: usize,
    outlier_cap: usize,
) -> usize {
    if (values_len > 0 && values.is_null())
        || offsets.is_null()
        || (centers_len > 0 && centers.is_null())
        || out_n_outliers.is_null()
        || !matches!(show_outliers, 0 | 1)
    {
        return usize::MAX;
    }
    let values = if values_len == 0 {
        &[]
    } else {
        std::slice::from_raw_parts(values, values_len)
    };
    let offsets = std::slice::from_raw_parts(offsets, offsets_len);
    let centers = if centers_len == 0 {
        &[]
    } else {
        std::slice::from_raw_parts(centers, centers_len)
    };
    let orientation = match orientation {
        0 => stats::BoxOrientation::Vertical,
        1 => stats::BoxOrientation::Horizontal,
        _ => return usize::MAX,
    };
    let Some(result) = ffi_guard(None, || {
        stats::grouped_box_geometry(
            values,
            offsets,
            centers,
            width,
            orientation,
            show_outliers != 0,
        )
    }) else {
        return usize::MAX;
    };
    let groups = result.active_groups.len();
    let outliers = result.outlier_values.len();
    *out_n_outliers = outliers;
    if group_cap < groups || outlier_cap < outliers {
        return groups;
    }
    if groups > 0
        && (active_groups.is_null() || group_records.is_null() || outlier_offsets.is_null())
        || outliers > 0 && outlier_records.is_null()
    {
        return usize::MAX;
    }
    for (dest, source) in std::slice::from_raw_parts_mut(active_groups, groups)
        .iter_mut()
        .zip(result.active_groups.iter().copied())
    {
        *dest = source as u32;
    }
    std::slice::from_raw_parts_mut(outlier_offsets, groups + 1)
        .copy_from_slice(&result.outlier_offsets);
    let group_records = std::slice::from_raw_parts_mut(group_records, groups * 25);
    for group in 0..groups {
        let record = &mut group_records[group * 25..(group + 1) * 25];
        record[..5].copy_from_slice(&result.stats[group * 5..(group + 1) * 5]);
        record[5..9].copy_from_slice(&[
            result.body_x0[group],
            result.body_y0[group],
            result.body_x1[group],
            result.body_y1[group],
        ]);
        for segment in 0..3 {
            let source = group * 3 + segment;
            let at = 9 + segment * 4;
            record[at..at + 4].copy_from_slice(&[
                result.whisker_x0[source],
                result.whisker_y0[source],
                result.whisker_x1[source],
                result.whisker_y1[source],
            ]);
        }
        record[21..25].copy_from_slice(&[
            result.median_x0[group],
            result.median_y0[group],
            result.median_x1[group],
            result.median_y1[group],
        ]);
    }
    if outliers > 0 {
        let outlier_records = std::slice::from_raw_parts_mut(outlier_records, outliers * 3);
        for index in 0..outliers {
            outlier_records[index * 3] = result.outlier_values[index];
            if show_outliers != 0 {
                outlier_records[index * 3 + 1] = result.outlier_x[index];
                outlier_records[index * 3 + 2] = result.outlier_y[index];
            } else {
                outlier_records[index * 3 + 1] = 0.0;
                outlier_records[index * 3 + 2] = 0.0;
            }
        }
    }
    groups
}

/// Borrowed x/y plus optional C for one hexbin FFI call.
type HexbinColumns<'a> = (&'a [f64], &'a [f64], Option<&'a [f64]>);

/// Optional explicit height and optional explicit data rectangle.
type HexbinPolicyArgs = (Option<usize>, Option<((f64, f64), (f64, f64))>);

/// Borrow hexbin source columns for one FFI call.
///
/// # Safety
/// Non-empty `x`/`y` (and `c` when non-null) must address `len` readable f64s.
unsafe fn hexbin_columns<'a>(
    x: *const f64,
    y: *const f64,
    c: *const f64,
    len: usize,
) -> Option<HexbinColumns<'a>> {
    let (xs, ys) = if len == 0 {
        (&[][..], &[][..])
    } else {
        if x.is_null() || y.is_null() {
            return None;
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
    Some((xs, ys, cs))
}

fn hexbin_policy_args(
    grid_h: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    use_range: i32,
) -> Option<HexbinPolicyArgs> {
    if !matches!(use_range, 0 | 1) {
        return None;
    }
    let grid_h = if grid_h == 0 { None } else { Some(grid_h) };
    let range = (use_range == 1).then_some(((x0, x1), (y0, y1)));
    Some((grid_h, range))
}

/// Resolve hexbin grid height and data domain. `grid_h == 0` selects the
/// matplotlib `int(width / √3)` default (floored at 2). `use_range` is exactly
/// zero (automatic finite-pair domain with the shared constant-pad rule) or one
/// (explicit finite increasing rectangle). `c` may be null; when present it
/// also participates in the finite-pair filter. Writes the resolved domain and
/// grid. Returns 1 on success, 0 when there is no finite pair or args are
/// invalid.
///
/// # Safety
/// Non-empty inputs and all out pointers must be valid for the given lengths.
#[no_mangle]
pub unsafe extern "C" fn xyg_hexbin_ingress(
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
    use_range: i32,
    out_x0: *mut f64,
    out_x1: *mut f64,
    out_y0: *mut f64,
    out_y1: *mut f64,
    out_grid_w: *mut usize,
    out_grid_h: *mut usize,
) -> i32 {
    if out_x0.is_null()
        || out_x1.is_null()
        || out_y0.is_null()
        || out_y1.is_null()
        || out_grid_w.is_null()
        || out_grid_h.is_null()
    {
        return 0;
    }
    let Some((grid_h, range)) = hexbin_policy_args(grid_h, x0, x1, y0, y1, use_range) else {
        return 0;
    };
    let Some((xs, ys, cs)) = hexbin_columns(x, y, c, len) else {
        return 0;
    };
    let Some(ingress) = ffi_guard(None, || {
        hexbin::hexbin_ingress(xs, ys, cs, grid_w, grid_h, range)
    }) else {
        return 0;
    };
    *out_x0 = ingress.x0;
    *out_x1 = ingress.x1;
    *out_y0 = ingress.y0;
    *out_y1 = ingress.y1;
    *out_grid_w = ingress.grid_w;
    *out_grid_h = ingress.grid_h;
    1
}

/// Matplotlib-compatible hex binning. `reduce` is 0=count, 1=mean, 2=sum.
/// `c` may be null when `reduce=count`. `grid_h == 0` selects the default
/// aspect; `use_range` is exactly zero (automatic domain) or one (explicit
/// `x0..y1`). Writes up to `capacity` occupied (or threshold-passing) cells
/// into the parallel out buffers and sets `*out_dx` / `*out_dy`. Returns the
/// cell count written, or `usize::MAX` on invalid args / no finite pair /
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
    use_range: i32,
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
    let Some((grid_h, range)) = hexbin_policy_args(grid_h, x0, x1, y0, y1, use_range) else {
        return usize::MAX;
    };
    let Some((xs, ys, cs)) = hexbin_columns(x, y, c, len) else {
        return usize::MAX;
    };
    let result = match ffi_guard(None, || {
        hexbin::hexbin_with_policy(xs, ys, cs, grid_w, grid_h, range, mincnt, reduce)
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

/// Compile grouped violin samples to canonical bounded Rect geometry.
/// Returns the required rectangle count, or `usize::MAX` for invalid input.
/// A zero-capacity call is a size query; successful writes fill four `f64`
/// rectangle planes, active source-group indices, group-major edges, and
/// group-major unnormalised density values.
///
/// # Safety
/// `values`, `offsets`, and `centers` must be aligned and readable for their
/// respective declared lengths; `offsets` must be non-null even when its
/// length is zero. When `out_cap` is at least the returned required rectangle
/// count, each rectangle output must be aligned and writable for that count,
/// `out_groups` must be writable for the number of active groups,
/// `out_edges` for `active_groups * (bins + 1)` values, and `out_density` for
/// `active_groups * bins` values. All writable output regions must be
/// non-overlapping with one another and with the readable input regions for
/// the duration of the call. Output pointers may be null for a size query or
/// whenever `out_cap` is smaller than the required rectangle count.
#[no_mangle]
pub unsafe extern "C" fn xyg_violin_rects(
    values: *const f64,
    values_len: usize,
    offsets: *const usize,
    offsets_len: usize,
    centers: *const f64,
    centers_len: usize,
    bins: usize,
    width: f64,
    orientation: u32,
    out_x0: *mut f64,
    out_y0: *mut f64,
    out_x1: *mut f64,
    out_y1: *mut f64,
    out_groups: *mut u32,
    out_edges: *mut f64,
    out_density: *mut f64,
    out_cap: usize,
) -> usize {
    if (values_len > 0 && values.is_null())
        || offsets.is_null()
        || (centers_len > 0 && centers.is_null())
    {
        return usize::MAX;
    }
    let values = if values_len == 0 {
        &[]
    } else {
        std::slice::from_raw_parts(values, values_len)
    };
    let offsets = std::slice::from_raw_parts(offsets, offsets_len);
    let centers = if centers_len == 0 {
        &[]
    } else {
        std::slice::from_raw_parts(centers, centers_len)
    };
    let orientation = match orientation {
        0 => stats::ViolinOrientation::Vertical,
        1 => stats::ViolinOrientation::Horizontal,
        _ => return usize::MAX,
    };
    let Some(result) = ffi_guard(None, || {
        stats::violin_rects(values, offsets, centers, bins, width, orientation)
    }) else {
        return usize::MAX;
    };
    let required = result.x0.len();
    if out_cap < required {
        return required;
    }
    let groups = result.active_groups.len();
    if required > 0 && [out_x0, out_y0, out_x1, out_y1].iter().any(|p| p.is_null())
        || groups > 0 && (out_groups.is_null() || out_edges.is_null() || out_density.is_null())
    {
        return usize::MAX;
    }
    std::slice::from_raw_parts_mut(out_x0, required).copy_from_slice(&result.x0);
    std::slice::from_raw_parts_mut(out_y0, required).copy_from_slice(&result.y0);
    std::slice::from_raw_parts_mut(out_x1, required).copy_from_slice(&result.x1);
    std::slice::from_raw_parts_mut(out_y1, required).copy_from_slice(&result.y1);
    for (dest, source) in std::slice::from_raw_parts_mut(out_groups, groups)
        .iter_mut()
        .zip(result.active_groups)
    {
        *dest = source as u32;
    }
    std::slice::from_raw_parts_mut(out_edges, result.edges.len()).copy_from_slice(&result.edges);
    std::slice::from_raw_parts_mut(out_density, result.density.len())
        .copy_from_slice(&result.density);
    required
}

/// Uniform histogram edges. `method` is 0 = NumPy `bins="auto"` (Sturges vs
/// Freedman–Diaconis with sqrt/2 floor — see `stats::histogram_edges`), 1 =
/// Sturges alone. When `use_range` is 0, `lo`/`hi` are ignored and outer edges
/// come from the finite sample (empty → `[0,1]`). Returns the number of edges
/// written (`n_bins + 1`), or `usize::MAX` on invalid args, resource overflow,
/// or undersized capacity. Automatic resolution is capped at 10,000 bins.
///
/// # Safety
/// `out_edges` must hold `capacity` writable f64s and be non-null. Non-empty
/// `data` must be valid for `len` readable f64s.
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

// -- geographic columns (#47): opaque u64 handles over GeoColumn ------------

fn geo_slice_f64<'a>(ptr: *const f64, len: usize) -> Option<&'a [f64]> {
    if len == 0 {
        Some(&[])
    } else if ptr.is_null() {
        None
    } else {
        Some(unsafe { std::slice::from_raw_parts(ptr, len) })
    }
}

fn geo_slice_u8<'a>(ptr: *const u8, len: usize) -> Option<&'a [u8]> {
    if len == 0 {
        Some(&[])
    } else if ptr.is_null() {
        None
    } else {
        Some(unsafe { std::slice::from_raw_parts(ptr, len) })
    }
}

fn geo_slice_u32<'a>(ptr: *const u32, len: usize) -> Option<&'a [u32]> {
    if len == 0 {
        Some(&[])
    } else if ptr.is_null() {
        None
    } else {
        Some(unsafe { std::slice::from_raw_parts(ptr, len) })
    }
}

fn geo_slice_u64<'a>(ptr: *const u64, len: usize) -> Option<&'a [u64]> {
    if len == 0 {
        Some(&[])
    } else if ptr.is_null() {
        None
    } else {
        Some(unsafe { std::slice::from_raw_parts(ptr, len) })
    }
}

fn write_geo_error(out_error: *mut i32, err: geo::GeoError) {
    if !out_error.is_null() {
        unsafe {
            *out_error = err as i32;
        }
    }
}

/// Validate and retain a geographic column from a typed host descriptor.
///
/// `geometry` is `1..=6` (`point`…`multipolygon`). `crs` is `4326` or `3857`.
/// `xy_len` is the interleaved f64 length (`2 * vertex_count`). `validity_len`
/// is the feature count. `feature_ids` may be null to assign dense `0..n`.
/// Offset planes follow `spec/design/geospatial.md`; unused planes pass
/// null/`0`. On failure returns `0` and writes a negative `GeoError` code to
/// `out_error` (or leaves it untouched when null).
///
/// # Safety
/// Non-empty pointer/len pairs must address readable arrays of that length.
#[no_mangle]
pub unsafe extern "C" fn xyg_geo_column_new(
    geometry: u32,
    crs: u32,
    xy: *const f64,
    xy_len: usize,
    validity: *const u8,
    validity_len: usize,
    feature_ids: *const u64,
    offsets0: *const u32,
    offsets0_len: usize,
    offsets1: *const u32,
    offsets1_len: usize,
    offsets2: *const u32,
    offsets2_len: usize,
    out_error: *mut i32,
) -> u64 {
    ffi_guard(0, || {
        let Some(geometry) = geo::GeoGeometry::from_u32(geometry) else {
            write_geo_error(out_error, geo::GeoError::InvalidArgument);
            return 0;
        };
        let Some(crs) = geo::GeoCrs::from_u32(crs) else {
            write_geo_error(out_error, geo::GeoError::UnsupportedCrs);
            return 0;
        };
        let Some(xy) = geo_slice_f64(xy, xy_len) else {
            write_geo_error(out_error, geo::GeoError::InvalidArgument);
            return 0;
        };
        let Some(validity) = geo_slice_u8(validity, validity_len) else {
            write_geo_error(out_error, geo::GeoError::InvalidArgument);
            return 0;
        };
        let feature_ids = if feature_ids.is_null() {
            None
        } else {
            match geo_slice_u64(feature_ids, validity_len) {
                Some(ids) => Some(ids),
                None => {
                    write_geo_error(out_error, geo::GeoError::InvalidArgument);
                    return 0;
                }
            }
        };
        let Some(offsets0) = geo_slice_u32(offsets0, offsets0_len) else {
            write_geo_error(out_error, geo::GeoError::InvalidArgument);
            return 0;
        };
        let Some(offsets1) = geo_slice_u32(offsets1, offsets1_len) else {
            write_geo_error(out_error, geo::GeoError::InvalidArgument);
            return 0;
        };
        let Some(offsets2) = geo_slice_u32(offsets2, offsets2_len) else {
            write_geo_error(out_error, geo::GeoError::InvalidArgument);
            return 0;
        };
        let desc = geo::GeoDescriptor {
            geometry,
            crs,
            xy,
            validity,
            feature_ids,
            offsets0,
            offsets1,
            offsets2,
            limits: geo::GeoLimits::default(),
        };
        match geo::GeoColumn::from_descriptor(desc) {
            Ok(col) => {
                if !out_error.is_null() {
                    *out_error = 0;
                }
                geo::reg_insert(col)
            }
            Err(err) => {
                write_geo_error(out_error, err);
                0
            }
        }
    })
}

/// Free a geographic column handle. Returns 1 if it existed, 0 if stale.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_geo_column_free(handle: u64) -> i32 {
    ffi_guard(0, || if geo::reg_free(handle).is_ok() { 1 } else { 0 })
}

/// Feature count (including nulls). `usize::MAX` on a stale handle.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_geo_column_len(handle: u64) -> usize {
    ffi_guard(usize::MAX, || {
        geo::reg_with(handle, |c| c.len()).unwrap_or(usize::MAX)
    })
}

/// Retained vertex count. `usize::MAX` on a stale handle.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_geo_column_vertex_count(handle: u64) -> usize {
    ffi_guard(usize::MAX, || {
        geo::reg_with(handle, |c| c.vertex_count()).unwrap_or(usize::MAX)
    })
}

/// Geometry kind (`1..=6`). `0` on a stale handle.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_geo_column_geometry(handle: u64) -> u32 {
    ffi_guard(0, || {
        geo::reg_with(handle, |c| c.geometry() as u32).unwrap_or(0)
    })
}

/// CRS authority code (`4326` or `3857`). `0` on a stale handle.
///
/// # Safety
/// No pointer arguments; safe for any handle value.
#[no_mangle]
pub unsafe extern "C" fn xyg_geo_column_crs(handle: u64) -> u32 {
    ffi_guard(0, || geo::reg_with(handle, |c| c.crs() as u32).unwrap_or(0))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn binned_ecdf_ffi_is_compact_bounded_and_atomic() {
        let values = [-1.0, 0.25, 0.75, 2.0, f64::NAN];
        let mut x = [-9.0; 3];
        let mut cumulative = [-8.0; 3];
        assert_eq!(
            unsafe {
                xyg_binned_ecdf(
                    values.as_ptr(),
                    values.len(),
                    2,
                    0.0,
                    1.0,
                    1,
                    x.as_mut_ptr(),
                    cumulative.as_mut_ptr(),
                    x.len(),
                )
            },
            3
        );
        assert_eq!(x, [0.0, 0.5, 1.0]);
        assert_eq!(cumulative, [0.0, 0.25, 0.5]);

        let sentinel_x = [11.0; 3];
        let sentinel_y = [12.0; 3];
        x = sentinel_x;
        cumulative = sentinel_y;
        assert_eq!(
            unsafe {
                xyg_binned_ecdf(
                    values.as_ptr(),
                    values.len(),
                    2,
                    1.0,
                    0.0,
                    1,
                    x.as_mut_ptr(),
                    cumulative.as_mut_ptr(),
                    x.len(),
                )
            },
            usize::MAX
        );
        assert_eq!(x, sentinel_x);
        assert_eq!(cumulative, sentinel_y);
        assert_eq!(
            unsafe {
                xyg_binned_ecdf(
                    values.as_ptr(),
                    values.len(),
                    2,
                    0.0,
                    1.0,
                    1,
                    x.as_mut_ptr(),
                    x.as_mut_ptr(),
                    x.len(),
                )
            },
            usize::MAX
        );
        assert_eq!(x, sentinel_x);
        let mut partially_overlapping = [13.0; 6];
        assert_eq!(
            unsafe {
                xyg_binned_ecdf(
                    values.as_ptr(),
                    values.len(),
                    1,
                    0.0,
                    1.0,
                    1,
                    partially_overlapping.as_mut_ptr(),
                    partially_overlapping.as_mut_ptr().add(2),
                    4,
                )
            },
            usize::MAX
        );
        assert_eq!(partially_overlapping, [13.0; 6]);
        assert_eq!(
            unsafe {
                xyg_binned_ecdf(
                    values.as_ptr(),
                    values.len(),
                    2,
                    0.0,
                    1.0,
                    1,
                    x.as_mut_ptr(),
                    cumulative.as_mut_ptr(),
                    2,
                )
            },
            usize::MAX
        );
        assert_eq!(x, sentinel_x);
        assert_eq!(cumulative, sentinel_y);
    }

    #[test]
    fn histogram_bins_ffi_is_bounded_and_atomic() {
        let values = [0.1, 0.2, 1.2, 2.4, f64::NAN];
        let edges = [0.0, 1.0, 2.0, 3.0];
        let mut counts = [-7.0; 3];
        assert_eq!(
            unsafe {
                xyg_histogram_bins(
                    values.as_ptr(),
                    values.len(),
                    edges.as_ptr(),
                    edges.len(),
                    0,
                    1,
                    counts.as_mut_ptr(),
                )
            },
            3
        );
        assert_eq!(counts, [2.0, 3.0, 4.0]);

        let sentinel = [11.0; 3];
        counts = sentinel;
        assert_eq!(
            unsafe {
                xyg_histogram_bins(
                    values.as_ptr(),
                    values.len(),
                    edges.as_ptr(),
                    edges.len(),
                    2,
                    0,
                    counts.as_mut_ptr(),
                )
            },
            usize::MAX
        );
        assert_eq!(counts, sentinel);
        assert_eq!(
            unsafe {
                xyg_histogram_bins(
                    values.as_ptr(),
                    values.len(),
                    edges.as_ptr(),
                    1,
                    0,
                    0,
                    counts.as_mut_ptr(),
                )
            },
            usize::MAX
        );
        assert_eq!(counts, sentinel);
        let mut overlapping = [0.0, 1.0, 2.0, 3.0];
        assert_eq!(
            unsafe {
                xyg_histogram_bins(
                    values.as_ptr(),
                    values.len(),
                    overlapping.as_ptr(),
                    overlapping.len(),
                    0,
                    0,
                    overlapping.as_mut_ptr(),
                )
            },
            usize::MAX
        );
        assert_eq!(overlapping, [0.0, 1.0, 2.0, 3.0]);
    }

    #[test]
    fn hexbin_ffi_auto_policy_and_explicit_range() {
        let x = [10.0, f64::NAN, 10.0];
        let y = [4.0, 1.0, 4.0];
        let mut out_x0 = 0.0;
        let mut out_x1 = 0.0;
        let mut out_y0 = 0.0;
        let mut out_y1 = 0.0;
        let mut out_w = 0usize;
        let mut out_h = 0usize;
        assert_eq!(
            unsafe {
                xyg_hexbin_ingress(
                    x.as_ptr(),
                    y.as_ptr(),
                    std::ptr::null(),
                    x.len(),
                    16,
                    0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0,
                    &mut out_x0,
                    &mut out_x1,
                    &mut out_y0,
                    &mut out_y1,
                    &mut out_w,
                    &mut out_h,
                )
            },
            1
        );
        assert_eq!((out_w, out_h), (16, 9));
        assert!((out_x0 - 9.5).abs() < 1e-12);
        assert!((out_x1 - 10.5).abs() < 1e-12);
        assert!((out_y0 - 3.8).abs() < 1e-12);
        assert!((out_y1 - 4.2).abs() < 1e-12);

        let cap = hexbin::hexbin_capacity(4, 4);
        let mut cx = vec![0.0; cap];
        let mut cy = vec![0.0; cap];
        let mut metric = vec![0.0; cap];
        let mut counts = vec![0.0; cap];
        let mut dx = 0.0;
        let mut dy = 0.0;
        let hx_x = [0.1, 0.5, 0.9, 0.2];
        let hx_y = [0.1, 0.5, 0.9, 0.8];
        let written = unsafe {
            xyg_hexbin(
                hx_x.as_ptr(),
                hx_y.as_ptr(),
                std::ptr::null(),
                hx_x.len(),
                4,
                4,
                0.0,
                1.0,
                0.0,
                1.0,
                1,
                1,
                0,
                cx.as_mut_ptr(),
                cy.as_mut_ptr(),
                metric.as_mut_ptr(),
                counts.as_mut_ptr(),
                cap,
                &mut dx,
                &mut dy,
            )
        };
        assert_eq!(written, 4);
        assert!((dx - 0.25).abs() < 1e-12);
        assert_eq!(counts[..written].iter().sum::<f64>(), 4.0);
        assert_eq!(
            unsafe {
                xyg_hexbin(
                    hx_x.as_ptr(),
                    hx_y.as_ptr(),
                    std::ptr::null(),
                    hx_x.len(),
                    4,
                    4,
                    0.0,
                    1.0,
                    0.0,
                    1.0,
                    2,
                    1,
                    0,
                    cx.as_mut_ptr(),
                    cy.as_mut_ptr(),
                    metric.as_mut_ptr(),
                    counts.as_mut_ptr(),
                    cap,
                    &mut dx,
                    &mut dy,
                )
            },
            usize::MAX
        );
    }

    #[test]
    fn histogram_edges_write_capacity_and_resource_contract() {
        let data = [0.0, 1.0];
        let required = 41;
        let mut edges = vec![0.0; required];
        assert_eq!(
            unsafe {
                xyg_histogram_edges(
                    data.as_ptr(),
                    data.len(),
                    -10.0,
                    10.0,
                    1,
                    0,
                    edges.as_mut_ptr(),
                    edges.len(),
                )
            },
            required
        );
        assert_eq!((edges[0], edges[required - 1]), (-10.0, 10.0));
        assert_eq!(
            unsafe {
                xyg_histogram_edges(
                    data.as_ptr(),
                    data.len(),
                    -10.0,
                    10.0,
                    1,
                    0,
                    edges.as_mut_ptr(),
                    required - 1,
                )
            },
            usize::MAX
        );
        assert_eq!(
            unsafe {
                xyg_histogram_edges(
                    data.as_ptr(),
                    data.len(),
                    -10.0,
                    10.0,
                    1,
                    0,
                    std::ptr::null_mut(),
                    0,
                )
            },
            usize::MAX
        );
        let mut maximum = vec![0.0; stats::MAX_HISTOGRAM_BINS + 1];
        assert_eq!(
            unsafe {
                xyg_histogram_edges(
                    data.as_ptr(),
                    data.len(),
                    0.0,
                    stats::MAX_HISTOGRAM_BINS as f64 / 2.0 + 0.5,
                    1,
                    0,
                    maximum.as_mut_ptr(),
                    maximum.len(),
                )
            },
            usize::MAX
        );
    }

    #[test]
    fn scene_support_abi_queries_copies_and_rejects_unknown_bits() {
        let features = scene::SCENE_FEATURE_CUSTOM_FONT;
        let required = unsafe {
            xyg_scene_support_reason(
                scene::SCENE_SUPPORT_REQUEST_VERSION,
                features,
                std::ptr::null_mut(),
                0,
            )
        };
        assert!(required > 0 && required < 256);
        let mut output = vec![0; required];
        assert_eq!(
            unsafe {
                xyg_scene_support_reason(
                    scene::SCENE_SUPPORT_REQUEST_VERSION,
                    features,
                    output.as_mut_ptr(),
                    output.len(),
                )
            },
            required
        );
        assert!(std::str::from_utf8(&output)
            .unwrap()
            .starts_with("XYG_SCENE_UNSUPPORTED_CUSTOM_FONT:"));
        assert_eq!(
            unsafe {
                xyg_scene_support_reason(
                    scene::SCENE_SUPPORT_REQUEST_VERSION,
                    1 << 63,
                    std::ptr::null_mut(),
                    0,
                )
            },
            usize::MAX
        );
        assert_eq!(
            unsafe { xyg_scene_support_reason(1, 0, std::ptr::null_mut(), 1) },
            usize::MAX
        );
    }

    #[test]
    fn scene_scale_abi_rejects_malformed_boundaries() {
        let input = [1.0f64];
        let mut output = [0.0f64];
        let call = |kind,
                    operation,
                    lo,
                    hi,
                    px0,
                    px1,
                    constant,
                    mask,
                    len,
                    input_ptr,
                    output_ptr| unsafe {
            xyg_scene_scale_map(
                input_ptr, len, kind, operation, lo, hi, px0, px1, constant, mask, output_ptr,
            )
        };

        assert_eq!(
            call(
                99,
                1,
                0.0,
                1.0,
                0.0,
                1.0,
                1.0,
                0,
                1,
                input.as_ptr(),
                output.as_mut_ptr()
            ),
            1
        );
        assert_eq!(
            call(
                0,
                99,
                0.0,
                1.0,
                0.0,
                1.0,
                1.0,
                0,
                1,
                input.as_ptr(),
                output.as_mut_ptr()
            ),
            1
        );
        assert_eq!(
            call(
                0,
                1,
                0.0,
                1.0,
                0.0,
                1.0,
                1.0,
                2,
                1,
                input.as_ptr(),
                output.as_mut_ptr()
            ),
            1
        );
        assert_eq!(
            call(
                0,
                1,
                0.0,
                1.0,
                0.0,
                1.0,
                1.0,
                0,
                1,
                std::ptr::null(),
                output.as_mut_ptr()
            ),
            1
        );
        assert_eq!(
            call(
                0,
                1,
                0.0,
                1.0,
                0.0,
                1.0,
                1.0,
                0,
                1,
                input.as_ptr(),
                std::ptr::null_mut()
            ),
            1
        );
        assert_eq!(
            call(
                0,
                1,
                0.0,
                1.0,
                0.0,
                1.0,
                1.0,
                0,
                0,
                std::ptr::null(),
                std::ptr::null_mut()
            ),
            0
        );
        assert_eq!(
            call(
                0,
                1,
                0.0,
                1.0,
                0.0,
                1.0,
                1.0,
                0,
                scene::MAX_SCENE_MARKS + 1,
                input.as_ptr(),
                output.as_mut_ptr()
            ),
            1
        );

        for (lo, hi, px0, px1, constant) in [
            (f64::NAN, 1.0, 0.0, 1.0, 1.0),
            (0.0, f64::INFINITY, 0.0, 1.0, 1.0),
            (0.0, 1.0, f64::NEG_INFINITY, 1.0, 1.0),
            (0.0, 1.0, 0.0, f64::NAN, 1.0),
            (0.0, 1.0, 0.0, 1.0, 0.0),
            (0.0, 1.0, 0.0, 1.0, f64::NAN),
        ] {
            assert_eq!(
                call(
                    2,
                    1,
                    lo,
                    hi,
                    px0,
                    px1,
                    constant,
                    0,
                    1,
                    input.as_ptr(),
                    output.as_mut_ptr()
                ),
                1
            );
        }
    }

    #[test]
    fn scene_layout_axis_format_abi_is_bounded_utf8_without_nul() {
        let mut margins = [0.0; 4];
        let call = |format: *const u8, format_len: usize, margins: &mut [f64; 4]| unsafe {
            xyg_scene_plot_layout(
                320.0,
                240.0,
                std::ptr::null(),
                0,
                0.0,
                1.0,
                1.0,
                0,
                0,
                0.0,
                1.0,
                1.0,
                0,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                format,
                format_len,
                std::ptr::null(),
                0,
                0,
                margins.as_mut_ptr(),
            )
        };
        let valid = b"$,.1f USD";
        assert_eq!(call(valid.as_ptr(), valid.len(), &mut margins), 4);
        assert!(margins.iter().all(|value| value.is_finite()));
        let nul = b"$.1f\0USD";
        assert_eq!(call(nul.as_ptr(), nul.len(), &mut margins), usize::MAX);
        let invalid_utf8 = [0xff];
        assert_eq!(
            call(invalid_utf8.as_ptr(), invalid_utf8.len(), &mut margins),
            usize::MAX
        );
        let oversized = vec![b'x'; scene::MAX_SCENE_AXIS_FORMAT_BYTES + 1];
        assert_eq!(
            call(oversized.as_ptr(), oversized.len(), &mut margins),
            usize::MAX
        );
        assert_eq!(call(std::ptr::null(), 1, &mut margins), usize::MAX);
    }

    #[test]
    fn scene_authoring_envelope_is_exact_bounded_and_legacy_compatible() {
        let legacy = b"XYADlegacy";
        let (x, y, annotations) = decode_scene_authoring_input(legacy).unwrap();
        assert_eq!((x, y, annotations), (None, None, legacy.as_slice()));

        let x_format = b".1%";
        let y_format = b"$,.0f USD";
        let mut envelope = b"XYAF".to_vec();
        envelope.extend_from_slice(&1u32.to_le_bytes());
        envelope.extend_from_slice(&(x_format.len() as u32).to_le_bytes());
        envelope.extend_from_slice(&(y_format.len() as u32).to_le_bytes());
        envelope.extend_from_slice(&(legacy.len() as u32).to_le_bytes());
        envelope.extend_from_slice(x_format);
        envelope.extend_from_slice(y_format);
        envelope.extend_from_slice(legacy);
        assert_eq!(
            decode_scene_authoring_input(&envelope),
            Some((Some(".1%"), Some("$,.0f USD"), legacy.as_slice()))
        );

        let mut malformed = envelope.clone();
        malformed[4..8].copy_from_slice(&2u32.to_le_bytes());
        assert!(decode_scene_authoring_input(&malformed).is_none());
        let mut trailing = envelope.clone();
        trailing.push(0);
        assert!(decode_scene_authoring_input(&trailing).is_none());
        let mut nul = envelope.clone();
        nul[20] = 0;
        assert!(decode_scene_authoring_input(&nul).is_none());
        let mut invalid_utf8 = envelope.clone();
        invalid_utf8[20] = 0xff;
        assert!(decode_scene_authoring_input(&invalid_utf8).is_none());
        let mut oversized = envelope;
        oversized[8..12]
            .copy_from_slice(&((scene::MAX_SCENE_AXIS_FORMAT_BYTES + 1) as u32).to_le_bytes());
        assert!(decode_scene_authoring_input(&oversized).is_none());
    }

    #[test]
    fn scene_batch_abi_is_bounded_and_rejects_malformed_records() {
        let kinds = [0u8];
        let ids = [1u64];
        let styles = [0u32];
        let rgba = [0u8; 4];
        let widths = [1.0f64];
        let diameter = [8.0f64];
        let symbols = [2u8];
        let expansion_modes = [0u8];
        let values = [0.5f64];
        let chrome = scene::SceneChromeStyle::default().style_input();
        let mut output = [0u8; 464];
        let expansion_modes_ptr = std::cell::Cell::new(expansion_modes.as_ptr());
        let mut call = |kind, mask, len, kinds_ptr, major_ptr, major_count, major_auto| unsafe {
            xyg_scene_batch_encode(
                100.0,
                80.0,
                10.0,
                10.0,
                10.0,
                10.0,
                11,
                kind,
                0.0,
                1.0,
                1.0,
                mask,
                12,
                0,
                0.0,
                1.0,
                1.0,
                0,
                chrome.as_ptr(),
                chrome.len(),
                major_ptr,
                major_count,
                major_auto,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                1,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                kinds_ptr,
                ids.as_ptr(),
                styles.as_ptr(),
                rgba.as_ptr(),
                rgba.as_ptr(),
                widths.as_ptr(),
                1,
                diameter.as_ptr(),
                symbols.as_ptr(),
                expansion_modes_ptr.get(),
                values.as_ptr(),
                values.as_ptr(),
                values.as_ptr(),
                values.as_ptr(),
                len,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                output.as_mut_ptr(),
                output.len(),
            )
        };
        assert_eq!(call(0, 0, 1, kinds.as_ptr(), std::ptr::null(), 0, 1), 480);
        assert_eq!(
            call(99, 0, 1, kinds.as_ptr(), std::ptr::null(), 0, 1),
            usize::MAX
        );
        assert_eq!(
            call(0, 2, 1, kinds.as_ptr(), std::ptr::null(), 0, 1),
            usize::MAX
        );
        assert_eq!(
            call(0, 0, 1, std::ptr::null(), std::ptr::null(), 0, 1),
            usize::MAX
        );
        expansion_modes_ptr.set(std::ptr::null());
        assert_eq!(
            call(0, 0, 1, kinds.as_ptr(), std::ptr::null(), 0, 1),
            usize::MAX
        );
        expansion_modes_ptr.set(expansion_modes.as_ptr());
        assert_eq!(
            call(
                0,
                0,
                scene::MAX_SCENE_MARKS + 1,
                kinds.as_ptr(),
                std::ptr::null(),
                0,
                1
            ),
            usize::MAX
        );
        let invalid_kind = [9u8];
        assert_eq!(
            call(0, 0, 1, invalid_kind.as_ptr(), std::ptr::null(), 0, 1),
            usize::MAX
        );
        assert_eq!(
            call(0, 0, 1, kinds.as_ptr(), values.as_ptr(), 1, 1),
            usize::MAX
        );

        let log_kinds = [0u8, 1, 1, 2];
        let log_ids = [1u64, 20, 20, 30];
        let log_style_refs = [0u32; 4];
        let log_x0 = [2.0f64, 2.0, 0.0, 2.0];
        let log_y0 = [2.0f64; 4];
        let reserved_or_corner = [0.0f64; 4];
        let log_diameter = [6.0f64, 0.0, 0.0, 0.0];
        let log_symbols = [0u8; 4];
        let log_expansion_modes = [0u8; 4];
        let mut log_output = [0u8; 648];
        assert_eq!(
            unsafe {
                xyg_scene_batch_encode(
                    100.0,
                    100.0,
                    10.0,
                    10.0,
                    10.0,
                    10.0,
                    1,
                    1,
                    1.0,
                    10.0,
                    1.0,
                    1,
                    2,
                    1,
                    1.0,
                    10.0,
                    1.0,
                    1,
                    chrome.as_ptr(),
                    chrome.len(),
                    std::ptr::null(),
                    0,
                    1,
                    std::ptr::null(),
                    0,
                    std::ptr::null(),
                    0,
                    1,
                    std::ptr::null(),
                    0,
                    std::ptr::null(),
                    0,
                    std::ptr::null(),
                    0,
                    std::ptr::null(),
                    0,
                    log_kinds.as_ptr(),
                    log_ids.as_ptr(),
                    log_style_refs.as_ptr(),
                    rgba.as_ptr(),
                    rgba.as_ptr(),
                    widths.as_ptr(),
                    1,
                    log_diameter.as_ptr(),
                    log_symbols.as_ptr(),
                    log_expansion_modes.as_ptr(),
                    log_x0.as_ptr(),
                    log_y0.as_ptr(),
                    reserved_or_corner.as_ptr(),
                    reserved_or_corner.as_ptr(),
                    4,
                    std::ptr::null(),
                    0,
                    std::ptr::null(),
                    0,
                    std::ptr::null(),
                    0,
                    std::ptr::null(),
                    0,
                    std::ptr::null(),
                    0,
                    log_output.as_mut_ptr(),
                    log_output.len(),
                )
            },
            log_output.len()
        );
        let records = scene::SCENE_BATCH_HEADER_BYTES + scene::SCENE_STYLE_RECORD_BYTES;
        let flags: Vec<u8> = (0..4)
            .map(|index| log_output[records + index * scene::SCENE_BATCH_RECORD_BYTES + 1])
            .collect();
        assert_eq!(flags, vec![1, 1, 0, 0]);
    }

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

    #[test]
    fn graph_force_abi_rejects_nonfinite_initial_positions() {
        let sources = [0_u64];
        let targets = [1_u64];
        let finite = [0.0_f64, 1.0];
        let bad_x = [f64::NAN, 1.0];
        let bad_y = [0.0_f64, f64::INFINITY];
        for (x, y) in [(&bad_x[..], &finite[..]), (&finite[..], &bad_y[..])] {
            let mut handle = u64::MAX;
            let status = unsafe {
                xyg_graph_force_create(
                    2,
                    1,
                    sources.as_ptr(),
                    targets.as_ptr(),
                    x.as_ptr(),
                    y.as_ptr(),
                    7,
                    graph::LAYOUT_COSE,
                    &mut handle,
                )
            };
            assert_eq!(status, -1);
            assert_eq!(handle, 0);
        }
    }

    #[test]
    fn configured_cose_abi_preserves_pins_and_rejects_compound_cycles() {
        let sources = [0_u64];
        let targets = [1_u64];
        let x = [-0.5_f64, 0.5];
        let y = [0.0_f64, 0.0];
        let pinned = [1_u8, 0];
        let parents = [graph::COSE_NO_PARENT, 0];
        let bounds = [-1.0_f64, -1.0, 1.0, 1.0];
        let descriptor = XygCoseDescriptor {
            in_x: x.as_ptr(),
            in_y: y.as_ptr(),
            pinned: pinned.as_ptr(),
            parents: parents.as_ptr(),
            ideal_edge_length: 0.4,
            repulsion_strength: 2.0,
            gravity_strength: 0.2,
            cooling_factor: 0.9,
            overlap_padding: 0.5,
            component_spacing: 3.0,
            bounds: bounds.as_ptr(),
            has_bounds: 1,
            reserved: 0,
        };
        let mut handle = 0;
        unsafe {
            assert_eq!(
                xyg_graph_force_create_cose(
                    &descriptor,
                    2,
                    1,
                    sources.as_ptr(),
                    targets.as_ptr(),
                    7,
                    &mut handle,
                ),
                0
            );
            let (mut out_x, mut out_y, mut alpha) = ([0.0; 2], [0.0; 2], 0.0);
            assert_eq!(
                xyg_graph_force_tick(
                    handle,
                    2,
                    10,
                    out_x.as_mut_ptr(),
                    out_y.as_mut_ptr(),
                    &mut alpha,
                ),
                0
            );
            assert_eq!((out_x[0], out_y[0]), (x[0], y[0]));
            assert_eq!(xyg_graph_force_destroy(handle), 1);
        }

        let cyclic = [1_u64, 0];
        let bad = XygCoseDescriptor {
            parents: cyclic.as_ptr(),
            ..descriptor
        };
        handle = u64::MAX;
        unsafe {
            assert_eq!(
                xyg_graph_force_create_cose(
                    &bad,
                    2,
                    1,
                    sources.as_ptr(),
                    targets.as_ptr(),
                    7,
                    &mut handle,
                ),
                -1
            );
        }
        assert_eq!(handle, 0);
    }

    #[test]
    fn graph_force_abi_never_exposes_overflowed_positions() {
        let sources = [0_u64];
        let targets = [1_u64];
        let x = [f64::MAX, -f64::MAX];
        let y = [0.0_f64, 0.0];
        let mut handle = 0_u64;
        let create = unsafe {
            xyg_graph_force_create(
                2,
                1,
                sources.as_ptr(),
                targets.as_ptr(),
                x.as_ptr(),
                y.as_ptr(),
                7,
                graph::LAYOUT_COSE,
                &mut handle,
            )
        };
        assert_eq!(create, 0);
        assert_ne!(handle, 0);

        let mut out_x = [17.0_f64; 2];
        let mut out_y = [19.0_f64; 2];
        let mut alpha = 23.0_f64;
        let tick = unsafe {
            xyg_graph_force_tick(
                handle,
                2,
                1,
                out_x.as_mut_ptr(),
                out_y.as_mut_ptr(),
                &mut alpha,
            )
        };
        assert_eq!(tick, -1);
        assert_eq!(out_x, [17.0; 2]);
        assert_eq!(out_y, [19.0; 2]);
        assert_eq!(alpha, 23.0);
        assert_eq!(unsafe { xyg_graph_force_destroy(handle) }, 1);
    }

    #[test]
    fn geo_column_abi_round_trips_point() {
        let xy = [-104.9903_f64, 39.7392];
        let validity = [1_u8];
        let mut err = 0_i32;
        let handle = unsafe {
            xyg_geo_column_new(
                1,
                4326,
                xy.as_ptr(),
                xy.len(),
                validity.as_ptr(),
                validity.len(),
                std::ptr::null(),
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                &mut err,
            )
        };
        assert_eq!(err, 0);
        assert_ne!(handle, 0);
        unsafe {
            assert_eq!(xyg_geo_column_len(handle), 1);
            assert_eq!(xyg_geo_column_vertex_count(handle), 1);
            assert_eq!(xyg_geo_column_geometry(handle), 1);
            assert_eq!(xyg_geo_column_crs(handle), 4326);
            assert_eq!(xyg_geo_column_free(handle), 1);
            assert_eq!(xyg_geo_column_free(handle), 0);
        }
        let bad = unsafe {
            xyg_geo_column_new(
                1,
                9999,
                xy.as_ptr(),
                xy.len(),
                validity.as_ptr(),
                validity.len(),
                std::ptr::null(),
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                &mut err,
            )
        };
        assert_eq!(bad, 0);
        assert_eq!(err, -2);
    }

    #[test]
    fn temporal_poll_initializes_all_outputs_on_failure() {
        let mut has_event = 9_u32;
        let mut group_id = 9_u64;
        let mut source = 9_u64;
        let mut revision = 9_u64;
        let mut range_start = 9_i64;
        let mut range_end = 9_i64;
        let mut cursor = 9_i64;
        let mut window = 9_i64;
        let mut selection = [9_u64; 1];
        let mut selection_count = 9_u64;
        let status = unsafe {
            xyg_temporal_controller_poll_event(
                0,
                &mut has_event,
                &mut group_id,
                &mut source,
                &mut revision,
                &mut range_start,
                &mut range_end,
                &mut cursor,
                &mut window,
                selection.as_mut_ptr(),
                selection.len() as u64,
                &mut selection_count,
            )
        };
        assert_eq!(status, temporal::TemporalError::StaleHandle as i32);
        assert_eq!(
            (
                has_event,
                group_id,
                source,
                revision,
                range_start,
                range_end,
                cursor,
                window,
                selection_count,
            ),
            (0, 0, 0, 0, 0, 0, 0, 0, 0)
        );
    }

    #[test]
    fn temporal_selection_abi_is_exact_and_poll_capacity_is_atomic() {
        let controller = temporal_controller::TemporalController::create(
            81,
            990_081,
            0,
            100,
            10,
            20,
            1,
            temporal_controller::PlaybackDirection::Forward,
            1000,
            false,
            false,
        )
        .unwrap();
        let handle = temporal_controller::controller_insert(controller).unwrap();
        let authored = [u64::MAX, 7, 7, 0];
        assert_eq!(
            unsafe {
                xyg_temporal_controller_set_selection(
                    handle,
                    authored.as_ptr(),
                    authored.len() as u64,
                )
            },
            0
        );

        let mut short = [0_u64; 1];
        let mut has_event = 0;
        let mut group = 0;
        let mut source = 0;
        let mut revision = 0;
        let mut start = 0;
        let mut end = 0;
        let mut cursor = 0;
        let mut window = 0;
        let mut count = 0;
        assert_eq!(
            unsafe {
                xyg_temporal_controller_poll_event(
                    handle,
                    &mut has_event,
                    &mut group,
                    &mut source,
                    &mut revision,
                    &mut start,
                    &mut end,
                    &mut cursor,
                    &mut window,
                    short.as_mut_ptr(),
                    short.len() as u64,
                    &mut count,
                )
            },
            temporal::TemporalError::OutputCapacity as i32
        );
        assert_eq!(count, 3);

        let mut selection = [0_u64; 3];
        assert_eq!(
            unsafe {
                xyg_temporal_controller_poll_event(
                    handle,
                    &mut has_event,
                    &mut group,
                    &mut source,
                    &mut revision,
                    &mut start,
                    &mut end,
                    &mut cursor,
                    &mut window,
                    selection.as_mut_ptr(),
                    selection.len() as u64,
                    &mut count,
                )
            },
            0
        );
        assert_eq!(has_event, 1);
        assert_eq!(selection, [0, 7, u64::MAX]);
        assert!(temporal_controller::controller_remove(handle));
    }

    #[test]
    fn semantic_legend_query_and_short_copy_are_capacity_safe() {
        let classes = [2_u8, 1, 2];
        let epistemic = [3_u8, 3, 1];
        let statuses = [4_u8, 0, 4];
        let mut count = 0_u64;
        assert_eq!(
            unsafe {
                xyg_graph_semantic_legend(
                    1,
                    0,
                    3,
                    classes.as_ptr(),
                    epistemic.as_ptr(),
                    statuses.as_ptr(),
                    0,
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    &mut count,
                )
            },
            0
        );
        assert_eq!(count, 6);
        let mut field = [99_u8; 5];
        let mut value = [99_u8; 5];
        let mut rgba = [99_u8; 20];
        let mut shape = [99_u8; 5];
        assert_eq!(
            unsafe {
                xyg_graph_semantic_legend(
                    1,
                    0,
                    3,
                    classes.as_ptr(),
                    epistemic.as_ptr(),
                    statuses.as_ptr(),
                    5,
                    field.as_mut_ptr(),
                    value.as_mut_ptr(),
                    rgba.as_mut_ptr(),
                    shape.as_mut_ptr(),
                    &mut count,
                )
            },
            -2
        );
        assert_eq!(count, 6);
        assert_eq!(field, [99; 5]);
        assert_eq!(value, [99; 5]);
        assert_eq!(rgba, [99; 20]);
        assert_eq!(shape, [99; 5]);
    }

    #[test]
    fn box_geometry_query_short_copy_and_empty_outlier_plane_are_safe() {
        let values = [1.0_f64, 2.0, 3.0];
        let offsets = [0_usize, 3];
        let centers = [4.0_f64];
        let mut n_outliers = 99_usize;
        let query = unsafe {
            xyg_box_geometry(
                values.as_ptr(),
                values.len(),
                offsets.as_ptr(),
                offsets.len(),
                centers.as_ptr(),
                centers.len(),
                0.6,
                0,
                1,
                &mut n_outliers,
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                0,
                0,
            )
        };
        assert_eq!(query, 1);
        assert_eq!(n_outliers, 0);

        let mut active = [99_u32; 1];
        let mut records = [99.0_f64; 25];
        let mut outlier_offsets = [99_usize; 2];
        assert_eq!(
            unsafe {
                xyg_box_geometry(
                    values.as_ptr(),
                    values.len(),
                    offsets.as_ptr(),
                    offsets.len(),
                    centers.as_ptr(),
                    centers.len(),
                    0.6,
                    0,
                    1,
                    &mut n_outliers,
                    active.as_mut_ptr(),
                    records.as_mut_ptr(),
                    outlier_offsets.as_mut_ptr(),
                    std::ptr::null_mut(),
                    0,
                    0,
                )
            },
            1
        );
        assert_eq!(active, [99]);
        assert_eq!(records, [99.0; 25]);
        assert_eq!(
            unsafe {
                xyg_box_geometry(
                    values.as_ptr(),
                    values.len(),
                    offsets.as_ptr(),
                    offsets.len(),
                    centers.as_ptr(),
                    centers.len(),
                    0.6,
                    0,
                    1,
                    &mut n_outliers,
                    active.as_mut_ptr(),
                    records.as_mut_ptr(),
                    outlier_offsets.as_mut_ptr(),
                    std::ptr::null_mut(),
                    1,
                    0,
                )
            },
            1
        );
        assert_eq!(active, [0]);
        assert_eq!(outlier_offsets, [0, 0]);
        assert!(records.iter().all(|value| value.is_finite()));

        assert_eq!(
            unsafe {
                xyg_box_geometry(
                    values.as_ptr(),
                    values.len(),
                    offsets.as_ptr(),
                    offsets.len(),
                    centers.as_ptr(),
                    centers.len(),
                    0.6,
                    2,
                    1,
                    &mut n_outliers,
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    0,
                    0,
                )
            },
            usize::MAX
        );
    }

    #[test]
    fn violin_rects_query_and_short_copy_are_capacity_safe() {
        let values = [1.0_f64, 2.0];
        let offsets = [0_usize, 2];
        let centers = [0.0_f64];
        let required = unsafe {
            xyg_violin_rects(
                values.as_ptr(),
                values.len(),
                offsets.as_ptr(),
                offsets.len(),
                centers.as_ptr(),
                centers.len(),
                4,
                0.8,
                0,
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                0,
            )
        };
        assert_eq!(required, 4);

        let mut x0 = [99.0_f64; 3];
        let mut y0 = [99.0_f64; 3];
        let mut x1 = [99.0_f64; 3];
        let mut y1 = [99.0_f64; 3];
        let mut groups = [99_u32; 1];
        let mut edges = [99.0_f64; 5];
        let mut density = [99.0_f64; 4];
        assert_eq!(
            unsafe {
                xyg_violin_rects(
                    values.as_ptr(),
                    values.len(),
                    offsets.as_ptr(),
                    offsets.len(),
                    centers.as_ptr(),
                    centers.len(),
                    4,
                    0.8,
                    0,
                    x0.as_mut_ptr(),
                    y0.as_mut_ptr(),
                    x1.as_mut_ptr(),
                    y1.as_mut_ptr(),
                    groups.as_mut_ptr(),
                    edges.as_mut_ptr(),
                    density.as_mut_ptr(),
                    3,
                )
            },
            required
        );
        assert_eq!(x0, [99.0; 3]);
        assert_eq!(density, [99.0; 4]);

        let mut x0 = [0.0_f64; 4];
        let mut y0 = [0.0_f64; 4];
        let mut x1 = [0.0_f64; 4];
        let mut y1 = [0.0_f64; 4];
        assert_eq!(
            unsafe {
                xyg_violin_rects(
                    values.as_ptr(),
                    values.len(),
                    offsets.as_ptr(),
                    offsets.len(),
                    centers.as_ptr(),
                    centers.len(),
                    4,
                    0.8,
                    0,
                    x0.as_mut_ptr(),
                    y0.as_mut_ptr(),
                    x1.as_mut_ptr(),
                    y1.as_mut_ptr(),
                    groups.as_mut_ptr(),
                    edges.as_mut_ptr(),
                    density.as_mut_ptr(),
                    4,
                )
            },
            required
        );
        assert!(x0
            .into_iter()
            .chain(y0)
            .chain(x1)
            .chain(y1)
            .all(f64::is_finite));
        assert_eq!(groups, [0]);
        assert_eq!(
            unsafe {
                xyg_violin_rects(
                    values.as_ptr(),
                    values.len(),
                    offsets.as_ptr(),
                    offsets.len(),
                    centers.as_ptr(),
                    centers.len(),
                    4,
                    0.8,
                    2,
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    0,
                )
            },
            usize::MAX
        );
    }
}
