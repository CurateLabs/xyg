//! Figure autorange / domain policy (M2 #280).
//!
//! Hosts pack a versioned `XYAR` envelope of axis options plus per-trace
//! column extents and rectangle zero-baseline predicates. Rust owns padding,
//! log-positive extents, polar theta/radial defaults, reverse, degenerate
//! widening, default 3% margin, and zero-baseline pinning. Python
//! `Figure._range` / `_auto_domain` and Node `Figure._range` are thin packers
//! around this ABI so the hosts cannot drift on domain decisions.

use std::f64::consts::PI;

const XYAR_MAGIC: &[u8; 4] = b"XYAR";
const XYAR_VERSION: u32 = 1;
const XYAR_HEADER_BYTES: usize = 48;
const XYAR_TRACE_BYTES: usize = 4;
const XYAR_COLUMN_BYTES: usize = 40;
const MAX_XYAR_TRACES: usize = 4_096;
const MAX_XYAR_COLUMNS: usize = 8;

const FLAG_USE_DOMAIN: u32 = 1 << 0;
const FLAG_REVERSE: u32 = 1 << 1;
const FLAG_DOMAIN_PRESENT: u32 = 1 << 2;
const FLAG_MARGIN_PRESENT: u32 = 1 << 3;
const FLAG_POLAR: u32 = 1 << 4;
const FLAG_AXIS_DIM_X: u32 = 1 << 5;

const SCALE_LINEAR: u8 = 0;
const SCALE_LOG: u8 = 1;
const SCALE_SYMLOG: u8 = 2;

const KIND_LINEAR: u8 = 0;
const KIND_TIME: u8 = 1;
const KIND_CATEGORY: u8 = 2;

const THETA_RADIANS: u8 = 0;
const THETA_DEGREES: u8 = 1;

const TRACE_X_MATCH: u8 = 1 << 0;
const TRACE_Y_MATCH: u8 = 1 << 1;
const TRACE_ENDPOINTS: u8 = 1 << 2;
const TRACE_HAS_BASE: u8 = 1 << 3;

const ROLE_X: u8 = 0;
const ROLE_Y: u8 = 1;
const ROLE_X0: u8 = 2;
const ROLE_X1: u8 = 3;
const ROLE_Y0: u8 = 4;
const ROLE_Y1: u8 = 5;
const ROLE_BASE: u8 = 6;

const KIND_BAR: u8 = 2;
const KIND_COLUMN: u8 = 3;
const KIND_HISTOGRAM: u8 = 4;
const KIND_AREA: u8 = 12;
const KIND_ERROR_BAND: u8 = 13;
const KIND_RIBBON: u8 = 14;
const KIND_TRIANGLE_MESH: u8 = 15;

/// Packed rectangle zero-baseline predicates. `0xFF` means the trace is not a
/// candidate (wrong kind, missing endpoints, or axis mismatch).
pub const ZB_FINITE: u8 = 1 << 0;
pub const ZB_NONZERO_BASE: u8 = 1 << 1;
pub const ZB_NEG: u8 = 1 << 2;
pub const ZB_POS: u8 = 1 << 3;
pub const ZB_SKIP: u8 = 0xFF;

const DEFAULT_MARGIN: f64 = 0.03;

/// Why an autorange envelope was rejected. Discriminants are the C-ABI error
/// codes (returned negated by `xyg_figure_autorange`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AutorangeError {
    Length = 1,
    Version = 2,
    Limit = 3,
    LogNonPositive = 4,
}

struct Cursor<'a> {
    bytes: &'a [u8],
    offset: usize,
}

