//! Atomic, bounded packed dynamic-axis tick resolution.
use xyg_engine::scene::{self, AxisTicks, ScaleKind, SceneError};
pub const REQUEST_MAGIC: &[u8; 4] = b"XYTK";
pub const OUTPUT_MAGIC: &[u8; 4] = b"XYTO";
pub const VERSION: u32 = 1;
pub const HEADER_BYTES: usize = 32;
pub const REQUEST_DESCRIPTOR_BYTES: usize = 96;
pub const OUTPUT_DESCRIPTOR_BYTES: usize = 64;
pub const MAX_AXES: usize = 32;
pub const MAX_TICKS: usize = 200;
pub const MAX_CATEGORIES: usize = 65_536;
pub const MAX_TEXT_BYTES_PER_AXIS: usize = 65_536;
pub const MAX_FORMAT_BYTES: usize = 256;
fn u(bytes: &[u8], o: usize) -> Result<u32, SceneError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(o..o + 4)
            .ok_or(SceneError::Length)?
            .try_into()
            .map_err(|_| SceneError::Length)?,
    ))
}
fn f(bytes: &[u8], o: usize) -> Result<f64, SceneError> {
    Ok(f64::from_le_bytes(
        bytes
            .get(o..o + 8)
            .ok_or(SceneError::Length)?
            .try_into()
            .map_err(|_| SceneError::Length)?,
    ))
}
fn part(bytes: &[u8], o: usize, n: usize) -> Result<&[u8], SceneError> {
    bytes
        .get(o..o.checked_add(n).ok_or(SceneError::Limit)?)
        .ok_or(SceneError::Length)
}
fn strings(
    bytes: &[u8],
    lo: usize,
    n: usize,
    to: usize,
    tn: usize,
) -> Result<Vec<String>, SceneError> {
    part(bytes, lo, n.checked_mul(4).ok_or(SceneError::Limit)?)?;
    let text = part(bytes, to, tn)?;
    let (mut out, mut at) = (Vec::with_capacity(n), 0usize);
    for i in 0..n {
        let end = at
            .checked_add(u(bytes, lo + i * 4)? as usize)
            .ok_or(SceneError::Limit)?;
        out.push(
            std::str::from_utf8(text.get(at..end).ok_or(SceneError::Length)?)
                .map_err(|_| SceneError::Length)?
                .to_owned(),
        );
        at = end;
    }
    if at != tn {
        return Err(SceneError::Length);
    }
    Ok(out)
}
struct Axis {
    id: u32,
    revision: u32,
    provenance: u32,
    ticks: AxisTicks,
    labels: Vec<String>,
}
fn labels(family: u32, t: &AxisTicks, c: &[String], fmt: Option<&str>) -> Vec<String> {
    t.labeled
        .iter()
        .map(|v| match family {
            3 => {
                if *v >= 0.0 {
                    c.get(v.round() as usize).cloned().unwrap_or_default()
                } else {
                    String::new()
                }
            }
            4 => scene::format_angular_tick(*v, t.step, false, fmt),
            5 => scene::format_angular_tick(*v, t.step, true, fmt),
            6 => scene::format_time_tick(*v, t.step, fmt),
            _ => scene::format_numeric_tick(
                *v,
                t.step,
                if family == 1 {
                    ScaleKind::Log
                } else {
                    ScaleKind::Linear
                },
                fmt,
            ),
        })
        .collect()
}
fn resolve(b: &[u8], d: usize) -> Result<Axis, SceneError> {
    let (id, revision, family, flags, provenance, target) = (
        u(b, d)?,
        u(b, d + 4)?,
        u(b, d + 8)?,
        u(b, d + 12)?,
        u(b, d + 16)?,
        u(b, d + 20)? as usize,
    );
    let (ac, alc, cc, fl, atl, ctl) = (
        u(b, d + 24)? as usize,
        u(b, d + 28)? as usize,
        u(b, d + 32)? as usize,
        u(b, d + 36)? as usize,
        u(b, d + 40)? as usize,
        u(b, d + 44)? as usize,
    );
    let (lo, hi, constant) = (f(b, d + 48)?, f(b, d + 56)?, f(b, d + 64)?);
    let (vo, alo, ato, clo, cto, fo) = (
        u(b, d + 72)? as usize,
        u(b, d + 76)? as usize,
        u(b, d + 80)? as usize,
        u(b, d + 84)? as usize,
        u(b, d + 88)? as usize,
        u(b, d + 92)? as usize,
    );
    if flags & !1 != 0
        || id == 0
        || revision == 0
        || (flags & 1 != 0 && family != 1)
        || family > 6
        || provenance > 2
        || target == 0
        || target > MAX_TICKS
        || ac > MAX_TICKS
        || cc > MAX_CATEGORIES
        || fl > MAX_FORMAT_BYTES
        || atl > MAX_TEXT_BYTES_PER_AXIS
        || ctl > MAX_TEXT_BYTES_PER_AXIS
        || atl
            .checked_add(ctl)
            .is_none_or(|total| total > MAX_TEXT_BYTES_PER_AXIS)
        || (alc != 0 && alc != ac)
        || (provenance == 0 && ac != 0)
        || (provenance == 1 && ac == 0)
        || (provenance == 2 && (ac != 0 || alc != 0))
        || (family == 2 && constant <= 0.0)
        || (family == 3 && cc == 0)
    {
        return Err(SceneError::Length);
    }
    if ![lo, hi, constant].into_iter().all(f64::is_finite) {
        return Err(SceneError::NonFinite);
    }
    part(b, vo, ac.checked_mul(8).ok_or(SceneError::Limit)?)?;
    let mut authored = Vec::with_capacity(ac);
    for i in 0..ac {
        let v = f(b, vo + i * 8)?;
        if !v.is_finite() {
            return Err(SceneError::NonFinite);
        }
        authored.push(v)
    }
    let al = strings(b, alo, alc, ato, atl)?;
    let cats = strings(b, clo, cc, cto, ctl)?;
    let fmt = if fl == 0 {
        None
    } else {
        Some(std::str::from_utf8(part(b, fo, fl)?).map_err(|_| SceneError::Length)?)
    };
    let (a, z) = if lo <= hi { (lo, hi) } else { (hi, lo) };
    let (ticks, labs) = if provenance == 2 {
        (
            AxisTicks {
                ticks: vec![],
                labeled: vec![],
                step: 1.0,
            },
            vec![],
        )
    } else if provenance == 1 {
        let (mut vals, mut explicit) = (vec![], vec![]);
        for (i, v) in authored.into_iter().enumerate() {
            if v >= a && v <= z {
                vals.push(v);
                if !al.is_empty() {
                    explicit.push(al[i].clone())
                }
            }
        }
        let step = vals
            .windows(2)
            .map(|p| (p[1] - p[0]).abs())
            .filter(|x| *x > 0.0)
            .fold(f64::INFINITY, f64::min);
        let t = AxisTicks {
            ticks: vals.clone(),
            labeled: vals,
            step: if step.is_finite() { step } else { 1.0 },
        };
        let l = if explicit.is_empty() {
            labels(family, &t, &cats, fmt)
        } else {
            explicit
        };
        (t, l)
    } else {
        let t = match family {
            0 => scene::linear_ticks(lo, hi, target)?,
            1 => scene::log_ticks(lo, hi, target)?,
            2 => scene::symlog_ticks(lo, hi, constant, target)?,
            3 => scene::category_ticks(lo, hi, cc, target)?,
            4 => scene::angular_ticks(lo, hi, false, target)?,
            5 => scene::angular_ticks(lo, hi, true, target)?,
            6 => scene::time_ticks(lo, hi, target)?,
            _ => unreachable!(),
        };
        let l = labels(family, &t, &cats, fmt);
        (t, l)
    };
    if ticks.ticks.len() > MAX_TICKS
        || ticks.labeled.len() > MAX_TICKS
        || labs.len() != ticks.labeled.len()
        || labs.iter().map(String::len).sum::<usize>() > MAX_TEXT_BYTES_PER_AXIS
    {
        return Err(SceneError::Limit);
    }
    Ok(Axis {
        id,
        revision,
        provenance,
        ticks,
        labels: labs,
    })
}
pub fn execute(b: &[u8]) -> Result<Vec<u8>, SceneError> {
    if b.len() < HEADER_BYTES
        || b.get(..4) != Some(REQUEST_MAGIC)
        || u(b, 4)? != VERSION
        || u(b, 8)? as usize != HEADER_BYTES
        || u(b, 12)? == 0
        || u(b, 20)? as usize != REQUEST_DESCRIPTOR_BYTES
        || u(b, 24)? as usize != b.len()
        || u(b, 28)? != 0
    {
        return Err(SceneError::Length);
    }
    let seq = u(b, 12)?;
    let n = u(b, 16)? as usize;
    if n == 0 || n > MAX_AXES {
        return Err(SceneError::Limit);
    }
    let de = HEADER_BYTES
        .checked_add(n * REQUEST_DESCRIPTOR_BYTES)
        .ok_or(SceneError::Limit)?;
    if de > b.len() {
        return Err(SceneError::Length);
    }
    let mut ranges = Vec::new();
    let mut empty_offsets = Vec::new();
    for i in 0..n {
        let d = HEADER_BYTES + i * REQUEST_DESCRIPTOR_BYTES;
        for (offset_field, bytes) in [
            (
                72,
                (u(b, d + 24)? as usize)
                    .checked_mul(8)
                    .ok_or(SceneError::Limit)?,
            ),
            (
                76,
                (u(b, d + 28)? as usize)
                    .checked_mul(4)
                    .ok_or(SceneError::Limit)?,
            ),
            (80, u(b, d + 40)? as usize),
            (
                84,
                (u(b, d + 32)? as usize)
                    .checked_mul(4)
                    .ok_or(SceneError::Limit)?,
            ),
            (88, u(b, d + 44)? as usize),
            (92, u(b, d + 36)? as usize),
        ] {
            let offset = u(b, d + offset_field)? as usize;
            if bytes == 0 {
                empty_offsets.push(offset);
            } else {
                ranges.push((offset, bytes));
            }
        }
    }
    ranges.sort_unstable_by_key(|range| range.0);
    let mut tail = de;
    let mut boundaries = vec![tail];
    for (offset, length) in ranges {
        if offset != tail {
            return Err(SceneError::Length);
        }
        tail = tail.checked_add(length).ok_or(SceneError::Limit)?;
        boundaries.push(tail);
    }
    if tail != b.len() || empty_offsets.iter().any(|offset| !boundaries.contains(offset)) {
        return Err(SceneError::Length);
    }
    let mut axes = Vec::with_capacity(n);
    for i in 0..n {
        let axis = resolve(b, HEADER_BYTES + i * REQUEST_DESCRIPTOR_BYTES)?;
        if axes.iter().any(|existing: &Axis| existing.id == axis.id) {
            return Err(SceneError::Length);
        }
        axes.push(axis)
    }
    let mut size = HEADER_BYTES + n * OUTPUT_DESCRIPTOR_BYTES;
    for a in &axes {
        size = size
            .checked_add(
                (a.ticks.ticks.len() + a.ticks.labeled.len()) * 8
                    + a.labels.len() * 4
                    + a.labels.iter().map(String::len).sum::<usize>(),
            )
            .ok_or(SceneError::Limit)?
    }
    if size > u32::MAX as usize {
        return Err(SceneError::Limit);
    }
    let mut out = vec![0; HEADER_BYTES + n * OUTPUT_DESCRIPTOR_BYTES];
    out[..4].copy_from_slice(OUTPUT_MAGIC);
    for (o, v) in [
        (4, VERSION),
        (8, HEADER_BYTES as u32),
        (12, seq),
        (16, n as u32),
        (20, OUTPUT_DESCRIPTOR_BYTES as u32),
        (24, size as u32),
    ] {
        out[o..o + 4].copy_from_slice(&v.to_le_bytes())
    }
    for (i, a) in axes.iter().enumerate() {
        let d = HEADER_BYTES + i * OUTPUT_DESCRIPTOR_BYTES;
        for (o, v) in [
            (0, a.id),
            (4, a.revision),
            (8, a.provenance),
            (16, a.ticks.ticks.len() as u32),
            (20, a.ticks.labeled.len() as u32),
            (24, a.labels.iter().map(String::len).sum::<usize>() as u32),
        ] {
            out[d + o..d + o + 4].copy_from_slice(&v.to_le_bytes())
        }
        out[d + 32..d + 40].copy_from_slice(&a.ticks.step.to_le_bytes());
        let at = out.len();
        out[d + 40..d + 44].copy_from_slice(&(at as u32).to_le_bytes());
        for v in &a.ticks.ticks {
            out.extend_from_slice(&v.to_le_bytes())
        }
        let at = out.len();
        out[d + 44..d + 48].copy_from_slice(&(at as u32).to_le_bytes());
        for v in &a.ticks.labeled {
            out.extend_from_slice(&v.to_le_bytes())
        }
        let at = out.len();
        out[d + 48..d + 52].copy_from_slice(&(at as u32).to_le_bytes());
        for l in &a.labels {
            out.extend_from_slice(&(l.len() as u32).to_le_bytes())
        }
        let at = out.len();
        out[d + 52..d + 56].copy_from_slice(&(at as u32).to_le_bytes());
        for l in &a.labels {
            out.extend_from_slice(l.as_bytes())
        }
    }
    debug_assert_eq!(out.len(), size);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn put_u32(bytes: &mut [u8], at: usize, value: u32) {
        bytes[at..at + 4].copy_from_slice(&value.to_le_bytes());
    }
    fn put_f64(bytes: &mut [u8], at: usize, value: f64) {
        bytes[at..at + 8].copy_from_slice(&value.to_le_bytes());
    }

    fn seven_family_request() -> Vec<u8> {
        let count = 7usize;
        let tail = HEADER_BYTES + count * REQUEST_DESCRIPTOR_BYTES;
        let categories = b"ABC";
        let mut request = vec![0; tail + 3 * 4 + categories.len()];
        request[..4].copy_from_slice(REQUEST_MAGIC);
        for (at, value) in [
            (4, VERSION),
            (8, HEADER_BYTES as u32),
            (12, 77),
            (16, count as u32),
            (20, REQUEST_DESCRIPTOR_BYTES as u32),
        ] {
            put_u32(&mut request, at, value);
        }
        let category_lengths = tail;
        let category_text = tail + 12;
        for index in 0..3 {
            put_u32(&mut request, category_lengths + index * 4, 1);
        }
        request[category_text..category_text + 3].copy_from_slice(categories);
        for family in 0..count {
            let d = HEADER_BYTES + family * REQUEST_DESCRIPTOR_BYTES;
            put_u32(&mut request, d, 100 + family as u32);
            put_u32(&mut request, d + 4, 9);
            put_u32(&mut request, d + 8, family as u32);
            put_u32(&mut request, d + 20, 6);
            put_u32(&mut request, d + 32, if family == 3 { 3 } else { 0 });
            put_u32(&mut request, d + 44, if family == 3 { 3 } else { 0 });
            let (lo, hi, constant) = match family {
                1 => (0.1, 100.0, 1.0),
                2 => (-10.0, 10.0, 1.0),
                3 => (0.0, 2.0, 1.0),
                4 => (0.0, std::f64::consts::TAU, 1.0),
                5 => (0.0, 360.0, 1.0),
                6 => (0.0, 7_200_000.0, 1.0),
                _ => (-2.0, 8.0, 1.0),
            };
            put_f64(&mut request, d + 48, lo);
            put_f64(&mut request, d + 56, hi);
            put_f64(&mut request, d + 64, constant);
            let request_end = request.len() as u32;
            for offset in [72, 76, 80, 84, 88, 92] {
                put_u32(&mut request, d + offset, request_end);
            }
            if family == 3 {
                put_u32(&mut request, d + 84, category_lengths as u32);
                put_u32(&mut request, d + 88, category_text as u32);
            }
        }
        let len = request.len() as u32;
        put_u32(&mut request, 24, len);
        request
    }

    #[test]
    fn resolves_all_families_atomically_and_echoes_identity() {
        let output = execute(&seven_family_request()).unwrap();
        assert_eq!(&output[..4], OUTPUT_MAGIC);
        assert_eq!(u(&output, 12).unwrap(), 77);
        assert_eq!(u(&output, 16).unwrap(), 7);
        for index in 0..7 {
            let d = HEADER_BYTES + index * OUTPUT_DESCRIPTOR_BYTES;
            assert_eq!(u(&output, d).unwrap(), 100 + index as u32);
            assert_eq!(u(&output, d + 4).unwrap(), 9);
            assert!(u(&output, d + 16).unwrap() <= 200);
        }
    }

    #[test]
    fn malformed_axis_makes_the_whole_batch_fail() {
        let mut request = seven_family_request();
        put_u32(
            &mut request,
            HEADER_BYTES + REQUEST_DESCRIPTOR_BYTES + 8,
            99,
        );
        assert_eq!(execute(&request), Err(SceneError::Length));
    }

    #[test]
    fn authored_empty_and_authored_labels_preserve_provenance() {
        let mut request = seven_family_request();
        request.truncate(HEADER_BYTES + REQUEST_DESCRIPTOR_BYTES);
        put_u32(&mut request, 16, 1);
        let request_end = request.len() as u32;
        put_u32(&mut request, 24, request_end);
        let d = HEADER_BYTES;
        put_u32(&mut request, d + 16, 2);
        put_u32(&mut request, d + 32, 0);
        put_u32(&mut request, d + 44, 0);
        let end = request.len() as u32;
        for offset in [72, 76, 80, 84, 88, 92] {
            put_u32(&mut request, d + offset, end);
        }
        let output = execute(&request).unwrap();
        assert_eq!(u(&output, HEADER_BYTES + 8).unwrap(), 2);
        assert_eq!(u(&output, HEADER_BYTES + 16).unwrap(), 0);
    }

    #[test]
    fn authored_value_plane_is_exactly_eight_bytes_per_value() {
        let mut request = seven_family_request();
        let descriptor = HEADER_BYTES;
        let values_offset = request.len();
        for value in [-1.5_f64, 3.25] {
            request.extend_from_slice(&value.to_le_bytes());
        }
        let lengths_offset = request.len();
        request.extend_from_slice(&3_u32.to_le_bytes());
        request.extend_from_slice(&4_u32.to_le_bytes());
        let labels_offset = request.len();
        request.extend_from_slice(b"lowhigh");
        put_u32(&mut request, descriptor + 16, 1);
        put_u32(&mut request, descriptor + 24, 2);
        put_u32(&mut request, descriptor + 28, 2);
        put_u32(&mut request, descriptor + 40, 7);
        put_u32(&mut request, descriptor + 72, values_offset as u32);
        put_u32(&mut request, descriptor + 76, lengths_offset as u32);
        put_u32(&mut request, descriptor + 80, labels_offset as u32);
        let total = request.len() as u32;
        for offset in [84, 88, 92] {
            put_u32(&mut request, descriptor + offset, total);
        }
        put_u32(&mut request, 24, total);
        let output = execute(&request).unwrap();
        let output_descriptor = HEADER_BYTES;
        assert_eq!(u(&output, output_descriptor + 8).unwrap(), 1);
        assert_eq!(u(&output, output_descriptor + 16).unwrap(), 2);
        assert_eq!(u(&output, output_descriptor + 20).unwrap(), 2);
    }

    #[test]
    fn rejects_nonfinite_and_resource_bounds() {
        let mut request = seven_family_request();
        put_f64(&mut request, HEADER_BYTES + 48, f64::NAN);
        assert_eq!(execute(&request), Err(SceneError::NonFinite));
        let mut request = seven_family_request();
        put_u32(&mut request, 16, (MAX_AXES + 1) as u32);
        assert_eq!(execute(&request), Err(SceneError::Limit));
    }

    #[test]
    fn mask_nonpositive_is_supported_but_unknown_flags_fail_closed() {
        let mut request = seven_family_request();
        let log_descriptor = HEADER_BYTES + REQUEST_DESCRIPTOR_BYTES;
        put_u32(&mut request, log_descriptor + 12, 1);
        execute(&request).unwrap();
        put_u32(&mut request, log_descriptor + 12, 2);
        assert_eq!(execute(&request), Err(SceneError::Length));
    }

    #[test]
    fn rejects_zero_and_duplicate_axis_identity_before_output() {
        let mut request = seven_family_request();
        put_u32(&mut request, HEADER_BYTES, 0);
        assert_eq!(execute(&request), Err(SceneError::Length));
        let mut request = seven_family_request();
        put_u32(&mut request, HEADER_BYTES + 4, 0);
        assert_eq!(execute(&request), Err(SceneError::Length));
        let mut request = seven_family_request();
        let first_id = u(&request, HEADER_BYTES).unwrap();
        put_u32(
            &mut request,
            HEADER_BYTES + REQUEST_DESCRIPTOR_BYTES,
            first_id,
        );
        assert_eq!(execute(&request), Err(SceneError::Length));
    }
}
