//! Canonical i64 temporal columns and interval/event indexes (#43).
//!
//! Product contract (dossier §16, M5):
//! - Instants are signed UTC microseconds end-to-end — never f64 milliseconds
//!   or JSON numbers on the product wire.
//! - Half-open intervals `[start, end)`; null endpoints are unbounded;
//!   reversed intervals fail before any partial visibility output.
//! - Indexes emit visibility bitsets and never mutate source columns.
//! - Naive local timestamps require an explicit timezone string and a
//!   disambiguation policy; DST gap/fold rows fail (or resolve) per policy.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, OnceLock};

/// Source unit / retained precision for an ingested Arrow-like timestamp column.
#[repr(u32)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TemporalPrecision {
    Second = 0,
    Millisecond = 1,
    Microsecond = 2,
    Nanosecond = 3,
}

impl TemporalPrecision {
    pub fn from_u32(value: u32) -> Option<Self> {
        match value {
            0 => Some(Self::Second),
            1 => Some(Self::Millisecond),
            2 => Some(Self::Microsecond),
            3 => Some(Self::Nanosecond),
            _ => None,
        }
    }

    fn scale_to_micros(self) -> Option<i64> {
        match self {
            Self::Second => Some(1_000_000),
            Self::Millisecond => Some(1_000),
            Self::Microsecond => Some(1),
            // Nanoseconds truncate toward zero to whole microseconds after
            // range checks; scale is applied as a divide, not a multiply.
            Self::Nanosecond => None,
        }
    }
}

/// How to resolve ambiguous local civil times (DST folds).
#[repr(u32)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DisambiguationPolicy {
    /// Gaps and folds are hard errors.
    Reject = 0,
    /// Prefer the earlier UTC instant in a fold (pre-transition offset).
    PreferEarlier = 1,
    /// Prefer the later UTC instant in a fold (post-transition offset).
    PreferLater = 2,
}

impl DisambiguationPolicy {
    pub fn from_u32(value: u32) -> Option<Self> {
        match value {
            0 => Some(Self::Reject),
            1 => Some(Self::PreferEarlier),
            2 => Some(Self::PreferLater),
            _ => None,
        }
    }
}

/// Per-row DST classification supplied by the host (or a tz helper).
/// Unique rows carry the single applicable UTC offset seconds.
#[repr(u8)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DstStatus {
    Unique = 0,
    Gap = 1,
    Fold = 2,
}

impl DstStatus {
    pub fn from_u8(value: u8) -> Option<Self> {
        match value {
            0 => Some(Self::Unique),
            1 => Some(Self::Gap),
            2 => Some(Self::Fold),
            _ => None,
        }
    }
}

#[repr(i32)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TemporalError {
    InvalidArgument = -1,
    CapacityExceeded = -2,
    Overflow = -3,
    TimezoneRequired = -4,
    DstGap = -5,
    DstFold = -6,
    ReversedInterval = -7,
    StaleHandle = -8,
    OutputCapacity = -9,
    Cancelled = -10,
    BudgetExceeded = -11,
    UnitUnsupported = -12,
}

/// Canonical temporal column: UTC micros + validity + timezone + precision.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TemporalColumn {
    values: Vec<i64>,
    validity: Vec<u8>,
    timezone: String,
    precision: TemporalPrecision,
}

impl TemporalColumn {
    pub fn len(&self) -> usize {
        self.values.len()
    }

    pub fn is_empty(&self) -> bool {
        self.values.is_empty()
    }

    pub fn values(&self) -> &[i64] {
        &self.values
    }

    pub fn validity(&self) -> &[u8] {
        &self.validity
    }

    pub fn timezone(&self) -> &str {
        &self.timezone
    }

    pub fn precision(&self) -> TemporalPrecision {
        self.precision
    }

    /// Build from values that are already UTC microseconds.
    pub fn from_utc_micros(
        values: &[i64],
        validity: &[u8],
        timezone: &str,
        precision: TemporalPrecision,
    ) -> Result<Self, TemporalError> {
        validate_timezone(timezone)?;
        if values.len() != validity.len() {
            return Err(TemporalError::InvalidArgument);
        }
        for &bit in validity {
            if bit > 1 {
                return Err(TemporalError::InvalidArgument);
            }
        }
        Ok(Self {
            values: values.to_vec(),
            validity: validity.to_vec(),
            timezone: timezone.to_owned(),
            precision,
        })
    }

    /// Normalize unit-scaled integer timestamps that are already UTC instants.
    pub fn from_utc_unit(
        values: &[i64],
        validity: &[u8],
        timezone: &str,
        unit: TemporalPrecision,
    ) -> Result<Self, TemporalError> {
        let micros = normalize_unit_values(values, validity, unit)?;
        Self::from_utc_micros(&micros, validity, timezone, unit)
    }