impl<'a> Cursor<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, offset: 0 }
    }

    fn remaining(&self) -> usize {
        self.bytes.len().saturating_sub(self.offset)
    }

    fn u8(&mut self) -> Result<u8, AutorangeError> {
        let value = *self.bytes.get(self.offset).ok_or(AutorangeError::Length)?;
        self.offset += 1;
        Ok(value)
    }

    fn u16(&mut self) -> Result<u16, AutorangeError> {
        let raw = self
            .bytes
            .get(self.offset..self.offset + 2)
            .ok_or(AutorangeError::Length)?;
        self.offset += 2;
        Ok(u16::from_le_bytes(
            raw.try_into().map_err(|_| AutorangeError::Length)?,
        ))
    }

    fn u32(&mut self) -> Result<u32, AutorangeError> {
        let raw = self
            .bytes
            .get(self.offset..self.offset + 4)
            .ok_or(AutorangeError::Length)?;
        self.offset += 4;
        Ok(u32::from_le_bytes(
            raw.try_into().map_err(|_| AutorangeError::Length)?,
        ))
    }

    fn f64(&mut self) -> Result<f64, AutorangeError> {
        let raw = self
            .bytes
            .get(self.offset..self.offset + 8)
            .ok_or(AutorangeError::Length)?;
        self.offset += 8;
        Ok(f64::from_le_bytes(
            raw.try_into().map_err(|_| AutorangeError::Length)?,
        ))
    }

    fn bytes(&mut self, count: usize) -> Result<&'a [u8], AutorangeError> {
        let end = self
            .offset
            .checked_add(count)
            .ok_or(AutorangeError::Limit)?;
        let slice = self
            .bytes
            .get(self.offset..end)
            .ok_or(AutorangeError::Length)?;
        self.offset = end;
        Ok(slice)
    }
}

#[derive(Clone, Copy)]
struct ColumnExtent {
    role: u8,
    min: f64,
    max: f64,
    pos_min: f64,
    pos_max: f64,
}

struct TraceRecord {
    kind: u8,
    flags: u8,
    zb_flags: u8,
    columns: Vec<ColumnExtent>,
}

/// Finite increasing domain for auto-scaled scalar marks.
///
/// Kernels require `hi > lo`; user data does not owe variance. Expand a
/// degenerate domain the same way Python `Figure._auto_domain` does so
/// constant histograms and heatmaps render instead of tripping a
/// precondition. `None` is the empty-input fallback `(0, 1)`.
pub fn auto_domain(bounds: Option<(f64, f64)>) -> (f64, f64) {
    let Some((lo, hi)) = bounds else {
        return (0.0, 1.0);
    };
    if lo == hi {
        let mut pad = lo.abs() * 0.05;
        if pad == 0.0 {
            pad = 0.5;
        }
        (lo - pad, hi + pad)
    } else {
        (lo, hi)
    }
}

/// Scan one rectangle baseline/value pair for zero-baseline pinning.
///
/// Bit 0: any finite pair; bit 1: any finite nonzero baseline; bit 2: any
/// finite negative value; bit 3: any finite positive value. Length mismatch
/// returns [`ZB_SKIP`].
pub fn rect_zero_baseline_flags(base: &[f64], value: &[f64]) -> u8 {
    if base.len() != value.len() {
        return ZB_SKIP;
    }
    let mut flags = 0u8;
    for (base_value, value_value) in base.iter().zip(value.iter()) {
        if !base_value.is_finite() || !value_value.is_finite() {
            continue;
        }
        flags |= ZB_FINITE;
        if *base_value != 0.0 {
            flags |= ZB_NONZERO_BASE;
        }
        if *value_value < 0.0 {
            flags |= ZB_NEG;
        }
        if *value_value > 0.0 {
            flags |= ZB_POS;
        }
    }
    flags
}

fn maybe_reverse(lo: f64, hi: f64, reverse: bool) -> (f64, f64) {
    if reverse {
        (hi, lo)
    } else {
        (lo, hi)
    }
}

fn column_for(trace: &TraceRecord, role: u8) -> Option<&ColumnExtent> {
    trace.columns.iter().find(|column| column.role == role)
}

