//! XYTM v2 screen lattice and exact, bounded source-member pages (§28).
//! Source IDs are never representative IDs. Aggregate IDs are publication-local cells.
use super::{TemporalError, MAX_BYTES};

fn u(b: &[u8], i: usize) -> u32 {
    u32::from_le_bytes(b[i..i + 4].try_into().unwrap())
}
fn t(b: &[u8], i: usize) -> i64 {
    i64::from_le_bytes(b[i..i + 8].try_into().unwrap())
}
fn f(b: &[u8], i: usize) -> f64 {
    f64::from_le_bytes(b[i..i + 8].try_into().unwrap())
}
fn hash(bytes: &[u8]) -> u64 {
    bytes.iter().fold(0xcbf29ce484222325, |v, b| {
        (v ^ *b as u64).wrapping_mul(0x100000001b3)
    })
}
#[derive(Clone, Default)]
struct Cell {
    count: u64,
    hash: u64,
    min: f64,
    max: f64,
}

pub(super) fn compile(b: &[u8], budget: usize) -> Result<Vec<u8>, TemporalError> {
    use TemporalError::{BudgetExceeded as Limit, InvalidArgument as Bad};
    let n = u(b, 12) as usize;
    let kind = u(b, 8);
    let op = u(b, 88);
    let key = u(b, 92) as usize;
    let offset = u(b, 96) as usize;
    let limit = u(b, 100) as usize;
    if op > 2 || limit > 256 || b[120..128].iter().any(|&v| v != 0) {
        return Err(Bad);
    }
    let width = f(b, 16);
    let columns = ((width as usize - 89) / 4).max(1);
    let lanes = if kind == 3 || kind == 4 { 1 } else { 16 };
    let cells = columns * lanes;
    // Includes retained packed source, transport/staging copies, validation index,
    // grid, recursive Scene compilation scratch, both in-flight publications.
    let admitted = b
        .len()
        .checked_mul(3)
        .and_then(|v| v.checked_add(n.checked_mul(16)?))
        .and_then(|v| v.checked_add(cells.checked_mul(4096)?))
        .and_then(|v| v.checked_add(131072))
        .ok_or(Limit)?;
    if admitted > budget || budget > MAX_BYTES || (op == 1 && (key >= cells || limit == 0)) {
        return Err(Limit);
    }
    let at = 128 + u(b, 56) as usize + u(b, 60) as usize;
    if op == 1
        && (b[104..112] != hash(&b[at..]).to_le_bytes()
            || b[112..120] != hash(&b[8..88]).to_le_bytes())
    {
        return Err(Bad);
    }
    let zone = &b[128..128 + u(b, 56) as usize];
    if zone != b"UTC" {
        return Err(TemporalError::UnitUnsupported);
    }
    std::str::from_utf8(&b[128 + zone.len()..at]).map_err(|_| Bad)?;
    let (min, max) = validate(b)?;
    let lo = t(b, 32) as i128;
    let hi = t(b, 40) as i128;
    let span = hi - lo;
    let bin = |v: i128| (((v - lo) * columns as i128) / span) as usize;
    let mut grid = vec![Cell::default(); cells];
    let mut members = Vec::new();
    let mut work = 0usize;
    let mut total = 0usize;
    for row in b[at..].chunks_exact(40) {
        let interval = kind == 1 || kind == 2;
        let start = if interval && row[32] == 0 {
            lo
        } else {
            t(row, 0) as i128
        };
        let end = if row[33] == 0 { hi } else { t(row, 8) as i128 };
        if interval {
            if end <= lo || start >= hi {
                continue;
            }
        } else if row[32] == 0 || start < lo || start >= hi {
            continue;
        }
        let first = bin(start.max(lo));
        // Ceil exact rational endpoint: an interval ending on a boundary never
        // enters the following half-open cell, even at signed time extremes.
        let last = if interval {
            (((end.min(hi) - lo) * columns as i128 - 1) / span) as usize
        } else {
            first
        };
        let value = f(row, 16);
        let lane = ((crate::scene::linear_fraction(value, min, max) * lanes as f64) as usize)
            .min(lanes - 1);
        work = work.checked_add(last - first + 1).ok_or(Limit)?;
        if work > 64 * 1024 * 1024 {
            return Err(Limit);
        }
        for column in first..=last {
            let index = column * lanes + lane;
            let cell = &mut grid[index];
            if cell.count == 0 {
                cell.min = value;
                cell.max = value;
            }
            cell.min = cell.min.min(value);
            cell.max = cell.max.max(value);
            cell.count += 1;
            cell.hash = (cell.hash ^ hash(&row[24..32])).wrapping_mul(0x100000001b3);
            if op == 1 && index == key {
                if total >= offset && members.len() / 8 < limit {
                    members.extend_from_slice(&row[24..32]);
                }
                total += 1;
            }
        }
    }
    if op != 0 {
        let mut out = vec![0u8; 64];
        out[..4].copy_from_slice(b"XYTL");
        for (at, v) in [
            (4, 2u64),
            (12, op as u64),
            (20, hash(&b[at..])),
            (28, hash(&b[8..88])),
            (36, admitted as u64),
            (44, n as u64),
            (52, cells as u64),
        ] {
            out[at..at + 8].copy_from_slice(&v.to_le_bytes());
        }
        if op == 1 {
            out[60..64].copy_from_slice(&(total as u32).to_le_bytes());
            out.extend_from_slice(&members);
        } else {
            for (i, c) in grid.iter().enumerate().filter(|(_, c)| c.count != 0) {
                out.extend_from_slice(&(i as u64).to_le_bytes());
                out.extend_from_slice(&c.count.to_le_bytes());
                out.extend_from_slice(&c.hash.to_le_bytes());
                out.extend_from_slice(&c.min.to_le_bytes());
                out.extend_from_slice(&c.max.to_le_bytes());
            }
        }
        return Ok(out);
    }
    let mut kinds = Vec::new();
    let mut out_ids = Vec::new();
    let mut x0 = Vec::new();
    let mut x1 = Vec::new();
    let mut y0 = Vec::new();
    let mut y1 = Vec::new();
    let pw = width - 89.0;
    let ph = f(b, 24) - 96.0;
    let y = |v: f64| crate::scene::linear_fraction(-v, -max, -min) * ph;
    for (i, c) in grid.iter().enumerate().filter(|(_, c)| c.count != 0) {
        kinds.push(2);
        out_ids.push(i as u64);
        x0.push((i / lanes) as f64 / columns as f64 * pw);
        x1.push((i / lanes + 1) as f64 / columns as f64 * pw);
        if kind == 3 || kind == 4 {
            y0.push(y(c.max).min(if kind == 4 { y(0.0) } else { y(c.min) }));
            y1.push(y(c.min).max(if kind == 4 { y(0.0) } else { y(c.max) }));
        } else {
            y0.push(ph - (i % lanes + 1) as f64 / lanes as f64 * ph);
            y1.push(ph - (i % lanes) as f64 / lanes as f64 * ph);
        }
    }
    for (a, z) in y0.iter_mut().zip(&mut y1) {
        if *a == *z {
            *a = (*a - 1.0).clamp(0.0, ph - 2.0);
            *z = *a + 2.0;
        }
    }
    let refs = vec![0; kinds.len()];
    let sizes = vec![0.0; kinds.len()];
    super::paint(
        b, budget, &kinds, &out_ids, &refs, &sizes, &x0, &y0, &x1, &y1,
    )
}