    /// Convert naive local unit values using per-row DST status and offsets.
    ///
    /// - `Unique`: `offset_seconds[i]` is the sole UTC offset.
    /// - `Gap`: always fails with [`TemporalError::DstGap`].
    /// - `Fold`: fails under [`DisambiguationPolicy::Reject`]; otherwise
    ///   `offset_seconds[i]` is the earlier offset and `fold_later_offset_seconds[i]`
    ///   is the later offset.
    #[allow(clippy::too_many_arguments)] // descriptor planes mirror the C ABI
    pub fn from_naive_local_unit(
        values: &[i64],
        validity: &[u8],
        timezone: &str,
        unit: TemporalPrecision,
        dst_status: &[u8],
        offset_seconds: &[i32],
        fold_later_offset_seconds: &[i32],
        policy: DisambiguationPolicy,
    ) -> Result<Self, TemporalError> {
        validate_timezone(timezone)?;
        let n = values.len();
        if validity.len() != n
            || dst_status.len() != n
            || offset_seconds.len() != n
            || fold_later_offset_seconds.len() != n
        {
            return Err(TemporalError::InvalidArgument);
        }
        let local_micros = normalize_unit_values(values, validity, unit)?;
        let mut utc = Vec::with_capacity(n);
        for i in 0..n {
            if validity[i] == 0 {
                utc.push(0);
                continue;
            }
            if validity[i] != 1 {
                return Err(TemporalError::InvalidArgument);
            }
            let status = DstStatus::from_u8(dst_status[i]).ok_or(TemporalError::InvalidArgument)?;
            let offset = match status {
                DstStatus::Unique => offset_seconds[i],
                DstStatus::Gap => return Err(TemporalError::DstGap),
                DstStatus::Fold => match policy {
                    DisambiguationPolicy::Reject => return Err(TemporalError::DstFold),
                    DisambiguationPolicy::PreferEarlier => offset_seconds[i],
                    DisambiguationPolicy::PreferLater => fold_later_offset_seconds[i],
                },
            };
            utc.push(apply_utc_offset(local_micros[i], offset)?);
        }
        Self::from_utc_micros(&utc, validity, timezone, unit)
    }
}

fn validate_timezone(timezone: &str) -> Result<(), TemporalError> {
    if timezone.is_empty() || timezone.len() > 128 || timezone.bytes().any(|b| b == 0) {
        return Err(TemporalError::TimezoneRequired);
    }
    Ok(())
}

fn normalize_unit_values(
    values: &[i64],
    validity: &[u8],
    unit: TemporalPrecision,
) -> Result<Vec<i64>, TemporalError> {
    if values.len() != validity.len() {
        return Err(TemporalError::InvalidArgument);
    }
    let mut out = Vec::with_capacity(values.len());
    for (&value, &valid) in values.iter().zip(validity) {
        if valid > 1 {
            return Err(TemporalError::InvalidArgument);
        }
        if valid == 0 {
            out.push(0);
            continue;
        }
        out.push(to_utc_micros(value, unit)?);
    }
    Ok(out)
}

fn to_utc_micros(value: i64, unit: TemporalPrecision) -> Result<i64, TemporalError> {
    match unit.scale_to_micros() {
        Some(scale) => value.checked_mul(scale).ok_or(TemporalError::Overflow),
        None => {
            // Nanoseconds → microseconds, toward zero.
            Ok(value / 1_000)
        }
    }
}

fn apply_utc_offset(local_micros: i64, offset_seconds: i32) -> Result<i64, TemporalError> {
    let offset_micros = i64::from(offset_seconds)
        .checked_mul(1_000_000)
        .ok_or(TemporalError::Overflow)?;
    local_micros
        .checked_sub(offset_micros)
        .ok_or(TemporalError::Overflow)
}

/// Half-open interval endpoints. Null endpoints are unbounded.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct IntervalEndpoints<'a> {
    pub starts: &'a [i64],
    pub start_valid: &'a [u8],
    pub ends: &'a [i64],
    pub end_valid: &'a [u8],
}

/// Deterministic interval index over half-open `[start, end)` rows.
#[derive(Clone, Debug)]
pub struct IntervalIndex {
    starts: Vec<i64>,
    start_valid: Vec<u8>,
    ends: Vec<i64>,
    end_valid: Vec<u8>,
    /// Row order sorted by start (unbounded starts sort first).
    order: Vec<u32>,
}

impl IntervalIndex {
    pub const MAX_ROWS: usize = 50_000_000;

