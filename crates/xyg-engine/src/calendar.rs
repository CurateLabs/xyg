//! Shared integer Gregorian arithmetic. Callers retain their declared time units.
/// Gregorian fields from a day ordinal shifted by the civil epoch offset.
#[cfg_attr(target_arch = "wasm32", inline(never))]
pub(crate) fn civil_from_shifted_days(z: i64) -> (i64, u64, u64) {
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = (z - era * 146097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let mut year = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    if month <= 2 {
        year += 1;
    }
    (year, month, day)
}
/// First of a Gregorian month as an integer day ordinal (not a timestamp).
#[cfg_attr(target_arch = "wasm32", inline(never))]
pub(crate) fn month_days(year: i64, month: i64) -> i64 {
    let y = year - if month <= 2 { 1 } else { 0 };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = (y - era * 400) as u64;
    let doy = (153 * if month > 2 { month - 3 } else { month + 9 } + 2) as u64 / 5;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe as i64 - 719468
}