fn contributing_roles(
    trace: &TraceRecord,
    axis_dim_x: bool,
) -> Result<&'static [u8], AutorangeError> {
    let matches = if axis_dim_x {
        trace.flags & TRACE_X_MATCH != 0
    } else {
        trace.flags & TRACE_Y_MATCH != 0
    };
    if !matches {
        return Ok(&[]);
    }
    let has_endpoints = trace.flags & TRACE_ENDPOINTS != 0;
    let has_base = trace.flags & TRACE_HAS_BASE != 0;
    if (trace.kind == KIND_AREA || trace.kind == KIND_ERROR_BAND) && has_base {
        return Ok(if axis_dim_x {
            &[ROLE_X]
        } else {
            &[ROLE_Y, ROLE_BASE]
        });
    }
    if trace.kind == KIND_TRIANGLE_MESH && has_endpoints {
        return Ok(if axis_dim_x {
            &[ROLE_X0, ROLE_X1, ROLE_X]
        } else {
            &[ROLE_Y0, ROLE_Y1, ROLE_Y]
        });
    }
    if trace.kind == KIND_RIBBON {
        let roles: &[u8] = if axis_dim_x {
            &[ROLE_X0, ROLE_X1]
        } else {
            &[ROLE_Y0, ROLE_Y1, ROLE_X, ROLE_Y]
        };
        for role in roles {
            if column_for(trace, *role).is_none() {
                return Err(AutorangeError::Length);
            }
        }
        return Ok(roles);
    }
    if has_endpoints {
        return Ok(if axis_dim_x {
            &[ROLE_X0, ROLE_X1]
        } else {
            &[ROLE_Y0, ROLE_Y1]
        });
    }
    Ok(if axis_dim_x { &[ROLE_X] } else { &[ROLE_Y] })
}

fn zero_baseline_anchor(traces: &[TraceRecord], axis_dim_x: bool) -> Option<&'static str> {
    for trace in traces {
        if !matches!(trace.kind, KIND_BAR | KIND_COLUMN | KIND_HISTOGRAM) {
            continue;
        }
        let matches = if axis_dim_x {
            trace.flags & TRACE_X_MATCH != 0
        } else {
            trace.flags & TRACE_Y_MATCH != 0
        };
        if !matches || trace.flags & TRACE_ENDPOINTS == 0 {
            continue;
        }
        if trace.zb_flags == ZB_SKIP {
            continue;
        }
        if trace.zb_flags & ZB_FINITE == 0 {
            continue;
        }
        if trace.zb_flags & ZB_NONZERO_BASE != 0 {
            continue;
        }
        if trace.zb_flags & ZB_NEG == 0 {
            return Some("lo");
        }
        if trace.zb_flags & ZB_POS == 0 {
            return Some("hi");
        }
    }
    None
}