    pub fn build(endpoints: IntervalEndpoints<'_>) -> Result<Self, TemporalError> {
        let n = endpoints.starts.len();
        if n > Self::MAX_ROWS {
            return Err(TemporalError::CapacityExceeded);
        }
        if endpoints.start_valid.len() != n
            || endpoints.ends.len() != n
            || endpoints.end_valid.len() != n
        {
            return Err(TemporalError::InvalidArgument);
        }
        for i in 0..n {
            if endpoints.start_valid[i] > 1 || endpoints.end_valid[i] > 1 {
                return Err(TemporalError::InvalidArgument);
            }
            if endpoints.start_valid[i] == 1
                && endpoints.end_valid[i] == 1
                && endpoints.starts[i] >= endpoints.ends[i]
            {
                return Err(TemporalError::ReversedInterval);
            }
        }
        let mut order: Vec<u32> = (0..n as u32).collect();
        order.sort_by_key(|&idx| {
            let i = idx as usize;
            // Unbounded starts sort before all finite starts.
            if endpoints.start_valid[i] == 0 {
                (0_u8, i64::MIN)
            } else {
                (1_u8, endpoints.starts[i])
            }
        });
        Ok(Self {
            starts: endpoints.starts.to_vec(),
            start_valid: endpoints.start_valid.to_vec(),
            ends: endpoints.ends.to_vec(),
            end_valid: endpoints.end_valid.to_vec(),
            order,
        })
    }

    pub fn len(&self) -> usize {
        self.starts.len()
    }

    pub fn is_empty(&self) -> bool {
        self.starts.is_empty()
    }

    /// Visibility at an instant: row i is visible iff
    /// `(start is null || start <= t) && (end is null || t < end)`.
    pub fn visibility_at(
        &self,
        instant_micros: i64,
        out: &mut [u8],
        cancel: &CancelFlag,
        budget: usize,
    ) -> Result<(), TemporalError> {
        let n = self.starts.len();
        if out.len() < n {
            return Err(TemporalError::OutputCapacity);
        }
        if budget < n {
            return Err(TemporalError::BudgetExceeded);
        }
        if cancel.is_cancelled() {
            return Err(TemporalError::Cancelled);
        }
        for (i, (((&start, &start_valid), &end), &end_valid)) in self
            .starts
            .iter()
            .zip(self.start_valid.iter())
            .zip(self.ends.iter())
            .zip(self.end_valid.iter())
            .enumerate()
        {
            if (i & 0xffff) == 0 && cancel.is_cancelled() {
                return Err(TemporalError::Cancelled);
            }
            let start_ok = start_valid == 0 || start <= instant_micros;
            let end_ok = end_valid == 0 || instant_micros < end;
            out[i] = u8::from(start_ok && end_ok);
        }
        Ok(())
    }

    /// Event membership: an event instant is visible when it falls in `[start, end)`.
    #[allow(clippy::too_many_arguments)] // mirrors the C ABI filter surface
    pub fn events_in_range(
        &self,
        event_micros: &[i64],
        event_valid: &[u8],
        range_start: Option<i64>,
        range_end: Option<i64>,
        out: &mut [u8],
        cancel: &CancelFlag,
        budget: usize,
    ) -> Result<(), TemporalError> {
        let n = event_micros.len();
        if event_valid.len() != n || out.len() < n {
            return Err(TemporalError::InvalidArgument);
        }
        if let (Some(a), Some(b)) = (range_start, range_end) {
            if a >= b {
                return Err(TemporalError::ReversedInterval);
            }
        }
        if budget < n {
            return Err(TemporalError::BudgetExceeded);
        }
        if cancel.is_cancelled() {
            return Err(TemporalError::Cancelled);
        }
        for (i, (&t, &valid)) in event_micros.iter().zip(event_valid.iter()).enumerate() {
            if (i & 0xffff) == 0 && cancel.is_cancelled() {
                return Err(TemporalError::Cancelled);
            }
            if valid > 1 {
                return Err(TemporalError::InvalidArgument);
            }
            if valid == 0 {
                out[i] = 0;
                continue;
            }
            let start_ok = range_start.map(|s| t >= s).unwrap_or(true);
            let end_ok = range_end.map(|e| t < e).unwrap_or(true);
            out[i] = u8::from(start_ok && end_ok);
        }
        Ok(())
    }

    pub fn order(&self) -> &[u32] {
        &self.order
    }
}

/// Cooperative cancellation for long interval queries.
#[derive(Default, Debug)]
pub struct CancelFlag {
    cancelled: Mutex<bool>,
}