pub(super) fn validate(b: &[u8]) -> Result<(f64, f64), TemporalError> {
    use TemporalError::InvalidArgument as Bad;
    let n = u(b, 12) as usize;
    let kind = u(b, 8);
    let at = 128 + u(b, 56) as usize + u(b, 60) as usize;
    let mut ids = Vec::with_capacity(n);
    let mut min = 0.0f64;
    let mut max = 1.0f64;
    let mut previous = None;
    for row in b[at..].chunks_exact(40) {
        let start = t(row, 0);
        if row[32] > 1
            || row[33] > 1
            || row[34..].iter().any(|&v| v != 0)
            || !f(row, 16).is_finite()
        {
            return Err(Bad);
        }
        if (kind == 1 || kind == 2) && row[32] != 0 && row[33] != 0 && start >= t(row, 8) {
            return Err(TemporalError::ReversedInterval);
        }
        if kind == 3 && row[32] != 0 {
            if previous.is_some_and(|v| start < v) {
                return Err(Bad);
            }
            previous = Some(start);
        }
        min = min.min(f(row, 16));
        max = max.max(f(row, 16));
        ids.push(u64::from_le_bytes(row[24..32].try_into().unwrap()));
    }
    ids.sort_unstable();
    if ids.windows(2).any(|v| v[0] == v[1]) {
        return Err(Bad);
    }
    drop(ids);
    Ok((min, max))
}