/// Resolve a packed `XYAR` v1 envelope to the product `(lo, hi)` pair.
pub fn figure_autorange(bytes: &[u8]) -> Result<(f64, f64), AutorangeError> {
    if bytes.len() < XYAR_HEADER_BYTES {
        return Err(AutorangeError::Length);
    }
    let mut cur = Cursor::new(bytes);
    let magic = cur.bytes(4)?;
    if magic != XYAR_MAGIC {
        return Err(AutorangeError::Version);
    }
    let version = cur.u32()?;
    if version != XYAR_VERSION {
        return Err(AutorangeError::Version);
    }
    let flags = cur.u32()?;
    let scale = cur.u8()?;
    let axis_kind = cur.u8()?;
    let theta_unit = cur.u8()?;
    let _reserved = cur.u8()?;
    let n_traces = cur.u16()? as usize;
    let n_categories = cur.u16()?;
    let _pad = cur.u32()?;
    let domain_lo = cur.f64()?;
    let domain_hi = cur.f64()?;
    let margin = cur.f64()?;
    if n_traces > MAX_XYAR_TRACES {
        return Err(AutorangeError::Limit);
    }
    if !matches!(scale, SCALE_LINEAR | SCALE_LOG | SCALE_SYMLOG) {
        return Err(AutorangeError::Length);
    }
    if !matches!(axis_kind, KIND_LINEAR | KIND_TIME | KIND_CATEGORY) {
        return Err(AutorangeError::Length);
    }
    if !matches!(theta_unit, THETA_RADIANS | THETA_DEGREES) {
        return Err(AutorangeError::Length);
    }

    let use_domain = flags & FLAG_USE_DOMAIN != 0;
    let reverse = flags & FLAG_REVERSE != 0;
    let domain_present = flags & FLAG_DOMAIN_PRESENT != 0;
    let margin_present = flags & FLAG_MARGIN_PRESENT != 0;
    let polar = flags & FLAG_POLAR != 0;
    let axis_dim_x = flags & FLAG_AXIS_DIM_X != 0;

    let mut traces = Vec::with_capacity(n_traces);
    for _ in 0..n_traces {
        if cur.remaining() < XYAR_TRACE_BYTES {
            return Err(AutorangeError::Length);
        }
        let kind = cur.u8()?;
        let trace_flags = cur.u8()?;
        let n_columns = cur.u8()? as usize;
        let zb_flags = cur.u8()?;
        if n_columns > MAX_XYAR_COLUMNS {
            return Err(AutorangeError::Limit);
        }
        let mut columns = Vec::with_capacity(n_columns);
        for _ in 0..n_columns {
            if cur.remaining() < XYAR_COLUMN_BYTES {
                return Err(AutorangeError::Length);
            }
            let role = cur.u8()?;
            let _ = cur.bytes(7)?;
            columns.push(ColumnExtent {
                role,
                min: cur.f64()?,
                max: cur.f64()?,
                pos_min: cur.f64()?,
                pos_max: cur.f64()?,
            });
        }
        traces.push(TraceRecord {
            kind,
            flags: trace_flags,
            zb_flags,
            columns,
        });
    }
    if cur.remaining() != 0 {
        return Err(AutorangeError::Length);
    }

    if use_domain && domain_present {
        return Ok(maybe_reverse(domain_lo, domain_hi, reverse));
    }

    let mut lo = f64::INFINITY;
    let mut hi = f64::NEG_INFINITY;
    for trace in &traces {
        for role in contributing_roles(trace, axis_dim_x)? {
            let Some(column) = column_for(trace, *role) else {
                continue;
            };
            if column.min.is_finite() {
                lo = lo.min(column.min);
            }
            if column.max.is_finite() {
                hi = hi.max(column.max);
            }
        }
    }
    if !lo.is_finite() || !hi.is_finite() {
        lo = 0.0;
        hi = 1.0;
    }

    if scale == SCALE_LOG {
        let mut positive_lo = f64::INFINITY;
        let mut positive_hi = f64::NEG_INFINITY;
        let mut any = false;
        for trace in &traces {
            for role in contributing_roles(trace, axis_dim_x)? {
                let Some(column) = column_for(trace, *role) else {
                    continue;
                };
                if column.pos_min.is_finite() {
                    any = true;
                    positive_lo = positive_lo.min(column.pos_min);
                    if column.pos_max.is_finite() {
                        positive_hi = positive_hi.max(column.pos_max);
                    }
                }
            }
        }
        if !any {
            return Err(AutorangeError::LogNonPositive);
        }
        lo = positive_lo;
        hi = positive_hi;
    }

    if polar && axis_dim_x {
        if n_categories > 0 {
            return Ok((0.0, f64::from(n_categories) - 1.0));
        }
        let turn = if theta_unit == THETA_DEGREES {
            360.0
        } else {
            2.0 * PI
        };
        return Ok((0.0, turn));
    }

    if lo == hi && !margin_present {
        if polar && !axis_dim_x && scale != SCALE_LOG && axis_kind != KIND_TIME {
            let lo_out = 0.0_f64.min(lo);
            let hi_out = if hi > lo_out { hi } else { lo_out + 1.0 };
            return Ok(maybe_reverse(lo_out, hi_out, reverse));
        }
        let mut pad = lo.abs() * 0.05;
        if pad == 0.0 {
            pad = 0.5;
        }
        lo -= pad;
        hi += pad;
        if scale == SCALE_LOG && lo <= 0.0 {
            lo = hi / 10.0;
        }
        return Ok(maybe_reverse(lo, hi, reverse));
    }

    if lo == hi {
        hi = lo + 1.0;
    }
    let configured_margin = if margin_present {
        margin
    } else {
        DEFAULT_MARGIN
    };
    let (mut out_lo, mut out_hi) = if scale == SCALE_LOG && margin_present {
        let transformed_lo = lo.log10();
        let transformed_hi = hi.log10();
        let pad = (transformed_hi - transformed_lo) * configured_margin;
        let out_lo = (10.0_f64.powf(transformed_lo - pad)).max(0.0_f64.next_up());
        let out_hi = 10.0_f64.powf(transformed_hi + pad);
        (out_lo, out_hi)
    } else {
        let pad = (hi - lo) * configured_margin;
        (lo - pad, hi + pad)
    };

    if polar && !axis_dim_x {
        if axis_kind == KIND_TIME {
            return Ok(maybe_reverse(out_lo, out_hi, reverse));
        }
        if scale == SCALE_LOG {
            out_lo = lo;
        } else if lo >= 0.0 {
            out_lo = 0.0;
        }
        if (lo >= 0.0 || scale == SCALE_LOG) && !margin_present {
            out_hi = hi;
        }
        return Ok(maybe_reverse(out_lo, out_hi, reverse));
    }

    match zero_baseline_anchor(&traces, axis_dim_x) {
        Some("lo") if lo == 0.0 && hi > 0.0 => out_lo = 0.0,
        Some("hi") if hi == 0.0 && lo < 0.0 => out_hi = 0.0,
        _ => {}
    }
    if scale == SCALE_LOG && !margin_present {
        out_lo = out_lo.max(lo / 10.0).max(0.0_f64.next_up());
    }
    Ok(maybe_reverse(out_lo, out_hi, reverse))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn header(
        flags: u32,
        scale: u8,
        axis_kind: u8,
        theta_unit: u8,
        n_traces: u16,
        n_categories: u16,
        domain_lo: f64,
        domain_hi: f64,
        margin: f64,
    ) -> Vec<u8> {
        let mut buf = Vec::from(*XYAR_MAGIC);
        buf.extend_from_slice(&XYAR_VERSION.to_le_bytes());
        buf.extend_from_slice(&flags.to_le_bytes());
        buf.push(scale);
        buf.push(axis_kind);
        buf.push(theta_unit);
        buf.push(0);
        buf.extend_from_slice(&n_traces.to_le_bytes());
        buf.extend_from_slice(&n_categories.to_le_bytes());
        buf.extend_from_slice(&0u32.to_le_bytes());
        buf.extend_from_slice(&domain_lo.to_le_bytes());
        buf.extend_from_slice(&domain_hi.to_le_bytes());
        buf.extend_from_slice(&margin.to_le_bytes());
        buf
    }

    fn push_trace(buf: &mut Vec<u8>, kind: u8, flags: u8, zb: u8, columns: &[ColumnExtent]) {
        buf.push(kind);
        buf.push(flags);
        buf.push(columns.len() as u8);
        buf.push(zb);
        for column in columns {
            buf.push(column.role);
            buf.extend_from_slice(&[0; 7]);
            buf.extend_from_slice(&column.min.to_le_bytes());
            buf.extend_from_slice(&column.max.to_le_bytes());
            buf.extend_from_slice(&column.pos_min.to_le_bytes());
            buf.extend_from_slice(&column.pos_max.to_le_bytes());
        }
    }

    fn xy_column(min: f64, max: f64) -> [ColumnExtent; 2] {
        [
            ColumnExtent {
                role: ROLE_X,
                min,
                max,
                pos_min: if min > 0.0 { min } else { f64::NAN },
                pos_max: if max > 0.0 { max } else { f64::NAN },
            },
            ColumnExtent {
                role: ROLE_Y,
                min,
                max,
                pos_min: if min > 0.0 { min } else { f64::NAN },
                pos_max: if max > 0.0 { max } else { f64::NAN },
            },
        ]
    }

    #[test]
    fn auto_domain_none_and_degenerate() {
        assert_eq!(auto_domain(None), (0.0, 1.0));
        assert_eq!(auto_domain(Some((2.0, 5.0))), (2.0, 5.0));
        let (lo, hi) = auto_domain(Some((10.0, 10.0)));
        assert!((lo - 9.5).abs() < 1e-12);
        assert!((hi - 10.5).abs() < 1e-12);
        let (zlo, zhi) = auto_domain(Some((0.0, 0.0)));
        assert_eq!((zlo, zhi), (-0.5, 0.5));
    }

    #[test]
    fn cartesian_scatter_uses_three_percent_margin() {
        let mut bytes = header(FLAG_USE_DOMAIN, 0, 0, 0, 1, 0, 0.0, 0.0, 0.0);
        push_trace(
            &mut bytes,
            0,
            TRACE_X_MATCH | TRACE_Y_MATCH,
            ZB_SKIP,
            &xy_column(-5.0, 5.0),
        );
        let (lo, hi) = figure_autorange(&bytes).unwrap();
        assert!((lo - (-5.3)).abs() < 1e-12);
        assert!((hi - 5.3).abs() < 1e-12);
    }

    #[test]
    fn authored_domain_short_circuits() {
        let bytes = header(
            FLAG_USE_DOMAIN | FLAG_DOMAIN_PRESENT,
            0,
            0,
            0,
            0,
            0,
            2.0,
            8.0,
            0.0,
        );
        assert_eq!(figure_autorange(&bytes).unwrap(), (2.0, 8.0));
        let reversed = header(
            FLAG_USE_DOMAIN | FLAG_DOMAIN_PRESENT | FLAG_REVERSE,
            0,
            0,
            0,
            0,
            0,
            2.0,
            8.0,
            0.0,
        );
        assert_eq!(figure_autorange(&reversed).unwrap(), (8.0, 2.0));
    }

    #[test]
    fn log_requires_positive_extent() {
        let mut bytes = header(FLAG_USE_DOMAIN, SCALE_LOG, 0, 0, 1, 0, 0.0, 0.0, 0.0);
        push_trace(
            &mut bytes,
            0,
            TRACE_X_MATCH | TRACE_Y_MATCH,
            ZB_SKIP,
            &[ColumnExtent {
                role: ROLE_Y,
                min: -2.0,
                max: -1.0,
                pos_min: f64::NAN,
                pos_max: f64::NAN,
            }],
        );
        assert_eq!(
            figure_autorange(&bytes),
            Err(AutorangeError::LogNonPositive)
        );
    }

    #[test]
    fn polar_theta_is_a_full_turn() {
        let flags = FLAG_USE_DOMAIN | FLAG_POLAR | FLAG_AXIS_DIM_X;
        let bytes = header(flags, 0, 0, THETA_RADIANS, 0, 0, 0.0, 0.0, 0.0);
        let (lo, hi) = figure_autorange(&bytes).unwrap();
        assert_eq!(lo, 0.0);
        assert!((hi - 2.0 * PI).abs() < 1e-12);
        let degrees = header(flags, 0, 0, THETA_DEGREES, 0, 0, 0.0, 0.0, 0.0);
        assert_eq!(figure_autorange(&degrees).unwrap(), (0.0, 360.0));
        let cats = header(flags, 0, KIND_CATEGORY, THETA_RADIANS, 0, 4, 0.0, 0.0, 0.0);
        assert_eq!(figure_autorange(&cats).unwrap(), (0.0, 3.0));
    }

    #[test]
    fn zero_baseline_pins_positive_bars() {
        let mut bytes = header(FLAG_USE_DOMAIN, 0, 0, 0, 1, 0, 0.0, 0.0, 0.0);
        let columns = [
            ColumnExtent {
                role: ROLE_Y0,
                min: 0.0,
                max: 0.0,
                pos_min: f64::NAN,
                pos_max: f64::NAN,
            },
            ColumnExtent {
                role: ROLE_Y1,
                min: 2.0,
                max: 4.0,
                pos_min: 2.0,
                pos_max: 4.0,
            },
        ];
        push_trace(
            &mut bytes,
            KIND_BAR,
            TRACE_Y_MATCH | TRACE_ENDPOINTS,
            ZB_FINITE | ZB_POS,
            &columns,
        );
        let (lo, hi) = figure_autorange(&bytes).unwrap();
        assert_eq!(lo, 0.0);
        assert!((hi - 4.0 * 1.03).abs() < 1e-12);
    }

    #[test]
    fn rect_zero_baseline_flags_match_python_predicates() {
        let base = [0.0, 0.0, f64::NAN];
        let value = [2.0, 4.0, 1.0];
        assert_eq!(rect_zero_baseline_flags(&base, &value), ZB_FINITE | ZB_POS);
        let mixed_base = [0.0, 1.0];
        let mixed_value = [2.0, -3.0];
        assert_eq!(
            rect_zero_baseline_flags(&mixed_base, &mixed_value),
            ZB_FINITE | ZB_NONZERO_BASE | ZB_NEG | ZB_POS
        );
        assert_eq!(rect_zero_baseline_flags(&[0.0], &[1.0, 2.0]), ZB_SKIP);
    }

    #[test]
    fn rejects_unknown_version_and_trailing_bytes() {
        let mut bad = header(0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0);
        bad[4] = 2;
        assert_eq!(figure_autorange(&bad), Err(AutorangeError::Version));
        let mut extra = header(0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0);
        extra.push(0);
        assert_eq!(figure_autorange(&extra), Err(AutorangeError::Length));
    }
}