impl CancelFlag {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn cancel(&self) {
        *self.cancelled.lock().expect("cancel flag poisoned") = true;
    }

    pub fn is_cancelled(&self) -> bool {
        *self.cancelled.lock().expect("cancel flag poisoned")
    }
}

// -- handle registries -------------------------------------------------------

type ColumnRegistry = (u64, HashMap<u64, Arc<TemporalColumn>>);
type IndexRegistry = (u64, HashMap<u64, Arc<IntervalIndex>>);

static COLUMN_REGISTRY: OnceLock<Mutex<ColumnRegistry>> = OnceLock::new();
static INDEX_REGISTRY: OnceLock<Mutex<IndexRegistry>> = OnceLock::new();

fn column_registry() -> &'static Mutex<ColumnRegistry> {
    COLUMN_REGISTRY.get_or_init(|| Mutex::new((0, HashMap::new())))
}

fn index_registry() -> &'static Mutex<IndexRegistry> {
    INDEX_REGISTRY.get_or_init(|| Mutex::new((0, HashMap::new())))
}

pub fn column_insert(column: TemporalColumn) -> u64 {
    let mut guard = column_registry()
        .lock()
        .expect("temporal column registry poisoned");
    guard.0 = guard
        .0
        .checked_add(1)
        .expect("temporal column handle exhausted");
    let handle = guard.0;
    guard.1.insert(handle, Arc::new(column));
    handle
}

pub fn column_with<R>(handle: u64, f: impl FnOnce(&TemporalColumn) -> R) -> Option<R> {
    let column = {
        let guard = column_registry()
            .lock()
            .expect("temporal column registry poisoned");
        guard.1.get(&handle).cloned()
    };
    column.map(|value| f(&value))
}

pub fn column_remove(handle: u64) -> bool {
    column_registry()
        .lock()
        .expect("temporal column registry poisoned")
        .1
        .remove(&handle)
        .is_some()
}

pub fn index_insert(index: IntervalIndex) -> u64 {
    let mut guard = index_registry()
        .lock()
        .expect("temporal index registry poisoned");
    guard.0 = guard
        .0
        .checked_add(1)
        .expect("temporal index handle exhausted");
    let handle = guard.0;
    guard.1.insert(handle, Arc::new(index));
    handle
}

pub fn index_with<R>(handle: u64, f: impl FnOnce(&IntervalIndex) -> R) -> Option<R> {
    let index = {
        let guard = index_registry()
            .lock()
            .expect("temporal index registry poisoned");
        guard.1.get(&handle).cloned()
    };
    index.map(|value| f(&value))
}

pub fn index_remove(handle: u64) -> bool {
    index_registry()
        .lock()
        .expect("temporal index registry poisoned")
        .1
        .remove(&handle)
        .is_some()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preserves_sub_millisecond_utc_micros() {
        // Not exactly representable as f64 milliseconds.
        let micros = 1_704_067_200_000_123_i64;
        let col =
            TemporalColumn::from_utc_micros(&[micros], &[1], "UTC", TemporalPrecision::Microsecond)
                .unwrap();
        assert_eq!(col.values(), &[micros]);
        assert_eq!(col.timezone(), "UTC");
        assert_eq!(col.precision(), TemporalPrecision::Microsecond);
    }

    #[test]
    fn normalizes_units_and_rejects_overflow() {
        let col = TemporalColumn::from_utc_unit(
            &[1_704_067_200_000],
            &[1],
            "UTC",
            TemporalPrecision::Millisecond,
        )
        .unwrap();
        assert_eq!(col.values(), &[1_704_067_200_000_000]);

        let err =
            TemporalColumn::from_utc_unit(&[i64::MAX], &[1], "UTC", TemporalPrecision::Second)
                .unwrap_err();
        assert_eq!(err, TemporalError::Overflow);
    }

    #[test]
    fn truncates_nanoseconds_toward_zero() {
        let col = TemporalColumn::from_utc_unit(
            &[1_234_567_890],
            &[1],
            "America/New_York",
            TemporalPrecision::Nanosecond,
        )
        .unwrap();
        assert_eq!(col.values(), &[1_234_567]);
    }

    #[test]
    fn requires_timezone_and_valid_validity() {
        assert_eq!(
            TemporalColumn::from_utc_micros(&[0], &[1], "", TemporalPrecision::Microsecond)
                .unwrap_err(),
            TemporalError::TimezoneRequired
        );
        assert_eq!(
            TemporalColumn::from_utc_micros(&[0], &[2], "UTC", TemporalPrecision::Microsecond)
                .unwrap_err(),
            TemporalError::InvalidArgument
        );
    }

    #[test]
    fn dst_gap_and_fold_policies() {
        let values = [0_i64];
        let validity = [1_u8];
        assert_eq!(
            TemporalColumn::from_naive_local_unit(
                &values,
                &validity,
                "America/New_York",
                TemporalPrecision::Microsecond,
                &[DstStatus::Gap as u8],
                &[0],
                &[0],
                DisambiguationPolicy::PreferEarlier,
            )
            .unwrap_err(),
            TemporalError::DstGap
        );
        assert_eq!(
            TemporalColumn::from_naive_local_unit(
                &values,
                &validity,
                "America/New_York",
                TemporalPrecision::Microsecond,
                &[DstStatus::Fold as u8],
                &[-14400],
                &[-18000],
                DisambiguationPolicy::Reject,
            )
            .unwrap_err(),
            TemporalError::DstFold
        );
        let earlier = TemporalColumn::from_naive_local_unit(
            &[3_600_000_000],
            &validity,
            "America/New_York",
            TemporalPrecision::Microsecond,
            &[DstStatus::Fold as u8],
            &[-14400],
            &[-18000],
            DisambiguationPolicy::PreferEarlier,
        )
        .unwrap();
        assert_eq!(earlier.values(), &[3_600_000_000 + 14_400_000_000]);
        let later = TemporalColumn::from_naive_local_unit(
            &[3_600_000_000],
            &validity,
            "America/New_York",
            TemporalPrecision::Microsecond,
            &[DstStatus::Fold as u8],
            &[-14400],
            &[-18000],
            DisambiguationPolicy::PreferLater,
        )
        .unwrap();
        assert_eq!(later.values(), &[3_600_000_000 + 18_000_000_000]);
    }

    #[test]
    fn half_open_interval_membership_and_unbounded() {
        let index = IntervalIndex::build(IntervalEndpoints {
            starts: &[10, 0, 50],
            start_valid: &[1, 0, 1],
            ends: &[20, 40, 0],
            end_valid: &[1, 1, 0],
        })
        .unwrap();
        let mut out = [0_u8; 3];
        index
            .visibility_at(10, &mut out, &CancelFlag::new(), 3)
            .unwrap();
        assert_eq!(out, [1, 1, 0]);
        index
            .visibility_at(20, &mut out, &CancelFlag::new(), 3)
            .unwrap();
        // end-exclusive at 20 for row 0; unbounded start still visible until 40;
        // unbounded end from 50 is not yet visible.
        assert_eq!(out, [0, 1, 0]);
        index
            .visibility_at(50, &mut out, &CancelFlag::new(), 3)
            .unwrap();
        assert_eq!(out, [0, 0, 1]);
    }

    #[test]
    fn reversed_intervals_fail_before_output() {
        assert_eq!(
            IntervalIndex::build(IntervalEndpoints {
                starts: &[5],
                start_valid: &[1],
                ends: &[5],
                end_valid: &[1],
            })
            .unwrap_err(),
            TemporalError::ReversedInterval
        );
    }

    #[test]
    fn event_range_filter_is_half_open() {
        let index = IntervalIndex::build(IntervalEndpoints {
            starts: &[],
            start_valid: &[],
            ends: &[],
            end_valid: &[],
        })
        .unwrap();
        let events = [10_i64, 20, 30];
        let valid = [1_u8, 1, 1];
        let mut out = [0_u8; 3];
        index
            .events_in_range(
                &events,
                &valid,
                Some(10),
                Some(30),
                &mut out,
                &CancelFlag::new(),
                3,
            )
            .unwrap();
        assert_eq!(out, [1, 1, 0]);
    }

    #[test]
    fn pre_epoch_values_survive() {
        let col = TemporalColumn::from_utc_micros(
            &[-1_000_000],
            &[1],
            "UTC",
            TemporalPrecision::Microsecond,
        )
        .unwrap();
        assert_eq!(col.values(), &[-1_000_000]);
    }

    #[test]
    fn cancellation_and_budget_errors() {
        let index = IntervalIndex::build(IntervalEndpoints {
            starts: &[0, 1, 2],
            start_valid: &[1, 1, 1],
            ends: &[10, 10, 10],
            end_valid: &[1, 1, 1],
        })
        .unwrap();
        let mut out = [0_u8; 3];
        assert_eq!(
            index
                .visibility_at(5, &mut out, &CancelFlag::new(), 2)
                .unwrap_err(),
            TemporalError::BudgetExceeded
        );
        let cancel = CancelFlag::new();
        cancel.cancel();
        assert_eq!(
            index.visibility_at(5, &mut out, &cancel, 3).unwrap_err(),
            TemporalError::Cancelled
        );
    }
}
